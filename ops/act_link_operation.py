#!/usr/bin/env python3
"""Private closed act-link operation. Production apply needs separate owner approval."""

from __future__ import annotations

import argparse
import fcntl
import grp
import hashlib
import json
import os
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import requests
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pisrs_ingest.act_link_manifest import (
    STAMP,
    TABLES,
    apply_locked,
    classify_pg,
    classify_point,
    closed_scope,
    digest,
    encoded,
    expected_points,
    expected_state,
    lock_and_validate,
    require,
    restore_sql,
    same,
    snapshot,
    sync_points,
    validate_manifest,
    vector_proof,
)

BASE = "895aee884a1484f30ecace713ead21e5af9bdef0"
SOURCE_EVIDENCE = Path("/home/rajko/.local/state/pisrs-p4-act-links-20261031T124739Z/evidence.json")
SOURCE_HASH = "361d5f023714d5a2cdefa16537173ad3d6bc8ebe82eceb7604e41700a5671c24"
KEEP = {
    "PISRS_DATABASE_DSN",
    "PISRS_EXPECTED_DATABASE",
    "PISRS_QDRANT_URL",
    "PISRS_QDRANT_COLLECTION",
    "PISRS_LOCK_PATH",
}
UNIT = "pisrs-ingest.service"


def command(args, *, input=None):
    r = subprocess.run(args, input=input, capture_output=True, text=True, timeout=120)
    require(r.returncode == 0, "local command failed: " + args[0])
    return r.stdout.strip()


def durable(directory, name, value):
    data = encoded(value)
    p = directory / name
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    require(p.read_bytes() == data, "durable file readback failed")
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)
    return hashlib.sha256(data).hexdigest()


def read_env(path, keys):
    require(path.is_file() and not path.is_symlink(), "missing/symlink environment file")
    result = {}
    for line in path.read_text().splitlines():
        k, sep, v = line.partition("=")
        if sep and k.strip() in keys:
            words = shlex.split(v, comments=False)
            require(len(words) <= 1 and not v.endswith("\\"), "unsupported environment syntax")
            result[k.strip()] = words[0] if words else ""
    return result


def inactive():
    require(
        command(["systemctl", "show", UNIT, "-p", "ActiveState", "--value"]) == "inactive",
        "nightly is not inactive",
    )


