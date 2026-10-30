from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from psycopg.types.json import Jsonb
from test_core import FakeCheckpoint, FakeClient, FakeEmbedder, FakeQdrant, nightly_env, vector_row

from pisrs_ingest import cli
from pisrs_ingest.config import ConfigError, load_settings, validate_runtime_paths
from pisrs_ingest.models import MANAGED_PAYLOAD_KEYS, Block, VectorRow, make_chunks
from pisrs_ingest.pipeline import PipelineError, plan_reconciliation, run_nightly
from pisrs_ingest.postgres import (
    ACT_STATUS_RECONCILIATION,
    PostgresDatabase,
    PostgresInvariantError,
)
from pisrs_ingest.postgres_chunks import ChunkStore
from pisrs_ingest.postgres_documents import DocumentStore
from pisrs_ingest.postgres_integrity import refresh_stored_payloads, repair_act_links


def test_manual_preflight_defers_only_missing_lock_directory(tmp_path, monkeypatch, capsys):
    env = nightly_env(tmp_path)
    missing = tmp_path / "absent-systemd-runtime"
    env["PISRS_LOCK_PATH"] = str(missing / "ingest.lock")
    settings = load_settings("preflight", env)
    before = list(tmp_path.iterdir())
    with pytest.raises(ConfigError, match="lock parent directory"):
        validate_runtime_paths(settings)
    monkeypatch.setattr(
        cli.PostgresBoundary,
        "create",
        lambda *a: SimpleNamespace(
            database=SimpleNamespace(preflight=lambda *a, **k: {"read_only": True})
        ),
    )
    monkeypatch.setattr(
        cli,
        "QdrantStore",
        lambda *a: SimpleNamespace(
            validate_collection=lambda *a: {"status": "green", "points_count": 2}
        ),
    )
    monkeypatch.setattr(cli, "PisrsClient", lambda *a: pytest.fail("external probe"))
    assert cli.main(["preflight", "--manual"], env) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["paths"] == {"lock": "deferred_missing_parent", "checkpoint": "ok"}
    assert result["runtime_ready"] is False
    assert result["writes"] == result["embedding_calls"] == 0
    assert result["pisrs"] == "skipped_by_policy"
    assert not missing.exists() and list(tmp_path.iterdir()) == before
    with pytest.raises(ConfigError, match="checkpoint parent directory"):
        validate_runtime_paths(
            replace(settings, checkpoint_path=missing / "checkpoint.json"),
            allow_missing_lock_parent=True,
        )
    assert cli.main(["preflight", "--manual"], {**env, "PISRS_ALLOW_WRITES": "1"}) == 2


@pytest.fixture
def pg():
    dsn = os.environ.get("PISRS_OLC85_TEST_DSN")
    if not dsn:
        pytest.skip("explicit isolated PostgreSQL fixture not configured")
    database = PostgresDatabase(dsn)
    with database.connect() as c:
        assert c.execute("SELECT current_database() AS name").fetchone()["name"] == "olc85_fixture"
        c.execute("DROP SCHEMA IF EXISTS pisrs CASCADE")
        c.execute(Path(__file__).with_name("olc85_fixture.sql").read_text())
    return database


def seed(
    pg, *, active: bool = True, text_id: int = 101, act_id=None, stored=None, automatic=False
) -> VectorRow:
    raw_text = f"fixture text {text_id}"
    block = Block(1, "p", ("odstavek",), raw_text, "paragraph", None, None)
    chunk = make_chunks((block,))[0]
    row = replace(
        vector_row(active=active, latest=active, text_id=text_id),
        act_id=act_id,
        chunk_text=chunk.chunk_text,
        chunk_text_len=len(chunk.chunk_text),
        content_hash=chunk.content_hash,
        token_estimate=chunk.token_estimate,
    )
    if stored is None:
        stored = {
            "source": "pisrs",
            "act_id": act_id,
            "is_latest_for_sop": True,
            "legacy_provenance": {"batch": "fixture", "nested": [1, 2]},
        }
    with pg.connect() as c:
        c.execute(
            "INSERT INTO pisrs.npb_catalog(id,text_id,sop_from_docno,npb_label) "
            "VALUES (%s,%s,%s,%s)",
            (row.text_id, row.text_id, row.sop_from_docno, row.npb_label),
        )
        c.execute(
            "INSERT INTO pisrs.act_text_versions(id,act_id,text_id,sop,sop_from_docno,"
            "npb_label,naziv,title,raw_meta) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                row.version_id,
                row.act_id,
                row.text_id,
                row.sop,
                row.sop_from_docno,
                row.npb_label,
                row.naziv,
                row.title,
                Jsonb({"automatic_act_link_repair": True} if automatic else {}),
            ),
        )
        c.execute(
            "INSERT INTO pisrs.act_text_blocks(version_id,act_id,text_id,block_index,"
            "block_type,text) VALUES (%s,%s,%s,1,'paragraph',%s)",
            (row.version_id, row.act_id, row.text_id, raw_text),
        )
        values = {
            k: getattr(row, k)
            for k in row.__dataclass_fields__
            if k not in ("database_id", "point_id")
        }
        values.update(qdrant_point_id=row.point_id, payload=Jsonb(stored))
        cols = list(values)
        c.execute(
            "INSERT INTO pisrs.embedding_chunks("
            + ",".join(cols)
            + ") VALUES ("
            + ",".join(["%s"] * len(cols))
            + ")",
            tuple(values.values()),
        )
    return row


