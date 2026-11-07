"""Fail-closed proof of the nightly's release and connection for catalog writes."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import pwd
import re
import shlex
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .config import Settings
from .locking import ApplicationLock, LockBusyError


class RuntimeProofError(RuntimeError):
    """The active nightly and the write target could not be proved identical."""


# Exact, independently reviewed seven-catalog source revision. A new production
# release requires a code review and a corresponding immutable manifest update.
REVIEWED_REVISION = "21f60ad607602e8e811ce6e5aaf10f60d320fe69"
REVIEWED_MODULES = {
    "__init__.py": "ff330b959a2b72bb01cb0210bf6c56193b9b002a03c3919ef6e6a4a491950b8d",
    "checkpoint.py": "1084c3ab32f24808e8a467d3a0987222c2e690f5e3ec1cb6b5879223899ae9f7",
    "cli.py": "c182c9d6af2e7b6425c07a3619c413a28db66436cca550593003ce859439fa62",
    "client.py": "eaf4b0a23ba2379fe0a467a76c7933d7c2f6daf9daaac96cd4ae4088a67f81b1",
    "config.py": "42adf434c48573e514e1a437ee5ce9bc01008bda097c21780f4dea0b2ebc3e63",
    "embeddings.py": "4d00c66bb555c3b7542dac4302370a21d10f34952f7dd7b3ae83a603bc4e3904",
    "locking.py": "db611e32cb2ab926b041ff6e209e71baab0d70bc51d28a09e13ce3aeee78154e",
    "models.py": "6b7c1e8769e4999f5a9deb0e073237b3508f2e4e22828f131ba76d4f0dceb5f7",
    "pipeline.py": "18a6b678624a3197ccbebe0f9de83ffd6db87e76e395c90fdfd336b8dac3d7f8",
    "postgres.py": "17363ba1a6eec40824bc76e9cc8fe6b7945e6c02f6e11d8fb68bc2df1fb839e4",
    "postgres_chunks.py": "e56135db433c980028a78b825db109d72ec40c18673fed54d4a35b8e2d6be658",
    "postgres_documents.py": "d8e069691773b6d506d5c2f2089b15b7ac81e724e16c45e7bb28d608f4ce9c5b",
    "qdrant.py": "6c13f5946254ab4a66eba83e232f98c36d43950cbecefc6c0c851fa60b96f96b",
}
SERVICE = "pisrs-ingest.service"
ENV_FILE = Path("/etc/pisrs-ingest.env")
RELEASE_ROOT = Path("/opt/pisrs-ingest/releases")
LOCK_PATH = Path("/run/pisrs-ingest/ingest.lock")
DATABASE_NAME = "appdb"
# Fingerprints of the independently identified local PostgreSQL container and
# cluster. A replacement requires a new review, even if it binds the same port.
APPROVED_CONTAINER_SHA256 = "130780cb3ce27a007feecae31e87133e58c0f66320463aef6355147cfdab58d0"
APPROVED_CLUSTER_SHA256 = "f0459f422ce7c8c6ce3701b9ecc9d43ddbd4b2850a5a662f58c392de18acf886"
LAUNCHER_SHA256 = "dfc47d5031a2b472d96c7cdb1f847e21b4abca6732c02643b8dafd66b5ff7529"
PTH_SHA256 = "69ac3d8f27e679c81b94ab30b3b56e9cd138219b1ba94a1fa3606d5a76a1433d"
VIRTUALENV_SHA256 = "6cf30c56faf2a55228914dbbd17f8088ed371ebb08f5e7fa6fd931f913fcaf1d"
VENV_CONFIG_SHA256 = "f5ef9b28fb646d6f68e32fb035425c5152b78665c0dd4d46086dedcf76afbd48"
PYTHON = Path("/opt/pisrs-ingest/runtime/cpython-3.12.3-linux-x86_64-gnu/bin/python3.12")
SYSTEMCTL = "/usr/bin/systemctl"
DOCKER = "/usr/bin/docker"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _secure(path: Path) -> None:
    """Reject links or components writable by anyone other than root."""
    if not path.is_absolute():
        raise RuntimeProofError("non-absolute trusted path")
    for item in (path, *path.parents):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeProofError("untrusted file ownership, mode, or symlink")


def _unit() -> dict[str, str]:
    names = (
        "ExecStart",
        "Environment",
        "EnvironmentFiles",
        "PassEnvironment",
        "UnsetEnvironment",
        "WorkingDirectory",
        "User",
        "Group",
        "RootDirectory",
        "RootImage",
        "BindPaths",
        "BindReadOnlyPaths",
        "FragmentPath",
        "DropInPaths",
    )
    result = subprocess.run(
        [SYSTEMCTL, "show", SERVICE, *(f"--property={n}" for n in names)],
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "SYSTEMD_COLORS": "0"},
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if set(values) != set(names):
        raise RuntimeProofError("service properties unavailable")
    if any(
        values[n]
        for n in (
            "Environment",
            "PassEnvironment",
            "UnsetEnvironment",
            "RootDirectory",
            "RootImage",
            "BindPaths",
            "BindReadOnlyPaths",
        )
    ):
        raise RuntimeProofError("unsupported service environment or filesystem overrides")
    if values["User"] != "pisrs-ingest" or values["Group"] != "pisrs-ingest":
        raise RuntimeProofError("unexpected service account")
    if values["EnvironmentFiles"] != f"{ENV_FILE} (ignore_errors=no)":
        raise RuntimeProofError("unexpected service environment file")
    for item in [values["FragmentPath"], *values["DropInPaths"].split()]:
        _secure(Path(item))
    return values


def _manager_environment() -> str:
    result = subprocess.run(
        [SYSTEMCTL, "show-environment"],
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "SYSTEMD_COLORS": "0"},
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    environment: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, value = line.split("=", 1)
        if name in environment:
            raise RuntimeProofError("ambiguous system manager environment")
        environment[name] = value
        if name.startswith(("PYTHON", "LD_", "PG")) or name in {
            "ENV",
            "BASH_ENV",
            "CDPATH",
            "IFS",
            "HOME",
            "GCONV_PATH",
            "LOCPATH",
        }:
            raise RuntimeProofError("unreviewed system manager environment")
    path = environment.get("PATH")
    if not path:
        raise RuntimeProofError("system manager executable path unavailable")
    for entry in path.split(":"):
        item = Path(entry)
        if not item.is_absolute() or not item.is_dir():
            raise RuntimeProofError("untrusted system manager executable path")
        for component in (item, *item.parents):
            info = component.lstat()
            if info.st_uid != 0 or (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022):
                raise RuntimeProofError("untrusted system manager executable path")
        _secure(item.resolve(strict=True))
    return hashlib.sha256(result.stdout.encode()).hexdigest()


def _file_environment() -> dict[str, str]:
    _secure(ENV_FILE)
    values: dict[str, str] = {}
    # Accept only a conservative single-line subset of systemd's syntax.
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if "\\" in line or "=" not in line:
            raise RuntimeProofError("unsupported environment file syntax")
        name, raw = line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) or name in values:
            raise RuntimeProofError("ambiguous environment file")
        parts = shlex.split(raw, comments=False, posix=True)
        if (
            len(parts) != 1
            or name.startswith(("PYTHON", "LD_", "PG"))
            or name in {"PATH", "ENV", "BASH_ENV", "CDPATH", "IFS", "HOME"}
        ):
            raise RuntimeProofError("unsupported environment setting")
        values[name] = parts[0]
    return values


def _check_bytecode(source: Path, item: Path) -> None:
    _secure(item)
    result = subprocess.run(
        [
            str(PYTHON),
            "-I",
            "-S",
            "-B",
            "-c",
            "import marshal,sys; s,p=sys.argv[1:]; "
            "a=compile(open(s,'rb').read(),s,'exec'); "
            "b=marshal.loads(open(p,'rb').read()[16:]); "
            "sys.exit(a!=b)",
            str(source),
            str(item),
        ],
        env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        capture_output=True,
        timeout=10,
    )
    if result.returncode:
        raise RuntimeProofError("cached bytecode differs from reviewed source")


def _release(values: dict[str, str]) -> None:
    release = RELEASE_ROOT / REVIEWED_REVISION
    launcher = release / ".venv/bin/pisrs-ingest"
    argv = f"/usr/bin/env PISRS_ALLOW_EXTERNAL_API=1 PISRS_ALLOW_WRITES=1 {launcher} nightly"
    prefix = "{ path=/usr/bin/env ; argv[]=" + argv + " ; ignore_errors=no ; "
    if values["WorkingDirectory"] != str(release) or not re.fullmatch(
        re.escape(prefix) + r"[^{}\n]* }", values["ExecStart"]
    ):
        raise RuntimeProofError("active nightly is not the reviewed release")
    _secure(launcher)
    if _sha(launcher) != LAUNCHER_SHA256:
        raise RuntimeProofError("unreviewed nightly launcher")
    for pattern in (
        "pisrs_ingest.*",
        "pisrs_ingest",
        "_virtualenv.*",
        "_virtualenv",
        "sitecustomize.*",
        "usercustomize.*",
    ):
        if any(launcher.parent.glob(pattern)):
            raise RuntimeProofError("unreviewed executable import path")
    cfg = release / ".venv/pyvenv.cfg"
    _secure(cfg)
    if _sha(cfg) != VENV_CONFIG_SHA256:
        raise RuntimeProofError("unreviewed Python environment")
    python_link = release / ".venv/bin/python"
    if not python_link.is_symlink() or python_link.resolve(strict=True) != PYTHON:
        raise RuntimeProofError("unreviewed Python interpreter")
    _secure(PYTHON)
    site = release / ".venv/lib/python3.12/site-packages"
    _secure(site)
    if {p.name for p in site.glob("*.pth")} != {"_virtualenv.pth"}:
        raise RuntimeProofError("unreviewed Python startup path")
    pth = site / "_virtualenv.pth"
    _secure(pth)
    if _sha(pth) != PTH_SHA256:
        raise RuntimeProofError("unreviewed Python startup path")
    virtualenv = site / "_virtualenv.py"
    _secure(virtualenv)
    if _sha(virtualenv) != VIRTUALENV_SHA256:
        raise RuntimeProofError("unreviewed Python startup module")
    if (
        any(site.glob("_virtualenv*.so"))
        or (site / "_virtualenv.pyc").exists()
        or (site / "_virtualenv").exists()
    ):
        raise RuntimeProofError("unreviewed Python startup module")
    if any(
        any(site.glob(pattern))
        for pattern in ("sitecustomize.*", "sitecustomize", "usercustomize.*", "usercustomize")
    ):
        raise RuntimeProofError("unreviewed Python startup module")
    virtualenv_cache = site / "__pycache__/_virtualenv.cpython-312.pyc"
    if virtualenv_cache.exists():
        _check_bytecode(virtualenv, virtualenv_cache)
    package = site / "pisrs_ingest"
    _secure(package)
    if {p.name for p in package.glob("*.py")} != set(REVIEWED_MODULES):
        raise RuntimeProofError("unexpected installed module set")
    if {p.name for p in package.iterdir()} - (set(REVIEWED_MODULES) | {"__pycache__"}):
        raise RuntimeProofError("unreviewed installed module or extension")
    for name, expected in REVIEWED_MODULES.items():
        path = package / name
        _secure(path)
        if _sha(path) != expected:
            raise RuntimeProofError("active nightly code differs from reviewed code")
    cache = package / "__pycache__"
    if cache.exists():
        _secure(cache)
        for item in cache.iterdir():
            _secure(item)
            if not item.name.endswith(".cpython-312.pyc"):
                raise RuntimeProofError("unreviewed Python bytecode")
            source = package / (item.name.removesuffix(".cpython-312.pyc") + ".py")
            if source.name not in REVIEWED_MODULES:
                raise RuntimeProofError("unreviewed Python bytecode")
            _check_bytecode(source, item)


def _server(dsn: str) -> None:
    parsed = urlsplit(dsn)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.username
        or parsed.hostname != "127.0.0.1"
        or parsed.port not in {None, 5432}
        or parsed.path != f"/{DATABASE_NAME}"
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeProofError("database connection is not the approved local endpoint")
    if any(name.startswith("PG") for name in os.environ):
        raise RuntimeProofError("unreviewed libpq environment")


def verify_lock(lock: object | None = None) -> None:
    """Use an existing private service lock file; reject links and inode changes."""
    service_uid = pwd.getpwnam("pisrs-ingest").pw_uid
    directory = LOCK_PATH.parent.lstat()
    item = LOCK_PATH.lstat()
    if (
        not stat.S_ISDIR(directory.st_mode)
        or directory.st_uid != service_uid
        or directory.st_mode & 0o077
        or not stat.S_ISREG(item.st_mode)
        or item.st_uid != service_uid
        or item.st_mode & 0o077
        or item.st_nlink != 1
    ):
        raise RuntimeProofError("service lock file or directory is not trusted")
    if lock is not None:
        if type(lock) is not CatalogApplicationLock:
            raise RuntimeProofError("application lock is not held by catalog-sync")
        handle = getattr(lock, "_handle", None)
        if handle is None:
            raise RuntimeProofError("application lock is not held")
        held = os.fstat(handle.fileno())
        if (held.st_dev, held.st_ino) != (item.st_dev, item.st_ino):
            raise RuntimeProofError("application lock inode changed")


class CatalogApplicationLock(ApplicationLock):
    """Take the existing nightly flock without creating or following a lock link."""

    def __enter__(self):
        fd = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        handle = os.fdopen(fd, "r", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._handle = handle
            verify_lock(self)
        except BlockingIOError as exc:
            handle.close()
            raise LockBusyError("another mutating pisrs-ingest process owns the lock") from exc
        except Exception:
            handle.close()
            self._handle = None
            raise
        return self


def _container_server_identity() -> tuple[str, str]:
    """Read the cluster identifier from the uniquely bound local PG container."""
    base = [DOCKER, "--host", "unix:///var/run/docker.sock"]
    options = {
        "env": {"PATH": "/usr/bin:/bin", "LANG": "C"},
        "capture_output": True,
        "text": True,
        "check": True,
        "timeout": 10,
    }
    output = subprocess.run(
        [*base, "ps", "-q", "--filter", "publish=5432"], **options
    ).stdout.splitlines()
    if not output or any(not re.fullmatch(r"[a-f0-9]{12,64}", c) for c in output):
        raise RuntimeProofError("approved PostgreSQL container is unavailable")
    matches = []
    for container in output:
        details = json.loads(subprocess.run([*base, "inspect", container], **options).stdout)
        if len(details) != 1:
            raise RuntimeProofError("ambiguous PostgreSQL container")
        instance = details[0]
        ports = instance["NetworkSettings"]["Ports"].get("5432/tcp") or []
        if instance["State"]["Running"] and any(
            p.get("HostIp") == "127.0.0.1" and p.get("HostPort") == "5432" for p in ports
        ):
            matches.append((container, instance["Id"]))
    if len(matches) != 1:
        raise RuntimeProofError("approved PostgreSQL container is ambiguous")
    if hashlib.sha256(matches[0][1].encode("ascii")).hexdigest() != APPROVED_CONTAINER_SHA256:
        raise RuntimeProofError("local PostgreSQL container is not approved")
    query = (
        "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY; "
        "SET LOCAL statement_timeout='3s'; "
        "SELECT system_identifier::text FROM pg_control_system(); ROLLBACK;"
    )
    value = subprocess.run(
        [
            *base,
            "exec",
            matches[0][1],
            "psql",
            "-X",
            "-w",
            "-qAt",
            "-U",
            "postgres",
            "-d",
            "appdb",
            "-c",
            query,
        ],
        **options,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9]+", value):
        raise RuntimeProofError("PostgreSQL server identity unavailable")
    return matches[0][1], value


def verify_connection(connection: object, dsn: str, expected_server_id: str) -> None:
    info = getattr(connection, "info", None)
    if (
        info is None
        or info.dbname != DATABASE_NAME
        or info.hostaddr != "127.0.0.1"
        or info.port != 5432
        or info.user != unquote(urlsplit(dsn).username or "")
    ):
        raise RuntimeProofError("connected PostgreSQL server is not the approved endpoint")
    try:
        row = connection.execute(
            "SELECT system_identifier::text AS server_id FROM pg_control_system()"
        ).fetchone()
        if not row or row["server_id"] != expected_server_id:
            raise RuntimeProofError("PostgreSQL server identity does not match the local container")
    except RuntimeProofError:
        raise
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise RuntimeProofError("PostgreSQL server identity unavailable") from None


@dataclass(frozen=True)
class RuntimeProof:
    unit: tuple[tuple[str, str], ...]
    environment_hash: str
    manager_environment_hash: str
    server_identity: tuple[str, str]


@dataclass(frozen=True)
class RuntimeGuard:
    settings: Settings
    lock: object
    proof: RuntimeProof

    def verify(self, connection: object) -> None:
        if verify_runtime(self.settings) != self.proof:
            raise RuntimeProofError("nightly configuration changed during apply")
        verify_lock(self.lock)
        verify_connection(connection, self.settings.database_dsn, self.proof.server_identity[1])


def verify_runtime(settings: Settings) -> RuntimeProof:
    """Prove active nightly configuration without displaying its secret values."""
    try:
        unit = _unit()
        manager_environment_hash = _manager_environment()
        _release(unit)
        values = _file_environment()
        if (
            values.get("PISRS_DATABASE_DSN") != settings.database_dsn
            or values.get("PISRS_EXPECTED_DATABASE") != DATABASE_NAME
            or settings.expected_database != DATABASE_NAME
            or values.get("PISRS_LOCK_PATH") != str(LOCK_PATH)
            or settings.lock_path != LOCK_PATH
        ):
            raise RuntimeProofError("nightly database or lock configuration differs")
        _server(settings.database_dsn)
        server_identity = _container_server_identity()
        if (
            hashlib.sha256(server_identity[0].encode("ascii")).hexdigest()
            != APPROVED_CONTAINER_SHA256
            or hashlib.sha256(server_identity[1].encode("ascii")).hexdigest()
            != APPROVED_CLUSTER_SHA256
        ):
            raise RuntimeProofError("local PostgreSQL server identity is not approved")
        return RuntimeProof(
            tuple(sorted(unit.items())),
            _sha(ENV_FILE),
            manager_environment_hash,
            server_identity,
        )
    except RuntimeProofError:
        raise
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise RuntimeProofError("nightly identity or protected configuration unavailable") from None