def bootstrap():
    require(os.geteuid() == 0, "requires legitimate local pkexec authentication")
    props = [
        "User",
        "Group",
        "RuntimeDirectory",
        "RuntimeDirectoryMode",
        "EnvironmentFiles",
        "Environment",
        "UnsetEnvironment",
        "ExecStart",
    ]
    props = dict(
        line.split("=", 1)
        for line in command(
            ["systemctl", "show", UNIT, *[x for p in props for x in ["-p", p]]]
        ).splitlines()
    )
    require(
        props["EnvironmentFiles"] == "/etc/pisrs-ingest.env (ignore_errors=no)",
        "EnvironmentFile contract changed",
    )
    env = dict(
        item.split("=", 1)
        for item in shlex.split(props.get("Environment", ""))
        if "=" in item and item.split("=", 1)[0] in KEEP
    )
    env.update(read_env(Path("/etc/pisrs-ingest.env"), KEEP))
    require(not set(shlex.split(props.get("UnsetEnvironment", ""))) & KEEP, "setting unset")
    require(env.keys() >= KEEP and all(env[k] for k in KEEP), "required setting UNSET")
    require(
        env["PISRS_EXPECTED_DATABASE"] == "appdb"
        and env["PISRS_QDRANT_COLLECTION"] == "pisrs_current"
        and env["PISRS_QDRANT_URL"].rstrip("/") == "http://127.0.0.1:6333",
        "wrong destination",
    )
    dsn = conninfo_to_dict(env["PISRS_DATABASE_DSN"])
    require(
        dsn.get("host") == "127.0.0.1"
        and dsn.get("port", "5432") == "5432"
        and dsn.get("dbname") == "appdb",
        "wrong database DSN",
    )
    user = pwd.getpwnam(props["User"])
    gid = grp.getgrnam(props["Group"] or user.pw_name).gr_gid
    require(user.pw_uid > 0 and props["RuntimeDirectory"] == "pisrs-ingest", "wrong service user")
    lock = Path(env["PISRS_LOCK_PATH"])
    require(
        str(lock) == "/run/pisrs-ingest/ingest.lock" and not lock.is_symlink(),
        "canonical lock changed",
    )
    rt = lock.parent.lstat()
    require(
        stat.S_ISDIR(rt.st_mode)
        and rt.st_uid == user.pw_uid
        and rt.st_gid == gid
        and stat.S_IMODE(rt.st_mode) == int(props["RuntimeDirectoryMode"], 8),
        "runtime absent or permissions changed; no creation during preparation",
    )
    m = re.search(
        r"(/opt/pisrs-ingest/releases/[^ ;]+/\.venv)/bin/pisrs-ingest nightly", props["ExecStart"]
    )
    require(m is not None, "deployed executable contract changed")
    deployed = Path(m[1]) / "lib/python3.12/site-packages/pisrs_ingest"
    require(
        "with ApplicationLock(settings.lock_path)" in (deployed / "cli.py").read_text(),
        "deployed application does not prove canonical flock",
    )
    # ApplicationLock's Linux flock, without its PID/truncate side effect.
    require(
        "fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)"
        in (deployed / "locking.py").read_text(),
        "deployed flock implementation changed",
    )
    inactive()
    return env, user, gid, lock, props


class Points:
    def __init__(self, base):
        self.base = base.rstrip("/") + "/collections/pisrs_current/points"
        self.session = requests.Session()
        self.session.trust_env = False

    def retrieve(self, ids):
        result = {}
        for start in range(0, len(ids), 64):
            batch = ids[start : start + 64]
            r = self.session.post(
                self.base,
                json={"ids": batch, "with_payload": True, "with_vector": True},
                timeout=(3, 30),
            )
            r.raise_for_status()
            for p in r.json()["result"]:
                identity = str(p["id"])
                require(identity in batch and identity not in result, "unexpected/duplicate point")
                require(isinstance(p.get("payload"), dict), "non-object Qdrant payload")
                vector_proof(p.get("vector"))
                result[identity] = {"payload": p["payload"], "vector": p["vector"]}
        return result

    def patch(self, point_id, act_id):
        # set_payload(null) deletes a key in Qdrant. Exact recovery of an existing
        # null key therefore uses overwrite_payload with the verified full image.
        # Both endpoints modify payload only; neither carries a vector or upserts.
        payload = {"act_id": act_id}
        method = self.session.post
        if act_id is None:
            payload = self.before_payloads[point_id]
            require(
                "act_id" in payload and payload["act_id"] is None,
                "missing exact NULL payload before-image",
            )
            method = self.session.put
        r = method(
            self.base + "/payload",
            params={"wait": "true"},
            json={"points": [point_id], "payload": payload},
            timeout=(3, 30),
        )
        r.raise_for_status()
        require(r.json().get("result", {}).get("status") == "completed", "Qdrant outcome unknown")


def connect(env, *, read_only=False):
    c = psycopg.connect(
        env["PISRS_DATABASE_DSN"],
        autocommit=True,
        row_factory=dict_row,
        connect_timeout=8,
        options="-c statement_timeout=30000 -c lock_timeout=3000 "
        "-c idle_in_transaction_session_timeout=120000 -c timezone=UTC"
        + (" -c default_transaction_read_only=on" if read_only else ""),
    )
    require(c.info.dbname == "appdb", "wrong connected database")
    return c