def add_act(pg, *, id=10, register_id=10, sop="SOP-1"):
    with pg.connect() as c:
        c.execute(
            "INSERT INTO pisrs.acts(id,register_id,sop) VALUES (%s,%s,%s)", (id, register_id, sop)
        )


def snapshot(pg):
    with pg.connect(read_only=True) as c:
        return c.execute(
            "SELECT id,act_id,qdrant_point_id,content_hash,chunk_text,"
            "qdrant_status,payload,updated_at FROM pisrs.embedding_chunks "
            "ORDER BY id"
        ).fetchall()


def test_late_act_is_not_pending_but_repair_is_atomic_and_idempotent(pg):
    old = seed(pg, active=False)
    new = seed(pg, text_id=102)
    assert DocumentStore(pg).pending(3, datetime(2026, 2, 1, tzinfo=UTC)) == []
    add_act(pg)
    assert DocumentStore(pg).pending(3, datetime(2026, 2, 1, tzinfo=UTC)) == []
    before = snapshot(pg)
    stats = repair_act_links(pg, "pisrs_current", 2, approved_targets={201: 10, 202: 10})
    assert (stats.versions, stats.blocks, stats.chunks) == (2, 2, 2)
    after = snapshot(pg)
    for a, b, row in zip(after, before, [old, new], strict=True):
        assert a["act_id"] == 10 and a["qdrant_status"] == "payload_pending"
        assert a["payload"] == {**b["payload"], **replace(row, act_id=10).payload()}
        assert a["qdrant_point_id"] == b["qdrant_point_id"]
        assert a["content_hash"] == b["content_hash"] and a["chunk_text"] == b["chunk_text"]
    assert (
        repair_act_links(pg, "pisrs_current", 2, approved_targets={201: 10, 202: 10}).versions == 0
    )
    assert snapshot(pg) == after
    with pg.connect(read_only=True) as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM pisrs.act_text_blocks WHERE act_id IS DISTINCT FROM 10"
            ).fetchone()["n"]
            == 0
        )


def test_ambiguous_sop_is_skipped_and_proven_link_preserved(pg):
    add_act(pg)
    add_act(pg, id=11, register_id=11)
    seed(pg)
    seed(pg, text_id=102, act_id=11)
    stats = repair_act_links(pg, "pisrs_current", 10)
    assert stats.versions == 0 and stats.ambiguous == 1
    assert [r["act_id"] for r in snapshot(pg)] == [None, 11]


def test_empty_sop_never_supplies_an_identity(pg):
    seed(pg)
    add_act(pg, sop="")
    with pg.connect() as c:
        c.execute("UPDATE pisrs.act_text_versions SET sop_from_docno='' ")
    stats = repair_act_links(pg, "pisrs_current", 10)
    assert stats.versions == 0 and stats.unmatched == 1
    assert snapshot(pg)[0]["act_id"] is None


def test_act_catalog_status_is_legacy_evidence_not_npb_import_state(pg):
    add_act(pg)
    seed(pg, act_id=10)
    with pg.connect() as c:
        c.execute(
            "INSERT INTO pisrs.act_sync_catalog(register_id,sop,status) "
            "VALUES (10,'SOP-1','pending'),(11,'OTHER','skipped_no_text')"
        )
        c.execute(ACT_STATUS_RECONCILIATION)
        assert (
            c.execute("SELECT status FROM pisrs.act_sync_catalog WHERE register_id=10").fetchone()[
                "status"
            ]
            == "pending"
        )
        c.commit()
        coverage = execute_readonly_script(pg, "olc85_status_coverage.sql")[0]
        pending = next(r for r in coverage if r["legacy_status"] == "pending")
        assert pending["coverage_reason"] == "known_npb_versions_linked"
        assert pending["current_legacy_presence"] == 0 and pending["with_known_npb"] == 1
        c.execute("INSERT INTO pisrs.laws(register_id,sop) VALUES (10,'SOP-1')")
        c.execute(ACT_STATUS_RECONCILIATION)
        assert [
            r["status"]
            for r in c.execute(
                "SELECT status FROM pisrs.act_sync_catalog ORDER BY register_id"
            ).fetchall()
        ] == ["imported", "skipped_no_text"]


