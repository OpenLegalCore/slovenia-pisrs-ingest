from __future__ import annotations

import importlib.util
import json
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import psycopg
import pytest
import requests
from psycopg.rows import dict_row
from test_act_links import pg_links, seed  # noqa: F401

from pisrs_ingest.act_link_manifest import (
    STAMP,
    TABLES,
    classify_point,
    closed_scope,
    digest,
    encoded,
    expected_points,
    expected_state,
    lock_and_validate,
    restore_sql,
    snapshot,
    validate_manifest,
    vector_proof,
)
from pisrs_ingest.postgres import PostgresInvariantError

spec = importlib.util.spec_from_file_location(
    "act_link_operation", Path(__file__).parents[1] / "ops/act_link_operation.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class FakePoints:
    def __init__(self, points):
        self.points = points
        self.calls = []
        self.interrupt = None

    def retrieve(self, ids):
        return {i: deepcopy(self.points[i]) for i in ids if i in self.points}

    def patch(self, pid, act_id):
        self.points[pid]["payload"]["act_id"] = act_id
        self.calls.append((pid, act_id))
        if self.interrupt:
            self.interrupt()


def seal(m):
    m["before_sha256"] = digest(m["before"])
    m["expected_template_sha256"] = digest(expected_state(m, STAMP))
    m["qdrant_before_sha256"] = digest(m["qdrant"])
    m["qdrant_expected_sha256"] = digest(expected_points(m))
    m["scope_sha256"] = digest(closed_scope(m))
    return m


@pytest.fixture
def operation_case(pg_links, monkeypatch, tmp_path):  # noqa: F811
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,'SOP-1')")
    seed(c, 1)
    seed(c, 2, active=False)
    c.execute("""CREATE FUNCTION pisrs.touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN NEW.updated_at=now(); RETURN NEW; END; $$""")
    for table in TABLES:
        c.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON pisrs.{table} "
            "FOR EACH ROW EXECUTE FUNCTION pisrs.touch_updated_at()"
        )
    targets = c.execute(
        "SELECT id AS version_id,sop_from_docno AS sop,10::bigint AS act_id "
        "FROM pisrs.act_text_versions ORDER BY id"
    ).fetchall()
    manifest = {"targets": targets, "database": "appdb", "collection": "pisrs_current"}
    manifest["before"] = snapshot(c, manifest)
    points = {
        r["qdrant_point_id"]: {"payload": deepcopy(r["payload"]), "vector": [0.125] * 3072}
        for r in manifest["before"][TABLES[2]]
    }
    manifest["qdrant"] = {
        i: {
            "payload": deepcopy(p["payload"]),
            "vector_sha256": vector_proof(p["vector"]),
            "dimensions": 3072,
        }
        for i, p in points.items()
    }
    seal(manifest)
    validate_manifest(manifest)
    q = FakePoints(points)

    def connection(env, *, read_only=False):
        return psycopg.connect(
            db.dsn,
            autocommit=True,
            row_factory=dict_row,
            options="-c timezone=UTC"
            + (" -c default_transaction_read_only=on" if read_only else ""),
        )

    monkeypatch.setattr(runner, "connect", connection)
    monkeypatch.setattr(runner, "Points", lambda _: q)
    return c, manifest, q, tmp_path, {"PISRS_QDRANT_URL": "unused"}, connection


def run(case, **kwargs):
    _, m, _, out, env, _ = case
    return runner.operation(env, m, out, **kwargs)


def test_pg_closed_apply_excludes_new_eligible_rows_and_repeats_without_update(operation_case):
    c, m, q, out, _, _ = operation_case
    extra = seed(c, 3)
    outside = c.execute(
        "SELECT to_jsonb(t) row FROM pisrs.act_text_versions t WHERE id=%s", (extra.version_id,)
    ).fetchone()
    assert run(operation_case)["result"] == "PASS_COMMITTED"
    after = snapshot(c, m)
    assert (
        classify_point(
            q.retrieve(list(q.points))[next(iter(q.points))], m["qdrant"][next(iter(q.points))], 10
        )
        == "after"
    )
    assert len(q.calls) == 2
    assert run(operation_case)["point_patches"] == 0
    assert snapshot(c, m) == after
    assert (
        c.execute(
            "SELECT to_jsonb(t) row FROM pisrs.act_text_versions t WHERE id=%s", (extra.version_id,)
        ).fetchone()
        == outside
    )
    assert json.loads((out / "precommit.json").read_text()) == after


