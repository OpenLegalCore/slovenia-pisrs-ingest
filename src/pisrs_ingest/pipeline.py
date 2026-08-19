"""Explicit linear nightly flow and bounded payload-only reconciliation."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .checkpoint import CheckpointStore, Interval
from .models import MANAGED_PAYLOAD_KEYS, VectorRow, parse_html, qdrant_point_id
from .qdrant import PointState, inspect_payload, payload_patch

LOGGER = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Raised when a bounded run cannot safely complete its interval."""


@dataclass(frozen=True)
class DocumentFailure:
    text_id: int
    phase: str
    error_type: str


class DocumentBatchError(PipelineError):
    def __init__(self, failures: list[DocumentFailure]) -> None:
        self.failures = failures
        summary = ", ".join(f"{item.text_id}:{item.phase}" for item in failures)
        super().__init__(
            f"{len(failures)} document(s) failed; checkpoint retained; failures={summary}"
        )


@dataclass
class NightlyStats:
    interval_start: str
    interval_end: str
    acts_discovered: int = 0
    npbs_discovered: int = 0
    versions_imported: int = 0
    documents_failed: int = 0
    sops_touched: int = 0
    vectors_embedded: int = 0
    vectors_reused: int = 0
    payloads_updated: int = 0
    inactive_points_missing: int = 0


@dataclass(frozen=True)
class PayloadChange:
    point_id: str
    patch: dict[str, Any]
    reason: str = "authoritative_payload_drift"


@dataclass
class ReconcilePlan:
    checked: int = 0
    qdrant_checked: int = 0
    change_count: int = 0
    changes: list[PayloadChange] = field(default_factory=list)
    missing_count: int = 0
    missing_examples: list[str] = field(default_factory=list)
    orphan_count: int = 0
    orphan_examples: list[str] = field(default_factory=list)
    orphan_deactivation_count: int = 0
    unsafe_point_count: int = 0
    unsafe_point_examples: list[str] = field(default_factory=list)
    unsafe_payload_count: int = 0
    unsafe_payload_examples: list[str] = field(default_factory=list)
    overflow: bool = False

    def summary(self) -> dict[str, Any]:
        return {
            "postgres_points_checked": self.checked,
            "qdrant_points_checked": self.qdrant_checked,
            "payload_changes": self.change_count,
            "missing_points": self.missing_count,
            "missing_examples": self.missing_examples,
            "orphan_points": self.orphan_count,
            "orphan_examples": self.orphan_examples,
            "orphan_deactivations": self.orphan_deactivation_count,
            "unsafe_points": self.unsafe_point_count,
            "unsafe_point_examples": self.unsafe_point_examples,
            "unsafe_payloads": self.unsafe_payload_count,
            "unsafe_payload_examples": self.unsafe_payload_examples,
            "change_limit_exceeded": self.overflow,
        }


def run_nightly(
    *,
    client: Any,
    postgres: Any,
    embedder: Any,
    qdrant: Any,
    checkpoint: CheckpointStore,
    model: str,
    dimensions: int,
    max_documents: int,
    embed_batch_size: int,
    max_embedding_input_bytes: int,
    interval: Interval | None = None,
    now: datetime | None = None,
) -> NightlyStats:
    """Run one interval; checkpoint advancement is deliberately the final statement."""

    interval = interval or checkpoint.interval(now or datetime.now(UTC))
    stats = NightlyStats(
        interval_start=interval.start.isoformat(), interval_end=interval.end.isoformat()
    )

    acts = client.discover_acts()
    npbs = client.discover_npbs()
    stats.acts_discovered = len(acts)
    stats.npbs_discovered = len(npbs)
    postgres.catalogs.synchronize(acts, npbs)

    pending = postgres.documents.pending(max_documents + 1, interval.start)
    if len(pending) > max_documents:
        raise PipelineError(
            f"new/changed document count exceeds PISRS_MAX_DOCUMENTS_PER_RUN={max_documents}"
        )
    failures: list[DocumentFailure] = []
    for document in pending:
        phase = "fetch"
        try:
            html = client.fetch_text(document.text_id)
            phase = "parse"
            parsed = parse_html(html)
            phase = "postgres_persist"
            postgres.documents.synchronize(document, parsed, client.source_url(document.text_id))
            stats.versions_imported += 1
        except Exception as exc:
            failure = DocumentFailure(document.text_id, phase, type(exc).__name__)
            failures.append(failure)
            LOGGER.error(
                json.dumps(
                    {
                        "event": "document_failure",
                        "text_id": failure.text_id,
                        "phase": failure.phase,
                        "error_type": failure.error_type,
                    },
                    sort_keys=True,
                )
            )
    stats.documents_failed = len(failures)

    touched_sops = postgres.chunks.touched_sops(interval.start)
    stats.sops_touched = len(touched_sops)
    rollover_rows: list[VectorRow] = []
    for sop in touched_sops:
        rollover_rows.extend(postgres.chunks.prepare_rollover(sop, model, dimensions))
    rows = _final_rollover_rows(postgres.chunks, rollover_rows)

    qdrant.validate_collection(dimensions, model)
    _ensure_vectors_and_payloads(
        rows=rows,
        chunks=postgres.chunks,
        embedder=embedder,
        qdrant=qdrant,
        embed_batch_size=embed_batch_size,
        max_embedding_input_bytes=max_embedding_input_bytes,
        stats=stats,
    )

    if failures:
        raise DocumentBatchError(failures)
    checkpoint.advance(interval.end)
    return stats


