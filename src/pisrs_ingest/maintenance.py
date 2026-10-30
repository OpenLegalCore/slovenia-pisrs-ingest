"""One-owner maintenance and approved-manifest-only act_id payload writes.

Library entry point only. No generic reconcile/apply subprocess or embedding client.
Production execution requires a separately authorized exclusive maintenance window.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .locking import ApplicationLock
from .models import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    MANAGED_PAYLOAD_KEYS,
    canonical_content_hash,
    qdrant_point_id,
)


class MaintenanceError(RuntimeError):
    """An approval, exclusion, identity or readback precondition failed."""


def _json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )


def _positive(value: Any) -> bool:
    return type(value) is int and value > 0


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise MaintenanceError("duplicate manifest key")
        value[key] = item
    return value


def payload_leaf(point_id: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json([point_id, payload]).encode()).hexdigest()


def collection_fingerprint(leaves: dict[str, str]) -> str:
    digest = hashlib.sha256(b"pisrs-maintenance-v1\n")
    for point_id in sorted(leaves):
        digest.update(point_id.encode() + b"\0" + bytes.fromhex(leaves[point_id]) + b"\n")
    return digest.hexdigest()


@dataclass(frozen=True)
class ManifestPoint:
    point_id: str
    new_act_id: int
    before_json: str

    def before(self) -> dict[str, Any]:
        return json.loads(self.before_json)

    def target(self, direction: str) -> dict[str, Any]:
        value = self.before()
        if direction == "forward":
            value["act_id"] = self.new_act_id
        return value


@dataclass(frozen=True, init=False)
class PinnedManifest:
    points: tuple[ManifestPoint, ...]
    version_links: tuple[tuple[int, int], ...]
    point_count: int
    fingerprint: str
    approved_sha256: str

    @classmethod
    def from_bytes(
        cls, body: bytes, approved_sha256: str, *, max_changes: int, max_versions: int
    ) -> PinnedManifest:
        if (
            not isinstance(approved_sha256, str)
            or len(body) > 32 * 1024 * 1024
            or not _positive(max_changes)
            or not _positive(max_versions)
            or not re.fullmatch(r"[0-9a-f]{64}", approved_sha256)
            or hashlib.sha256(body).hexdigest() != approved_sha256
        ):
            raise MaintenanceError("manifest differs from its explicit approved hash or budget")
        try:
            raw = json.loads(body, object_pairs_hook=_pairs)
            if set(raw) != {
                "version",
                "collection",
                "points",
                "version_links",
                "point_count",
                "collection_fingerprint",
            }:
                raise MaintenanceError("unknown manifest schema")
            if (
                type(raw["version"]) is not int
                or raw["version"] != 1
                or raw["collection"] != "pisrs_current"
            ):
                raise MaintenanceError("manifest collection/version mismatch")
            if not _positive(raw["point_count"]) or not re.fullmatch(
                r"[0-9a-f]{64}", raw["collection_fingerprint"]
            ):
                raise MaintenanceError("invalid full-collection baseline")
            if (
                not isinstance(raw["version_links"], list)
                or len(raw["version_links"]) > max_versions
            ):
                raise MaintenanceError("version map exceeds approved budget")
            links = {}
            for link in raw["version_links"]:
                if (
                    set(link) != {"version_id", "old_act_id", "new_act_id"}
                    or link["old_act_id"] is not None
                    or not _positive(link["version_id"])
                    or not _positive(link["new_act_id"])
                    or link["version_id"] in links
                ):
                    raise MaintenanceError("invalid or duplicate approved version link")
                links[link["version_id"]] = link["new_act_id"]
            if (
                not isinstance(raw["points"], list)
                or not raw["points"]
                or len(raw["points"]) > max_changes
                or len(raw["points"]) > raw["point_count"]
            ):
                raise MaintenanceError("point manifest exceeds approved budget")
            points = []
            seen = set()
            for entry in raw["points"]:
                if set(entry) != {"point_id", "old_act_id", "new_act_id", "before_payload"}:
                    raise MaintenanceError("unexpected manifest point field")
                before = entry["before_payload"]
                if (
                    not isinstance(before, dict)
                    or set(before) != MANAGED_PAYLOAD_KEYS
                    or entry["old_act_id"] is not None
                    or before["act_id"] is not None
                    or not _positive(entry["new_act_id"])
                    or not _positive(before["text_id"])
                    or not _positive(before["version_id"])
                    or type(before["chunk_index"]) is not int
                    or before["chunk_index"] < 0
                    or type(before["is_active"]) is not bool
                    or type(before["is_latest_for_sop"]) is not bool
                    or type(before["embedding_dimensions"]) is not int
                    or before["embedding_dimensions"] != EMBEDDING_DIMENSIONS
                    or before["embedding_model"] != EMBEDDING_MODEL
                    or before["source"] != "pisrs"
                    or before["collection_name"] != "pisrs_current"
                    or not isinstance(before["text"], str)
                    or canonical_content_hash(before["text"]) != before["content_hash"]
                    or links.get(before["version_id"]) != entry["new_act_id"]
                ):
                    raise MaintenanceError("manifest payload identity/contract mismatch")
                point_id = entry["point_id"]
                if (
                    point_id
                    != qdrant_point_id("pisrs_current", before["text_id"], before["chunk_index"])
                    or point_id in seen
                ):
                    raise MaintenanceError("noncanonical or duplicate approved point ID")
                seen.add(point_id)
                points.append(ManifestPoint(point_id, entry["new_act_id"], _json(before)))
            if {point.before()["version_id"] for point in points} != set(links):
                raise MaintenanceError("every approved version requires manifest points")
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise MaintenanceError("invalid manifest") from exc
        result = object.__new__(cls)
        for name, value in (
            ("points", tuple(sorted(points, key=lambda x: x.point_id))),
            ("version_links", tuple(sorted(links.items()))),
            ("point_count", raw["point_count"]),
            ("fingerprint", raw["collection_fingerprint"]),
            ("approved_sha256", approved_sha256),
        ):
            object.__setattr__(result, name, value)
        return result


class SystemdMaintenanceWindow:
    """Read-only guard. Never stops, masks, starts or edits a unit itself."""

    def __init__(
        self, deadline: datetime, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ):
        now = clock()
        if deadline.tzinfo is None or not now < deadline <= now + timedelta(hours=2):
            raise MaintenanceError("a maintenance deadline within two hours is required")
        self.deadline = deadline
        self.clock = clock

    @staticmethod
    def _properties(unit: str, keys: tuple[str, ...]) -> dict[str, str]:
        args = ["systemctl", "show", unit]
        for key in keys:
            args.extend(("-p", key))
        r = subprocess.run(args, check=True, capture_output=True, text=True, timeout=5)
        return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)

    def check(self) -> None:
        if self.clock() + timedelta(seconds=30) >= self.deadline:
            raise MaintenanceError("maintenance deadline reached")
        service = self._properties(
            "pisrs-ingest.service",
            ("LoadState", "UnitFileState", "ActiveState", "SubState", "MainPID", "ControlPID"),
        )
        expected = {
            "LoadState": "masked",
            "ActiveState": "inactive",
            "SubState": "dead",
            "MainPID": "0",
            "ControlPID": "0",
        }
        if service.get("UnitFileState") not in ("masked", "masked-runtime") or any(
            service.get(key) != value for key, value in expected.items()
        ):
            raise MaintenanceError("service start exclusion is not established")
        timer = self._properties("pisrs-ingest.timer", ("ActiveState",))
        if timer != {"ActiveState": "inactive"}:
            raise MaintenanceError("timer is not excluded from the maintenance window")
        jobs = subprocess.run(
            ["systemctl", "list-jobs", "--no-legend", "--no-pager"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        if "pisrs-ingest.service" in jobs or "pisrs-ingest.timer" in jobs:
            raise MaintenanceError("an ingest systemd job remains queued")


class MaintenanceOwner:
    """One live owner/inode from the first PG write through final readback."""

    def __init__(self, lock_path: Path, checkpoint_path: Path, window: Any):
        self.lock = ApplicationLock(lock_path)
        self.checkpoint_path = checkpoint_path
        self.window = window
        self.checkpoint_before: bytes | None = None
        self.parent_identity = None

    def __enter__(self) -> MaintenanceOwner:
        self.window.check()
        parent = self.lock.path.parent
        if parent.is_symlink() or not parent.is_dir():
            raise MaintenanceError("canonical runtime lock directory must already exist")
        s = parent.stat()
        if s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
            raise MaintenanceError("runtime directory owner/mode is not exclusive")
        self.parent_identity = (s.st_dev, s.st_ino)
        self.checkpoint_before = self.checkpoint_path.read_bytes()
        self.lock.__enter__()
        try:
            self.check()
        except BaseException:
            self.lock.__exit__(None, None, None)
            raise
        return self

    def check(self, *, read_only: bool = False) -> None:
        if read_only:
            if self.window.clock() + timedelta(seconds=30) >= self.window.deadline:
                raise MaintenanceError("maintenance deadline reached")
        else:
            self.window.check()
        self.lock.assert_owned()
        parent = self.lock.path.parent.stat(follow_symlinks=False)
        if (parent.st_dev, parent.st_ino) != self.parent_identity:
            raise MaintenanceError("runtime directory inode changed")
        if self.checkpoint_path.read_bytes() != self.checkpoint_before:
            raise MaintenanceError("checkpoint changed during maintenance")

    def __exit__(self, *args: object) -> None:
        self.lock.__exit__(*args)


def _normal_payload(point: ManifestPoint, actual: dict[str, Any]) -> dict[str, Any]:
    if _json(actual) not in (point.before_json, _json(point.target("forward"))):
        raise MaintenanceError("manifest point acquired an unexpected payload")
    return point.before()


def _verify_scope(
    owner: MaintenanceOwner,
    manifest: PinnedManifest,
    postgres: Any,
    qdrant: Any,
    direction: str,
    *,
    target_pg: bool,
    target_q: bool,
) -> list[str]:
    """Full prewrite/readback, normalized only for approved act_id transitions."""

    owner.check()
    qdrant.validate_collection()
    approved = {point.point_id: point for point in manifest.points}
    expected_by_version = {version_id: set() for version_id, _ in manifest.version_links}
    for point in manifest.points:
        expected_by_version[point.before()["version_id"]].add(point.point_id)
    pg_by_version = {version_id: set() for version_id in expected_by_version}
    pg_leaves = {}
    for batch in postgres.chunks.iter_authoritative_payload_batches():
        owner.check(read_only=True)
        for row in batch:
            if row.point_id in pg_leaves:
                raise MaintenanceError("duplicate authoritative point")
            if row.collection_name != "pisrs_current" or row.point_id != qdrant_point_id(
                row.collection_name, row.text_id, row.chunk_index
            ):
                raise MaintenanceError("noncanonical authoritative point identity")
            payload = row.payload()
            if row.version_id in pg_by_version:
                pg_by_version[row.version_id].add(row.point_id)
            if row.point_id in approved:
                point = approved[row.point_id]
                normalized = _normal_payload(point, payload)
                if target_pg and _json(payload) != _json(point.target(direction)):
                    raise MaintenanceError("PG repair does not match the approved target")
            else:
                normalized = payload
            pg_leaves[row.point_id] = payload_leaf(row.point_id, normalized)
    # This gate runs in the initial read-only verification, before prepare_pg.
    # A baseline hash alone cannot prove that every affected sibling was approved.
    if pg_by_version != expected_by_version:
        raise MaintenanceError("manifest does not cover exactly all PG points per version")
    if (
        len(pg_leaves) != manifest.point_count
        or not set(approved) <= pg_leaves.keys()
        or collection_fingerprint(pg_leaves) != manifest.fingerprint
    ):
        raise MaintenanceError("PG collection changed outside the approved act_id transition")
    q_leaves = {}
    q_by_version = {version_id: set() for version_id in expected_by_version}
    pending = []
    for batch in qdrant.iter_point_batches():
        owner.check(read_only=True)
        for state in batch:
            if state.point_id in q_leaves or state.point_id not in pg_leaves:
                raise MaintenanceError("duplicate or orphan Qdrant point")
            actual = state.payload
            version_id = actual.get("version_id")
            if type(version_id) is int and version_id in q_by_version:
                q_by_version[version_id].add(state.point_id)
            if state.point_id in approved:
                point = approved[state.point_id]
                normalized = _normal_payload(point, actual)
                if _json(actual) != _json(point.target(direction)):
                    if target_q:
                        raise MaintenanceError("Qdrant readback differs from the approved target")
                    pending.append(state.point_id)
            else:
                normalized = actual
            leaf = payload_leaf(state.point_id, normalized)
            if leaf != pg_leaves[state.point_id]:
                raise MaintenanceError("Qdrant drift outside the pinned act_id transition")
            q_leaves[state.point_id] = leaf
    if q_by_version != expected_by_version:
        raise MaintenanceError("manifest does not cover exactly all Qdrant points per version")
    if (
        len(q_leaves) != manifest.point_count
        or collection_fingerprint(q_leaves) != manifest.fingerprint
    ):
        raise MaintenanceError("Qdrant collection baseline is incomplete or changed")
    owner.check()
    return sorted(pending)


def run_manifest_repair(
    *,
    lock_path: Path,
    checkpoint_path: Path,
    window: Any,
    manifest: PinnedManifest,
    postgres: Any,
    qdrant: Any,
    prepare_pg: Callable,
    acknowledge_pg: Callable,
    readback_pg: Callable,
    direction: str = "forward",
    allow_writes: bool = False,
    allow_external_api: bool = False,
    expected_vector_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Single process, single lock; callbacks never invoke a locking CLI.

    For rollback use the same approved manifest and callbacks restoring PG before-
    images under this owner. Replays accept already-applied per-point transitions.
    No unrelated point/key is exposed as a possible Qdrant mutation.
    """

    if allow_writes is not True or allow_external_api is not False:
        raise MaintenanceError("maintenance requires explicit writes=true and external=false")
    if type(window) is not SystemdMaintenanceWindow:
        raise MaintenanceError("maintenance requires the executable systemd exclusion guard")
    if qdrant.collection != "pisrs_current" or postgres.chunks.collection != "pisrs_current":
        raise MaintenanceError("maintenance collection differs from the approved manifest")
    if direction not in ("forward", "rollback") or not isinstance(manifest, PinnedManifest):
        raise MaintenanceError("invalid repair direction or unapproved manifest")
    if expected_vector_fingerprint is not None and not re.fullmatch(
        r"[0-9a-f]{64}", expected_vector_fingerprint
    ):
        raise MaintenanceError("invalid approved vector fingerprint")
    if direction == "rollback" and expected_vector_fingerprint is None:
        raise MaintenanceError("rollback requires an approved complete vector fingerprint")
    approved = {point.point_id: point for point in manifest.points}
    with MaintenanceOwner(lock_path, checkpoint_path, window) as owner:
        _verify_scope(owner, manifest, postgres, qdrant, direction, target_pg=False, target_q=False)
        if (
            expected_vector_fingerprint is not None
            and qdrant.vector_fingerprint() != expected_vector_fingerprint
        ):
            raise MaintenanceError("Qdrant vectors differ from the approved baseline")
        owner.check()
        prepare_pg(owner, manifest, direction)
        pending = _verify_scope(
            owner, manifest, postgres, qdrant, direction, target_pg=True, target_q=False
        )
        applied = 0
        for point_id in pending:
            owner.check()
            point = approved[point_id]
            current = qdrant.get_point(point_id)
            if current is None or current.point_id != point_id:
                raise MaintenanceError(
                    "approved point disappeared or changed identity before payload write"
                )
            _normal_payload(point, current.payload)
            target = point.target(direction)
            if _json(current.payload) != _json(target):
                owner.check()
                if direction == "rollback":
                    # set_payload(null) deletes the key on Qdrant 1.17.1.
                    # Full replacement is pinned to this exact approved before-image.
                    vector_before = qdrant.point_vector_fingerprint(point_id)
                    owner.check()
                    latest = qdrant.get_point(point_id)
                    if latest is None or latest.point_id != point_id:
                        raise MaintenanceError("approved point identity changed before restore")
                    _normal_payload(point, latest.payload)
                    owner.check()
                    qdrant.overwrite_payload(point_id, point.before())
                    if qdrant.point_vector_fingerprint(point_id) != vector_before:
                        raise MaintenanceError("approved point vector changed during restore")
                else:
                    qdrant.set_payload(point_id, {"act_id": target["act_id"]})
                applied += 1
            readback = qdrant.get_point(point_id)
            if (
                readback is None
                or readback.point_id != point_id
                or _json(readback.payload) != _json(target)
            ):
                raise MaintenanceError("approved point payload readback failed")
        _verify_scope(owner, manifest, postgres, qdrant, direction, target_pg=True, target_q=True)
        owner.check()
        acknowledge_pg(owner, manifest, direction)
        readback_pg(owner, manifest, direction)
        _verify_scope(owner, manifest, postgres, qdrant, direction, target_pg=True, target_q=True)
        if (
            expected_vector_fingerprint is not None
            and qdrant.vector_fingerprint() != expected_vector_fingerprint
        ):
            raise MaintenanceError("Qdrant vectors changed during maintenance")
        owner.check()
    return {
        "manifest_sha256": manifest.approved_sha256,
        "direction": direction,
        "payloads_applied": applied,
        "collection_points_readback": manifest.point_count,
        "checkpoint_unchanged": True,
        "other_payloads_changed": 0,
    }