@pytest.mark.parametrize("drift", ["sop_ambiguous", "new_child", "nonnull", "json", "status"])
def test_pg_manifest_drift_fails_before_any_write(operation_case, drift):
    c, m, q, _, _, _ = operation_case
    if drift == "sop_ambiguous":
        c.execute("INSERT INTO pisrs.acts VALUES (11,'SOP-1')")
    elif drift == "new_child":
        c.execute(
            "INSERT INTO pisrs.act_text_blocks(version_id,text_id,act_id) VALUES (%s,1,NULL)",
            (m["targets"][0]["version_id"],),
        )
    elif drift == "nonnull":
        c.execute("UPDATE pisrs.act_text_blocks SET act_id=10")
    elif drift == "json":
        c.execute("UPDATE pisrs.embedding_chunks SET payload=payload || '{\"new\":1}'")
    else:
        c.execute("UPDATE pisrs.embedding_chunks SET qdrant_status='changed'")
    before = snapshot(c, m)
    with pytest.raises(PostgresInvariantError):
        run(operation_case)
    assert snapshot(c, m) == before and q.calls == []


def test_pg_constraint_failure_rolls_back_parents_and_children(operation_case):
    c, m, q, _, _, _ = operation_case
    c.execute("ALTER TABLE pisrs.embedding_chunks ADD CHECK (act_id IS NULL)")
    with pytest.raises(psycopg.errors.CheckViolation):
        run(operation_case)
    assert snapshot(c, m) == m["before"] and q.calls == []


@pytest.mark.parametrize("point_fault", ["missing", "vector", "payload"])
def test_pg_point_preflight_blocks_pg_update(operation_case, point_fault):
    c, m, q, _, _, _ = operation_case
    pid = next(iter(q.points))
    if point_fault == "missing":
        del q.points[pid]
    elif point_fault == "vector":
        q.points[pid]["vector"][0] = 9.0
    else:
        q.points[pid]["payload"]["unknown"] = "drift"
    with pytest.raises(PostgresInvariantError):
        run(operation_case)
    assert snapshot(c, m) == m["before"] and not q.calls


def test_pg_lost_commit_response_is_resolved_without_second_update(operation_case, monkeypatch):
    c, m, q, out, _, connection = operation_case
    lost = []

    class LoseCommit:
        def __init__(self, conn):
            self.conn = conn

        def __getattr__(self, k):
            return getattr(self.conn, k)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.conn.__exit__(*args)

        @contextmanager
        def transaction(self):
            with self.conn.transaction():
                yield self
            if (out / "precommit.json").exists() and not lost:
                lost.append(True)
                raise OSError("lost commit response")

    def factory(env, *, read_only=False):
        conn = connection(env, read_only=read_only)
        return conn if read_only else LoseCommit(conn)

    monkeypatch.setattr(runner, "connect", factory)
    with pytest.raises(OSError):
        run(operation_case)
    expected = json.loads((out / "expected-after.json").read_text())
    assert snapshot(c, m) == expected and not q.calls
    monkeypatch.setattr(runner, "apply_locked", lambda *_: pytest.fail("second UPDATE"))
    assert run(operation_case)["result"] == "PASS_COMMITTED"
    assert snapshot(c, m) == expected and len(q.calls) == 2


def test_pg_partial_qdrant_lost_response_resume_skips_completed_patch(operation_case):
    c, m, q, out, _, _ = operation_case
    q.interrupt = lambda: (_ for _ in ()).throw(OSError("lost patch response"))
    with pytest.raises(OSError):
        run(operation_case)
    assert len(q.calls) == 1
    expected = json.loads((out / "expected-after.json").read_text())
    q.interrupt = None
    assert run(operation_case)["point_patches"] == 1
    assert len({pid for pid, _ in q.calls}) == len(q.calls) == 2
    assert snapshot(c, m) == expected


