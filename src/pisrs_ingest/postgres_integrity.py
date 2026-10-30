"""Metadata-only link repair and lossless materialized-payload maintenance.

No CLI apply entry point: the one-time operation requires the separate runbook.
Normal nightly calls only bounded link repair and refreshes payloads of touched SOPs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import CANONICAL_PAYLOAD_COLUMNS
from .postgres import PostgresDatabase, PostgresInvariantError


def canonical_payload_sql(alias: str = "chunk", *, act_alias: str | None = None) -> str:
    """Generate SQL from the same trusted field map as canonical_payload()."""

    for value in (alias, act_alias):
        if value is not None and not re.fullmatch(r"[a-z_]+", value):
            raise ValueError("SQL aliases must be fixed identifiers")
    fields = ["'source'", "'pisrs'"]
    for key, column in CANONICAL_PAYLOAD_COLUMNS.items():
        owner = act_alias if key == "act_id" and act_alias else alias
        fields.extend((f"'{key}'", f"{owner}.{column}"))
    return "jsonb_build_object(" + ", ".join(fields) + ")"


def refresh_stored_payloads(cursor: Any, collection: str, *, ids: list[int]) -> int:
    """One-time cache repair: explicit, distinct positive PKs, at most 1000."""

    if (
        collection != "pisrs_current"
        or not isinstance(ids, list)
        or len(ids) > 1000
        or any(type(value) is not int or value <= 0 for value in ids)
        or len(ids) != len(set(ids))
    ):
        raise PostgresInvariantError("cache repair requires at most 1000 distinct positive PKs")
    if not ids:
        return 0
    params = (collection, ids)
    scope = "chunk.collection_name = %s AND chunk.id = ANY(%s)"
    non_object = cursor.execute(
        f"SELECT chunk.id FROM pisrs.embedding_chunks AS chunk WHERE {scope} "
        "AND jsonb_typeof(chunk.payload) IS DISTINCT FROM 'object' LIMIT 1",
        params,
    ).fetchone()
    if non_object is not None:
        raise PostgresInvariantError("stored payload is not an object; repair requires review")
    canonical = canonical_payload_sql()
    cursor.execute(
        f"UPDATE pisrs.embedding_chunks AS chunk SET payload = chunk.payload || {canonical}, "
        f"updated_at = now() WHERE {scope} "
        f"AND chunk.payload IS DISTINCT FROM (chunk.payload || {canonical})",
        params,
    )
    return cursor.rowcount


def refresh_sop_payloads(cursor: Any, collection: str, sop: str) -> int:
    """Nightly-only touched SOP selection; every UPDATE still uses <=1000 PKs."""

    if not isinstance(sop, str) or not sop.strip():
        raise PostgresInvariantError("touched-SOP refresh requires a nonempty SOP")
    changed = 0
    last_id = 0
    while True:
        rows = cursor.execute(
            "SELECT id FROM pisrs.embedding_chunks WHERE collection_name = %s "
            "AND sop_from_docno = %s AND id > %s ORDER BY id LIMIT 1000",
            (collection, sop, last_id),
        ).fetchall()
        if not rows:
            return changed
        ids = [row["id"] for row in rows]
        changed += refresh_stored_payloads(cursor, collection, ids=ids)
        last_id = ids[-1]


@dataclass(frozen=True)
class LinkRepairStats:
    versions: int = 0
    blocks: int = 0
    chunks: int = 0
    ambiguous: int = 0
    unmatched: int = 0


LINK_COUNTS = """
SELECT count(*) FILTER (WHERE matches > 1) AS ambiguous,
       count(*) FILTER (WHERE matches = 0) AS unmatched
FROM (
    SELECT version.id, count(act.id) AS matches
    FROM pisrs.act_text_versions AS version
    LEFT JOIN pisrs.acts AS act ON act.sop = version.sop_from_docno
      AND btrim(version.sop_from_docno) <> ''
    WHERE version.act_id IS NULL
    GROUP BY version.id
) AS candidates
"""

LINK_TARGETS = """
SELECT version.id AS version_id, (array_agg(act.id ORDER BY act.id))[1] AS act_id
FROM pisrs.act_text_versions AS version
JOIN pisrs.acts AS act ON act.sop = version.sop_from_docno
WHERE version.act_id IS NULL
  AND btrim(version.sop_from_docno) <> ''
  AND (%s OR version.raw_meta -> 'automatic_act_link_repair' = 'true'::jsonb)
