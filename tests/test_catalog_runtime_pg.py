"""Opt-in small disposable PostgreSQL test for identity checks and rollback ordering."""

from __future__ import annotations

import hashlib
import os

import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
from test_catalog_provenance import acts
from test_catalog_runtime import identified  # noqa: F401

from pisrs_ingest import catalog_runtime as runtime
from pisrs_ingest.catalog_provenance import METADATA, TABLES, catalog_provenance
from pisrs_ingest.catalog_runtime import CatalogApplicationLock, RuntimeGuard, RuntimeProofError
from pisrs_ingest.postgres import PostgresDatabase


def test_runtime_recheck_rolls_back_and_unchanged_plan_applies(monkeypatch, request):
    dsn = os.environ.get("PISRS_CATALOG_TEST_DSN")
    if not dsn:
        pytest.skip("requires a disposable isolated PostgreSQL fixture")
    fixture_data = request.getfixturevalue("identified")
    info = conninfo_to_dict(dsn)
    assert info["dbname"] == "pisrs_catalog_test"
    assert info.get("host", "").startswith("/tmp/pisrs-catalog-")
    database = PostgresDatabase(dsn)
    source = acts()
    fields = (
        "moped_id text,sop text,naziv text,kratica text,osnovni boolean,"
        "vrsta_akta_id bigint,vrsta_akta_naziv text,datum_sprejetja date,datum_objave date,"
        "datum_zacetka_veljavnosti date,datum_prenehanja_veljavnosti date"
    )
    with database.connect() as conn:
        conn.execute("CREATE SCHEMA pisrs")
        for table in TABLES:
            conn.execute(
                sql.SQL(
                    "CREATE TABLE pisrs.{} (id bigserial PRIMARY KEY,register_id bigint UNIQUE,"
                    + fields
                    + ",endpoint text,seen_in_endpoints text[],source_item jsonb,"
                    "other jsonb,updated_at timestamptz DEFAULT now())"
                ).format(sql.Identifier(table))
            )
            for act in source:
                old = [e for e in act.seen_in_endpoints if e in runtime_endpoints()[:4]]
                envelope = {**act.provenance(), "seen_in_endpoints": old, "extra": "keep"}
                names = [
                    "register_id",
                    *METADATA,
                    "endpoint",
                    "seen_in_endpoints",
                    "source_item",
                    "other",
                ]
                values = [
                    act.register_id,
                    *(getattr(act, k) for k in METADATA),
                    old[0],
                    old,
                    Jsonb(envelope),
                    Jsonb({"keep": True}),
                ]
                conn.execute(
                    sql.SQL("INSERT INTO pisrs.{} ({}) VALUES ({})").format(
                        sql.Identifier(table),
                        sql.SQL(",").join(map(sql.Identifier, names)),
                        sql.SQL(",").join(sql.Placeholder() for _ in names),
                    ),
                    values,
                )
        conn.execute("CREATE TABLE pisrs.sentinel (value text)")
        conn.execute("INSERT INTO pisrs.sentinel VALUES ('unchanged')")
    before = snapshot(database)
    plan = catalog_provenance(database, source, "pisrs_catalog_test")
    assert {t: len(c) for t, c in plan.changes.items()} == {t: 3 for t in TABLES}
    fixture_data.settings.database_dsn = dsn
    fixture_data.settings.expected_database = "pisrs_catalog_test"
    fixture_data.env_file.write_text(
        f"PISRS_DATABASE_DSN='{dsn}'\nPISRS_EXPECTED_DATABASE=pisrs_catalog_test\n"
        f"PISRS_LOCK_PATH={fixture_data.lock}\n"
    )
    monkeypatch.setattr(runtime, "DATABASE_NAME", "pisrs_catalog_test")

    def test_socket_target(value):
        parsed = conninfo_to_dict(value)
        assert parsed["dbname"] == "pisrs_catalog_test" and parsed["host"] == info["host"]

    def test_socket_connection(connection, value, expected_server_id):
        test_socket_target(value)
        assert connection.info.dbname == "pisrs_catalog_test"
        assert connection.info.host == info["host"]
        row = connection.execute(
            "SELECT system_identifier::text AS server_id FROM pg_control_system()"
        ).fetchone()
        assert row["server_id"] == expected_server_id

    monkeypatch.setattr(runtime, "_server", test_socket_target)
    monkeypatch.setattr(runtime, "verify_connection", test_socket_connection)
    with database.connect(read_only=True) as conn:
        server_id = conn.execute(
            "SELECT system_identifier::text AS server_id FROM pg_control_system()"
        ).fetchone()["server_id"]
    monkeypatch.setattr(
        runtime, "APPROVED_CONTAINER_SHA256", hashlib.sha256(b"test-container").hexdigest()
    )
    monkeypatch.setattr(
        runtime, "APPROVED_CLUSTER_SHA256", hashlib.sha256(server_id.encode()).hexdigest()
    )
    calls = []

    def container_changed_before_commit():
        calls.append(1)
        return ("changed-container" if len(calls) == 4 else "test-container", server_id)

    monkeypatch.setattr(runtime, "_container_server_identity", container_changed_before_commit)
    with CatalogApplicationLock(fixture_data.lock) as lock:
        guard = RuntimeGuard(
            fixture_data.settings, lock, runtime.verify_runtime(fixture_data.settings)
        )
        with pytest.raises(RuntimeProofError, match="identity|changed"):
            catalog_provenance(
                database,
                source,
                "pisrs_catalog_test",
                apply=True,
                expected_plan=plan.sha256,
                runtime_guard=guard,
            )
    assert len(calls) == 4 and snapshot(database) == before
    monkeypatch.setattr(
        runtime, "_container_server_identity", lambda: ("test-container", server_id)
    )
    with CatalogApplicationLock(fixture_data.lock) as lock:
        guard = RuntimeGuard(
            fixture_data.settings, lock, runtime.verify_runtime(fixture_data.settings)
        )
        catalog_provenance(
            database,
            source,
            "pisrs_catalog_test",
            apply=True,
            expected_plan=plan.sha256,
            runtime_guard=guard,
        )
        after = snapshot(database)
        assert after["sentinel"] == before["sentinel"]
        again = catalog_provenance(database, source, "pisrs_catalog_test")
        assert not any(again.changes.values())
        catalog_provenance(
            database,
            source,
            "pisrs_catalog_test",
            apply=True,
            expected_plan=again.sha256,
            runtime_guard=guard,
        )
        assert snapshot(database) == after


def runtime_endpoints():
    from pisrs_ingest.client import PisrsClient

    return PisrsClient.ACT_ENDPOINTS


def snapshot(database):
    with database.connect(read_only=True) as conn:
        return {
            table: conn.execute(
                sql.SQL("SELECT jsonb_agg(to_jsonb(t) ORDER BY id) AS rows FROM pisrs.{} t").format(
                    sql.Identifier(table)
                )
            ).fetchone()
            for table in (*TABLES,)
        } | {"sentinel": conn.execute("SELECT value FROM pisrs.sentinel").fetchone()}
