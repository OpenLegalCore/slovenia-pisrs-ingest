"""Opt-in integration test against an isolated socket-only PostgreSQL database."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from pisrs_ingest.checkpoint import CheckpointStore
from pisrs_ingest.models import Act, ExternalCatalogItem, parse_html
from pisrs_ingest.pipeline import run_nightly
from pisrs_ingest.postgres import CatalogStore, PostgresDatabase, PostgresInvariantError
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

    bad_eu = ExternalCatalogItem.from_raw({"celex": "32024R0002"}, "/predpis-eu", "EU")
    bad_local = ExternalCatalogItem.from_raw(
        {"id": 8, "mopedPlusId": "LS8", "sop": "abc-2026-8", "non_json": object()},
        "/akt-ls/veljavni-akti",
        "LS_ACT",
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


@pytest.mark.parametrize(
    "interrupt_after",
    ["external", "catalogs", "state_raw", "processing"],
)
def test_catalog_restart_between_commits_on_disposable_postgres(
    interrupt_after: str, tmp_path: Path
) -> None:
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
            "CREATE TABLE pisrs.acts ("
            "id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
            "register_id bigint UNIQUE, moped_id text, sop text, naziv text, "
            "kratica text, endpoint text, seen_in_endpoints text[], "
            "vrsta_akta_id bigint, vrsta_akta_naziv text, vrsta_akta jsonb, "
            "kazalo_pravnih_aktov jsonb, osnovni boolean, "
            "datum_sprejetja date, datum_objave date, datum_zacetka_veljavnosti date, "
            "datum_prenehanja_veljavnosti date, source_item jsonb, "
            "raw_register_json jsonb, sync_status text, "
            "unrelated text NOT NULL DEFAULT 'keep', updated_at timestamptz DEFAULT now())"
        )
        connection.execute(
            "CREATE TABLE pisrs.act_sync_catalog ("
            "register_id bigint UNIQUE, moped_id text, sop text, naziv text, "
            "kratica text, endpoint text, seen_in_endpoints text[], "
            "vrsta_akta_id bigint, vrsta_akta_naziv text, vrsta_akta jsonb, "
            "kazalo_pravnih_aktov jsonb, osnovni boolean, "
            "datum_sprejetja date, datum_objave date, datum_zacetka_veljavnosti date, "
            "datum_prenehanja_veljavnosti date, source_item jsonb, "
            "raw_register_json jsonb, status text DEFAULT 'pending', status_reason text, "
            "imported_at timestamptz, unrelated text NOT NULL DEFAULT 'keep', "
            "updated_at timestamptz DEFAULT now())"
        )
        connection.execute(
            "CREATE TABLE pisrs.npb_catalog (text_id bigint UNIQUE, naziv text, "
            "datum_dokumenta date, stevilka_dokumenta text, sop_from_docno text, "
            "npb_label text, raw_item jsonb, updated_at timestamptz DEFAULT now())"
        )
        connection.execute("CREATE TABLE pisrs.laws (register_id bigint, sop text, moped_id text)")
        if (
            connection.execute("SELECT 1 FROM pg_roles WHERE rolname = 'pisrs_ingest'").fetchone()
            is None
        ):
            connection.execute("CREATE ROLE pisrs_ingest LOGIN")
        connection.execute(Path("docs/sql/001_source_catalog_items.sql").read_text())

    database = PostgresDatabase(admin_dsn)
    actual_external = ExternalCatalogStore(database)
    actual_catalogs = CatalogStore(database)
    state = Act.from_raw(
        {"id": 1, "mopedId": "RS1", "naziv": "State"}, "/predpis/register-predpisov"
    )
    eu = ExternalCatalogItem.from_raw({"celex": "32024R0001"}, "/predpis-eu", "EU")
    local = ExternalCatalogItem.from_raw(
        {"id": 7, "mopedPlusId": "LS7", "sop": "abc-2026-1"},
        "/akt-ls/veljavni-akti",
        "LS_ACT",
    )
    local_npb = ExternalCatalogItem.from_raw(
        {"id": 9, "stevilkaDokumenta": "x-y-z-abc-2026-1-npb01"},
        "/npb-ls",
        "LS_NPB",
    )
    interrupted = False

    def after_commit(phase: str, operation, *args) -> None:
        nonlocal interrupted
        operation(*args)
        if phase == interrupt_after and not interrupted:
            interrupted = True
            raise RuntimeError(f"simulated interruption after {phase}")

    def validate_collection(_dimensions: int, _model: str) -> None:
        return None

    def no_embedding(_texts) -> None:
        raise AssertionError("catalog-only retry must not call embeddings")

    class Source:
        def discover_acts(self):
            return [state]

        def discover_npbs(self):
            return []

        def discover_eu_acts(self):
            return [eu]

        def discover_local_acts(self):
            return [local]

        def discover_local_npbs(self):
            return [local_npb]

    postgres = SimpleNamespace(
        external=SimpleNamespace(
            synchronize=lambda items: after_commit("external", actual_external.synchronize, items),
            synchronize_state_raw=lambda acts: after_commit(
                "state_raw", actual_external.synchronize_state_raw, acts
            ),
        ),
        catalogs=SimpleNamespace(
            synchronize=lambda acts, npbs: after_commit(
                "catalogs", actual_catalogs.synchronize, acts, npbs
            )
        ),
        documents=SimpleNamespace(pending=lambda _limit, _since: []),
        external_text=SimpleNamespace(pending=lambda _limit: []),
        chunks=SimpleNamespace(touched_sops=lambda _since: []),
    )
    checkpoint_path = tmp_path / "checkpoint.json"
    start = datetime(2026, 11, 6, tzinfo=UTC)
    end = datetime(2026, 11, 7, tzinfo=UTC)
    stored_checkpoint = CheckpointStore(checkpoint_path, start)

    def advance_checkpoint(value: datetime) -> None:
        nonlocal interrupted
        if interrupt_after == "processing" and not interrupted:
            interrupted = True
            raise RuntimeError("simulated interruption after processing")
        stored_checkpoint.advance(value)

    checkpoint = SimpleNamespace(interval=stored_checkpoint.interval, advance=advance_checkpoint)
    kwargs = dict(
        client=Source(),
        postgres=postgres,
        embedder=SimpleNamespace(embed=no_embedding),
        qdrant=SimpleNamespace(validate_collection=validate_collection),
        checkpoint=checkpoint,
        model="text-embedding-3-large",
        dimensions=3072,
        max_documents=1,
        embed_batch_size=1,
        max_embedding_input_bytes=1,
        now=end,
    )

    def snapshot() -> dict[str, list[tuple]]:
        with database.connect(read_only=True) as connection:
            return {
                "external": connection.execute(
                    "SELECT namespace, source_id, xmin::text, linked_act_source_id, "
                    "seen_in_endpoints, raw_by_endpoint "
                    "FROM pisrs.source_catalog_items ORDER BY namespace, source_id"
                ).fetchall(),
                "acts": connection.execute(
                    "SELECT register_id, xmin::text, unrelated, seen_in_endpoints, "
                    "source_item, raw_register_json FROM pisrs.acts ORDER BY register_id"
                ).fetchall(),
                "catalog": connection.execute(
                    "SELECT register_id, xmin::text, unrelated, seen_in_endpoints, "
                    "source_item, raw_register_json "
                    "FROM pisrs.act_sync_catalog ORDER BY register_id"
                ).fetchall(),
                "raw": connection.execute(
                    "SELECT register_id, endpoint, xmin::text, raw_item "
                    "FROM pisrs.state_raw_variants ORDER BY register_id, endpoint"
                ).fetchall(),
            }

    with pytest.raises(RuntimeError, match=f"after {interrupt_after}"):
        run_nightly(**kwargs)
    assert interrupted
    assert not checkpoint_path.exists()
    partial = snapshot()
    assert len(partial["external"]) == 3
    assert len(partial["acts"]) == (0 if interrupt_after == "external" else 1)
    assert len(partial["catalog"]) == len(partial["acts"])
    assert len(partial["raw"]) == (0 if interrupt_after in {"external", "catalogs"} else 1)

    stats = run_nightly(**kwargs)
    assert not stats.backlog_remaining
    assert stored_checkpoint.validate()["last_successful_end"] == "2026-11-07T00:00:00Z"
    complete = snapshot()
    assert [(row["namespace"], row["source_id"]) for row in complete["external"]] == [
        ("EU", "32024R0001"),
        ("LS_ACT", "7"),
        ("LS_NPB", "9"),
    ]
    assert complete["external"][-1]["linked_act_source_id"] == "7"
    assert complete["external"][-1]["raw_by_endpoint"]["/npb-ls"]["id"] == 9
    assert [row["register_id"] for row in complete["acts"]] == [1]
    assert [row["register_id"] for row in complete["catalog"]] == [1]
    assert [row["register_id"] for row in complete["raw"]] == [1]
    assert complete["raw"][0]["raw_item"]["mopedId"] == "RS1"
    assert complete["acts"][0]["unrelated"] == "keep"
    assert complete["catalog"][0]["unrelated"] == "keep"
    for table, rows in partial.items():
        assert complete[table][: len(rows)] == rows
