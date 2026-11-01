from __future__ import annotations

import hashlib
import json
import marshal
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pisrs_ingest import catalog_runtime as runtime
from pisrs_ingest import cli
from pisrs_ingest.catalog_provenance import CatalogScopeError, catalog_provenance
from pisrs_ingest.locking import ApplicationLock, LockBusyError


def sha(content):
    return hashlib.sha256(content).hexdigest()


@pytest.fixture
def identified(tmp_path, monkeypatch):
    """A disposable service/release layout with a fake systemd response."""
    root = tmp_path / "releases"
    release = root / "fixture-reviewed-seven"
    site = release / ".venv/lib/python3.12/site-packages"
    package = site / "pisrs_ingest"
    package.mkdir(parents=True)
    bin_dir = release / ".venv/bin"
    bin_dir.mkdir(parents=True)
    python = tmp_path / "python3.12"
    python.write_bytes(b"python fixture")
    (bin_dir / "python").symlink_to(python)
    files = {
        bin_dir / "pisrs-ingest": b"reviewed launcher",
        release / ".venv/pyvenv.cfg": b"reviewed venv config",
        site / "_virtualenv.pth": b"reviewed pth",
        site / "_virtualenv.py": b"reviewed startup",
        package / "__init__.py": b"reviewed init",
        package / "client.py": b"reviewed seven catalogs",
    }
    for path, content in files.items():
        path.write_bytes(content)
    lock_dir = tmp_path / "run"
    lock_dir.mkdir(mode=0o700)
    lock = lock_dir / "ingest.lock"
    lock.write_text("")
    lock.chmod(0o600)
    env_file = tmp_path / "service.env"
    dsn = "postgresql://fixture:fixture@127.0.0.1:5432/appdb"
    env_file.write_text(
        f"PISRS_DATABASE_DSN='{dsn}'\nPISRS_EXPECTED_DATABASE=appdb\nPISRS_LOCK_PATH={lock}\n"
    )
    settings = SimpleNamespace(database_dsn=dsn, expected_database="appdb", lock_path=lock)
    exec_argv = (
        f"/usr/bin/env PISRS_ALLOW_EXTERNAL_API=1 PISRS_ALLOW_WRITES=1 "
        f"{bin_dir}/pisrs-ingest nightly"
    )
    unit = {
        "WorkingDirectory": str(release),
        "ExecStart": "{ path=/usr/bin/env ; argv[]="
        + exec_argv
        + " ; ignore_errors=no ; start_time=[Sun 2026-11-01 03:00:06 CET] ; status=0 }",
    }
    monkeypatch.setattr(runtime, "RELEASE_ROOT", root)
    monkeypatch.setattr(runtime, "REVIEWED_REVISION", "fixture-reviewed-seven")
    monkeypatch.setattr(runtime, "LOCK_PATH", lock)
    monkeypatch.setattr(runtime, "ENV_FILE", env_file)
    monkeypatch.setattr(runtime, "PYTHON", python)
    monkeypatch.setattr(runtime, "LAUNCHER_SHA256", sha(files[bin_dir / "pisrs-ingest"]))
    monkeypatch.setattr(runtime, "VENV_CONFIG_SHA256", sha(files[release / ".venv/pyvenv.cfg"]))
    monkeypatch.setattr(runtime, "PTH_SHA256", sha(files[site / "_virtualenv.pth"]))
    monkeypatch.setattr(runtime, "VIRTUALENV_SHA256", sha(files[site / "_virtualenv.py"]))
    monkeypatch.setattr(
        runtime,
        "REVIEWED_MODULES",
        {
            "__init__.py": sha(files[package / "__init__.py"]),
            "client.py": sha(files[package / "client.py"]),
        },
    )
    monkeypatch.setattr(runtime, "_secure", lambda path: None)
    monkeypatch.setattr(runtime, "_unit", lambda: unit.copy())
    monkeypatch.setattr(runtime, "_manager_environment", lambda: "fixture-manager")
    monkeypatch.setattr(runtime, "_container_server_identity", lambda: ("fixture-container", "123"))
    monkeypatch.setattr(runtime, "APPROVED_CONTAINER_SHA256", sha(b"fixture-container"))
    monkeypatch.setattr(runtime, "APPROVED_CLUSTER_SHA256", sha(b"123"))
    monkeypatch.setattr(
        runtime.pwd, "getpwnam", lambda _: SimpleNamespace(pw_uid=lock.stat().st_uid)
    )
    for name in list(runtime.os.environ):
        if name.startswith("PG"):
            monkeypatch.delenv(name)
    return SimpleNamespace(
        settings=settings, unit=unit, package=package, lock=lock, env_file=env_file, site=site
    )