GROUP BY version.id
HAVING count(act.id) = 1
ORDER BY version.id
LIMIT %s
"""

TARGET_CTE = """
WITH targets AS (
    SELECT * FROM unnest(%s::bigint[], %s::bigint[]) AS target(version_id, act_id)
)
"""


def repair_act_links(
    database: PostgresDatabase,
    collection: str,
    max_versions: int,
    *,
    approved_targets: dict[int, int] | None = None,
) -> LinkRepairStats:
    """Fill only proven NULL links, atomically across parent, children and cache.

    An indexed changed chunk receives the durable payload_pending marker. It is
    retried independently of the checkpoint, including inactive chunks. Content,
    vector identities, embedding contract and existing non-NULL links are immutable.
    Historical versions require an explicit approved_targets map under maintenance;
    the default selects only versions marked on their first import by the new code.
    """

    if collection != "pisrs_current" or max_versions <= 0:
        raise PostgresInvariantError("invalid bounded link repair scope")
    with (
        database.connect() as connection,
        connection.transaction(),
        connection.cursor() as cursor,
    ):
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute("SET LOCAL lock_timeout = '3s'")
        # Freeze SOP candidate membership while selecting and applying links.
        cursor.execute("LOCK TABLE pisrs.acts IN SHARE MODE")
        counts = cursor.execute(LINK_COUNTS).fetchone()
        # No approval map means ongoing repair of explicitly enrolled new versions.
        # Existing versions are never enrolled by re-fetching or catalog refresh.
        targets = cursor.execute(
            LINK_TARGETS, (approved_targets is not None, max_versions + 1)
        ).fetchall()
        if len(targets) > max_versions:
            raise PostgresInvariantError("link repair exceeds the reviewed version budget")
        if approved_targets is not None:
            if any(
                type(k) is not int or k <= 0 or type(v) is not int or v <= 0
                for k, v in approved_targets.items()
            ):
                raise PostgresInvariantError("invalid approved version map")
            approved_rows = cursor.execute(
                "SELECT id,act_id FROM pisrs.act_text_versions WHERE id = ANY(%s) FOR UPDATE",
                (sorted(approved_targets),),
            ).fetchall()
            if {row["id"] for row in approved_rows} != set(approved_targets):
                raise PostgresInvariantError("approved version map is incomplete")
            remaining = {}
            for row in approved_rows:
                target = approved_targets[row["id"]]
                if row["act_id"] is None:
                    remaining[row["id"]] = target
                elif row["act_id"] != target:
                    raise PostgresInvariantError("approved version acquired an unexpected act_id")
            if {row["version_id"]: row["act_id"] for row in targets} != remaining:
                raise PostgresInvariantError(
                    "live link candidates differ from the approved version map"
                )
        if not targets:
            return LinkRepairStats(ambiguous=counts["ambiguous"], unmatched=counts["unmatched"])
        ids = [target["version_id"] for target in targets]
        act_ids = [target["act_id"] for target in targets]
        cursor.execute(
            "SELECT id FROM pisrs.act_text_versions WHERE id = ANY(%s) FOR UPDATE", (ids,)
        )
        cursor.fetchall()
        for table in ("act_text_blocks", "embedding_chunks"):
            cursor.execute(
                f"SELECT id FROM pisrs.{table} WHERE version_id = ANY(%s) FOR UPDATE", (ids,)
            )
            cursor.fetchall()
        conflicts = cursor.execute(
            TARGET_CTE
            + """
            SELECT count(*) AS conflicts FROM (
                SELECT block.id FROM pisrs.act_text_blocks AS block
                JOIN targets ON targets.version_id = block.version_id
                JOIN pisrs.act_text_versions AS version ON version.id = block.version_id
                WHERE (block.act_id IS NOT NULL AND block.act_id <> targets.act_id)
                   OR block.text_id <> version.text_id
                UNION ALL
                SELECT chunk.id FROM pisrs.embedding_chunks AS chunk
                JOIN targets ON targets.version_id = chunk.version_id
                JOIN pisrs.act_text_versions AS version ON version.id = chunk.version_id
                WHERE (chunk.act_id IS NOT NULL AND chunk.act_id <> targets.act_id)
                   OR chunk.text_id <> version.text_id
                   OR chunk.sop_from_docno IS DISTINCT FROM version.sop_from_docno
                   OR chunk.collection_name <> %s
                   OR jsonb_typeof(chunk.payload) IS DISTINCT FROM 'object'
                   OR (chunk.qdrant_status = 'uploaded' AND chunk.qdrant_point_id IS NULL)
            ) AS unsafe
            """,
            (ids, act_ids, collection),
        ).fetchone()["conflicts"]
        if conflicts:
            raise PostgresInvariantError(
                "link repair found conflicting child identities or payloads"
            )
        cursor.execute(
            TARGET_CTE
            + """
            UPDATE pisrs.act_text_versions AS version
            SET act_id = targets.act_id, updated_at = now()
            FROM targets WHERE version.id = targets.version_id AND version.act_id IS NULL
            """,
            (ids, act_ids),
        )
        versions = cursor.rowcount
        if versions != len(targets):
            raise PostgresInvariantError("link candidates changed concurrently; repair rolled back")
        cursor.execute(
            """
            UPDATE pisrs.act_text_blocks AS block
            SET act_id = version.act_id, updated_at = now()
            FROM pisrs.act_text_versions AS version
            WHERE block.version_id = version.id AND version.id = ANY(%s)
              AND block.act_id IS NULL
            """,
            (ids,),
        )
        blocks = cursor.rowcount
        cursor.execute(
            """
            UPDATE pisrs.embedding_chunks AS chunk
            SET act_id = version.act_id,
                qdrant_status = CASE WHEN chunk.qdrant_status = 'uploaded'
                                    THEN 'payload_pending' ELSE chunk.qdrant_status END,
                updated_at = now()
            FROM pisrs.act_text_versions AS version
            WHERE chunk.version_id = version.id AND version.id = ANY(%s)
              AND chunk.collection_name = %s AND chunk.act_id IS NULL
            RETURNING chunk.id
            """,
            (ids, collection),
        )
        chunk_ids = [row["id"] for row in cursor.fetchall()]
        for start in range(0, len(chunk_ids), 1000):
            refresh_stored_payloads(cursor, collection, ids=chunk_ids[start : start + 1000])
        return LinkRepairStats(
            versions, blocks, len(chunk_ids), counts["ambiguous"], counts["unmatched"]
        )
