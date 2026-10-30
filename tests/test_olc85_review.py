from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from test_core import FakePostgres, FakeQdrant, vector_row

from pisrs_ingest import maintenance
from pisrs_ingest.locking import ApplicationLock, LockLostError
from pisrs_ingest.maintenance import (
    MaintenanceError,
    PinnedManifest,
    SystemdMaintenanceWindow,
    collection_fingerprint,
    payload_leaf,
    run_manifest_repair,
)
from pisrs_ingest.postgres import PostgresInvariantError
from pisrs_ingest.postgres_integrity import refresh_stored_payloads


class RecordingQdrant(FakeQdrant):
    def __init__(self, rows):
        super().__init__(rows)
        self.writes = []

    def set_payload(self, point_id, patch):
        self.writes.append((point_id, copy.deepcopy(patch)))
        super().set_payload(point_id, patch)

    def overwrite_payload(self, point_id, payload):
        self.writes.append((point_id, {"act_id": payload["act_id"]}))
        super().overwrite_payload(point_id, payload)

    def upsert(self, *args):
        pytest.fail("manifest maintenance must never send vectors")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    states = {"timer": "inactive", "masked": True, "jobs": ""}
    service = {
        "LoadState": "masked",
        "UnitFileState": "masked-runtime",
        "ActiveState": "inactive",
        "SubState": "dead",
        "MainPID": "0",
        "ControlPID": "0",
    }

    def properties(unit, keys):
        if unit.endswith(".timer"):
            return {"ActiveState": states["timer"]}
        result = dict(service)
        result["UnitFileState"] = states.get("mask_kind", "masked-runtime")
        if not states["masked"]:
            result.update(LoadState="loaded", UnitFileState="static")
        return result

    real_run = subprocess.run

    def run(args, **kwargs):
        if args[:2] == ["systemctl", "list-jobs"]:
            return SimpleNamespace(stdout=states["jobs"])
        return real_run(args, **kwargs)

    monkeypatch.setattr(SystemdMaintenanceWindow, "_properties", staticmethod(properties))
    monkeypatch.setattr(maintenance.subprocess, "run", run)
    now = datetime(2026, 10, 30, tzinfo=UTC)
    window = SystemdMaintenanceWindow(now + timedelta(minutes=30), clock=lambda: now)
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    checkpoint = tmp_path / "checkpoint"
    checkpoint.write_bytes(b"checkpoint-before")
    rows = [
        replace(vector_row(active=False, latest=False, text_id=101), act_id=None),
        replace(vector_row(active=True, latest=True, text_id=102), act_id=None),
        vector_row(active=True, latest=True, text_id=999),
    ]
    pg = FakePostgres(rows)
    pg.chunks.collection = "pisrs_current"
    q = RecordingQdrant(rows)
    raw = {
        "version": 1,
        "collection": "pisrs_current",
        "point_count": len(rows),
        "collection_fingerprint": collection_fingerprint(
            {r.point_id: payload_leaf(r.point_id, r.payload()) for r in rows}
        ),
        "version_links": [
            {"version_id": r.version_id, "old_act_id": None, "new_act_id": 10} for r in rows[:2]
        ],
        "points": [
            {
                "point_id": r.point_id,
                "old_act_id": None,
                "new_act_id": 10,
                "before_payload": r.payload(),
            }
            for r in rows[:2]
        ],
    }
    body = json.dumps(raw).encode()
    manifest = PinnedManifest.from_bytes(
        body, hashlib.sha256(body).hexdigest(), max_changes=2, max_versions=2
    )
    callbacks = []

    def prepare(owner, pinned, direction):
        owner.check()
        callbacks.append(("pg", id(owner)))
        ids = {p.point_id for p in pinned.points}
        pg.rows = [
            replace(r, act_id=10 if direction == "forward" else None) if r.point_id in ids else r
            for r in pg.rows
        ]

    def ack(owner, *args):
        owner.check()
        callbacks.append(("ack", id(owner)))

    def readback(owner, *args):
        owner.check()
        callbacks.append(("readback", id(owner)))

    arguments = dict(
        lock_path=runtime / "ingest.lock",
        checkpoint_path=checkpoint,
        window=window,
        manifest=manifest,
        postgres=pg,
        qdrant=q,
        prepare_pg=prepare,
        acknowledge_pg=ack,
        readback_pg=readback,
        allow_writes=True,
        allow_external_api=False,
        expected_vector_fingerprint=q.vector_fingerprint(),
    )
    return SimpleNamespace(
        args=arguments,
        pg=pg,
        q=q,
        rows=rows,
        raw=raw,
        body=body,
        states=states,
        callbacks=callbacks,
        checkpoint=checkpoint,
    )


