from __future__ import annotations

import os
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

import psycopg
import pytest
import requests
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from test_core import FakeCheckpoint, FakeClient, FakeEmbedder, FakePostgres, FakeQdrant, vector_row

from pisrs_ingest.checkpoint import CheckpointStore
from pisrs_ingest.models import Block, make_chunks
from pisrs_ingest.pipeline import PipelineError, run_nightly
from pisrs_ingest.postgres import PostgresDatabase, PostgresInvariantError
from pisrs_ingest.postgres_act_links import link_missing_acts
from pisrs_ingest.postgres_chunks import ChunkStore
from pisrs_ingest.qdrant import QdrantInvariantError, QdrantStore


def nightly(postgres, qdrant, checkpoint, embedder=None, *, embedding_bytes=1, **kwargs):
    return run_nightly(
        client=FakeClient(),
        postgres=postgres,
        qdrant=qdrant,
        checkpoint=checkpoint,
        embedder=embedder or FakeEmbedder(),
        model="text-embedding-3-large",
        dimensions=3072,
        max_documents=10,
        embed_batch_size=5,
        max_embedding_input_bytes=embedding_bytes,
        **kwargs,
    )


@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize("failure", ["missing", "hash", "model", "dimensions", "extra"])
def test_existing_upload_blocks_before_any_embedding_or_qdrant_write(active, failure):
    row = vector_row(active=active, latest=active, text_id=1)
    pg = FakePostgres([row])
    pg.chunks.uploaded_point_ids = lambda ids: ids
    qdrant = FakeQdrant([row])
    if failure == "missing":
        qdrant.points.clear()
    else:
        key = {
            "hash": "content_hash",
            "model": "embedding_model",
            "dimensions": "embedding_dimensions",
            "extra": "unknown",
        }[failure]
        qdrant.points[row.point_id][key] = "wrong"
    embedder = FakeEmbedder()
    checkpoint = FakeCheckpoint()
    with pytest.raises((PipelineError, QdrantInvariantError)):
        nightly(pg, qdrant, checkpoint, embedder)
    assert qdrant.upsert_calls == qdrant.payload_calls == embedder.calls == 0
    assert checkpoint.advanced == []


def test_simulated_act_only_change_reuses_vectors_and_patches_active_and_inactive():
    rows = [vector_row(active=flag, latest=flag, text_id=i) for i, flag in [(1, True), (2, False)]]
    pg = FakePostgres(rows)
    pg.chunks.uploaded_point_ids = lambda ids: ids
    qdrant = FakeQdrant([replace(row, act_id=None) for row in rows])
    embedder = FakeEmbedder()
    checkpoint = FakeCheckpoint()
    stats = nightly(pg, qdrant, checkpoint, embedder)
    assert stats.payloads_updated == 2
    assert embedder.calls == qdrant.upsert_calls == 0
    assert all(point["act_id"] == 10 for point in qdrant.points.values())


def test_bad_existing_upload_blocks_a_new_embedding_before_any_provider_call():
    new = vector_row(active=True, latest=True, text_id=1)
    old = vector_row(active=False, latest=False, text_id=2)
    pg = FakePostgres([new, old])
    pg.chunks.uploaded_point_ids = lambda ids: {old.point_id}
    qdrant = FakeQdrant([old])
    qdrant.points[old.point_id]["content_hash"] = "wrong"
    embedder, checkpoint = FakeEmbedder(), FakeCheckpoint()
    with pytest.raises(PipelineError, match="existing upload"):
        nightly(pg, qdrant, checkpoint, embedder, embedding_bytes=100)
    assert embedder.calls == qdrant.payload_calls == qdrant.upsert_calls == 0
    assert checkpoint.advanced == []


def test_wrong_returned_point_identity_blocks_payload_only_sync():
    row = vector_row(active=True, latest=True, text_id=1)
    pg = FakePostgres([row])
    pg.chunks.uploaded_point_ids = lambda ids: ids
    qdrant = FakeQdrant([row])
    original = qdrant.get_point
    qdrant.get_point = lambda point_id: replace(original(point_id), point_id="other")
    checkpoint, embedder = FakeCheckpoint(), FakeEmbedder()
    with pytest.raises(PipelineError, match="existing upload"):
        nightly(pg, qdrant, checkpoint, embedder)
    assert qdrant.payload_calls == qdrant.upsert_calls == embedder.calls == 0


