from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from psycopg.types.json import Jsonb
from test_olc85 import add_act, seed, snapshot
from test_olc85 import pg as pg
from test_olc85_review import RecordingQdrant
from test_olc85_review import setup as setup

from pisrs_ingest import postgres_integrity
from pisrs_ingest.maintenance import (
    PinnedManifest,
    collection_fingerprint,
    payload_leaf,
    run_manifest_repair,
)
from pisrs_ingest.models import MANAGED_PAYLOAD_KEYS, qdrant_point_id
from pisrs_ingest.postgres import PostgresInvariantError
from pisrs_ingest.postgres_chunks import ChunkStore
from pisrs_ingest.postgres_integrity import (
    refresh_sop_payloads,
    refresh_stored_payloads,
    repair_act_links,
)


def clone_chunks(pg, total=1001):
    seed(pg)
    with pg.connect() as c, c.cursor() as cursor:
        row = c.execute("SELECT * FROM pisrs.embedding_chunks").fetchone()
        row.pop("id")
        cols = list(row)
        parameters = []
        for index in range(2, total + 1):
            clone = dict(row)
            clone["chunk_index"] = index
            clone["qdrant_point_id"] = qdrant_point_id("pisrs_current", clone["text_id"], index)
            clone["payload"] = Jsonb(clone["payload"])
            parameters.append(tuple(clone.values()))
        cursor.executemany(
            "INSERT INTO pisrs.embedding_chunks("
            + ",".join(cols)
            + ") VALUES ("
            + ",".join(["%s"] * len(cols))
            + ")",
            parameters,
        )


def test_real_json_guard_and_touched_sop_use_pk_batches_at_most_1000(pg, monkeypatch):
    clone_chunks(pg)
    before = snapshot(pg)
    ids = [r["id"] for r in before]
    with (
        pytest.raises(PostgresInvariantError, match="1000"),
        pg.connect() as c,
        c.transaction(),
        c.cursor() as cur,
    ):
        refresh_stored_payloads(cur, "pisrs_current", ids=ids)
    assert snapshot(pg) == before
    with pg.connect() as c, c.transaction(), c.cursor() as cur:
        assert refresh_stored_payloads(cur, "pisrs_current", ids=ids[:1000]) == 1000
        assert refresh_stored_payloads(cur, "pisrs_current", ids=ids[:1000]) == 0
    assert snapshot(pg)[-1] == before[-1]
    original = postgres_integrity.refresh_stored_payloads
    batch_sizes = []

    def bounded(cursor, collection, *, ids):
        batch_sizes.append(len(ids))
        return original(cursor, collection, ids=ids)

    monkeypatch.setattr(postgres_integrity, "refresh_stored_payloads", bounded)
    with pg.connect() as c, c.transaction(), c.cursor() as cur:
        assert refresh_sop_payloads(cur, "pisrs_current", "SOP-1") == 1
    assert batch_sizes == [1000, 1]


def test_link_refresh_is_bounded_and_pg_target_map_cannot_expand(pg, monkeypatch):
    clone_chunks(pg)
    add_act(pg)
    before = snapshot(pg)
    with pytest.raises(PostgresInvariantError, match="approved version map"):
        repair_act_links(pg, "pisrs_current", 100, approved_targets={})
    assert snapshot(pg) == before
    with pytest.raises(PostgresInvariantError, match="approved version map"):
        repair_act_links(pg, "pisrs_current", 100, approved_targets={201: 11})
    assert snapshot(pg) == before
    original = postgres_integrity.refresh_stored_payloads
    sizes = []

    def bounded(cursor, collection, *, ids):
        sizes.append(len(ids))
        return original(cursor, collection, ids=ids)

    monkeypatch.setattr(postgres_integrity, "refresh_stored_payloads", bounded)
    assert repair_act_links(pg, "pisrs_current", 100, approved_targets={201: 10}).chunks == 1001
    assert sizes == [1000, 1]
    after = snapshot(pg)
    assert all(r["act_id"] == 10 and r["qdrant_status"] == "payload_pending" for r in after)
    assert [r["qdrant_point_id"] for r in after] == [r["qdrant_point_id"] for r in before]
    assert repair_act_links(pg, "pisrs_current", 100, approved_targets={201: 10}).versions == 0