def test_matching_isolated_identity_is_accepted(identified):
    proof = runtime.verify_runtime(identified.settings)
    with runtime.CatalogApplicationLock(identified.lock) as held:
        runtime.verify_lock(held)
        with pytest.raises(LockBusyError), ApplicationLock(identified.lock):
            pass
        runtime.verify_connection(
            SimpleNamespace(
                info=SimpleNamespace(
                    dbname="appdb", hostaddr="127.0.0.1", port=5432, user="fixture"
                ),
                execute=lambda _: SimpleNamespace(fetchone=lambda: {"server_id": "123"}),
            ),
            identified.settings.database_dsn,
            "123",
        )
        assert runtime.verify_runtime(identified.settings) == proof


def test_old_four_catalog_code_or_wrong_active_release_is_rejected(identified):
    (identified.package / "client.py").write_bytes(b"old four catalogs")
    with pytest.raises(runtime.RuntimeProofError, match="code differs"):
        runtime.verify_runtime(identified.settings)


def test_additional_nightly_command_is_rejected(identified):
    identified.unit["ExecStart"] += (
        " { path=/tmp/other ; argv[]=/tmp/other ; ignore_errors=no ; x }"
    )
    with pytest.raises(runtime.RuntimeProofError, match="reviewed release"):
        runtime.verify_runtime(identified.settings)


def test_wrong_active_release_path_is_rejected(identified):
    identified.unit["WorkingDirectory"] += "-old"
    with pytest.raises(runtime.RuntimeProofError, match="reviewed release"):
        runtime.verify_runtime(identified.settings)


def test_changed_startup_path_and_missing_config_are_rejected(identified):
    (identified.site / "other.pth").write_text("external path")
    with pytest.raises(runtime.RuntimeProofError, match="startup path"):
        runtime.verify_runtime(identified.settings)
    (identified.site / "other.pth").unlink()
    identified.env_file.unlink()
    with pytest.raises(runtime.RuntimeProofError, match="unavailable"):
        runtime.verify_runtime(identified.settings)


def test_cached_bytecode_must_match_verified_source(identified, monkeypatch):
    python = Path(sys.executable).resolve()
    launcher = identified.package.parents[3] / "bin/python"
    launcher.unlink()
    launcher.symlink_to(python)
    monkeypatch.setattr(runtime, "PYTHON", python)
    cache = identified.package / "__pycache__"
    cache.mkdir()
    source = identified.package / "client.py"
    pyc = cache / "client.cpython-312.pyc"
    # The fixture source need only be valid Python for compilation.
    source.write_text("catalogs = 7\n")
    monkeypatch.setitem(runtime.REVIEWED_MODULES, "client.py", sha(source.read_bytes()))
    pyc.write_bytes(
        bytes(16)
        + marshal.dumps(compile(source.read_bytes(), str(source), "exec", dont_inherit=True))
    )
    runtime.verify_runtime(identified.settings)
    pyc.write_bytes(
        bytes(16) + marshal.dumps(compile("catalogs = 4", str(source), "exec", dont_inherit=True))
    )
    with pytest.raises(runtime.RuntimeProofError, match="bytecode differs"):
        runtime.verify_runtime(identified.settings)


def test_wrong_lock_or_changed_inode_is_rejected(identified):
    identified.settings.lock_path = identified.lock.parent / "wrong.lock"
    with pytest.raises(runtime.RuntimeProofError, match="database or lock"):
        runtime.verify_runtime(identified.settings)
    identified.settings.lock_path = identified.lock
    with runtime.CatalogApplicationLock(identified.lock) as held:
        identified.lock.unlink()
        identified.lock.write_text("")
        identified.lock.chmod(0o600)
        with pytest.raises(runtime.RuntimeProofError, match="inode changed"):
            runtime.verify_lock(held)


def test_lock_symlink_is_not_opened_or_modified(identified):
    target = identified.lock.parent / "other"
    target.write_text("unchanged")
    identified.lock.unlink()
    identified.lock.symlink_to(target)
    with pytest.raises(OSError), runtime.CatalogApplicationLock(identified.lock):
        pass
    assert target.read_text() == "unchanged"


def test_arbitrary_open_file_is_not_accepted_as_application_lock(identified):
    with (
        identified.lock.open("r") as handle,
        pytest.raises(runtime.RuntimeProofError, match="not held by catalog-sync"),
    ):
        runtime.verify_lock(SimpleNamespace(_handle=handle))


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://fixture:fixture@127.0.0.2:5432/appdb",
        "postgresql://fixture:fixture@127.0.0.1:5432/otherdb",
        "postgresql://fixture:fixture@127.0.0.1:5433/appdb",
        "postgresql://fixture:fixture@127.0.0.1:5432/appdb?hostaddr=127.0.0.2",
    ],
)
def test_wrong_database_or_server_is_rejected(identified, dsn):
    identified.settings.database_dsn = dsn
    with pytest.raises(runtime.RuntimeProofError):
        runtime.verify_runtime(identified.settings)
    # Even if a substituted protected configuration matched, endpoint validation fails.
    with pytest.raises(runtime.RuntimeProofError):
        runtime._server(dsn)