def test_pg_not_committed_intent_is_not_retried(operation_case, monkeypatch):
    c, m, q, _, _, _ = operation_case
    monkeypatch.setattr(runner, "apply_locked", lambda *_: (_ for _ in ()).throw(OSError("stop")))
    with pytest.raises(OSError):
        run(operation_case)
    monkeypatch.setattr(runner, "apply_locked", lambda *_: pytest.fail("retry UPDATE"))
    assert run(operation_case)["result"] == "NOT_APPLIED_STOP"
    assert snapshot(c, m) == m["before"] and not q.calls


def test_pg_conditional_rollback_restores_full_rows_vectors_and_timestamps(operation_case):
    c, m, q, _, _, _ = operation_case
    run(operation_case)
    result = run(operation_case, rollback=True, admin_restore=lambda sql: c.execute(sql))
    assert result["result"] == "ROLLED_BACK"
    assert snapshot(c, m) == m["before"]
    assert len(q.calls) == 4
    for pid, p in q.points.items():
        assert p["payload"] == m["qdrant"][pid]["payload"]
        assert vector_proof(p["vector"]) == m["qdrant"][pid]["vector_sha256"]
    assert (
        run(operation_case, rollback=True, admin_restore=lambda _: pytest.fail("repeat restore"))[
            "point_patches"
        ]
        == 0
    )


def test_pg_lost_restore_response_resolved_without_second_restore(operation_case):
    c, m, q, _, _, _ = operation_case
    run(operation_case)

    def lose_response(sql):
        c.execute(sql)
        raise OSError("lost restore commit response")

    with pytest.raises(OSError):
        run(operation_case, rollback=True, admin_restore=lose_response)
    assert snapshot(c, m) == m["before"]
    assert (
        run(operation_case, rollback=True, admin_restore=lambda _: pytest.fail("repeat"))["result"]
        == "ROLLED_BACK"
    )
    assert len(q.calls) == 4


@pytest.mark.parametrize("location", ["pg", "qdrant"])
def test_pg_rollback_refuses_changed_post_state(operation_case, location):
    c, m, q, _, _, _ = operation_case
    run(operation_case)
    if location == "pg":
        c.execute("UPDATE pisrs.embedding_chunks SET qdrant_status='external'")
    else:
        q.points[next(iter(q.points))]["vector"][0] = 1.0
    before = snapshot(c, m)
    with pytest.raises(PostgresInvariantError):
        run(operation_case, rollback=True, admin_restore=lambda _: pytest.fail("restore"))
    assert snapshot(c, m) == before and len(q.calls) == 2


def test_pg_restore_sql_checks_every_table_before_first_update(operation_case):
    c, m, _, out, _, _ = operation_case
    run(operation_case)
    expected = json.loads((out / "expected-after.json").read_text())
    c.execute("UPDATE pisrs.embedding_chunks SET qdrant_status='external'")
    before = snapshot(c, m)
    with pytest.raises(psycopg.errors.RaiseException), c.transaction():
        c.execute(restore_sql(m, expected))
    assert snapshot(c, m) == before


def test_pg_share_lock_acl_with_only_acts_update(operation_case):
    c, _, _, _, _, _ = operation_case
    c.execute("CREATE ROLE pisrs_act_link_acl_test")
    try:
        c.execute("GRANT USAGE ON SCHEMA pisrs TO pisrs_act_link_acl_test")
        c.execute("GRANT SELECT, UPDATE ON pisrs.acts TO pisrs_act_link_acl_test")
        with c.transaction():
            c.execute("SET LOCAL ROLE pisrs_act_link_acl_test")
            c.execute("LOCK TABLE pisrs.acts IN SHARE MODE")
            assert not c.execute(
                "SELECT has_table_privilege(current_user,'pisrs.acts','DELETE') x"
            ).fetchone()["x"]
    finally:
        c.execute("DROP OWNED BY pisrs_act_link_acl_test")
        c.execute("DROP ROLE pisrs_act_link_acl_test")


