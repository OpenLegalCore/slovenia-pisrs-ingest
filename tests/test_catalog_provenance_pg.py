"""Opt-in: private recorded API replay and a disposable, socket-only PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import LockNotAvailable
from psycopg.types.json import Jsonb

from pisrs_ingest import catalog_provenance as operation
from pisrs_ingest import cli
from pisrs_ingest.catalog_provenance import CatalogScopeError, catalog_provenance
from pisrs_ingest.catalog_runtime import RuntimeGuard
from pisrs_ingest.client import PisrsClient
from pisrs_ingest.locking import ApplicationLock
from pisrs_ingest.postgres import ACT_CATALOG_UPSERT, ACTS_UPSERT, PostgresDatabase


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while b := f.read(1024 * 1024):
            h.update(b)
    return h.hexdigest()


class Replay:
    def __init__(self, root):
        self.root = root
        raw = (root / "SHA256SUMS").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == (
            "0de2d7da1cbeda2fbc998b66a9c86f6b34f29e1033fece23dfd6427fb609ce55"
        )
        self.hashes = {}
        for line in raw.decode().splitlines():
            h, name = line.split(None, 1)
            self.hashes[name.lstrip("* ")] = h
        self.pages = {}
        self.calls = 0
        for name in ["probe-requests.json", "catalogs-requests.json"]:
            assert digest(root / name) == self.hashes[name]
            for item in json.loads((root / name).read_text())["calls"]:
                if item["endpoint"] in PisrsClient.ACT_ENDPOINTS and item.get("status") == 200:
                    params = item["params"]
                    self.pages[item["endpoint"], params["page"], params["pageSize"]] = item

    def request(self, method, url, **kwargs):
        assert method == "GET"
        ep = urlsplit(url).path.removeprefix("/extapi")
        params = kwargs["params"]
        item = self.pages[ep, params["page"], params["pageSize"]]
        raw = (self.root / item["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"] == self.hashes[item["file"]]
        self.calls += 1
        payload = json.loads(raw)
        return type("Response", (), {"json": lambda _: payload})()


@pytest.fixture(scope="module")
def case():
    dsn = os.environ.get("PISRS_CATALOG_TEST_DSN")
    replay_root = os.environ.get("PISRS_CATALOG_REPLAY_ROOT")
    if not dsn or not replay_root:
        pytest.skip("requires private API replay and disposable catalog-test DSN")
    info = conninfo_to_dict(dsn)
    assert info["dbname"] == "pisrs_catalog_test"
    assert info.get("host", "").startswith("/tmp/pisrs-catalog-")
    database = PostgresDatabase(dsn)
    replay = Replay(Path(replay_root))
    client = PisrsClient("https://pisrs.si/extapi", "OFFLINE_FIXTURE", replay)
    acts = client.discover_acts()
    assert replay.calls == 134 and len(acts) == 65271
    fields = (
        "moped_id text,sop text,naziv text,kratica text,osnovni boolean,vrsta_akta_id bigint,"
        "vrsta_akta_naziv text,datum_sprejetja date,datum_objave date,"
        "datum_zacetka_veljavnosti date,datum_prenehanja_veljavnosti date"
    )
    with database.connect() as c:
        c.execute("CREATE SCHEMA pisrs")
        for table in operation.TABLES:
            c.execute(
                sql.SQL(
                    "CREATE TABLE pisrs.{} (id bigserial PRIMARY KEY,register_id bigint UNIQUE,"
                    + fields
                    + ",endpoint text,seen_in_endpoints text[],source_item jsonb,"
                    "raw_register_json jsonb,unrelated jsonb,status text DEFAULT 'keep-status',"
                    "vrsta_akta jsonb,kazalo_pravnih_aktov jsonb,"
                    "sync_status text DEFAULT 'metadata_only',"
                    "status_reason text,imported_at timestamptz,"
                    "updated_at timestamptz DEFAULT now())"
                ).format(sql.Identifier(table))
            )
            # Keep background maintenance out of deterministic lock-timeout tests.
            c.execute(
                sql.SQL("ALTER TABLE pisrs.{} SET (autovacuum_enabled=false)").format(
                    sql.Identifier(table)
                )
            )
        untouched = [
            "npb_catalog",
            "act_text_versions",
            "act_text_blocks",
            "embedding_chunks",
            "laws",
            "law_versions",
            "law_articles",
            "law_sync_catalog",
            "ingestion_runs",
        ]
        for table in untouched:
            c.execute(
                sql.SQL("CREATE TABLE pisrs.{} (id bigserial PRIMARY KEY,value text)").format(
                    sql.Identifier(table)
                )
            )
            c.execute(
                sql.SQL("INSERT INTO pisrs.{} (value) VALUES ('must remain unchanged')").format(
                    sql.Identifier(table)
                )
            )
        names = [
            "register_id",
            *operation.METADATA,
            "endpoint",
            "seen_in_endpoints",
            "source_item",
            "raw_register_json",
            "unrelated",
        ]
        statement = sql.SQL("INSERT INTO pisrs.{} ({}) VALUES ({})")
        values = []
        for a in acts:
            seen = [e for e in a.seen_in_endpoints if e in operation.ENDPOINTS[:4]]
            assert seen
            # Real source identities/normalized fields, synthetic unrelated metadata.
            raw = {"unchanged_order": [2, 1], "text": "unrelated metadata"}
            envelope = {
                **a.provenance(),
                "seen_in_endpoints": seen,
                "raw": raw,
                "extra_provenance": {"retain": [3, 1, 2]},
            }
            values.append(
                (
                    a.register_id,
                    *(getattr(a, k) for k in operation.METADATA),
                    seen[0],
                    seen,
                    Jsonb(envelope),
                    Jsonb(raw),
                    Jsonb({"keep": True}),
                )
            )
        with c.cursor() as cur:
            for table in operation.TABLES:
                cur.executemany(
                    statement.format(
                        sql.Identifier(table),
                        sql.SQL(",").join(map(sql.Identifier, names)),
                        sql.SQL(",").join(sql.Placeholder() for _ in names),
                    ),
                    values,
                )
    return database, acts, replay, untouched


def snapshot(database):
    tables = {}
    with database.connect(read_only=True) as c:
        names = c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='pisrs' ORDER BY tablename"
        ).fetchall()
        for item in names:
            name = item["tablename"]
            tables[name] = c.execute(
                sql.SQL(
                    "SELECT count(*) AS rows,"
                    "md5(string_agg(md5(to_jsonb(t)::text),'' ORDER BY id)) "
                    "AS hash FROM pisrs.{} t"
                ).format(sql.Identifier(name))
            ).fetchone()
        sequences = c.execute(
            "SELECT sequencename,last_value FROM pg_sequences "
            "WHERE schemaname='pisrs' ORDER BY sequencename"
        ).fetchall()
    return tables, sequences


def protected(database):
    with database.connect(read_only=True) as c:
        return {
            table: c.execute(
                sql.SQL(
                    "SELECT md5(string_agg(md5((to_jsonb(t)-'seen_in_endpoints'-'source_item'-"
                    "'updated_at')::text)||md5((source_item-'seen_in_endpoints')::text),"
                    "'' ORDER BY id)) "
                    "AS hash FROM pisrs.{} t"
                ).format(sql.Identifier(table))
            ).fetchone()
            for table in operation.TABLES
        }


def test_full_recorded_scope_atomicity_idempotency_and_cli_boundary(
    case, monkeypatch, tmp_path, capsys
):
    database, acts, replay, untouched = case
    # Identity verification itself is covered by the dedicated isolated guard tests.
    guard = RuntimeGuard(SimpleNamespace(database_dsn=database.dsn), object(), object())
    monkeypatch.setattr(RuntimeGuard, "verify", lambda *_: None)
    monkeypatch.setattr(cli, "verify_runtime", lambda *_: object())
    monkeypatch.setattr(cli, "verify_lock", lambda *_: None)
    monkeypatch.setattr(cli, "CatalogApplicationLock", ApplicationLock)
    before, sequences_before = snapshot(database)
    protected_before = protected(database)
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_bytes(b"checkpoint must remain unchanged")
    plan = catalog_provenance(database, acts, "pisrs_catalog_test")
    assert plan.identities == 65271
    assert {t: len(v) for t, v in plan.changes.items()} == {t: 31760 for t in operation.TABLES}
    assert sum(plan.links_added.values()) == 31760
    assert snapshot(database) == (before, sequences_before)

    with pytest.raises(CatalogScopeError, match="no longer matches"):
        catalog_provenance(
            database,
            acts,
            "pisrs_catalog_test",
            apply=True,
            runtime_guard=guard,
            expected_plan="0" * 64,
        )
    assert snapshot(database) == (before, sequences_before)
    with pytest.raises(CatalogScopeError, match="empty"):
        catalog_provenance(
            database,
            [],
            "pisrs_catalog_test",
            apply=True,
            runtime_guard=guard,
            expected_plan=plan.sha256,
        )
    with pytest.raises(CatalogScopeError, match="identity sets"):
        catalog_provenance(database, acts[:-1], "pisrs_catalog_test")

    with database.connect() as blocker:
        blocker.execute("LOCK TABLE pisrs.acts IN ROW EXCLUSIVE MODE")
        with pytest.raises(LockNotAvailable):
            catalog_provenance(
                database,
                acts,
                "pisrs_catalog_test",
                apply=True,
                runtime_guard=guard,
                expected_plan=plan.sha256,
            )
    assert snapshot(database) == (before, sequences_before)

    original_read = operation._read
    count = 0

    def corrupt_postflight(cursor):
        nonlocal count
        rows = original_read(cursor)
        count += 1
        if count == 2:
            rows["acts"][0]["other_hash"] = "simulated postflight drift"
        return rows

    monkeypatch.setattr(operation, "_read", corrupt_postflight)
    with pytest.raises(CatalogScopeError, match="rolling back"):
        catalog_provenance(
            database,
            acts,
            "pisrs_catalog_test",
            apply=True,
            runtime_guard=guard,
            expected_plan=plan.sha256,
        )
    monkeypatch.setattr(operation, "_read", original_read)
    assert snapshot(database) == (before, sequences_before)

    # Unrelated row drift between approval and apply is caught by the full-row plan hash.
    with database.connect() as c:
        c.execute(
            "UPDATE pisrs.acts SET unrelated='{}' WHERE register_id=%s", (acts[0].register_id,)
        )
    drifted = snapshot(database)
    with pytest.raises(CatalogScopeError, match="no longer matches"):
        catalog_provenance(
            database,
            acts,
            "pisrs_catalog_test",
            apply=True,
            runtime_guard=guard,
            expected_plan=plan.sha256,
        )
    assert snapshot(database) == drifted
    with database.connect() as c:
        c.execute(
            "UPDATE pisrs.acts SET unrelated=%s WHERE register_id=%s",
            (Jsonb({"keep": True}), acts[0].register_id),
        )
    assert snapshot(database) == (before, sequences_before)

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden stage or external call")

    monkeypatch.setattr(
        cli,
        "PisrsClient",
        lambda *a: PisrsClient("https://pisrs.si/extapi", "OFFLINE_FIXTURE", replay),
    )
    for name in [
        "QdrantStore",
        "EmbeddingClient",
        "CheckpointStore",
        "PostgresBoundary",
        "run_nightly",
    ]:
        monkeypatch.setattr(cli, name, forbidden)
    env = {
        "PISRS_DATABASE_DSN": os.environ["PISRS_CATALOG_TEST_URI"],
        "PISRS_EXPECTED_DATABASE": "pisrs_catalog_test",
        "PISRS_QDRANT_URL": "http://127.0.0.1:1",
        "PISRS_QDRANT_COLLECTION": "pisrs_current",
        "PISRS_RECONCILE_MAX_CHANGES": "1",
        "PISRS_LOCK_PATH": str(tmp_path / "app.lock"),
        "PISRS_ALLOW_EXTERNAL_API": "1",
        "PISRS_ALLOW_WRITES": "0",
        "PISRS_PORTAL_BASE_URL": "https://pisrs.si/extapi",
        "PISRS_API_TOKEN": "OFFLINE_FIXTURE",
    }
    assert cli.main(["catalog-sync"], env) == 0
    dry = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert dry["plan_sha256"] == plan.sha256
    env["PISRS_ALLOW_WRITES"] = "1"
    assert (
        cli.main(
            [
                "catalog-sync",
                "--apply",
                "--expect-plan",
                plan.sha256,
                "--confirm-active-catalog-code",
            ],
            env,
        )
        == 0
    )
    output = capsys.readouterr().out.strip().splitlines()
    assert json.loads(output[0])["phase"] == "before_write"
    assert json.loads(output[-1])["applied_rows"] == 63520
    after, sequences_after = snapshot(database)
    assert protected(database) == protected_before
    assert all(after[t] == before[t] for t in untouched)
    assert all(after[t]["rows"] == 65271 for t in operation.TABLES)
    assert sequences_after == sequences_before
    assert checkpoint.read_bytes() == b"checkpoint must remain unchanged"

    again = catalog_provenance(database, acts, "pisrs_catalog_test")
    assert not any(again.changes.values())
    catalog_provenance(
        database,
        acts,
        "pisrs_catalog_test",
        apply=True,
        runtime_guard=guard,
        expected_plan=again.sha256,
    )
    assert snapshot(database) == (after, sequences_after)
    with pytest.raises(CatalogScopeError, match="no longer matches"):
        catalog_provenance(
            database,
            acts,
            "pisrs_catalog_test",
            apply=True,
            runtime_guard=guard,
            expected_plan=plan.sha256,
        )

    # Demonstrate why the active-code acknowledgment is necessary, using the old SQL.
    old_act = next(
        a for a in acts if any(e in operation.ADDITIONAL_ENDPOINTS for e in a.seen_in_endpoints)
    )
    from dataclasses import replace

    from pisrs_ingest.postgres import CatalogStore

    old_act = replace(
        old_act,
        seen_in_endpoints=tuple(
            e for e in old_act.seen_in_endpoints if e in operation.ENDPOINTS[:4]
        ),
    )
    params = CatalogStore._act_parameters(old_act)
    with database.connect() as c:
        c.execute(ACTS_UPSERT, params)
        c.execute(ACT_CATALOG_UPSERT, params)
        seen = c.execute(
            "SELECT seen_in_endpoints FROM pisrs.acts WHERE register_id=%s", (old_act.register_id,)
        ).fetchone()["seen_in_endpoints"]
        assert seen == list(old_act.seen_in_endpoints)
        c.rollback()  # Do not retain this destructive old-code demonstration in the fixture.

    report_path = os.environ.get("PISRS_CATALOG_TEST_REPORT")
    if report_path:
        report = {
            "identities": plan.identities,
            "links_added_per_table": sum(plan.links_added.values()),
            "updated_rows_per_table": dry["rows_to_update"],
            "total_updated_rows": json.loads(output[-1])["applied_rows"],
            "other_tables_unchanged": {t: after[t] == before[t] for t in untouched},
            "unrelated_columns_and_raw_json_unchanged": protected_before == protected(database),
            "sequences_before": sequences_before,
            "sequences_after_new_command": sequences_after,
            "sequence_delta_new_command": 0,
            "checkpoint_unchanged": checkpoint.read_bytes() == b"checkpoint must remain unchanged",
            "second_apply_row_and_timestamp_changes": 0,
            "wrong_plan_rejected": True,
            "postflight_failure_rolled_back": True,
            "row_drift_rejected": True,
            "old_upserts_remove_added_provenance": True,
            "old_upsert_demo_is_separate_and_consumes_sequence_values_even_on_rollback": True,
            "production_access": False,
        }
        with Path(report_path).open("x") as f:
            json.dump(report, f, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())


def test_unreviewed_trigger_is_blocked_before_writes(case):
    database, acts, _, _ = case
    with database.connect() as c:
        c.execute(
            "CREATE FUNCTION pisrs.bad_trigger() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN UPDATE pisrs.npb_catalog SET value='forbidden';RETURN NEW;END $$"
        )
        c.execute(
            "CREATE TRIGGER bad BEFORE UPDATE ON pisrs.acts "
            "FOR EACH ROW EXECUTE FUNCTION pisrs.bad_trigger()"
        )
    before = snapshot(database)
    try:
        with pytest.raises(CatalogScopeError, match="triggers or rules"):
            catalog_provenance(database, acts, "pisrs_catalog_test")
        assert snapshot(database) == before
    finally:
        with database.connect() as c:
            c.execute("DROP TRIGGER bad ON pisrs.acts")
            c.execute("DROP FUNCTION pisrs.bad_trigger()")