def test_connected_server_is_checked_independently(identified):
    for info in [
        SimpleNamespace(dbname="wrong", hostaddr="127.0.0.1", port=5432, user="fixture"),
        SimpleNamespace(dbname="appdb", hostaddr="127.0.0.2", port=5432, user="fixture"),
        SimpleNamespace(dbname="appdb", hostaddr="127.0.0.1", port=5433, user="fixture"),
        SimpleNamespace(dbname="appdb", hostaddr="127.0.0.1", port=5432, user="wrong"),
    ]:
        with pytest.raises(runtime.RuntimeProofError):
            runtime.verify_connection(
                SimpleNamespace(info=info), identified.settings.database_dsn, "123"
            )


def test_wrong_postgres_cluster_is_rejected(identified):
    connection = SimpleNamespace(
        info=SimpleNamespace(dbname="appdb", hostaddr="127.0.0.1", port=5432, user="fixture"),
        execute=lambda _: SimpleNamespace(fetchone=lambda: {"server_id": "different"}),
    )
    with pytest.raises(runtime.RuntimeProofError, match="server identity"):
        runtime.verify_connection(connection, identified.settings.database_dsn, "123")


def test_container_proof_requires_one_local_binding(monkeypatch):
    monkeypatch.setattr(runtime, "APPROVED_CONTAINER_SHA256", sha(("a" * 64).encode()))

    def run(args, **kwargs):
        if "ps" in args:
            return SimpleNamespace(stdout="a" * 12 + "\n")
        if "inspect" in args:
            return SimpleNamespace(
                stdout=json.dumps(
                    [
                        {
                            "Id": "a" * 64,
                            "State": {"Running": True},
                            "NetworkSettings": {
                                "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5432"}]}
                            },
                        }
                    ]
                )
            )
        assert "exec" in args and "READ ONLY" in args[-1]
        return SimpleNamespace(stdout="123\n")

    monkeypatch.setattr(runtime.subprocess, "run", run)
    assert runtime._container_server_identity() == ("a" * 64, "123")

    def ambiguous(args, **kwargs):
        if "ps" in args:
            return SimpleNamespace(stdout=("a" * 12 + "\n") * 2)
        return run(args, **kwargs)

    monkeypatch.setattr(runtime.subprocess, "run", ambiguous)
    with pytest.raises(runtime.RuntimeProofError, match="ambiguous"):
        runtime._container_server_identity()


def test_container_change_is_detected_before_commit(identified, monkeypatch):
    proof = runtime.verify_runtime(identified.settings)
    with runtime.CatalogApplicationLock(identified.lock) as lock:
        guard = runtime.RuntimeGuard(identified.settings, lock, proof)
        monkeypatch.setattr(runtime, "_container_server_identity", lambda: ("new-container", "123"))
        with pytest.raises(runtime.RuntimeProofError, match="identity|changed"):
            guard.verify(object())


def test_wrong_server_is_rejected_even_if_listening_on_same_endpoint(identified, monkeypatch):
    monkeypatch.setattr(runtime, "_container_server_identity", lambda: ("wrong-container", "123"))
    with pytest.raises(runtime.RuntimeProofError, match="not approved"):
        runtime.verify_runtime(identified.settings)


def test_unreviewed_manager_environment_is_rejected(monkeypatch):
    monkeypatch.setattr(
        runtime.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="PYTHONPATH=/tmp/x\n")
    )
    with pytest.raises(runtime.RuntimeProofError, match="manager environment"):
        runtime._manager_environment()


def test_apply_requires_guard_even_when_plan_is_supplied():
    from dataclasses import replace

    from pisrs_ingest.client import PisrsClient
    from pisrs_ingest.models import Act

    acts = [
        replace(
            Act.from_raw({"id": i, "mopedId": f"M{i}", "naziv": "Fixture"}, ep),
            seen_in_endpoints=(ep,),
        )
        for i, ep in enumerate(PisrsClient.ACT_ENDPOINTS, 1)
    ]

    with pytest.raises(CatalogScopeError, match="verification"):
        catalog_provenance(object(), acts, "appdb", apply=True, expected_plan="a" * 64)


def test_operator_confirmation_alone_cannot_authorize_apply(tmp_path, monkeypatch):
    from test_catalog_provenance import environment

    env = environment(tmp_path)
    env["PISRS_ALLOW_WRITES"] = "1"
    monkeypatch.setattr(
        cli, "verify_runtime", lambda _: (_ for _ in ()).throw(runtime.RuntimeProofError("blocked"))
    )
    monkeypatch.setattr(cli, "_catalog_sync", lambda *a, **k: pytest.fail("must not write"))
    assert (
        cli.main(
            ["catalog-sync", "--apply", "--expect-plan", "a" * 64, "--confirm-active-catalog-code"],
            env,
        )
        == cli.EXIT_RECONCILE_BLOCKED
    )