def test_pg_closed_hash_tampering_rejected(operation_case):
    c, m, q, _, _, _ = operation_case
    m["targets"][0]["act_id"] = 99
    with pytest.raises(PostgresInvariantError):
        run(operation_case)
    assert snapshot(c, m) == m["before"] and not q.calls


def test_pg_metadata_change_blocks_operation(operation_case):
    c, m, q, _, _, _ = operation_case
    expected_metadata = runner.metadata(c)
    expected_metadata["triggers"] = []
    with pytest.raises(PostgresInvariantError, match="metadata drift"):
        run(operation_case, expected_metadata=expected_metadata)
    assert snapshot(c, m) == m["before"] and not q.calls


def test_pg_runtime_image_corruption_blocks_resume(operation_case):
    _, _, q, out, _, _ = operation_case
    q.interrupt = lambda: (_ for _ in ()).throw(OSError("stop"))
    with pytest.raises(OSError):
        run(operation_case)
    data = json.loads((out / "expected-after.json").read_text())
    data[TABLES[0]][0]["title"] = "tampered"
    (out / "expected-after.json").write_bytes(encoded(data))
    q.interrupt = None
    with pytest.raises(PostgresInvariantError):
        run(operation_case)
    assert len(q.calls) == 1


@pytest.mark.parametrize("partial", [False, True])
def test_pg_real_qdrant_closed_operation_and_conditional_recovery(
    operation_case, monkeypatch, partial
):
    url = os.environ.get("PISRS_TEST_QDRANT_URL")
    if not url:
        pytest.skip("requires isolated real Qdrant")
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    assert parsed.hostname == "127.0.0.1" and parsed.port not in [6333, 6334, 5432]
    c, m, _, out, env, _ = operation_case
    base = url + "/collections/pisrs_current"
    session = requests.Session()
    session.trust_env = False
    assert session.put(base, json={"vectors": {"size": 3072, "distance": "Cosine"}}, timeout=10).ok
    try:
        points = [
            {"id": pid, "payload": proof["payload"], "vector": [0.125] * 3072}
            for pid, proof in m["qdrant"].items()
        ]
        assert session.put(base + "/points?wait=true", json={"points": points}, timeout=10).ok
        adapter = runner.Points  # patched fixture; reload actual class from file
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        adapter = fresh.Points(url)
        actual = adapter.retrieve(list(m["qdrant"]))
        for pid, p in actual.items():
            m["qdrant"][pid]["vector_sha256"] = vector_proof(p["vector"])
        seal(m)
        calls = []
        original = adapter.patch

        def patch(pid, act):
            original(pid, act)
            calls.append((pid, act))
            if partial and len(calls) == 1:
                raise OSError("lost real Qdrant response")

        adapter.patch = patch
        monkeypatch.setattr(runner, "Points", lambda _: adapter)
        env["PISRS_QDRANT_URL"] = url
        if partial:
            with pytest.raises(OSError):
                run(operation_case)
        assert run(operation_case)["result"] == "PASS_COMMITTED"
        assert len(calls) == 2
        assert run(operation_case)["point_patches"] == 0
        assert (
            run(operation_case, rollback=True, admin_restore=lambda sql: c.execute(sql))["result"]
            == "ROLLED_BACK"
        )
        assert snapshot(c, m) == m["before"] and len(calls) == 4
        for pid, p in adapter.retrieve(list(m["qdrant"])).items():
            assert p["payload"] == m["qdrant"][pid]["payload"]
            assert vector_proof(p["vector"]) == m["qdrant"][pid]["vector_sha256"]
        assert (out / "confirmed.json").exists()
    finally:
        assert session.delete(base, timeout=10).ok