@pytest.fixture
def pg_links():
    dsn = os.environ.get("PISRS_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("requires isolated pisrs_test_* PostgreSQL")
    connection = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
    assert connection.info.dbname.startswith("pisrs_test_")
    assert connection.execute("SELECT to_regnamespace('pisrs') AS n").fetchone()["n"] is None
    connection.execute("CREATE SCHEMA pisrs")
    connection.execute("CREATE TABLE pisrs.acts (id bigint PRIMARY KEY, sop text)")
    connection.execute(
        """CREATE TABLE pisrs.act_text_versions (
            id bigint PRIMARY KEY, act_id bigint REFERENCES pisrs.acts, text_id bigint UNIQUE,
            sop text, sop_from_docno text, npb_label text, naziv text, title text,
            updated_at timestamptz DEFAULT '2020-01-01Z',
            html text DEFAULT '<html>fixture</html>')"""
    )
    connection.execute(
        """CREATE TABLE pisrs.act_text_blocks (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            version_id bigint REFERENCES pisrs.act_text_versions,
            act_id bigint REFERENCES pisrs.acts, text_id bigint, block_index integer,
            block_type text, article_no text, article_title text, class_list text[], text text,
            updated_at timestamptz DEFAULT '2020-01-01Z')"""
    )
    connection.execute(
        """CREATE TABLE pisrs.embedding_chunks (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source text, collection_name text, act_id bigint REFERENCES pisrs.acts,
            version_id bigint REFERENCES pisrs.act_text_versions, text_id bigint,
            sop text, sop_from_docno text, npb_label text, naziv text, title text,
            chunk_index integer, chunk_type text, chunk_text text, chunk_text_len integer,
            block_start_index integer, block_end_index integer, block_count integer,
            token_estimate integer, content_hash text, is_latest_for_sop boolean,
            is_active boolean, embedding_model text, embedding_dimensions integer,
            qdrant_point_id text, qdrant_status text, qdrant_error text,
            qdrant_upserted_at timestamptz, payload jsonb,
            updated_at timestamptz DEFAULT '2020-01-01Z',
            UNIQUE(collection_name,text_id,chunk_index))"""
    )
    try:
        yield connection, PostgresDatabase(dsn)
    finally:
        connection.execute("DROP SCHEMA pisrs CASCADE")
        connection.close()


def seed(connection, text_id=1, *, active=True, act_id=None, sop="SOP-1"):
    block_text = f"fixture text {text_id}"
    chunk = make_chunks((Block(1, "p", (), block_text, "paragraph"),))[0]
    row = replace(
        vector_row(active=active, latest=active, text_id=text_id),
        act_id=act_id,
        sop=sop,
        sop_from_docno=sop,
        chunk_text=chunk.chunk_text,
        chunk_text_len=len(chunk.chunk_text),
        token_estimate=chunk.token_estimate,
        content_hash=chunk.content_hash,
    )
    connection.execute(
        "INSERT INTO pisrs.act_text_versions "
        "(id,act_id,text_id,sop,sop_from_docno,npb_label,naziv,title) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (row.version_id, act_id, text_id, sop, sop, row.npb_label, row.naziv, row.title),
    )
    connection.execute(
        "INSERT INTO pisrs.act_text_blocks "
        "(version_id,act_id,text_id,block_index,block_type,class_list,text) "
        "VALUES (%s,%s,%s,1,'paragraph','{}',%s)",
        (row.version_id, act_id, text_id, block_text),
    )
    values = asdict(row)
    values.pop("database_id")
    values["qdrant_point_id"] = values.pop("point_id")
    values.update(
        source="pisrs",
        qdrant_status="uploaded",
        payload=Jsonb({**row.payload(), "provenance": {"retain": [1, 2]}}),
    )
    parameters = ",".join("%(" + key + ")s" for key in values)
    connection.execute(
        f"INSERT INTO pisrs.embedding_chunks ({','.join(values)}) VALUES ({parameters})",
        values,
    )
    return row


def snapshot(c):
    return {
        table: c.execute(f"SELECT to_jsonb(t) AS row FROM pisrs.{table} t ORDER BY id").fetchall()
        for table in ["act_text_versions", "act_text_blocks", "embedding_chunks"]
    }


def test_pg_unique_link_is_atomic_preserves_content_provenance_and_is_idempotent(pg_links):
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,'SOP-1')")
    seed(c)
    seed(c, 2, active=False)
    before = snapshot(c)
    stats = link_missing_acts(db, "pisrs_current", 2)
    assert (stats.versions, stats.blocks, stats.chunks) == (2, 2, 2)
    after = snapshot(c)
    for table in before:
        for a, b in zip(before[table], after[table], strict=True):
            a, b = a["row"], b["row"]
            assert b["act_id"] == 10
            assert {k: v for k, v in a.items() if k not in {"act_id", "payload", "updated_at"}} == {
                k: v for k, v in b.items() if k not in {"act_id", "payload", "updated_at"}
            }
            if table == "embedding_chunks":
                assert b["payload"] == {**a["payload"], "act_id": 10}
                assert b["qdrant_status"] == "uploaded"
    assert link_missing_acts(db, "pisrs_current", 2).versions == 0
    assert snapshot(c) == after