def test_one_owner_pg_payload_apply_readback_and_reverse_apply(setup, monkeypatch):
    s = setup
    before = copy.deepcopy(s.q.points)
    enters = []
    original_enter = ApplicationLock.__enter__

    def enter(lock):
        enters.append(lock)
        return original_enter(lock)

    monkeypatch.setattr(ApplicationLock, "__enter__", enter)
    prepare = s.args["prepare_pg"]

    def with_competitor(owner, manifest, direction):
        code = (
            'import fcntl,sys; f=open(sys.argv[1],"a+")\n'
            "try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
            "except BlockingIOError: sys.exit(75)\n"
            "sys.exit(1)"
        )
        result = subprocess.run([sys.executable, "-B", "-c", code, str(s.args["lock_path"])])
        assert result.returncode == 75
        prepare(owner, manifest, direction)

    s.args["prepare_pg"] = with_competitor
    forward = run_manifest_repair(**s.args)
    assert forward["payloads_applied"] == 2 and len(enters) == 1
    assert len({owner for stage, owner in s.callbacks}) == 1
    allowed = {r.point_id for r in s.rows[:2]}
    assert {pid for pid, patch in s.q.writes} == allowed
    assert all(set(patch) == {"act_id"} and patch["act_id"] == 10 for pid, patch in s.q.writes)
    assert s.q.points[s.rows[-1].point_id] == before[s.rows[-1].point_id]
    assert run_manifest_repair(**s.args)["payloads_applied"] == 0
    assert len(s.q.writes) == 2
    reverse = run_manifest_repair(**s.args, direction="rollback")
    assert reverse["payloads_applied"] == 2
    assert s.q.points == before
    assert all(patch == {"act_id": None} for pid, patch in s.q.writes[2:])
    assert run_manifest_repair(**s.args, direction="rollback")["payloads_applied"] == 0
    assert s.checkpoint.read_bytes() == b"checkpoint-before"


@pytest.mark.parametrize(
    "change", ["other-q", "other-both", "approved-field", "orphan", "missing", "old-act"]
)
def test_unexpected_collection_change_stops_before_pg_or_q_writes(setup, change):
    s = setup
    outside = s.rows[-1]
    if change in ("other-q", "other-both"):
        s.q.points[outside.point_id]["title"] = "unapproved"
        if change == "other-both":
            s.pg.rows = [
                replace(r, title="unapproved") if r.point_id == outside.point_id else r
                for r in s.pg.rows
            ]
    elif change == "approved-field":
        s.q.points[s.rows[0].point_id]["is_active"] = True
    elif change == "orphan":
        s.q.points["unexpected-point"] = outside.payload()
    elif change == "missing":
        del s.q.points[s.rows[0].point_id]
    else:
        s.q.points[s.rows[0].point_id]["act_id"] = 123
    with pytest.raises(MaintenanceError):
        run_manifest_repair(**s.args)
    assert s.callbacks == [] and s.q.writes == []


def test_post_pg_unrelated_drift_cannot_enter_payload_writer(setup):
    s = setup
    prepare = s.args["prepare_pg"]

    def unexpected(owner, pinned, direction):
        prepare(owner, pinned, direction)
        s.pg.rows = [
            replace(r, title="unapproved") if r.point_id == s.rows[-1].point_id else r
            for r in s.pg.rows
        ]

    s.args["prepare_pg"] = unexpected
    with pytest.raises(MaintenanceError, match="outside"):
        run_manifest_repair(**s.args)
    assert s.q.writes == []


def test_partial_payload_failure_resumes_exact_manifest_only(setup):
    s = setup
    original = s.q.set_payload
    calls = 0

    def fail_second(point_id, patch):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fixture interruption")
        original(point_id, patch)

    s.q.set_payload = fail_second
    with pytest.raises(RuntimeError, match="interruption"):
        run_manifest_repair(**s.args)
    assert len(s.q.writes) == 1
    assert [stage for stage, owner in s.callbacks] == ["pg"]
    s.q.set_payload = original
    assert run_manifest_repair(**s.args)["payloads_applied"] == 1
    assert len(s.q.writes) == 2
    assert all(patch == {"act_id": 10} for pid, patch in s.q.writes)


@pytest.mark.parametrize("changed", ["inode", "parent", "checkpoint"])
def test_lost_exclusion_aborts_before_any_payload_write(setup, changed):
    s = setup
    prepare = s.args["prepare_pg"]

    def lose(owner, pinned, direction):
        prepare(owner, pinned, direction)
        path = s.args["lock_path"]
        if changed == "checkpoint":
            s.checkpoint.write_bytes(b"unexpected-checkpoint")
        else:
            path.unlink()
            if changed == "parent":
                path.parent.rmdir()
                path.parent.mkdir(mode=0o700)
            path.write_text("different inode")

    s.args["prepare_pg"] = lose
    with pytest.raises((MaintenanceError, LockLostError)):
        run_manifest_repair(**s.args)
    assert s.q.writes == []


@pytest.mark.parametrize("unsafe", ["active-timer", "unmasked", "queued-job", "deadline"])
def test_maintenance_window_must_be_executable_not_owner_assurance(setup, unsafe):
    s = setup
    if unsafe == "active-timer":
        s.states["timer"] = "active"
    elif unsafe == "unmasked":
        s.states["masked"] = False
    elif unsafe == "queued-job":
        s.states["jobs"] = "1 pisrs-ingest.service start waiting"
    else:
        s.args["window"].clock = lambda: s.args["window"].deadline
    with pytest.raises(MaintenanceError):
        run_manifest_repair(**s.args)
    assert s.callbacks == [] and s.q.writes == [] and not s.args["lock_path"].exists()