def test_pg_parent_lock_prevents_unmanifested_child_insert(operation_case):
    c, m, _, _, env, connection = operation_case
    with connection(env) as owner, owner.transaction():
        lock_and_validate(owner, m)
        with connection(env) as other, pytest.raises(psycopg.errors.LockNotAvailable):
            other.execute("SET lock_timeout='100ms'")
            other.execute(
                "INSERT INTO pisrs.act_text_blocks(version_id,text_id) VALUES (%s,1)",
                (m["targets"][0]["version_id"],),
            )
    assert snapshot(c, m) == m["before"]


def test_pg_boolean_numeric_payload_drift_is_not_equal(operation_case):
    _, m, q, _, _, _ = operation_case
    pid = next(iter(q.points))
    q.points[pid]["payload"]["is_active"] = int(q.points[pid]["payload"]["is_active"])
    with pytest.raises(PostgresInvariantError):
        run(operation_case)
    assert not q.calls


def test_launcher_seal_rejects_tampering_and_stages_exact_bytes(tmp_path):
    launch_spec = importlib.util.spec_from_file_location(
        "launch_act_link", Path(__file__).parents[1] / "ops/launch_act_link.py"
    )
    launch = importlib.util.module_from_spec(launch_spec)
    launch_spec.loader.exec_module(launch)
    package = tmp_path / "package"
    package.mkdir()
    content = b"closed test package\n"
    (package / "member").write_bytes(content)
    import hashlib

    sums = (hashlib.sha256(content).hexdigest() + "  member\n").encode()
    (package / "SHA256SUMS").write_bytes(sums)
    h = hashlib.sha256(sums).hexdigest()
    files = launch.verified_files(package, h)
    target = tmp_path / "stage"
    launch.stage(files, target)
    launch.stage(files, target)
    assert (target / "member").read_bytes() == content
    (package / "member").write_bytes(b"drift")
    with pytest.raises(ValueError):
        launch.verified_files(package, h)
    (target / "member").write_bytes(b"drift")
    with pytest.raises(ValueError):
        launch.stage(files, target)


@pytest.mark.parametrize("fault", ["port", "system_identifier", "can_set_replication_role"])
def test_recovery_broker_identity_guard_is_read_only(tmp_path, monkeypatch, fault):
    pinned = {
        "database": "appdb",
        "admin_role": "test_admin",
        "system_identifier": "123",
        "can_set_replication_role": True,
    }
    (tmp_path / "recovery-identity.json").write_text(json.dumps(pinned))
    monkeypatch.setattr(
        runner,
        "read_env",
        lambda *_: {
            "PISRS_PG_CONTAINER": "fixture",
            "PISRS_PG_USER": "test_admin",
            "PISRS_PG_DB": "appdb",
        },
    )
    commands = []

    def command(args, *, input=None):
        commands.append((args, input))
        if "inspect" in args:
            return json.dumps(
                {
                    "5432/tcp": [
                        {"HostIp": "127.0.0.1", "HostPort": "9999" if fault == "port" else "5432"}
                    ]
                }
            )
        assert "BEGIN READ ONLY" in input and "UPDATE" not in input and "SET ROLE" not in input
        value = {**pinned}
        if fault == "system_identifier":
            value[fault] = "wrong"
        if fault == "can_set_replication_role":
            value[fault] = False
        return json.dumps(value)

    monkeypatch.setattr(runner, "command", command)
    with pytest.raises(PostgresInvariantError):
        runner.recovery_context(tmp_path)
    assert commands


def test_pg_recovery_is_independent_of_admin_session_timezone(operation_case):
    c, m, _, _, _, _ = operation_case
    run(operation_case)
    c.execute("SET TIME ZONE 'Europe/Ljubljana'")
    try:
        assert (
            run(operation_case, rollback=True, admin_restore=lambda sql: c.execute(sql))["result"]
            == "ROLLED_BACK"
        )
        assert c.execute("SHOW timezone").fetchone()["TimeZone"] == "Europe/Ljubljana"
    finally:
        c.execute("SET TIME ZONE 'UTC'")
    assert snapshot(c, m) == m["before"]