def test_pg_zero_ambiguous_and_nonnull_links_are_never_guessed(pg_links):
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,'DUP'),(11,'DUP')")
    seed(c, 1, sop="NONE")
    seed(c, 2, sop="DUP")
    seed(c, 3, act_id=11, sop="DUP")
    before = snapshot(c)
    stats = link_missing_acts(db, "pisrs_current", 10)
    assert (stats.versions, stats.unmatched, stats.ambiguous) == (0, 1, 1)
    assert snapshot(c) == before


@pytest.mark.parametrize(
    "conflict", ["block", "chunk", "text", "sop", "collection", "payload", "point", "missing_point"]
)
def test_pg_child_conflict_rolls_back_whole_link_batch(pg_links, conflict):
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,'SOP-1'),(99,'OTHER')")
    seed(c)
    seed(c, 2, active=False)
    sql = {
        "block": "UPDATE pisrs.act_text_blocks SET act_id=99 WHERE text_id=2",
        "chunk": "UPDATE pisrs.embedding_chunks SET act_id=99 WHERE text_id=2",
        "text": "UPDATE pisrs.embedding_chunks SET text_id=99 WHERE text_id=2",
        "sop": "UPDATE pisrs.embedding_chunks SET sop_from_docno='OTHER' WHERE text_id=2",
        "collection": "UPDATE pisrs.embedding_chunks SET collection_name='other' WHERE text_id=2",
        "payload": "UPDATE pisrs.embedding_chunks SET payload='[]' WHERE text_id=2",
        "point": "UPDATE pisrs.embedding_chunks SET qdrant_point_id='wrong' WHERE text_id=2",
        "missing_point": "UPDATE pisrs.embedding_chunks SET qdrant_point_id=NULL WHERE text_id=2",
    }[conflict]
    c.execute(sql)
    before = snapshot(c)
    with pytest.raises(PostgresInvariantError, match="conflict"):
        link_missing_acts(db, "pisrs_current", 10)
    assert snapshot(c) == before


def test_pg_budget_overflow_never_truncates_or_writes(pg_links):
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,'SOP-1')")
    seed(c)
    seed(c, 2)
    before = snapshot(c)
    with pytest.raises(PostgresInvariantError, match="budget"):
        link_missing_acts(db, "pisrs_current", 1)
    assert snapshot(c) == before


