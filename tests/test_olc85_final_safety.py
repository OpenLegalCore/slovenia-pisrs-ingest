"""B1/B2 regressions only; all providers are fixtures, PG is disposable."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_core import FakeCheckpoint, FakeClient, FakeEmbedder
from test_olc85 import add_act, seed
from test_olc85 import pg as pg
from test_olc85_review import RecordingQdrant
from test_olc85_review import setup as setup

from pisrs_ingest.maintenance import (
    MaintenanceError,
    PinnedManifest,
    collection_fingerprint,
    payload_leaf,
    run_manifest_repair,
)
from pisrs_ingest.models import NpbDocument, parse_html, qdrant_point_id
from pisrs_ingest.pipeline import run_nightly
from pisrs_ingest.postgres_chunks import ChunkStore
from pisrs_ingest.postgres_documents import DocumentStore
from pisrs_ingest.postgres_integrity import repair_act_links


def pin(raw):
    body = json.dumps(raw).encode()
    return PinnedManifest.from_bytes(
        body, hashlib.sha256(body).hexdigest(), max_changes=10, max_versions=10
    )


def full_snapshot(pg):
    with pg.connect(read_only=True) as c:
        return {
            table: c.execute(f"SELECT * FROM pisrs.{table} ORDER BY id").fetchall()
            for table in ("act_text_versions", "act_text_blocks", "embedding_chunks")
        }


def enable_document_fixture(pg):
    """Only the extra columns needed to exercise real DocumentStore SQL."""
    with pg.connect() as c:
        c.execute("CREATE SEQUENCE pisrs.version_fixture_id START 10000")
        c.execute(
            "ALTER TABLE pisrs.act_text_versions ALTER COLUMN id "
            "SET DEFAULT nextval('pisrs.version_fixture_id')"
        )
        for name, sql_type in {
            "npb_catalog_id": "bigint",
            "source_url": "text",
            "datum_dokumenta": "date",
            "stevilka_dokumenta": "text",
            "html": "text",
            "html_len": "integer",
            "plain_text": "text",
            "plain_text_len": "integer",
            "clen_count": "integer",
            "odstavek_count": "integer",
            "block_count": "integer",
            "parser_version": "text",
            "parser_warnings": "jsonb",
            "imported_at": "timestamptz",
        }.items():
            c.execute(f"ALTER TABLE pisrs.act_text_versions ADD COLUMN {name} {sql_type}")
        for name, sql_type in {
            "status_reason": "text",
            "imported_at": "timestamptz",
            "last_attempt_at": "timestamptz",
            "last_error": "text",
        }.items():
            c.execute(f"ALTER TABLE pisrs.npb_catalog ADD COLUMN {name} {sql_type}")
        for name, sql_type in {
            "paragraph_no": "integer",
            "text_len": "integer",
            "raw_block": "jsonb",
        }.items():
            c.execute(f"ALTER TABLE pisrs.act_text_blocks ADD COLUMN {name} {sql_type}")


def synchronize(store, text_id, sop="SOP-1"):
    document = NpbDocument(
        text_id,
        "Fixture",
        None,
        sop,
        sop,
        "npb02",
        {"automatic_act_link_repair": True},  # untrusted source cannot enroll old versions
    )
    parsed = parse_html(f"<html><body><p class='odstavek'>fixture text {text_id}</p></body></html>")
    store.synchronize(document, parsed, f"https://example.invalid/{text_id}")


@pytest.mark.parametrize("refetch", [False, True])
def test_first_nightly_and_refetch_do_not_enroll_historical_null_links(pg, refetch):
    rows = [seed(pg, active=False), seed(pg, text_id=102)]
    add_act(pg)
    if refetch:
        enable_document_fixture(pg)
        store = DocumentStore(pg)
        for r in rows:
            synchronize(store, r.text_id)
    with pg.connect(read_only=True) as c:
        versions = c.execute("SELECT act_id,raw_meta FROM pisrs.act_text_versions").fetchall()
        assert all(v["act_id"] is None for v in versions)
        assert all("automatic_act_link_repair" not in v["raw_meta"] for v in versions)
    # New source metadata or updated_at cannot turn the historical NULLs into approvals.
    before = full_snapshot(pg)
    q = RecordingQdrant(rows)
    q_before = copy.deepcopy(q.points)
    checkpoint = FakeCheckpoint()
    embedder = FakeEmbedder()
    backend = SimpleNamespace(
        catalogs=SimpleNamespace(synchronize=lambda *a: None),
        documents=SimpleNamespace(pending=lambda *a: []),
        chunks=ChunkStore(pg, "pisrs_current"),
    )
    after_first = None
    for _ in range(2):
        stats = run_nightly(
            client=FakeClient(),
            postgres=backend,
            qdrant=q,
            checkpoint=checkpoint,
            embedder=embedder,
            model="text-embedding-3-large",
            dimensions=3072,
            max_documents=100000,
            embed_batch_size=2,
            max_embedding_input_bytes=1,
        )
        assert (
            stats.act_links_repaired
            == stats.link_blocks_repaired
            == stats.link_chunks_repaired
            == 0
        )
        current = full_snapshot(pg)
        for table in before:
            assert [(r["id"], r["act_id"]) for r in current[table]] == [
                (r["id"], r["act_id"]) for r in before[table]
            ]
        if after_first is None:
            after_first = current
        else:
            assert current == after_first
    assert set(q.points) == set(q_before)
    assert all(payload["act_id"] is None for payload in q.points.values())
    assert all("act_id" not in patch for _, patch in q.writes)
    assert embedder.calls == q.upsert_calls == 0


def test_new_import_marker_survives_late_act_retry_and_does_not_expand_to_history(pg):
    historical = seed(pg, active=False)
    enable_document_fixture(pg)
    store = DocumentStore(pg)
    with pg.connect() as c:
        c.execute(
            "INSERT INTO pisrs.npb_catalog(id,text_id,sop_from_docno,npb_label) "
            "VALUES (302,302,'SOP-1','npb02')"
        )
    synchronize(store, 302)  # new version, no act yet
    with pg.connect(read_only=True) as c:
        new = c.execute("SELECT * FROM pisrs.act_text_versions WHERE text_id=302").fetchone()
    assert new["act_id"] is None and new["raw_meta"]["automatic_act_link_repair"] is True
    assert repair_act_links(pg, "pisrs_current", 100000).versions == 0
    add_act(pg)
    # A later invocation (including after checkpoint progress) can still repair this new row.
    assert repair_act_links(pg, "pisrs_current", 100000).versions == 1
    assert repair_act_links(pg, "pisrs_current", 100000).versions == 0
    synchronize(store, 302)
    synchronize(store, historical.text_id)
    with pg.connect(read_only=True) as c:
        rows = c.execute(
            "SELECT text_id,act_id,raw_meta FROM pisrs.act_text_versions ORDER BY text_id"
        ).fetchall()
        blocks = c.execute(
            "SELECT text_id,act_id FROM pisrs.act_text_blocks ORDER BY text_id"
        ).fetchall()
    assert [(r["text_id"], r["act_id"]) for r in rows] == [(101, None), (302, 10)]
    assert rows[1]["raw_meta"]["automatic_act_link_repair"] is True
    assert "automatic_act_link_repair" not in rows[0]["raw_meta"]
    assert [(r["text_id"], r["act_id"]) for r in blocks] == [(101, None), (302, 10)]


def test_omitted_entire_version_is_rejected_at_parse_without_writes(setup):
    raw = copy.deepcopy(setup.raw)
    raw["points"].pop()
    with pytest.raises(MaintenanceError, match="every approved version"):
        pin(raw)
    assert setup.callbacks == [] and setup.q.writes == []


@pytest.mark.parametrize("phase", ["initial", "resume", "rollback", "partial-rollback"])
@pytest.mark.parametrize("inactive", [False, True])
def test_omitted_sibling_point_fails_before_pg_or_q_writes(setup, phase, inactive):
    s = setup
    sibling = replace(
        s.rows[0],
        database_id=12345,
        chunk_index=2,
        point_id=qdrant_point_id("pisrs_current", s.rows[0].text_id, 2),
        is_active=not inactive,
        is_latest_for_sop=not inactive,
    )
    all_rows = [*s.rows, sibling]
    s.pg.rows = all_rows
    q = RecordingQdrant(all_rows)
    raw = copy.deepcopy(s.raw)
    raw["point_count"] = len(all_rows)
    raw["collection_fingerprint"] = collection_fingerprint(
        {r.point_id: payload_leaf(r.point_id, r.payload()) for r in all_rows}
    )
    # Correct full baseline hash and represented version IDs do not authorize the omitted sibling.
    manifest = pin(raw)
    if phase != "initial":
        s.pg.rows = [
            replace(r, act_id=10) if r.version_id in dict(manifest.version_links) else r
            for r in all_rows
        ]
        if phase == "resume":
            q.points[s.rows[0].point_id]["act_id"] = 10
        else:
            for r in all_rows:
                if r.version_id in dict(manifest.version_links):
                    q.points[r.point_id]["act_id"] = 10
            if phase == "partial-rollback":
                s.pg.rows = [
                    replace(r, act_id=None) if r.version_id in dict(manifest.version_links) else r
                    for r in all_rows
                ]
                q.points[s.rows[0].point_id]["act_id"] = None
    pg_before = copy.deepcopy(s.pg.rows)
    q_before = copy.deepcopy(q.points)
    args = {**s.args, "manifest": manifest, "qdrant": q}
    with pytest.raises(MaintenanceError):
        run_manifest_repair(**args, direction="rollback" if "rollback" in phase else "forward")
    assert s.callbacks == [] and q.writes == []
    assert s.pg.rows == pg_before and q.points == q_before


@pytest.mark.parametrize("direction", ["forward", "rollback"])
def test_real_pg_missing_sibling_never_reaches_write_callback(pg, setup, direction):
    s = setup
    rows = [seed(pg, active=False), seed(pg, text_id=102)]
    add_act(pg)
    first = rows[0]
    # A second actual PG/Qdrant chunk in the same approved version, absent from manifest.
    with pg.connect() as c:
        c.execute(
            "INSERT INTO pisrs.embedding_chunks ("
            "source,collection_name,act_id,version_id,text_id,sop,sop_from_docno,npb_label,"
            "naziv,title,chunk_index,chunk_type,chunk_text,chunk_text_len,block_count,"
            "token_estimate,content_hash,is_latest_for_sop,is_active,embedding_model,"
            "embedding_dimensions,qdrant_point_id,payload) "
            "SELECT source,collection_name,act_id,version_id,text_id,sop,sop_from_docno,npb_label,"
            "naziv,title,2,chunk_type,chunk_text,chunk_text_len,block_count,token_estimate,"
            "content_hash,FALSE,FALSE,embedding_model,embedding_dimensions,%s,payload "
            "FROM pisrs.embedding_chunks WHERE text_id=%s",
            (qdrant_point_id("pisrs_current", first.text_id, 2), first.text_id),
        )
    store = ChunkStore(pg, "pisrs_current")
    all_rows = [r for batch in store.iter_authoritative_payload_batches() for r in batch]
    q = RecordingQdrant(all_rows)
    raw = copy.deepcopy(s.raw)
    raw["point_count"] = len(all_rows)
    raw["collection_fingerprint"] = collection_fingerprint(
        {r.point_id: payload_leaf(r.point_id, r.payload()) for r in all_rows}
    )
    raw["points"] = [
        {
            "point_id": r.point_id,
            "old_act_id": None,
            "new_act_id": 10,
            "before_payload": r.payload(),
        }
        for r in rows
    ]
    manifest = pin(raw)
    if direction == "rollback":
        with pg.connect() as c:
            for table in ("act_text_versions", "act_text_blocks", "embedding_chunks"):
                c.execute(f"UPDATE pisrs.{table} SET act_id=10")
        for payload in q.points.values():
            payload["act_id"] = 10
    before = full_snapshot(pg)
    q_before = copy.deepcopy(q.points)
    writes = []

    def forbidden(*args):
        writes.append("PG")
        pytest.fail("incomplete manifest reached PG write callback")

    with pytest.raises(MaintenanceError):
        run_manifest_repair(
            **{
                **s.args,
                "manifest": manifest,
                "postgres": SimpleNamespace(chunks=store),
                "qdrant": q,
                "prepare_pg": forbidden,
                "acknowledge_pg": forbidden,
                "readback_pg": forbidden,
            },
            direction=direction,
        )
    assert writes == q.writes == [] and full_snapshot(pg) == before and q.points == q_before


def test_complete_sibling_manifest_resumes_forward_and_inverse_without_scope_expansion(setup):
    s = setup
    sibling = replace(
        s.rows[0],
        database_id=12345,
        chunk_index=2,
        point_id=qdrant_point_id("pisrs_current", s.rows[0].text_id, 2),
    )
    all_rows = [*s.rows, sibling]
    s.pg.rows = all_rows
    q = RecordingQdrant(all_rows)
    q_before = copy.deepcopy(q.points)
    raw = copy.deepcopy(s.raw)
    raw["point_count"] = len(all_rows)
    raw["collection_fingerprint"] = collection_fingerprint(
        {r.point_id: payload_leaf(r.point_id, r.payload()) for r in all_rows}
    )
    raw["points"].append(
        {
            "point_id": sibling.point_id,
            "old_act_id": None,
            "new_act_id": 10,
            "before_payload": sibling.payload(),
        }
    )
    args = {**s.args, "manifest": pin(raw), "qdrant": q}
    original = q.set_payload
    for direction in ("forward", "rollback"):
        calls = 0

        def fail_second(point_id, patch):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("fixture interrupted")
            original(point_id, patch)

        q.set_payload = fail_second
        with pytest.raises(RuntimeError, match="fixture interrupted"):
            run_manifest_repair(**args, direction=direction)
        q.set_payload = original
        assert run_manifest_repair(**args, direction=direction)["payloads_applied"] == 2
        assert run_manifest_repair(**args, direction=direction)["payloads_applied"] == 0
    assert q.points == q_before and s.pg.rows == all_rows
    assert len(q.writes) == 6
    assert {pid for pid, _ in q.writes} == {p.point_id for p in args["manifest"].points}
    assert all(set(patch) == {"act_id"} for _, patch in q.writes)
    assert s.checkpoint.read_bytes() == b"checkpoint-before"
