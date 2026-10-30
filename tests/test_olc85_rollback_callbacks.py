"""Focused A/B regressions; full legacy CI suite is deliberately not duplicated."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from types import SimpleNamespace

import pytest
from psycopg.types.json import Jsonb
from test_olc85 import add_act, seed
from test_olc85 import pg as pg
from test_olc85_review import RecordingQdrant
from test_olc85_review import setup as setup

from pisrs_ingest.maintenance import (
    MaintenanceError,
    MaintenanceOwner,
    PinnedManifest,
    collection_fingerprint,
    payload_leaf,
    run_manifest_repair,
)
from pisrs_ingest.postgres_chunks import ChunkStore
from pisrs_ingest.postgres_maintenance import PgMaintenanceCallbacks, capture_pg_images


def test_restore_uses_exact_full_before_image_and_keeps_null(setup):
    s = setup
    run_manifest_repair(**s.args)
    calls = []
    original = s.q.overwrite_payload

    def overwrite(pid, payload):
        expected = next(p.before() for p in s.args["manifest"].points if p.point_id == pid)
        assert payload == expected and "act_id" in payload and payload["act_id"] is None
        calls.append(pid)
        original(pid, payload)

    s.q.overwrite_payload = overwrite
    s.q.set_payload = lambda *a: pytest.fail("rollback may not merge null")
    assert run_manifest_repair(**s.args, direction="rollback")["payloads_applied"] == 2
    assert len(calls) == 2


def test_absent_key_and_changed_vector_stop_before_pg_or_q_write(setup):
    s = setup
    del s.q.points[s.rows[0].point_id]["act_id"]
    with pytest.raises(MaintenanceError):
        run_manifest_repair(**s.args, direction="rollback")
    assert s.callbacks == s.q.writes == []
    s.q.points[s.rows[0].point_id]["act_id"] = None
    s.q.vector_fingerprint = lambda: "0" * 64
    with pytest.raises(MaintenanceError, match="vectors differ"):
        run_manifest_repair(**s.args, direction="rollback")
    assert s.callbacks == s.q.writes == []


def test_missing_vector_approval_fails_before_lock_or_callbacks(setup):
    with pytest.raises(MaintenanceError, match="approved complete vector"):
        run_manifest_repair(
            **{**setup.args, "expected_vector_fingerprint": None}, direction="rollback"
        )
    assert setup.callbacks == [] and not setup.args["lock_path"].exists()


@pytest.fixture
def concrete(pg, setup, tmp_path):
    seed(pg, active=False)
    seed(pg, text_id=102)
    add_act(pg)
    store = ChunkStore(pg, "pisrs_current")
    rows = [r for batch in store.iter_authoritative_payload_batches() for r in batch]
    q = RecordingQdrant(rows)
    raw = {
        "version": 1,
        "collection": "pisrs_current",
        "point_count": len(rows),
        "collection_fingerprint": collection_fingerprint(
            {r.point_id: payload_leaf(r.point_id, r.payload()) for r in rows}
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
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    directory = parent / "images"
    with MaintenanceOwner(setup.args["lock_path"], setup.checkpoint, setup.args["window"]) as owner:
        approved = capture_pg_images(
            database=pg,
            owner=owner,
            manifest=manifest,
            qdrant=q,
            cache_ids=[],
            directory=directory,
            max_rows=10,
        )
    cb = PgMaintenanceCallbacks(pg, directory, approved, manifest)
    args = {
        **setup.args,
        "manifest": manifest,
        "postgres": SimpleNamespace(chunks=store),
        "qdrant": q,
        "prepare_pg": cb.prepare_pg,
        "acknowledge_pg": cb.acknowledge_pg,
        "readback_pg": cb.readback_pg,
        "expected_vector_fingerprint": cb.vector_fingerprint,
    }
    return SimpleNamespace(
        pg=pg, args=args, cb=cb, q=q, directory=directory, approved=approved, manifest=manifest
    )


def stable_rows(pg):
    with pg.connect(read_only=True) as c:
        return {
            t: c.execute(
                f"SELECT to_jsonb(r)-'updated_at' AS image FROM pisrs.{t} r ORDER BY id"
            ).fetchall()
            for t in ("act_text_versions", "act_text_blocks", "embedding_chunks")
        }


def test_concrete_callbacks_forward_restart_and_inverse_are_exact_noops(concrete):
    s = concrete
    before = stable_rows(s.pg)
    assert run_manifest_repair(**s.args)["payloads_applied"] == 2
    cb = PgMaintenanceCallbacks(s.pg, s.directory, s.approved, s.manifest)
    args = {
        **s.args,
        "prepare_pg": cb.prepare_pg,
        "acknowledge_pg": cb.acknowledge_pg,
        "readback_pg": cb.readback_pg,
    }
    assert run_manifest_repair(**args)["payloads_applied"] == 0
    assert run_manifest_repair(**args, direction="rollback")["payloads_applied"] == 2
    assert stable_rows(s.pg) == before
    assert run_manifest_repair(**args, direction="rollback")["payloads_applied"] == 0
    assert stable_rows(s.pg) == before


@pytest.mark.parametrize(
    "damage", ["checksum", "permissions", "after-image", "omitted-block", "hardlink"]
)
def test_private_image_damage_fails_before_data_updates(concrete, tmp_path, damage):
    s = concrete
    before = stable_rows(s.pg)
    target = tmp_path / "copy"
    shutil.copytree(s.directory, target)
    target.chmod(0o700)
    index = json.loads((target / "index.json").read_text())
    batch = target / index["batches"][0]["file"]
    approved = s.approved
    if damage == "permissions":
        batch.chmod(0o644)
    elif damage == "hardlink":
        os.link(batch, target / "unexpected-hardlink")
    elif damage == "checksum":
        batch.write_text(batch.read_text() + " ")
    elif damage == "omitted-block":
        index["scope"]["act_text_blocks"] = []
        index["batches"] = [b for b in index["batches"] if b["table"] != "act_text_blocks"]
        (target / "index.json").write_text(json.dumps(index))
        approved = hashlib.sha256((target / "index.json").read_bytes()).hexdigest()
    else:
        records = json.loads(batch.read_text())
        records[0]["staged"]["text_id"] = 123456
        batch.write_text(json.dumps(records))
        index["batches"][0]["sha256"] = hashlib.sha256(batch.read_bytes()).hexdigest()
        (target / "index.json").write_text(json.dumps(index))
        approved = hashlib.sha256((target / "index.json").read_bytes()).hexdigest()
    with pytest.raises(MaintenanceError):
        PgMaintenanceCallbacks(s.pg, target, approved, s.manifest)
    assert stable_rows(s.pg) == before and s.q.writes == []


def test_provenance_type_drift_cas_refused_without_earlier_updates(concrete):
    s = concrete
    with s.pg.connect() as c:
        row = c.execute(
            "SELECT id,payload FROM pisrs.embedding_chunks ORDER BY id DESC LIMIT 1"
        ).fetchone()
        row["payload"]["legacy_provenance"]["nested"][0] = True  # bool is not integer 1
        c.execute(
            "UPDATE pisrs.embedding_chunks SET payload=%s WHERE id=%s",
            (Jsonb(row["payload"]), row["id"]),
        )
    before = stable_rows(s.pg)
    with pytest.raises(MaintenanceError, match="unapproved image"):
        run_manifest_repair(**s.args)
    assert stable_rows(s.pg) == before and s.q.writes == []


def test_completed_repair_cannot_be_recaptured_as_original_before_images(concrete, tmp_path):
    s = concrete
    run_manifest_repair(**s.args)
    before = stable_rows(s.pg)
    with (
        MaintenanceOwner(s.args["lock_path"], s.args["checkpoint_path"], s.args["window"]) as owner,
        pytest.raises(MaintenanceError, match="original NULL"),
    ):
        capture_pg_images(
            database=s.pg,
            owner=owner,
            manifest=s.manifest,
            qdrant=s.q,
            cache_ids=[],
            directory=tmp_path / "new-images",
            max_rows=10,
        )
    assert stable_rows(s.pg) == before and not (tmp_path / "new-images").exists()


@pytest.mark.parametrize("change", ["checkpoint", "payload"])
def test_late_vector_read_rechecks_owner_and_all_payload_keys_before_overwrite(setup, change):
    s = setup
    run_manifest_repair(**s.args)
    writes_before = list(s.q.writes)
    original = s.q.point_vector_fingerprint

    def disturb(point_id):
        if change == "checkpoint":
            s.checkpoint.write_bytes(b"unexpected checkpoint")
        else:
            s.q.points[point_id]["title"] = "unexpected external value"
        return original(point_id)

    s.q.point_vector_fingerprint = disturb
    with pytest.raises(MaintenanceError):
        run_manifest_repair(**s.args, direction="rollback")
    assert s.q.writes == writes_before
