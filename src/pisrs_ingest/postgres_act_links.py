"""Bounded late act linkage; retry uses the existing version timestamp/checkpoint."""

from __future__ import annotations

from dataclasses import dataclass

from .models import qdrant_point_id
from .postgres import PostgresDatabase, PostgresInvariantError


@dataclass(frozen=True)
class ActLinkStats:
    versions: int = 0
    blocks: int = 0
    chunks: int = 0
    unmatched: int = 0
    ambiguous: int = 0


CANDIDATES = """
SELECT version.id, count(act.id) AS matches
FROM pisrs.act_text_versions AS version
LEFT JOIN pisrs.acts AS act ON act.sop = version.sop_from_docno
  AND btrim(version.sop_from_docno) <> ''
WHERE version.act_id IS NULL
GROUP BY version.id
"""


def link_missing_acts(
    database: PostgresDatabase, collection: str, max_versions: int
) -> ActLinkStats:
    """Fill unique NULL links without refetching or changing document/vector identity.

    A changed parent's updated_at keeps every child, including inactive points,
    reachable through touched_sops() until the nightly checkpoint succeeds.
    Existing non-NULL links are never reassigned. All conflicts abort this batch.
    """

    if collection != "pisrs_current" or type(max_versions) is not int or max_versions <= 0:
        raise PostgresInvariantError("invalid late-link scope")
    with (
        database.connect() as connection,
        connection.transaction(),
        connection.cursor() as cursor,
    ):
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute("SET LOCAL lock_timeout = '3s'")
        # Prevent an act insertion/SOP change from invalidating uniqueness mid-transaction.
        cursor.execute("LOCK TABLE pisrs.acts IN SHARE MODE")
        counts = cursor.execute(
            "SELECT count(*) FILTER (WHERE matches=0) AS unmatched, "
            "count(*) FILTER (WHERE matches>1) AS ambiguous FROM (" + CANDIDATES + ") c"
        ).fetchone()
        targets = cursor.execute(
            """
            SELECT version.id, version.sop_from_docno, min(act.id) AS act_id
            FROM pisrs.act_text_versions AS version
            JOIN pisrs.acts AS act ON act.sop=version.sop_from_docno
            WHERE version.act_id IS NULL AND btrim(version.sop_from_docno)<>''
            GROUP BY version.id HAVING count(act.id)=1
            ORDER BY version.id LIMIT %s
            """,
            (max_versions + 1,),
        ).fetchall()
        if len(targets) > max_versions:
            raise PostgresInvariantError("late-link count exceeds document budget")
        if not targets:
            return ActLinkStats(unmatched=counts["unmatched"], ambiguous=counts["ambiguous"])
        ids = [row["id"] for row in targets]
        locked = cursor.execute(
            "SELECT id, act_id, sop_from_docno FROM pisrs.act_text_versions "
            "WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
            (ids,),
        ).fetchall()
        if len(locked) != len(targets) or any(
            row["id"] != target["id"]
            or row["act_id"] is not None
            or row["sop_from_docno"] != target["sop_from_docno"]
            for row, target in zip(locked, targets, strict=True)
        ):
            raise PostgresInvariantError("late-link parent changed concurrently")
        cursor.execute(
            "SELECT id FROM pisrs.act_text_blocks WHERE version_id=ANY(%s) ORDER BY id FOR UPDATE",
            (ids,),
        ).fetchall()
        chunks = cursor.execute(
            "SELECT id,text_id,chunk_index,qdrant_point_id FROM pisrs.embedding_chunks "
            "WHERE version_id=ANY(%s) ORDER BY id FOR UPDATE",
            (ids,),
        ).fetchall()
        if any(
            row["qdrant_point_id"]
            != qdrant_point_id(collection, row["text_id"], row["chunk_index"])
            for row in chunks
        ):
            raise PostgresInvariantError("late-link child point identity conflict")
        act_ids = [row["act_id"] for row in targets]
        target_cte = """
            WITH targets AS (
                SELECT * FROM unnest(%s::bigint[],%s::bigint[]) AS t(version_id,act_id)
            )
        """
        conflicts = cursor.execute(
            target_cte
            + """
            SELECT count(*) AS n FROM (
                SELECT block.id FROM pisrs.act_text_blocks AS block
                JOIN targets t ON t.version_id=block.version_id
                JOIN pisrs.act_text_versions v ON v.id=block.version_id
                WHERE (block.act_id IS NOT NULL AND block.act_id<>t.act_id)
                   OR block.text_id IS DISTINCT FROM v.text_id
                UNION ALL
                SELECT chunk.id FROM pisrs.embedding_chunks AS chunk
                JOIN targets t ON t.version_id=chunk.version_id
                JOIN pisrs.act_text_versions v ON v.id=chunk.version_id
                WHERE (chunk.act_id IS NOT NULL AND chunk.act_id<>t.act_id)
                   OR chunk.text_id IS DISTINCT FROM v.text_id
                   OR chunk.sop_from_docno IS DISTINCT FROM v.sop_from_docno
                   OR chunk.collection_name IS DISTINCT FROM %s
                   OR jsonb_typeof(chunk.payload) IS DISTINCT FROM 'object'
            ) unsafe
            """,
            (ids, act_ids, collection),
        ).fetchone()["n"]
        if conflicts:
            raise PostgresInvariantError("late-link child identity or payload conflict")
        cursor.execute(
            target_cte
            + """
            UPDATE pisrs.act_text_versions AS version
            SET act_id=t.act_id, updated_at=now()
            FROM targets t WHERE version.id=t.version_id AND version.act_id IS NULL
            """,
            (ids, act_ids),
        )
        versions = cursor.rowcount
        if versions != len(targets):
            raise PostgresInvariantError("late-link parent set changed")
        cursor.execute(
            """
            UPDATE pisrs.act_text_blocks AS block SET act_id=v.act_id, updated_at=now()
            FROM pisrs.act_text_versions v
            WHERE block.version_id=v.id AND v.id=ANY(%s) AND block.act_id IS NULL
            """,
            (ids,),
        )
        blocks = cursor.rowcount
        cursor.execute(
            """
            UPDATE pisrs.embedding_chunks AS chunk
            SET act_id=v.act_id, payload=chunk.payload || jsonb_build_object('act_id',v.act_id),
                updated_at=now()
            FROM pisrs.act_text_versions v
            WHERE chunk.version_id=v.id AND v.id=ANY(%s) AND chunk.collection_name=%s
              AND (chunk.act_id IS NULL
                   OR chunk.payload->'act_id' IS DISTINCT FROM to_jsonb(v.act_id))
            """,
            (ids, collection),
        )
        return ActLinkStats(
            versions, blocks, cursor.rowcount, counts["unmatched"], counts["ambiguous"]
        )
