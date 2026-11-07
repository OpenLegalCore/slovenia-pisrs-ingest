"""Opt-in integration test against an isolated socket-only PostgreSQL database."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from pisrs_ingest.models import Act, ExternalCatalogItem, parse_html
from pisrs_ingest.postgres import PostgresDatabase, PostgresInvariantError
from pisrs_ingest.postgres_documents import DocumentStore
from pisrs_ingest.postgres_external import ExternalCatalogStore
from pisrs_ingest.postgres_external_text import ExternalTextStore


def test_extended_catalog_and_text_roundtrip_on_disposable_postgres() -> None:
    admin_dsn = os.environ.get("PISRS_EXTENDED_TEST_DSN")
    if not admin_dsn:
        pytest.skip("requires an isolated, disposable PostgreSQL socket")
    identity = conninfo_to_dict(admin_dsn)
    assert identity["dbname"] == "pisrs_catalog_test"
    assert identity["host"].startswith("/tmp/pisrs-f1f2-pg-socket-")
    assert identity["user"] == "postgres"
    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS pisrs CASCADE")
        connection.execute("CREATE SCHEMA pisrs")
        connection.execute(
            "CREATE TABLE pisrs.acts (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
            "register_id bigint UNIQUE NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE pisrs.npb_catalog (text_id bigint UNIQUE, naziv text, "
            "datum_dokumenta date, stevilka_dokumenta text, sop_from_docno text, "
            "npb_label text, raw_item jsonb, status text, status_reason text, "
            "last_attempt_at timestamptz, last_error text, imported_at timestamptz, "
            "updated_at timestamptz NOT NULL DEFAULT now())"
        )
        connection.execute(
            "CREATE TABLE pisrs.act_text_versions (id bigint GENERATED ALWAYS AS IDENTITY, "
            "text_id bigint UNIQUE, imported_at timestamptz)"
        )
        if (
            connection.execute("SELECT 1 FROM pg_roles WHERE rolname = 'pisrs_ingest'").fetchone()
            is None
        ):
            connection.execute("CREATE ROLE pisrs_ingest LOGIN")
        connection.execute("GRANT USAGE ON SCHEMA pisrs TO pisrs_ingest")
        connection.execute("GRANT SELECT, UPDATE ON pisrs.npb_catalog TO pisrs_ingest")
        connection.execute("GRANT SELECT ON pisrs.act_text_versions TO pisrs_ingest")
        connection.execute(Path("docs/sql/001_source_catalog_items.sql").read_text())
        connection.execute("INSERT INTO pisrs.acts (register_id) VALUES (1)")

    role_dsn = f"host={identity['host']} dbname=pisrs_catalog_test user=pisrs_ingest"
    database = PostgresDatabase(role_dsn)
    store = ExternalCatalogStore(database)
    state = Act.from_raw(
        {"id": 1, "mopedId": "RS1", "naziv": "State"},
        "/predpis/register-predpisov",
    )
    store.synchronize_state_raw([state])
    eu = ExternalCatalogItem.from_raw({"celex": "32024R0001", "naziv": "EU"}, "/predpis-eu", "EU")
    local = ExternalCatalogItem.from_raw(
        {"id": 7, "mopedPlusId": "LS7", "sop": "abc-2026-1"},
        "/akt-ls/veljavni-akti",
        "LS_ACT",
    )
    npb = ExternalCatalogItem.from_raw(
        {"id": 9, "stevilkaDokumenta": "x-y-z-abc-2026-1-npb01"},
        "/npb-ls",
        "LS_NPB",
    )
    store.synchronize([eu, local, npb])
    with database.connect(read_only=True) as connection:
        before = connection.execute(
            "SELECT namespace, source_id, xmin::text AS version, link_status, "
            "linked_act_source_id FROM pisrs.source_catalog_items ORDER BY namespace"
        ).fetchall()
        raw_before = connection.execute(
            "SELECT xmin::text AS version FROM pisrs.state_raw_variants"
        ).fetchone()["version"]
    assert len(before) == 3
    assert (
        next(row for row in before if row["namespace"] == "LS_NPB")["linked_act_source_id"] == "7"
    )
    store.synchronize_state_raw([state])
    store.synchronize([eu, local, npb])
    with database.connect(read_only=True) as connection:
        assert (
            connection.execute(
                "SELECT namespace, source_id, xmin::text AS version, link_status, "
                "linked_act_source_id FROM pisrs.source_catalog_items ORDER BY namespace"
            ).fetchall()
            == before
        )
        assert (
            connection.execute(
                "SELECT xmin::text AS version FROM pisrs.state_raw_variants"
            ).fetchone()["version"]
            == raw_before
        )

    second_local = ExternalCatalogItem.from_raw(
        {"id": 8, "mopedPlusId": "LS8", "sop": "abc-2026-1"},
        "/akt-ls/veljavni-akti",
        "LS_ACT",
    )
    with pytest.raises(PostgresInvariantError, match="previous local NPB act link changed"):
        store.synchronize([eu, local, second_local, npb])
    with database.connect(read_only=True) as connection:
        assert (
            connection.execute("SELECT count(*) AS n FROM pisrs.source_catalog_items").fetchone()[
                "n"
            ]
            == 3
        )

    bad_eu = ExternalCatalogItem.from_raw(
        {"celex": "32024R0002"}, "/predpis-eu", "EU"
    )
    bad_local = ExternalCatalogItem.from_raw(
        {"id": 8, "mopedPlusId": "LS8", "sop": "abc-2026-8", "non_json": object()},
        "/akt-ls/veljavni-akti", "LS_ACT",
    )
    with pytest.raises(TypeError, match="JSON serializable"):
        store.synchronize([eu, bad_eu, local, bad_local, npb])
    with database.connect(read_only=True) as connection:
        assert (
            connection.execute("SELECT count(*) AS n FROM pisrs.source_catalog_items").fetchone()[
                "n"
            ]
            == 3
        )

    texts = ExternalTextStore(database)
    pending = texts.pending(2)
    assert [item.text_id for item in pending] == [9]
    parsed = parse_html("<html><body><p>Local text.</p></body></html>")
    texts.synchronize(pending[0], parsed, "https://example.invalid/besedilo/9")
    with database.connect(read_only=True) as connection:
        row = connection.execute(
            "SELECT status, html, blocks FROM pisrs.source_text_versions"
        ).fetchone()
        assert row["status"] == "imported"
        assert row["html"] == parsed.html
        assert len(row["blocks"]) == len(parsed.blocks)
    assert texts.pending(2) == []
    missing = ExternalCatalogItem.from_raw(
        {"id": 10, "stevilkaDokumenta": "bad number"}, "/npb-ls", "LS_NPB"
    )
    store.synchronize([eu, local, npb, missing])
    missing_pending = texts.pending(2)
    assert [item.text_id for item in missing_pending] == [10]
    texts.record_unavailable(missing_pending[0], "https://example.invalid/besedilo/10")
    with database.connect(read_only=True) as connection:
        unavailable = connection.execute(
            "SELECT status, last_attempt_reason, html FROM pisrs.source_text_versions "
            "WHERE source_id = '10'"
        ).fetchone()
        assert unavailable == {
            "status": "not_available",
            "last_attempt_reason": "NOT_AVAILABLE_FROM_API:HTTP_404",
            "html": None,
        }
    assert texts.pending(2) == []
    with psycopg.connect(admin_dsn) as connection:
        connection.execute(
            "INSERT INTO pisrs.npb_catalog "
            "(text_id, sop_from_docno, npb_label, raw_item, status, updated_at, last_attempt_at) "
            "VALUES (1, 'abc-2026-1', 'npb01', '{\"id\":1}', 'pending', now(), NULL), "
            "(2, 'abc-2026-2', 'npb01', '{\"id\":2}', 'imported', "
            "now() - interval '1 hour', NULL), "
            "(3, 'abc-2026-3', 'npb01', '{\"id\":3}', 'skipped_no_text', "
            "now(), now())"
        )
        connection.execute(
            "INSERT INTO pisrs.act_text_versions (text_id, imported_at) VALUES (2, now())"
        )
    documents = DocumentStore(database)
    since = datetime(2026, 11, 6, tzinfo=UTC)
    assert [item.text_id for item in documents.pending(10, since)] == [1]
    documents.record_unavailable(documents.pending(10, since)[0])
    assert documents.pending(10, since) == []
    with psycopg.connect(admin_dsn) as connection:
        connection.execute(
            "UPDATE pisrs.npb_catalog SET last_attempt_at = now() - interval '2 days' "
            "WHERE text_id = 3"
        )
    assert [item.text_id for item in documents.pending(10, since)] == [3]
    with psycopg.connect(admin_dsn) as connection:
        connection.execute("INSERT INTO pisrs.npb_catalog (text_id) VALUES (9)")
    with pytest.raises(PostgresInvariantError, match="collide"):
        texts.pending(2)