def _final_rollover_rows(chunks: Any, candidates: list[VectorRow]) -> list[VectorRow]:
    point_ids = {row.point_id for row in candidates}
    final_by_id: dict[str, VectorRow] = {}
    for row in chunks.rows_for_point_ids(point_ids) if point_ids else []:
        if row.point_id in final_by_id:
            raise PipelineError("PostgreSQL returned duplicate final rollover point IDs")
        final_by_id[row.point_id] = row
    if set(final_by_id) != point_ids:
        raise PipelineError(
            "PostgreSQL did not return exactly one final row for every rollover point ID"
        )
    return [final_by_id[point_id] for point_id in sorted(point_ids)]


def _ensure_vectors_and_payloads(
    *,
    rows: list[VectorRow],
    chunks: Any,
    embedder: Any,
    qdrant: Any,
    embed_batch_size: int,
    max_embedding_input_bytes: int,
    stats: NightlyStats,
) -> None:
    active_rows = [row for row in rows if row.is_active and row.is_latest_for_sop]
    planned_batches: list[tuple[list[tuple[VectorRow, PointState]], list[VectorRow]]] = []
    for start in range(0, len(active_rows), embed_batch_size):
        batch = active_rows[start : start + embed_batch_size]
        reusable: list[tuple[VectorRow, PointState]] = []
        needs_embedding: list[VectorRow] = []
        for row in batch:
            state = qdrant.get_point(row.point_id)
            if state is not None and _vector_contract_matches(row, state):
                reusable.append((row, state))
            else:
                needs_embedding.append(row)
        planned_batches.append((reusable, needs_embedding))

    embedding_input_bytes = sum(
        len(row.chunk_text.encode("utf-8"))
        for _, needs_embedding in planned_batches
        for row in needs_embedding
    )
    if embedding_input_bytes > max_embedding_input_bytes:
        raise PipelineError(
            f"embedding input is {embedding_input_bytes} bytes; exceeds "
            "PISRS_MAX_EMBEDDING_INPUT_BYTES_PER_RUN="
            f"{max_embedding_input_bytes}"
        )

    for reusable, needs_embedding in planned_batches:
        for row, state in reusable:
            patch = payload_patch(row.payload(), state.payload)
            if patch:
                qdrant.set_payload(row.point_id, patch)
                stats.payloads_updated += 1
        if needs_embedding:
            vectors = embedder.embed([row.chunk_text for row in needs_embedding])
            qdrant.upsert(needs_embedding, vectors)
            stats.vectors_embedded += len(needs_embedding)
        if reusable:
            stats.vectors_reused += len(reusable)
        chunks.mark_uploaded([*(row for row, _ in reusable), *needs_embedding])

    for row in rows:
        if row.is_active and row.is_latest_for_sop:
            continue
        state = qdrant.get_point(row.point_id)
        if state is None:
            stats.inactive_points_missing += 1
            continue
        patch = payload_patch(row.payload(), state.payload)
        if patch:
            qdrant.set_payload(row.point_id, patch)
            stats.payloads_updated += 1


def _vector_contract_matches(row: VectorRow, state: PointState) -> bool:
    return (
        state.payload.get("content_hash") == row.content_hash
        and state.payload.get("embedding_model") == row.embedding_model
        and state.payload.get("embedding_dimensions") == row.embedding_dimensions
    )


def _append_change(plan: ReconcilePlan, change: PayloadChange, max_changes: int) -> None:
    plan.change_count += 1
    if len(plan.changes) < max_changes:
        plan.changes.append(change)
    else:
        plan.overflow = True