def test_child_conflict_and_budget_roll_back_before_any_reassignment(pg):
    seed(pg)
    seed(pg, text_id=102)
    add_act(pg)
    add_act(pg, id=11, register_id=11, sop="OTHER")
    before = snapshot(pg)
    with pytest.raises(PostgresInvariantError, match="budget"):
        repair_act_links(pg, "pisrs_current", 1, approved_targets={201: 10, 202: 10})
    assert snapshot(pg) == before
    with pg.connect() as c:
        c.execute("UPDATE pisrs.act_text_blocks SET act_id=11 WHERE text_id=102")
    with pytest.raises(PostgresInvariantError, match="conflicting"):
        repair_act_links(pg, "pisrs_current", 2, approved_targets={201: 10, 202: 10})
    assert snapshot(pg) == before
    with pg.connect(read_only=True) as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM pisrs.act_text_versions WHERE act_id IS NOT NULL"
            ).fetchone()["n"]
            == 0
        )


def test_full_cached_payload_repair_retains_provenance_and_needs_no_qdrant_write(pg):
    rows = [seed(pg, active=False), seed(pg, text_id=102)]
    qdrant = FakeQdrant(rows)
    for expected_count in (2, 0):
        with pg.connect() as c, c.transaction(), c.cursor() as cursor:
            assert (
                refresh_stored_payloads(
                    cursor, "pisrs_current", ids=[r["id"] for r in snapshot(pg)]
                )
                == expected_count
            )
    for actual, row in zip(snapshot(pg), rows, strict=True):
        assert {
            k: v for k, v in actual["payload"].items() if k in MANAGED_PAYLOAD_KEYS
        } == row.payload()
        assert actual["payload"]["legacy_provenance"] == {"batch": "fixture", "nested": [1, 2]}
    postgres = SimpleNamespace(chunks=ChunkStore(pg, "pisrs_current"))
    assert plan_reconciliation(postgres, qdrant, 1).change_count == 0
    assert qdrant.payload_calls == qdrant.upsert_calls == 0


def test_nonobject_payload_is_not_overwritten(pg):
    seed(pg, stored=["legacy-array"])
    before = snapshot(pg)
    with (
        pytest.raises(PostgresInvariantError, match="not an object"),
        pg.connect() as c,
        c.transaction(),
        c.cursor() as cursor,
    ):
        refresh_stored_payloads(cursor, "pisrs_current", ids=[r["id"] for r in snapshot(pg)])
    assert snapshot(pg) == before


def test_empty_and_bounded_cache_batches_never_expand_scope(pg):
    seed(pg)
    seed(pg, text_id=102)
    before = snapshot(pg)
    with pg.connect() as c, c.transaction(), c.cursor() as cursor:
        assert refresh_stored_payloads(cursor, "pisrs_current", ids=[]) == 0
        assert refresh_stored_payloads(cursor, "pisrs_current", ids=[before[0]["id"]]) == 1
        assert refresh_stored_payloads(cursor, "pisrs_current", ids=[before[0]["id"]]) == 0
    assert snapshot(pg)[1] == before[1]


def test_touched_sop_upsert_retains_provenance_and_second_run_is_noop(pg):
    add_act(pg)
    row = seed(pg, act_id=10)
    chunks = ChunkStore(pg, "pisrs_current")
    chunks.prepare_rollover("SOP-1", "text-embedding-3-large", 3072)
    after = snapshot(pg)
    assert after[0]["payload"]["legacy_provenance"]["nested"] == [1, 2]
    assert {
        k: v for k, v in after[0]["payload"].items() if k in MANAGED_PAYLOAD_KEYS
    } == row.payload()
    chunks.prepare_rollover("SOP-1", "text-embedding-3-large", 3072)
    assert snapshot(pg) == after


def execute_readonly_script(pg, name):
    with pg.connect(read_only=True) as c:
        c.autocommit = True
        cursor = c.execute((Path(__file__).parents[1] / "ops" / name).read_text())
        results = []
        while True:
            if cursor.description:
                results.append(cursor.fetchall())
            if not cursor.nextset():
                break
        return results


def test_preview_and_readback_scripts_are_readonly_and_match_real_fixture(pg):
    seed(pg)
    add_act(pg)
    before = snapshot(pg)
    preview = execute_readonly_script(pg, "olc85_preview.sql")
    assert preview[0][0]["unique_repairable_versions"] == 1
    assert preview[1][0]["blocks_to_link"] == 1
    assert preview[2][0]["managed_json_mismatches"] == 1
    assert snapshot(pg) == before
    repair_act_links(pg, "pisrs_current", 1, approved_targets={201: 10})
    readback = execute_readonly_script(pg, "olc85_readback.sql")
    assert [list(r[0].values())[0] for r in readback[:4]] == [0, 0, 0, 0]