def metadata(c):
    identity = c.execute(
        "SELECT current_user AS role, session_user, current_database() AS database, "
        "current_setting('transaction_read_only') AS read_only, "
        "transaction_timestamp() AS measured_at"
    ).fetchone()
    identity["measured_at"] = identity["measured_at"].isoformat()
    rights = c.execute("""SELECT t,pg_get_userbyid(cl.relowner) AS owner,
        has_table_privilege(current_user,cl.oid,'SELECT') AS can_select,
        has_table_privilege(current_user,cl.oid,'UPDATE') AS can_update,
        has_table_privilege(current_user,cl.oid,'DELETE') AS can_delete,
        has_table_privilege(current_user,cl.oid,'TRUNCATE') AS can_truncate,
        cl.relrowsecurity AS rls,
        (SELECT count(*) FROM pg_rewrite r WHERE r.ev_class=cl.oid AND rulename<>'_RETURN') rules
        FROM unnest(ARRAY['acts','act_text_versions','act_text_blocks','embedding_chunks']) t
        JOIN pg_class cl ON cl.oid=('pisrs.'||t)::regclass ORDER BY t""").fetchall()
    columns = c.execute(
        """SELECT table_name,column_name,
        has_column_privilege(current_user,'pisrs.'||table_name,column_name,'UPDATE') can_update
        FROM information_schema.columns WHERE table_schema='pisrs'
        AND table_name=ANY(%s) AND column_name IN ('act_id','payload','updated_at')
        ORDER BY table_name,column_name""",
        (list(TABLES),),
    ).fetchall()
    triggers = c.execute("""SELECT c.relname AS table_name,t.tgname,t.tgenabled,
        pg_get_triggerdef(t.oid) AS definition, pg_get_functiondef(t.tgfoid) AS function
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        WHERE t.tgrelid=ANY(ARRAY['pisrs.act_text_versions'::regclass,
        'pisrs.act_text_blocks'::regclass,'pisrs.embedding_chunks'::regclass])
        AND NOT t.tgisinternal ORDER BY c.relname,t.tgname""").fetchall()
    return {
        "identity": identity,
        "table_rights": rights,
        "column_rights": columns,
        "triggers": triggers,
        "share_lock_from_acl": any(
            r["t"] == "acts" and (r["can_update"] or r["can_delete"] or r["can_truncate"])
            for r in rights
        ),
        "all_updates_from_acl": all(r["can_update"] for r in columns),
    }


def collect(env, source, out, context):
    original = json.loads(source)
    require(hashlib.sha256(source).hexdigest() == SOURCE_HASH, "dated scope evidence changed")
    candidates = original["candidates"]["data"]
    require(
        len(candidates) == 352 and all(t["matches"] == 1 for t in candidates),
        "original closed scope changed",
    )
    manifest = {
        "database": "appdb",
        "collection": "pisrs_current",
        "base": BASE,
        "original_evidence_sha256": SOURCE_HASH,
        "targets": [
            {"version_id": t["id"], "act_id": t["act_ids"][0], "sop": t["sop_from_docno"]}
            for t in candidates
        ],
    }
    with connect(env, read_only=True) as c, c.transaction():
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        meta = metadata(c)
        manifest["before"] = snapshot(c, manifest)
        for t in manifest["targets"]:
            matches = c.execute(
                "SELECT id FROM pisrs.acts WHERE sop=%s ORDER BY id", (t["sop"],)
            ).fetchall()
            require([x["id"] for x in matches] == [t["act_id"]], "original candidate proof drift")
    require(meta["identity"]["read_only"] == "on", "preparation was not read-only")
    manifest["before_sha256"] = digest(manifest["before"])
    manifest["expected_template_sha256"] = digest(expected_state(manifest, STAMP))
    rows = manifest["before"][TABLES[2]]
    points = Points(env["PISRS_QDRANT_URL"]).retrieve([r["qdrant_point_id"] for r in rows])
    require(set(points) == {r["qdrant_point_id"] for r in rows}, "missing affected point")
    manifest["qdrant"] = {
        pid: {
            "payload": p["payload"],
            "vector_sha256": vector_proof(p["vector"]),
            "dimensions": len(p["vector"]),
        }
        for pid, p in points.items()
    }
    manifest["qdrant_before_sha256"] = digest(manifest["qdrant"])
    manifest["qdrant_expected_sha256"] = digest(expected_points(manifest))
    manifest["scope_sha256"] = digest(closed_scope(manifest))
    validate_manifest(manifest)
    # Close the sequential read window: recheck PG full state after Qdrant reads.
    with connect(env, read_only=True) as c, c.transaction():
        require(
            same(snapshot(c, manifest), manifest["before"]), "PG changed during point measurement"
        )
    meta.update(context)
    meta["counts"] = {t: len(manifest["before"][t]) for t in TABLES}
    meta["points"] = len(points)
    meta["space_free_bytes"] = os.statvfs(out).f_bavail * os.statvfs(out).f_frsize
    durable(out, "manifest.json", manifest)
    durable(out, "expected-template.json", expected_state(manifest, STAMP))
    durable(out, "metadata.json", meta)
    return {
        "result": "PREPARED_NO_PRODUCTION_WRITE",
        "counts": meta["counts"],
        "points": len(points),
        "manifest_sha256": digest(manifest),
        "share_lock_from_acl": meta["share_lock_from_acl"],
        "all_updates_from_acl": meta["all_updates_from_acl"],
    }