def plan_reconciliation(postgres: Any, qdrant: Any, max_changes: int) -> ReconcilePlan:
    """Fully compare authoritative PG payloads and all Qdrant IDs without writes."""

    qdrant.validate_collection()
    plan = ReconcilePlan()
    authoritative_ids: set[str] = set()
    for batch in postgres.chunks.iter_authoritative_payload_batches():
        batch_ids = [row.point_id for row in batch]
        if len(batch_ids) != len(set(batch_ids)) or authoritative_ids.intersection(batch_ids):
            raise PipelineError("PostgreSQL contains duplicate authoritative Qdrant point IDs")
        authoritative_ids.update(batch_ids)
        points = qdrant.retrieve_points(batch_ids)
        for row in batch:
            plan.checked += 1
            state = points.get(row.point_id)
            if state is None:
                plan.missing_count += 1
                if len(plan.missing_examples) < 5:
                    plan.missing_examples.append(row.point_id)
                continue
            inspection = inspect_payload(row.payload(), state.payload)
            if inspection.unexpected_keys:
                plan.unsafe_payload_count += 1
                if len(plan.unsafe_payload_examples) < 5:
                    plan.unsafe_payload_examples.append(row.point_id)
            elif inspection.patch:
                _append_change(
                    plan,
                    PayloadChange(row.point_id, inspection.patch),
                    max_changes,
                )

    qdrant_ids: set[str] = set()
    for batch in qdrant.iter_point_batches():
        for point in batch:
            plan.qdrant_checked += 1
            if point.point_id in qdrant_ids:
                raise PipelineError("Qdrant complete scroll returned a duplicate point ID")
            qdrant_ids.add(point.point_id)
            if point.point_id in authoritative_ids:
                continue
            plan.orphan_count += 1
            if len(plan.orphan_examples) < 5:
                plan.orphan_examples.append(point.point_id)
            if set(point.payload) - MANAGED_PAYLOAD_KEYS:
                plan.unsafe_payload_count += 1
                if len(plan.unsafe_payload_examples) < 5:
                    plan.unsafe_payload_examples.append(point.point_id)
                continue
            if not _has_proven_orphan_identity(point):
                plan.unsafe_point_count += 1
                if len(plan.unsafe_point_examples) < 5:
                    plan.unsafe_point_examples.append(point.point_id)
                continue
            patch = {
                key: False
                for key in ("is_active", "is_latest_for_sop")
                if point.payload.get(key) is not False
            }
            if patch:
                plan.orphan_deactivation_count += 1
                _append_change(
                    plan,
                    PayloadChange(point.point_id, patch, reason="orphan_deactivation"),
                    max_changes,
                )
    return plan


def _has_proven_orphan_identity(point: PointState) -> bool:
    payload = point.payload
    text_id = payload.get("text_id")
    chunk_index = payload.get("chunk_index")
    if (
        payload.get("source") != "pisrs"
        or payload.get("collection_name") != "pisrs_current"
        or type(text_id) is not int
        or text_id <= 0
        or type(chunk_index) is not int
        or chunk_index < 0
    ):
        return False
    try:
        parsed = uuid.UUID(point.point_id)
    except (ValueError, AttributeError):
        return False
    return parsed.version == 5 and point.point_id == qdrant_point_id(
        "pisrs_current", text_id, chunk_index
    )


def apply_reconciliation(plan: ReconcilePlan, qdrant: Any) -> None:
    """Apply a completed capped plan; never create/delete vectors or request embeddings."""

    if plan.missing_count:
        raise PipelineError(
            "reconciliation found points missing from Qdrant; "
            "payload-only repair cannot create vectors"
        )
    if plan.unsafe_payload_count:
        raise PipelineError(
            "reconciliation found unexpected payload keys; removal requires a separate approval"
        )
    if plan.unsafe_point_count:
        raise PipelineError(
            "reconciliation found orphan points without a provable PISRS payload identity"
        )
    if plan.overflow:
        raise PipelineError("reconciliation change count exceeds PISRS_RECONCILE_MAX_CHANGES")
    for change in plan.changes:
        if change.reason == "orphan_deactivation" and (
            set(change.patch) - {"is_active", "is_latest_for_sop"}
            or any(value is not False for value in change.patch.values())
        ):
            raise PipelineError("orphan plan contains a non-deactivation mutation")
        qdrant.set_payload(change.point_id, change.patch)