def test_no_write_authorization_or_recomputed_approval(setup):
    s = setup
    with pytest.raises(MaintenanceError, match="explicit writes"):
        run_manifest_repair(**{**s.args, "allow_writes": False})
    with pytest.raises(MaintenanceError, match="approved hash"):
        PinnedManifest.from_bytes(s.body, "0" * 64, max_changes=2, max_versions=2)
    assert s.callbacks == [] and s.q.writes == []


@pytest.mark.parametrize(
    "invalid",
    ["extra-key", "bad-act", "duplicate", "wrong-uuid", "changed-binding", "extra-version"],
)
def test_manifest_is_pinned_to_exact_approved_id_and_act_id_transition(setup, invalid):
    raw = copy.deepcopy(setup.raw)
    p = raw["points"][0]
    if invalid == "extra-key":
        p["patch"] = {"title": "not allowed"}
    elif invalid == "bad-act":
        p["new_act_id"] = True
    elif invalid == "duplicate":
        raw["points"].append(copy.deepcopy(p))
    elif invalid == "wrong-uuid":
        p["point_id"] = "ffffffff-ffff-5fff-bfff-ffffffffffff"
    elif invalid == "changed-binding":
        p["before_payload"]["act_id"] = 10
    else:
        raw["version_links"].append(copy.deepcopy(raw["version_links"][0]))
    body = json.dumps(raw).encode()
    with pytest.raises(MaintenanceError):
        PinnedManifest.from_bytes(
            body, hashlib.sha256(body).hexdigest(), max_changes=10, max_versions=10
        )


def test_last_moment_payload_change_stops_before_write(setup):
    s = setup
    original = s.q.get_point

    def changed(point_id):
        s.q.points[point_id]["unexpected"] = "unapproved"
        return original(point_id)

    s.q.get_point = changed
    with pytest.raises(MaintenanceError):
        run_manifest_repair(**s.args)
    assert s.q.writes == []


@pytest.mark.parametrize("ids", [None, list(range(1, 1002)), [1, 1], [True], [-1], ["1"], (1,)])
def test_json_refresh_rejects_unbounded_or_invalid_pk_scope_before_sql(ids):
    cursor = SimpleNamespace(execute=lambda *a: pytest.fail("invalid scope reached SQL"))
    with pytest.raises(PostgresInvariantError):
        refresh_stored_payloads(cursor, "pisrs_current", ids=ids)


def test_json_refresh_has_no_unbounded_or_sop_backdoor():
    cursor = SimpleNamespace(execute=lambda *a: pytest.fail("unscoped update"))
    with pytest.raises(TypeError):
        refresh_stored_payloads(cursor, "pisrs_current")
    with pytest.raises(TypeError):
        refresh_stored_payloads(cursor, "pisrs_current", sop="SOP-1")


def test_misidentified_point_response_is_rejected_before_write(setup):
    from pisrs_ingest.qdrant import PointState

    s = setup
    original = s.q.get_point

    def wrong_identity(point_id):
        state = original(point_id)
        return PointState("wrong-point-id", state.payload)

    s.q.get_point = wrong_identity
    with pytest.raises(MaintenanceError, match="changed identity"):
        run_manifest_repair(**s.args)
    assert s.q.writes == []


def test_unrelated_late_change_cannot_receive_a_success_readback(setup):
    s = setup
    original = s.q.set_payload

    def unrelated_change(point_id, patch):
        original(point_id, patch)
        s.q.points[s.rows[-1].point_id]["title"] = "unexpected late writer"

    s.q.set_payload = unrelated_change
    with pytest.raises(MaintenanceError, match="outside"):
        run_manifest_repair(**s.args)
    assert all(set(patch) == {"act_id"} for pid, patch in s.q.writes)
    assert all(pid in {p.point_id for p in s.args["manifest"].points} for pid, patch in s.q.writes)
    assert [stage for stage, owner in s.callbacks] == ["pg"]


@pytest.mark.parametrize("flag", [True, None, 1])
def test_external_authorization_must_be_explicitly_false(setup, flag):
    s = setup
    with pytest.raises(MaintenanceError, match="external=false"):
        run_manifest_repair(**{**s.args, "allow_external_api": flag})
    assert s.q.writes == [] and s.callbacks == []


def test_effective_local_unit_mask_is_accepted_without_assuming_runtime_precedence(setup):
    setup.states["mask_kind"] = "masked"
    assert run_manifest_repair(**setup.args)["payloads_applied"] == 2


def test_absent_runtime_directory_stops_without_creating_it(setup):
    s = setup
    s.args["lock_path"].parent.rmdir()
    with pytest.raises(MaintenanceError, match="already exist"):
        run_manifest_repair(**s.args)
    assert not s.args["lock_path"].parent.exists()
    assert s.callbacks == [] and s.q.writes == []