def save_verified(out, name, value):
    if (out / name).exists():
        require((out / name).read_bytes() == encoded(value), "prior readback evidence drift")
    else:
        durable(out, name, value)


def final_points(q, manifest, *, reverse=False):
    actual = q.retrieve(list(manifest["qdrant"]))
    require(set(actual) == set(manifest["qdrant"]), "final point subset incomplete")
    proof = {
        pid: {
            "payload": p["payload"],
            "vector_sha256": vector_proof(p["vector"]),
            "dimensions": len(p["vector"]),
        }
        for pid, p in actual.items()
    }
    require(
        same(proof, manifest["qdrant"] if reverse else expected_points(manifest)),
        "final vector/payload proof drift",
    )
    return proof


def operation(
    env,
    manifest,
    out,
    *,
    rollback=False,
    admin_restore=None,
    check=lambda: None,
    expected_metadata=None,
):
    validate_manifest(manifest)
    before = manifest["before"]
    expected_file = out / "expected-after.json"
    q = Points(env["PISRS_QDRANT_URL"])
    q.before_payloads = {pid: p["payload"] for pid, p in manifest["qdrant"].items()}
    original_patch = q.patch

    def guarded_patch(pid, act_id):
        check()
        return original_patch(pid, act_id)

    q.patch = guarded_patch
    with connect(env, read_only=True) as c:
        current = metadata(c)
    if expected_metadata is not None:
        for key in ["table_rights", "column_rights", "triggers"]:
            require(current[key] == expected_metadata[key], "database ACL/schema metadata drift")
        require(
            current["identity"]["role"] == expected_metadata["identity"]["role"],
            "database role drift",
        )
    require(
        current["share_lock_from_acl"] and current["all_updates_from_acl"],
        "required database rights unavailable",
    )
    if not expected_file.exists():
        require(not rollback, "no durable commit intent to recover")
        with connect(env) as c, c.transaction():
            expected = lock_and_validate(c, manifest)
            # Fsync both full before/after images before the first UPDATE.
            durable(out, "before.json", before)
            durable(out, "expected-after.json", expected)
            durable(
                out,
                "commit-intent.json",
                {
                    "manifest_sha256": digest(manifest),
                    "before_sha256": digest(before),
                    "expected_sha256": digest(expected),
                },
            )
            # Validate all vectors and payloads before the PG write too.
            actual = q.retrieve(list(manifest["qdrant"]))
            require(set(actual) == set(manifest["qdrant"]), "point subset incomplete")
            mapping = {t["version_id"]: t["act_id"] for t in manifest["targets"]}
            for row in before[TABLES[2]]:
                pid = row["qdrant_point_id"]
                require(
                    classify_point(actual[pid], manifest["qdrant"][pid], mapping[row["version_id"]])
                    == "before",
                    "point baseline drift",
                )
            check()
            apply_locked(c, manifest, expected)
            durable(out, "precommit.json", expected)
        # No automatic retry of this transaction, including when COMMIT response is lost.
    else:
        expected = json.loads(expected_file.read_text())
        intent = json.loads((out / "commit-intent.json").read_text())
        require(
            intent
            == {
                "manifest_sha256": digest(manifest),
                "before_sha256": digest(before),
                "expected_sha256": digest(expected),
            },
            "durable intent corrupted",
        )
        require(
            expected == expected_state(manifest, expected[TABLES[0]][0]["updated_at"]),
            "expected image inconsistent",
        )
    # A fresh locked read waits out any old transaction before classifying the commit.
    with connect(env) as c, c.transaction():
        actual = snapshot(c, manifest, lock=True)
        state = classify_pg(actual, before, expected)
    if state == "before":
        require(
            not (out / "pg-confirmed.json").exists()
            or (rollback and (out / "rollback-intent.json").exists()),
            "PG reverted externally",
        )
        if rollback:
            require((out / "rollback-intent.json").exists(), "no own rollback intent")
            changed = sync_points(manifest, q.retrieve, q.patch, reverse=True)
            save_verified(out, "rollback-qdrant.json", final_points(q, manifest, reverse=True))
            save_verified(out, "rollback-pg.json", before)
            return {"result": "ROLLED_BACK", "point_patches": changed}
        return {
            "result": "NOT_APPLIED_STOP",
            "reason": "commit intent exists but PG is unchanged; review before any new attempt; "
            "UPDATE not repeated",
        }
    if not (out / "pg-confirmed.json").exists():
        durable(out, "pg-confirmed.json", {"expected_sha256": digest(expected)})
    if rollback:
        require(admin_restore is not None, "privileged timestamp recovery unavailable")
        if not (out / "rollback-intent.json").exists():
            durable(out, "rollback-intent.json", {"expected_sha256": digest(expected)})
        changed = sync_points(manifest, q.retrieve, q.patch, reverse=True)
        admin_restore(restore_sql(manifest, expected))
        with connect(env, read_only=True) as c:
            require(same(snapshot(c, manifest), before), "PG restore readback mismatch")
        save_verified(out, "rollback-qdrant.json", final_points(q, manifest, reverse=True))
        save_verified(out, "rollback-pg.json", before)
        return {"result": "ROLLED_BACK", "point_patches": changed}
    require(not (out / "rollback-intent.json").exists(), "rollback already started")
    changed = sync_points(manifest, q.retrieve, q.patch)
    with connect(env, read_only=True) as c:
        require(same(snapshot(c, manifest), expected), "fresh PG readback drift")
    save_verified(out, "verified-pg.json", expected)
    save_verified(out, "verified-qdrant.json", final_points(q, manifest))
    if not (out / "confirmed.json").exists():
        durable(
            out,
            "confirmed.json",
            {
                "manifest_sha256": digest(manifest),
                "expected_sha256": digest(expected),
                "vectors_unchanged": True,
            },
        )
    return {
        "result": "PASS_COMMITTED",
        "point_patches": changed,
        "rows": {t: len(before[t]) for t in TABLES},
    }