def test_pg_error_after_parent_update_rolls_back_parent_blocks_and_chunks(pg_links):
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,'SOP-1')")
    seed(c)
    c.execute(
        "ALTER TABLE pisrs.embedding_chunks ADD CONSTRAINT fixture_abort CHECK(act_id IS NULL)"
    )
    before = snapshot(c)
    with pytest.raises(psycopg.errors.CheckViolation):
        link_missing_acts(db, "pisrs_current", 1)
    assert snapshot(c) == before


def test_pg_matching_nonnull_child_links_are_preserved(pg_links):
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,'SOP-1')")
    seed(c, act_id=10)
    c.execute("UPDATE pisrs.act_text_versions SET act_id=NULL")
    before = snapshot(c)
    stats = link_missing_acts(db, "pisrs_current", 1)
    assert (stats.versions, stats.blocks, stats.chunks) == (1, 0, 0)
    after = snapshot(c)
    assert before["act_text_blocks"] == after["act_text_blocks"]
    assert before["embedding_chunks"] == after["embedding_chunks"]


@pytest.mark.parametrize("parent_act", [None, 11])
def test_pg_rollover_never_clears_or_reassigns_nonnull_chunk_links(pg_links, parent_act):
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,'SOP-1'),(11,'SOP-1')")
    seed(c, act_id=10)
    c.execute("UPDATE pisrs.act_text_versions SET act_id=%s", (parent_act,))
    before = snapshot(c)
    with pytest.raises(PostgresInvariantError, match="existing non-NULL"):
        ChunkStore(db, "pisrs_current").prepare_rollover("SOP-1", "text-embedding-3-large", 3072)
    assert snapshot(c) == before


@pytest.mark.parametrize("sop", [None, "", " "])
def test_pg_missing_sop_is_unmatched_even_if_an_act_has_empty_sop(pg_links, sop):
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,%s)", (sop,))
    seed(c, sop=sop)
    before = snapshot(c)
    stats = link_missing_acts(db, "pisrs_current", 1)
    assert stats.unmatched == 1 and stats.versions == 0
    assert snapshot(c) == before


def boundary(db):
    return SimpleNamespace(
        chunks=ChunkStore(db, "pisrs_current"),
        catalogs=SimpleNamespace(synchronize=lambda a, n: None),
        documents=SimpleNamespace(pending=lambda limit, since: []),
    )


@pytest.mark.parametrize("failure_stage", ["after_pg_commit", "partial_qdrant"])
def test_pg_qdrant_failure_retries_via_unchanged_checkpoint_without_fetch_or_embeddings(
    pg_links, failure_stage
):
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,'SOP-1')")
    rows = [seed(c), seed(c, 2, active=False)]
    pg = boundary(db)
    qdrant = FakeQdrant(rows)
    embedder = FakeEmbedder()
    checkpoint = FakeCheckpoint()
    original = qdrant.set_payload
    original_link = pg.chunks.link_missing_acts

    def fail(point_id, patch):
        if point_id == rows[1].point_id:
            raise RuntimeError("interrupted after PG and first Qdrant patch")
        original(point_id, patch)

    if failure_stage == "partial_qdrant":
        qdrant.set_payload = fail
    else:

        def fail_after_pg_commit(limit):
            original_link(limit)
            raise RuntimeError("interrupted after PG commit before Qdrant")

        pg.chunks.link_missing_acts = fail_after_pg_commit
    with pytest.raises(RuntimeError, match="interrupted"):
        nightly(pg, qdrant, checkpoint, embedder)
    assert checkpoint.advanced == []
    assert (
        c.execute("SELECT count(*) n FROM pisrs.act_text_versions WHERE act_id=10").fetchone()["n"]
        == 2
    )
    assert pg.chunks.touched_sops(checkpoint.start) == ["SOP-1"]
    qdrant.set_payload = original
    pg.chunks.link_missing_acts = original_link
    stats = nightly(pg, qdrant, checkpoint, embedder)
    assert stats.act_links_filled == 0
    assert all(p["act_id"] == 10 for p in qdrant.points.values())
    assert checkpoint.advanced == [checkpoint.end]
    assert embedder.calls == qdrant.upsert_calls == 0
    assert c.execute("SELECT DISTINCT qdrant_status FROM pisrs.embedding_chunks").fetchall() == [
        {"qdrant_status": "uploaded"}
    ]