def run_fixture_nightly(pg, qdrant, checkpoint, embedder):
    postgres = SimpleNamespace(
        catalogs=SimpleNamespace(synchronize=lambda *a: None),
        documents=SimpleNamespace(pending=lambda *a: []),
        chunks=ChunkStore(pg, "pisrs_current"),
    )
    return run_nightly(
        client=FakeClient(),
        postgres=postgres,
        qdrant=qdrant,
        checkpoint=checkpoint,
        embedder=embedder,
        model="text-embedding-3-large",
        dimensions=3072,
        max_documents=10,
        embed_batch_size=2,
        max_embedding_input_bytes=1,
    )


def test_payload_only_retry_survives_checkpoint_boundary_for_inactive_chunks(pg):
    rows = [seed(pg, active=False), seed(pg, text_id=102)]
    qdrant = FakeQdrant(rows)
    add_act(pg)
    repair_act_links(pg, "pisrs_current", 2, approved_targets={201: 10, 202: 10})
    checkpoint = FakeCheckpoint()
    checkpoint.start = datetime(2099, 1, 1, tzinfo=UTC)
    checkpoint.end = datetime(2099, 1, 2, tzinfo=UTC)
    embedder = FakeEmbedder()
    stats = run_fixture_nightly(pg, qdrant, checkpoint, embedder)
    assert stats.act_links_repaired == 0 and stats.payloads_updated == 2
    assert embedder.calls == qdrant.upsert_calls == 0
    assert all(r["qdrant_status"] == "uploaded" for r in snapshot(pg))
    assert all(qdrant.points[r.point_id]["act_id"] == 10 for r in rows)
    assert qdrant.points[rows[0].point_id]["is_active"] is False
    assert qdrant.points[rows[0].point_id]["is_latest_for_sop"] is False
    assert len(checkpoint.advanced) == 1
    run_fixture_nightly(pg, qdrant, checkpoint, embedder)
    assert qdrant.payload_calls == 2 and embedder.calls == 0


def test_partial_payload_failure_retains_marker_and_retry_never_embeds(pg):
    rows = [seed(pg, active=False, automatic=True), seed(pg, text_id=102, automatic=True)]
    qdrant = FakeQdrant(rows)
    original = qdrant.set_payload

    def fail_inactive_once(point_id, patch):
        if point_id == rows[0].point_id:
            raise RuntimeError("fixture Qdrant failure")
        original(point_id, patch)

    qdrant.set_payload = fail_inactive_once
    add_act(pg)
    checkpoint = FakeCheckpoint()
    embedder = FakeEmbedder()
    with pytest.raises(RuntimeError, match="fixture Qdrant failure"):
        run_fixture_nightly(pg, qdrant, checkpoint, embedder)
    assert checkpoint.advanced == [] and embedder.calls == 0
    assert [r["qdrant_status"] for r in snapshot(pg)] == ["payload_pending", "uploaded"]
    qdrant.set_payload = original
    run_fixture_nightly(pg, qdrant, checkpoint, embedder)
    assert all(r["qdrant_status"] == "uploaded" for r in snapshot(pg))
    assert embedder.calls == qdrant.upsert_calls == 0
    assert all(qdrant.points[r.point_id]["act_id"] == 10 for r in rows)
    assert checkpoint.advanced == [checkpoint.end]


@pytest.mark.parametrize(
    "inactive_missing,wrong_hash", [(False, False), (True, False), (False, True)]
)
def test_payload_only_never_embeds_on_missing_or_mismatched_vector(
    pg, inactive_missing, wrong_hash
):
    rows = [seed(pg, active=False, automatic=True), seed(pg, text_id=102, automatic=True)]
    qdrant = FakeQdrant(rows)
    victim = rows[0] if inactive_missing else rows[1]
    if wrong_hash:
        qdrant.points[victim.point_id]["content_hash"] = "wrong"
    else:
        del qdrant.points[victim.point_id]
    add_act(pg)
    checkpoint = FakeCheckpoint()
    embedder = FakeEmbedder()
    with pytest.raises(PipelineError, match="existing matching vector"):
        run_fixture_nightly(pg, qdrant, checkpoint, embedder)
    assert embedder.calls == qdrant.payload_calls == qdrant.upsert_calls == 0
    assert checkpoint.advanced == []
    assert all(r["qdrant_status"] == "payload_pending" for r in snapshot(pg))