def recovery_context(package):
    pinned = json.loads((package / "recovery-identity.json").read_text())
    legacy = read_env(
        Path("/home/rajko/.config/case-law-ingest/pisrs.local.env"),
        {"PISRS_PG_CONTAINER", "PISRS_PG_USER", "PISRS_PG_DB"},
    )
    require(legacy["PISRS_PG_DB"] == "appdb", "recovery database mismatch")
    ports = json.loads(
        command(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .NetworkSettings.Ports}}",
                legacy["PISRS_PG_CONTAINER"],
            ]
        )
    )
    require(
        any(
            p["HostIp"] == "127.0.0.1" and p["HostPort"] == "5432"
            for p in ports.get("5432/tcp", [])
        ),
        "recovery loopback binding changed",
    )
    query = """BEGIN READ ONLY; SET LOCAL statement_timeout='5s';
        SELECT jsonb_build_object('database',current_database(),'admin_role',current_user,
        'system_identifier',(SELECT system_identifier::text FROM pg_control_system()),
        'can_set_replication_role',has_parameter_privilege(
            current_user,'session_replication_role','SET')); ROLLBACK;"""
    raw = command(
        [
            "docker",
            "exec",
            "-i",
            legacy["PISRS_PG_CONTAINER"],
            "psql",
            "-X",
            "-w",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            legacy["PISRS_PG_USER"],
            "-d",
            "appdb",
        ],
        input=query,
    )
    values = [json.loads(line) for line in raw.splitlines() if line.startswith("{")]
    require(
        len(values) == 1
        and all(values[0][k] == pinned[k] for k in values[0])
        and values[0]["can_set_replication_role"],
        "recovery identity/permission drift",
    )
    return legacy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "apply", "rollback"])
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--approved-manifest-sha256")
    parser.add_argument("--approved-package-sha256")
    args = parser.parse_args()
    env, user, gid, lock, props = bootstrap()
    package = args.package.resolve()
    require(
        package.is_dir() and stat.S_IMODE(package.stat().st_mode) == 0o700,
        "private package directory required",
    )
    source = SOURCE_EVIDENCE.read_bytes() if args.mode == "prepare" else None
    manifest = None
    expected_metadata = None
    if args.mode != "prepare":
        raw = (package / "manifest.json").read_bytes()
        require(
            args.approved_manifest_sha256 == hashlib.sha256(raw).hexdigest(),
            "separate approval of exact manifest required",
        )
        manifest = json.loads(raw)
        require(
            manifest["base"] == BASE and manifest["original_evidence_sha256"] == SOURCE_HASH,
            "source revision or original closed scope changed",
        )
        validate_manifest(manifest)
        expected_metadata = json.loads((package / "metadata.json").read_text())
        require(
            hashlib.sha256((package / "SHA256SUMS").read_bytes()).hexdigest()
            == args.approved_package_sha256,
            "separate exact package approval required",
        )
        # The sealed launcher has already checked code before importing this module.
        for line in (package / "SHA256SUMS").read_text().splitlines():
            h, name = line.split(None, 1)
            p = package / name.strip()
            require(
                p.resolve().is_relative_to(package)
                and not p.is_symlink()
                and hashlib.sha256(p.read_bytes()).hexdigest() == h,
                "sealed package changed",
            )
    legacy = recovery_context(package) if manifest is not None else None
    key = (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") if manifest is None else digest(manifest)[:20]
    )
    out = Path("/var/lib/pisrs-ingest") / ("act-link-" + key)
    if not out.exists():
        out.mkdir(mode=0o700)
        os.chown(out, user.pw_uid, gid)
    require(
        not out.is_symlink()
        and out.stat().st_uid == user.pw_uid
        and stat.S_IMODE(out.stat().st_mode) == 0o700,
        "unsafe evidence directory",
    )
    # Parent root is retained only for conditional timestamp restore via local PG socket.
    request_r, request_w = os.pipe()
    response_r, response_w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(request_r)
        os.close(response_w)
        os.initgroups(user.pw_name, gid)
        os.setgid(gid)
        os.setuid(user.pw_uid)
        os.environ.clear()
        os.environ.update(PATH="/usr/bin:/bin", PYTHONDONTWRITEBYTECODE="1")
        try:
            fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
            st = os.fstat(fd)
            require(stat.S_ISREG(st.st_mode) and st.st_uid == user.pw_uid, "wrong lock inode")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            inode = (st.st_dev, st.st_ino)
            started = time.monotonic()

            def check():
                require(time.monotonic() - started < 3600, "one-hour operation budget exceeded")
                require((lock.stat().st_dev, lock.stat().st_ino) == inode, "lock inode replaced")
                inactive()

            check()
            context = {
                "service_user": user.pw_name,
                "uid": os.geteuid(),
                "lock": str(lock),
                "lock_device_inode": inode,
                "lock_file_modified": False,
                "settings": {k: "SET" if env.get(k) else "UNSET" for k in KEEP},
            }

            def broker(sql_text):
                # Parent regenerates the restore from immutable manifest/images, not this input.
                os.write(request_w, b"RESTORE\n")
                require(os.read(response_r, 64) == b"RESTORED\n", "restore outcome unknown")

            if args.mode == "prepare":
                result = collect(env, source, out, context)
            else:
                result = operation(
                    env,
                    manifest,
                    out,
                    rollback=args.mode == "rollback",
                    admin_restore=broker,
                    check=check,
                    expected_metadata=expected_metadata,
                )
            require((lock.stat().st_dev, lock.stat().st_ino) == inode, "lock inode replaced")
            inactive()
            durable(
                out, "result-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json", result
            )
            os._exit(0)
        except BaseException as error:
            # Never print DSNs, server errors, source rows or tokens.
            print(
                json.dumps(
                    {
                        "result": "STOPPED",
                        "error_type": type(error).__name__,
                        "reason": str(error)
                        if type(error).__name__ == "PostgresInvariantError"
                        else "inspect private operation phase; no automatic mutation retry",
                    }
                ),
                flush=True,
            )
            os._exit(1)
    os.close(request_w)
    os.close(response_r)
    request = os.read(request_r, 64)
    if request:
        require(
            args.mode == "rollback" and request == b"RESTORE\n", "unexpected privileged request"
        )
        expected = json.loads((out / "expected-after.json").read_text())
        intent = json.loads((out / "commit-intent.json").read_text())
        require(
            intent["expected_sha256"] == digest(expected)
            and intent["manifest_sha256"] == digest(manifest),
            "restore evidence changed",
        )
        command(
            [
                "docker",
                "exec",
                "-i",
                legacy["PISRS_PG_CONTAINER"],
                "psql",
                "-X",
                "-w",
                "-qAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                legacy["PISRS_PG_USER"],
                "-d",
                "appdb",
            ],
            input=restore_sql(manifest, expected),
        )
        os.write(response_w, b"RESTORED\n")
    _, status = os.waitpid(pid, 0)
    require(os.waitstatus_to_exitcode(status) == 0, "service-user preparation/operation failed")
    if args.mode == "prepare":
        for p in out.iterdir():
            dest = package / p.name
            require(not dest.exists(), "review file already exists")
            shutil.copyfile(p, dest)
            with dest.open("rb") as saved:
                os.fsync(saved.fileno())
            os.chmod(dest, 0o600)
            os.chown(dest, package.stat().st_uid, package.stat().st_gid)
        directory_fd = os.open(package, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(directory_fd)
        os.close(directory_fd)
    print(
        json.dumps(
            {
                "result": json.loads(sorted(out.glob("result-*.json"))[-1].read_text())["result"],
                "evidence": str(out),
                "package": str(package),
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                {
                    "result": "STOPPED",
                    "error_type": type(error).__name__,
                    "reason": str(error)
                    if type(error).__name__ == "PostgresInvariantError"
                    else "private context failure; secrets suppressed",
                }
            ),
            flush=True,
        )
        sys.exit(1)