def test_pg_future_nightly_finds_act_added_after_successful_interval(pg_links, tmp_path):
    c, db = pg_links
    row = seed(c)
    pg = boundary(db)
    qdrant = FakeQdrant([row])
    embedder = FakeEmbedder()
    checkpoint = CheckpointStore(tmp_path / "checkpoint.json", datetime(2025, 1, 1, tzinfo=UTC))
    end = datetime.now(UTC).replace(microsecond=0)
    assert nightly(pg, qdrant, checkpoint, embedder, now=end).act_links_unmatched == 1
    c.execute("INSERT INTO pisrs.acts VALUES (10,'SOP-1')")
    stats = nightly(pg, qdrant, checkpoint, embedder, now=end + timedelta(seconds=5))
    assert stats.act_links_filled == 1
    assert qdrant.points[row.point_id]["act_id"] == 10
    assert embedder.calls == qdrant.upsert_calls == 0
    assert checkpoint.interval(end + timedelta(seconds=10)).start == end + timedelta(seconds=5)


@pytest.fixture
def real_qdrant():
    url = os.environ.get("PISRS_TEST_QDRANT_URL")
    if not url:
        pytest.skip("requires an isolated Qdrant fixture")
    parsed = urlsplit(url)
    assert parsed.hostname == "127.0.0.1" and parsed.port not in {None, 6333, 6334}
    session = requests.Session()
    session.trust_env = False
    collection = "pisrs_test_links_" + uuid.uuid4().hex
    response = session.put(
        f"{url}/collections/{collection}",
        json={"vectors": {"size": 3072, "distance": "Cosine"}},
        timeout=15,
    )
    response.raise_for_status()
    try:
        yield QdrantStore(url, collection), session
    finally:
        session.delete(f"{url}/collections/{collection}", timeout=15).raise_for_status()


@pytest.mark.parametrize("interrupt", [False, True])
def test_pg_real_qdrant_link_patch_preserves_vectors_on_success_and_retry(
    pg_links, real_qdrant, interrupt, monkeypatch
):
    c, db = pg_links
    c.execute("INSERT INTO pisrs.acts VALUES (10,'SOP-1')")
    rows = [seed(c), seed(c, 2, active=False)]
    qdrant, session = real_qdrant
    qdrant.upsert(rows, [[1.0, *([0.0] * 3071)]] * len(rows))

    def read_points():
        response = session.post(
            f"{qdrant.base_url}/collections/{qdrant.collection}/points",
            json={"ids": [r.point_id for r in rows], "with_payload": True, "with_vector": True},
            timeout=15,
        )
        response.raise_for_status()
        return {str(p["id"]): p for p in response.json()["result"]}

    before = read_points()
    monkeypatch.setattr(
        qdrant, "upsert", lambda *a: pytest.fail("vector upsert during link-only sync")
    )
    pg, checkpoint, embedder = boundary(db), FakeCheckpoint(), FakeEmbedder()
    original = qdrant.set_payload
    if interrupt:

        def fail_inactive(point_id, patch):
            if point_id == rows[1].point_id:
                raise RuntimeError("isolated Qdrant interruption")
            original(point_id, patch)

        monkeypatch.setattr(qdrant, "set_payload", fail_inactive)
        with pytest.raises(RuntimeError, match="interruption"):
            nightly(pg, qdrant, checkpoint, embedder)
        assert checkpoint.advanced == []
        monkeypatch.setattr(qdrant, "set_payload", original)
    nightly(pg, qdrant, checkpoint, embedder)
    after = read_points()
    assert set(after) == set(before)
    for point_id in after:
        assert after[point_id]["vector"] == before[point_id]["vector"]
        assert after[point_id]["payload"] == {**before[point_id]["payload"], "act_id": 10}
    assert embedder.calls == 0
    assert checkpoint.advanced == [checkpoint.end]
    assert nightly(pg, qdrant, checkpoint, embedder).payloads_updated == 0