@pytest.mark.parametrize("partial", [False, True])
def test_real_pg_and_manifest_apply_and_rollback_share_one_owner(pg, setup, partial):
    s = setup
    rows = [seed(pg, active=False), seed(pg, text_id=102)]
    add_act(pg)
    outside = seed(pg, text_id=999, act_id=10)
    all_rows = [*rows, outside]
    store = ChunkStore(pg, "pisrs_current")
    backend = SimpleNamespace(chunks=store)
    q = RecordingQdrant(all_rows)
    q_before = copy.deepcopy(q.points)

    def detailed_snapshot():
        with pg.connect(read_only=True) as c:
            return c.execute(
                "SELECT id,act_id,qdrant_point_id,content_hash,chunk_text,"
                "qdrant_status,qdrant_error,qdrant_upserted_at,payload,updated_at "
                "FROM pisrs.embedding_chunks ORDER BY id"
            ).fetchall()

    chunks_before = detailed_snapshot()
    after_images = {}
    raw = {
        "version": 1,
        "collection": "pisrs_current",
        "point_count": 3,
        "collection_fingerprint": collection_fingerprint(
            {r.point_id: payload_leaf(r.point_id, r.payload()) for r in all_rows}
        ),
        "version_links": [
            {"version_id": r.version_id, "old_act_id": None, "new_act_id": 10} for r in rows
        ],
        "points": [
            {
                "point_id": r.point_id,
                "old_act_id": None,
                "new_act_id": 10,
                "before_payload": r.payload(),
            }
            for r in rows
        ],
    }
    body = json.dumps(raw).encode()
    manifest = PinnedManifest.from_bytes(
        body, hashlib.sha256(body).hexdigest(), max_changes=2, max_versions=2
    )
    identities = {
        r["id"]: (r["qdrant_point_id"], r["content_hash"], r["chunk_text"]) for r in chunks_before
    }

    def prepare(owner, pinned, direction):
        owner.check()
        if direction == "forward":
            repair_act_links(pg, "pisrs_current", 2, approved_targets=dict(pinned.version_links))
            with pg.connect() as c, c.transaction(), c.cursor() as cur:
                refresh_stored_payloads(cur, "pisrs_current", ids=[r["id"] for r in chunks_before])
                owner.check()
        else:
            with pg.connect() as c, c.transaction():
                for row in rows:
                    c.execute(
                        "UPDATE pisrs.act_text_versions SET act_id=NULL WHERE id=%s AND act_id=10",
                        (row.version_id,),
                    )
                    c.execute(
                        "UPDATE pisrs.act_text_blocks SET act_id=NULL "
                        "WHERE version_id=%s AND act_id=10",
                        (row.version_id,),
                    )
                current = {r["id"]: r for r in detailed_snapshot()}
                for old in chunks_before:
                    cur = current[old["id"]]
                    expected = next(r for r in all_rows if r.point_id == old["qdrant_point_id"])
                    target = replace(expected, act_id=10) if expected.act_id is None else expected
                    assert cur["act_id"] in (old["act_id"], target.act_id)
                    fields = (
                        "act_id",
                        "payload",
                        "qdrant_status",
                        "qdrant_error",
                        "qdrant_upserted_at",
                    )
                    assert tuple(cur[k] for k in fields) in (
                        tuple(old[k] for k in fields),
                        tuple(after_images[old["id"]][k] for k in fields),
                    )
                    if all(
                        cur[k] == old[k]
                        for k in (
                            "act_id",
                            "payload",
                            "qdrant_status",
                            "qdrant_error",
                            "qdrant_upserted_at",
                        )
                    ):
                        continue
                    c.execute(
                        "UPDATE pisrs.embedding_chunks SET act_id=%s,payload=%s,qdrant_status=%s, "
                        "qdrant_error=%s,qdrant_upserted_at=%s "
                        "WHERE id=%s AND act_id IS NOT DISTINCT FROM %s",
                        (
                            old["act_id"],
                            Jsonb(old["payload"]),
                            old["qdrant_status"],
                            old["qdrant_error"],
                            old["qdrant_upserted_at"],
                            old["id"],
                            cur["act_id"],
                        ),
                    )
                owner.check()

    def ack(owner, pinned, direction):
        owner.check()
        if direction == "forward":
            store.mark_uploaded(store.rows_for_point_ids({r.point_id for r in rows}))

    def readback(owner, pinned, direction):
        owner.check()
        actual = detailed_snapshot()
        assert all(
            identities[r["id"]] == (r["qdrant_point_id"], r["content_hash"], r["chunk_text"])
            for r in actual
        )
        assert all(r["qdrant_status"] == "uploaded" for r in actual)
        if direction == "forward":
            after_images.update({r["id"]: r for r in actual})
            final = {
                r.point_id: r for batch in store.iter_authoritative_payload_batches() for r in batch
            }
            for r in actual:
                assert {
                    k: v for k, v in r["payload"].items() if k in MANAGED_PAYLOAD_KEYS
                } == final[r["qdrant_point_id"]].payload()
        else:
            # touch_updated_at remains enabled: semantic before-images are restored;
            # trigger-owned timestamps deliberately advance rather than being disabled.
            fields = ("act_id", "payload", "qdrant_status", "qdrant_error", "qdrant_upserted_at")
            assert [tuple(r[k] for k in fields) for r in actual] == [
                tuple(r[k] for k in fields) for r in chunks_before
            ]

    args = {
        **s.args,
        "manifest": manifest,
        "postgres": backend,
        "qdrant": q,
        "prepare_pg": prepare,
        "acknowledge_pg": ack,
        "readback_pg": readback,
    }
    if partial:
        original = q.set_payload
        calls = 0

        def fail_second(point_id, patch):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("fixture partial Qdrant apply")
            original(point_id, patch)

        q.set_payload = fail_second
        with pytest.raises(RuntimeError, match="partial Qdrant"):
            run_manifest_repair(**args)
        assert [
            r["qdrant_status"]
            for r in snapshot(pg)
            if r["act_id"] == 10 and r["qdrant_point_id"] != outside.point_id
        ] == ["payload_pending", "payload_pending"]
        q.set_payload = original
    assert run_manifest_repair(**args)["payloads_applied"] == (1 if partial else 2)
    assert q.points[outside.point_id] == q_before[outside.point_id]
    assert run_manifest_repair(**args, direction="rollback")["payloads_applied"] == 2
    assert q.points == q_before
    after_rollback = snapshot(pg)
    assert run_manifest_repair(**args, direction="rollback")["payloads_applied"] == 0
    assert snapshot(pg) == after_rollback
    assert all(set(patch) == {"act_id"} for pid, patch in q.writes)
