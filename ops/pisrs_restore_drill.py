#!/usr/bin/env python3
"""Restore a sealed PISRS backup only into fresh containers with network=none."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


def run(args, *, data=None, timeout=120):
    p = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError("local backup/restore command failed: " + args[0])
    return p.stdout


def inspect(identity):
    return json.loads(run(["docker", "inspect", identity]))[0]


def psql_args(identity, database, user):
    return [
        "docker",
        "exec",
        "-i",
        "-e",
        "PGOPTIONS=-c default_transaction_read_only=on -c timezone=UTC",
        identity,
        "psql",
        "-X",
        "-w",
        "-qAt",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        user,
        "-d",
        database,
    ]


def pg_query(identity, database, user, sql):
    query = (
        "BEGIN READ ONLY; SET LOCAL statement_timeout='30min'; SET LOCAL timezone='UTC';"
        + sql
        + ";ROLLBACK;"
    )
    return (
        run(psql_args(identity, database, user), data=query.encode(), timeout=1900).decode().strip()
    )


def pg_fingerprint(identity, database, user):
    # Read-only source or isolated destination; no SQL mutation is accepted.
    names = json.loads(
        pg_query(
            identity,
            database,
            user,
            """SELECT coalesce(jsonb_agg(
        jsonb_build_object('table',c.relname,'order_by',coalesce((SELECT string_agg(
          quote_ident(a.attname),',' ORDER BY k.n) FROM pg_index i,
          unnest(i.indkey) WITH ORDINALITY k(attnum,n)
          JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
          WHERE i.indrelid=c.oid AND i.indisprimary),'to_jsonb(t)::text'))
        ORDER BY c.relname),'[]'::jsonb) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='pisrs' AND c.relkind IN ('r','p','m')""",
        )
    )
    tables = {}
    for item in names:
        name = '"' + item["table"].replace('"', '""') + '"'
        query = (
            "BEGIN READ ONLY; SET LOCAL timezone='UTC'; SET LOCAL statement_timeout='30min'; "
            f"COPY (SELECT to_jsonb(t)::text FROM pisrs.{name} t ORDER BY {item['order_by']}) "
            "TO STDOUT; ROLLBACK;"
        )
        with tempfile.TemporaryFile() as errors:
            p = subprocess.Popen(
                psql_args(identity, database, user),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=errors,
            )
            p.stdin.write(query.encode())
            p.stdin.close()
            h = hashlib.sha256()
            count = 0
            started = time.monotonic()
            while chunk := p.stdout.read(1024 * 1024):
                h.update(chunk)
                count += chunk.count(b"\n")
                if time.monotonic() - started > 1900:
                    p.kill()
                    p.wait()
                    raise TimeoutError("fingerprint table budget")
            if p.wait(timeout=10):
                raise RuntimeError("read-only table fingerprint failed")
        tables[item["table"]] = {"rows": count, "sha256": h.hexdigest()}
    sequences = json.loads(
        pg_query(
            identity,
            database,
            user,
            """SELECT coalesce(jsonb_agg(
        jsonb_build_object('name',sequencename,'last_value',last_value,
          'increment',increment_by,'start',start_value,'min',min_value,'max',max_value,'cycle',cycle)
        ORDER BY sequencename),'[]'::jsonb) FROM pg_sequences WHERE schemaname='pisrs'""",
        )
    )
    # is_called is read directly, because pg_sequences.last_value alone is insufficient.
    for sequence in sequences:
        name = '"' + sequence["name"].replace('"', '""') + '"'
        sequence["state"] = json.loads(
            pg_query(
                identity,
                database,
                user,
                f"SELECT jsonb_build_object('last_value',last_value,'is_called',is_called) "
                f"FROM pisrs.{name}",
            )
        )
    constraints = json.loads(
        pg_query(
            identity,
            database,
            user,
            """SELECT coalesce(jsonb_agg(
        jsonb_build_object('table',c.conrelid::regclass::text,'name',c.conname,
          'definition',pg_get_constraintdef(c.oid),'validated',c.convalidated)
        ORDER BY c.conrelid::regclass::text,c.conname),'[]'::jsonb)
        FROM pg_constraint c WHERE c.connamespace='pisrs'::regnamespace""",
        )
    )
    if any(not c["validated"] for c in constraints):
        raise ValueError("unvalidated constraint")
    schema = pg_query(
        identity,
        database,
        user,
        """SELECT jsonb_build_object(
        'columns',(SELECT jsonb_agg(jsonb_build_object('table',c.relname,'name',a.attname,
            'type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull,
            'identity',a.attidentity,'generated',a.attgenerated,
            'default',pg_get_expr(d.adbin,d.adrelid)) ORDER BY c.relname,a.attnum)
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname='pisrs' AND c.relkind IN ('r','p','m','v')
              AND a.attnum>0 AND NOT a.attisdropped),
        'indexes',(SELECT jsonb_agg(jsonb_build_object('table',tablename,'name',indexname,
            'definition',indexdef) ORDER BY tablename,indexname)
            FROM pg_indexes WHERE schemaname='pisrs'),
        'triggers',(SELECT jsonb_agg(jsonb_build_object('table',c.relname,'name',t.tgname,
            'enabled',t.tgenabled,'definition',pg_get_triggerdef(t.oid))
            ORDER BY c.relname,t.tgname)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='pisrs'
              AND NOT t.tgisinternal),
        'functions',(SELECT jsonb_agg(pg_get_functiondef(p.oid) ORDER BY p.oid::regprocedure::text)
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='pisrs' AND p.prokind IN ('f','p')),
        'views',(SELECT jsonb_agg(jsonb_build_object('name',c.relname,
            'definition',pg_get_viewdef(c.oid,true)) ORDER BY c.relname)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='pisrs' AND c.relkind IN ('v','m')))""",
    )
    schema_hash = hashlib.sha256(
        json.dumps(json.loads(schema), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "tables": tables,
        "sequences": sequences,
        "constraints": constraints,
        "schema_sha256": schema_hash,
    }


def q_request(identity, path, body=None, *, isolated=False, method=None):
    state = inspect(identity)
    if isolated and state["HostConfig"]["NetworkMode"] != "none":
        raise ValueError("restore target has network access")
    if method == "PATCH" and (
        not isolated or not state["Config"]["Labels"].get("pisrs.restore_drill")
    ):
        raise ValueError("optimizer resume is restricted to isolated owned restore containers")
    pid = state["State"]["Pid"]
    if not pid:
        raise ValueError("Qdrant container is not running")
    args = [
        "/usr/bin/nsenter",
        "--target",
        str(pid),
        "--net",
        "/usr/bin/curl",
        "--disable",
        "--noproxy",
        "*",
        "--fail",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "3",
        "--max-time",
        "60",
        "http://127.0.0.1:6333" + path,
    ]
    if method is not None:
        args.extend(["--request", method])
    if body is not None:
        args.extend(["-H", "Content-Type: application/json", "--data-binary", json.dumps(body)])
    return json.loads(run(args, timeout=70))["result"]


def q_fingerprint(identity, *, isolated=False):
    collection = "/collections/pisrs_current"
    info = q_request(identity, collection, isolated=isolated)
    if info["status"] != "green":
        raise ValueError("Qdrant is not green")
    h = hashlib.sha256()
    count = 0
    offset = None
    seen = set()
    while True:
        body = {"limit": 128, "with_payload": True, "with_vector": True}
        if offset is not None:
            body["offset"] = offset
        result = q_request(identity, collection + "/points/scroll", body, isolated=isolated)
        for point in result["points"]:
            h.update(
                (
                    json.dumps(point, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
                ).encode()
            )
            count += 1
        offset = result.get("next_page_offset")
        if offset is None:
            break
        if str(offset) in seen:
            raise ValueError("Qdrant scroll cycle")
        seen.add(str(offset))
    config = info["config"]["params"]
    exact = q_request(identity, collection + "/points/count", {"exact": True}, isolated=isolated)[
        "count"
    ]
    if exact != count:
        raise ValueError("incomplete point fingerprint")
    return {
        "count": count,
        "sha256": h.hexdigest(),
        "vectors": config["vectors"],
        "payload_schema": info.get("payload_schema", {}),
    }


def verify_bundle(bundle, expected):
    raw = (bundle / "SHA256SUMS").read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("backup manifest hash mismatch")
    names = set()
    for line in raw.decode().splitlines():
        h, name = line.split(None, 1)
        name = name.strip()
        p = bundle / name
        if p.is_symlink() or not p.resolve().is_relative_to(bundle.resolve()) or name in names:
            raise ValueError("unsafe backup member")
        check = hashlib.sha256()
        with p.open("rb") as f:
            while data := f.read(8 * 1024 * 1024):
                check.update(data)
        if check.hexdigest() != h:
            raise ValueError("backup checksum mismatch")
        names.add(name)
    if (
        not {"pg.dump", "pisrs_current.snapshot", "checkpoint.json", "baseline.json", "images.json"}
        <= names
    ):
        raise ValueError("incomplete backup set")
    json.loads((bundle / "checkpoint.json").read_text())
    return json.loads((bundle / "images.json").read_text())


def restore(bundle, expected, work):
    if os.geteuid() != 0:
        raise ValueError("legitimate local administrator authentication required")
    started = time.monotonic()
    free_before = shutil.disk_usage(work.parent).free
    images = verify_bundle(bundle, expected)
    baseline = json.loads((bundle / "baseline.json").read_text())
    for value in [images["postgres"], images["qdrant"]]:
        if not re.fullmatch("sha256:[0-9a-f]{64}", value):
            raise ValueError("unpinned image")
        run(["docker", "image", "inspect", value])
    allowed = (
        work.parent == Path("/var/lib/pisrs-restore-drills")
        or work.parent == Path("/tmp")
        and work.name.startswith("pisrs-restore-test-")
    )
    if not allowed or work.exists() or work.is_symlink() or work.absolute() != work.resolve():
        raise ValueError("fresh dedicated restore directory required")
    if shutil.disk_usage(work.parent).free < images["required_free_bytes"]:
        raise ValueError("insufficient shared restore space")
    work.mkdir(mode=0o700)
    pgdata = work / "postgres"
    pgdata.mkdir(mode=0o700)
    os.chown(pgdata, 999, 999)
    qdata = work / "qdrant"
    qdata.mkdir(mode=0o700)
    token = uuid.uuid4().hex
    owned = []

    def assert_owned(identity):
        obj = inspect(identity)
        if (
            obj["Config"]["Labels"].get("pisrs.restore_drill") != token
            or obj["HostConfig"]["NetworkMode"] != "none"
        ):
            raise ValueError("restore ownership/isolation mismatch")
        if obj["HostConfig"].get("PortBindings"):
            raise ValueError("restore target publishes ports")
        for mount in obj["Mounts"]:
            if mount["Type"] == "tmpfs":
                continue
            if mount["Type"] != "bind":
                raise ValueError("unexpected persistent restore mount")
            source = Path(mount["Source"]).resolve()
            if source == bundle.resolve():
                if mount["RW"]:
                    raise ValueError("backup input mounted writable")
            elif source not in [pgdata.resolve(), qdata.resolve()]:
                raise ValueError("source data mounted in restore target")
        return obj

    try:
        common = [
            "--pull",
            "never",
            "--network",
            "none",
            "--restart",
            "no",
            "--read-only",
            "--label",
            "pisrs.restore_drill=" + token,
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--cpus",
            "2",
        ]
        pg = (
            run(
                [
                    "docker",
                    "create",
                    *common,
                    "--memory",
                    "2g",
                    "--user",
                    "999:999",
                    "--mount",
                    f"type=bind,src={pgdata},dst=/var/lib/postgresql",
                    "--tmpfs",
                    "/var/run/postgresql:rw,uid=999,gid=999,mode=700",
                    "--tmpfs",
                    "/tmp:rw,uid=999,gid=999,mode=700",
                    "-e",
                    "POSTGRES_HOST_AUTH_METHOD=trust",
                    "-e",
                    "POSTGRES_DB=pisrs_test_restore",
                    "-e",
                    "PGDATA=/var/lib/postgresql/data",
                    images["postgres"],
                ]
            )
            .decode()
            .strip()
        )
        owned.append(pg)
        assert_owned(pg)
        run(["docker", "start", pg])
        for _ in range(150):
            try:
                logs = run(["docker", "logs", pg])
                if b"init process complete" not in logs:
                    time.sleep(0.2)
                    continue
                if (
                    pg_query(pg, "pisrs_test_restore", "postgres", "SELECT current_database()")
                    == "pisrs_test_restore"
                ):
                    break
            except RuntimeError:
                pass
            time.sleep(0.2)
        else:
            raise TimeoutError("isolated PostgreSQL startup")
        empty = pg_query(
            pg, "pisrs_test_restore", "postgres", "SELECT to_regnamespace('pisrs') IS NULL"
        )
        if empty != "t":
            raise ValueError("restore database is not empty")
        assert_owned(pg)
        with (bundle / "pg.dump").open("rb") as source:
            p = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    pg,
                    "pg_restore",
                    "-U",
                    "postgres",
                    "-d",
                    "pisrs_test_restore",
                    "--single-transaction",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                ],
                stdin=source,
                capture_output=True,
                timeout=7200,
            )
            if p.returncode:
                raise RuntimeError("isolated pg_restore failed")
        q = (
            run(
                [
                    "docker",
                    "create",
                    *common,
                    "--memory",
                    "8g",
                    "--user",
                    "0:0",
                    "--mount",
                    f"type=bind,src={qdata},dst=/qdrant/storage",
                    "--mount",
                    f"type=bind,src={bundle},dst=/restore,readonly",
                    "--tmpfs",
                    "/qdrant/snapshots:rw,mode=700",
                    "--tmpfs",
                    "/tmp:rw,mode=700",
                    "-e",
                    "QDRANT__TELEMETRY_DISABLED=true",
                    "-e",
                    "QDRANT__CLUSTER__ENABLED=false",
                    "--entrypoint",
                    "/qdrant/qdrant",
                    images["qdrant"],
                    "--snapshot",
                    "/restore/pisrs_current.snapshot:pisrs_current",
                ]
            )
            .decode()
            .strip()
        )
        owned.append(q)
        assert_owned(q)
        run(["docker", "start", q])
        optimizer_resumed = False
        for _ in range(1800):
            if assert_owned(q)["State"]["Status"] == "exited":
                raise RuntimeError("isolated Qdrant snapshot startup failed")
            try:
                info = q_request(q, "/collections/pisrs_current", isolated=True)
                if info["status"] == "red" or isinstance(info.get("optimizer_status"), dict):
                    raise AssertionError("restored optimizer error")
                if info["status"] == "grey" and not optimizer_resumed:
                    assert_owned(q)
                    q_request(
                        q,
                        "/collections/pisrs_current",
                        {"optimizers_config": {}},
                        isolated=True,
                        method="PATCH",
                    )
                    optimizer_resumed = True
                if (
                    info["status"] == "green"
                    and q_request(
                        q, "/collections/pisrs_current/points/count", {"exact": True}, isolated=True
                    )["count"]
                    == baseline["qdrant"]["count"]
                ):
                    break
            except (RuntimeError, ValueError):
                pass
            time.sleep(1)
        else:
            raise TimeoutError("isolated Qdrant snapshot startup")
        copied = work / "checkpoint.json"
        shutil.copyfile(bundle / "checkpoint.json", copied)
        copied.chmod(0o600)
        with copied.open("rb") as f:
            os.fsync(f.fileno())
        actual = {
            "pg": pg_fingerprint(pg, "pisrs_test_restore", "postgres"),
            "qdrant": q_fingerprint(q, isolated=True),
            "checkpoint_sha256": hashlib.sha256(copied.read_bytes()).hexdigest(),
        }
        verify_bundle(bundle, expected)
        if actual != baseline:
            raise ValueError("full restore fingerprint mismatch")
        report = {
            "result": "PASS_ISOLATED_RESTORE",
            "elapsed_seconds": time.monotonic() - started,
            "free_bytes_before": free_before,
            "free_bytes_after": shutil.disk_usage(work).free,
            "restore_apparent_bytes": int(run(["du", "-sb", str(work)]).split()[0]),
            "memory_caps_bytes": {"postgres": 2 * 1024**3, "qdrant": 8 * 1024**3},
            "cpu_cap_each": 2,
            "measurements_are_not_peak_wal_or_memory": True,
            "fingerprints": actual,
            "network": "none",
            "ports_published": False,
            "production_mounts": 0,
            "source_mutations": 0,
            "isolated_optimizer_resumed": optimizer_resumed,
        }
        target = work / "report.json"
        with target.open("x") as f:
            target.chmod(0o600)
            json.dump(report, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        return report
    finally:
        for identity in reversed(owned):
            assert_owned(identity)
            run(["docker", "rm", "-f", identity])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    report = restore(args.bundle.resolve(), args.bundle_sha256, args.work)
    print(json.dumps({"result": report["result"], "report": str(args.work / "report.json")}))


if __name__ == "__main__":
    main()
