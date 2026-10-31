"""Scoped materialization of managed PostgreSQL chunk payload fields."""

from __future__ import annotations

import re
from typing import Any

from .models import CANONICAL_PAYLOAD_COLUMNS
from .postgres import PostgresInvariantError


def canonical_payload_sql(alias: str = "chunk") -> str:
    """Use the same fixed field map as the Python/Qdrant representation."""

    if not re.fullmatch(r"[a-z_]+", alias):
        raise ValueError("SQL alias must be a fixed identifier")
    fields = ["'source'", "'pisrs'"]
    for key, column in CANONICAL_PAYLOAD_COLUMNS.items():
        fields.extend((f"'{key}'", f"{alias}.{column}"))
    return "jsonb_build_object(" + ", ".join(fields) + ")"


def refresh_stored_payloads(
    cursor: Any, collection: str, *, sop: str | None = None, ids: list[int] | None = None
) -> int:
    """Refresh one SOP or <=1000 explicit IDs in the caller's write transaction.

    This internal helper neither opens nor commits a transaction. The caller owns
    write authorization and rollback on failure. Additional provenance is retained;
    malformed JSON is rejected. An unscoped collection-wide write is never allowed.
    """

    if sop is not None and (not isinstance(sop, str) or not sop.strip()):
        raise ValueError("SOP scope must be nonempty")
    if ids is None and sop is None:
        raise ValueError("payload refresh requires an explicit SOP or ID scope")
    if ids is not None:
        if len(ids) > 1000 or any(type(value) is not int or value <= 0 for value in ids):
            raise ValueError("ID scope must contain at most 1000 positive integer IDs")
        if not ids:
            return 0

    scope = "chunk.collection_name = %s"
    parameters: tuple[Any, ...] = (collection,)
    if ids is not None:
        scope += " AND chunk.id = ANY(%s)"
        parameters += (ids,)
    if sop is not None:
        scope += " AND chunk.sop_from_docno = %s"
        parameters += (sop,)

    # Validate and lock the exact selected set before changing any of its JSON.
    rows = cursor.execute(
        "SELECT chunk.id, jsonb_typeof(chunk.payload) AS payload_type "
        f"FROM pisrs.embedding_chunks AS chunk WHERE {scope} ORDER BY chunk.id FOR UPDATE",
        parameters,
    ).fetchall()
    if any(row["payload_type"] != "object" for row in rows):
        raise PostgresInvariantError("stored payload is not an object; repair requires review")
    if not rows:
        return 0

    canonical = canonical_payload_sql()
    cursor.execute(
        f"UPDATE pisrs.embedding_chunks AS chunk SET payload = chunk.payload || {canonical}, "
        "updated_at = now() WHERE chunk.collection_name = %s AND chunk.id = ANY(%s) "
        f"AND chunk.payload IS DISTINCT FROM (chunk.payload || {canonical})",
        (collection, [row["id"] for row in rows]),
    )
    return cursor.rowcount
