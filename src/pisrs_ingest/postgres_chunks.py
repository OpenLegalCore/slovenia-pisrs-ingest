"""Chunk rollover and vector-state persistence for PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from .models import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    Block,
    VectorRow,
    canonical_payload,
    make_chunks,
    qdrant_point_id,
    version_rank,
)
from .postgres import PostgresDatabase, PostgresInvariantError

VECTOR_COLUMNS = """
id AS database_id, qdrant_point_id AS point_id, act_id, version_id, text_id, sop,
sop_from_docno, npb_label, naziv, title, chunk_index, chunk_type, chunk_text,
chunk_text_len, block_start_index, block_end_index, block_count, token_estimate,
content_hash, is_latest_for_sop, is_active, embedding_model, embedding_dimensions,
collection_name
"""


def latest_version(versions: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the deterministic latest version without persistence side effects."""

    if not versions:
        raise ValueError("latest_version requires at least one version")
    return max(versions, key=lambda row: (version_rank(row["npb_label"]), row["text_id"]))


class ChunkStore:
    """Persist chunk rollover and expose authoritative vector rows in bounded batches."""

    def __init__(self, database: PostgresDatabase, collection: str) -> None:
        self.database = database
        self.collection = collection

    def touched_sops(self, since: datetime) -> list[str]:
        with self.database.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                WITH touched AS (
                    SELECT version.sop_from_docno
                    FROM pisrs.act_text_versions AS version
                    WHERE version.sop_from_docno IS NOT NULL
                      AND version.updated_at >= %s
                    UNION
                    SELECT chunk.sop_from_docno
                    FROM pisrs.embedding_chunks AS chunk
                    JOIN pisrs.act_text_versions AS version
                      ON version.id = chunk.version_id
                    WHERE chunk.collection_name = %s
                      AND chunk.sop_from_docno IS NOT NULL
                      AND chunk.sop_from_docno IS DISTINCT FROM version.sop_from_docno
                )
                SELECT sop_from_docno FROM touched ORDER BY sop_from_docno
                """,
                (since, self.collection),
            ).fetchall()
        return [row["sop_from_docno"] for row in rows]

    def prepare_rollover(self, sop: str, model: str, dimensions: int) -> list[VectorRow]:
        if model != EMBEDDING_MODEL or dimensions != EMBEDDING_DIMENSIONS:
            raise PostgresInvariantError(
                "embedding contract change requires a separately reviewed full reindex"
            )
        with (
            self.database.connect() as connection,
            connection.transaction(),
            connection.cursor() as cursor,
        ):
            versions = cursor.execute(
                """
                    SELECT id, act_id, text_id, sop, sop_from_docno, npb_label,
                           naziv, title
                    FROM pisrs.act_text_versions
                    WHERE sop_from_docno = %s
                    ORDER BY text_id
                    FOR UPDATE
                    """,
                (sop,),
            ).fetchall()
            if not versions:
                cursor.execute(DEACTIVATE_SOP, (self.collection, sop))
                return self._rows_for_sop(cursor, sop)

            latest = latest_version(versions)
            block_rows = cursor.execute(
                """
                    SELECT block_index, block_type, article_no, article_title,
                           class_list, text
                    FROM pisrs.act_text_blocks
                    WHERE version_id = %s
                    ORDER BY block_index
                    """,
                (latest["id"],),
            ).fetchall()
            blocks = tuple(
                Block(
                    index=row["block_index"],
                    tag="",
                    classes=tuple(row["class_list"]),
                    text=row["text"],
                    block_type=row["block_type"],
                    article_no=row["article_no"],
                    article_title=row["article_title"],
                )
                for row in block_rows
            )
            chunks = make_chunks(blocks)
            if not chunks:
                raise PostgresInvariantError(f"latest SOP version has no chunkable blocks: {sop}")

            cursor.execute(
                DEACTIVATE_OLD_VERSIONS,
                (self.collection, sop, latest["text_id"]),
            )
            cursor.execute(
                DEACTIVATE_OBSOLETE_CHUNKS,
                (
                    self.collection,
                    latest["text_id"],
                    [chunk.chunk_index for chunk in chunks],
                ),
            )
            cursor.executemany(
                CHUNK_UPSERT,
                [self._chunk_parameters(latest, chunk, model, dimensions) for chunk in chunks],
            )
            return self._rows_for_sop(cursor, sop)

    def _chunk_parameters(
        self, latest: dict[str, Any], chunk: Any, model: str, dimensions: int
    ) -> dict[str, Any]:
        row = VectorRow(
            database_id=0,
            point_id=qdrant_point_id(self.collection, latest["text_id"], chunk.chunk_index),
            act_id=latest["act_id"],
            version_id=latest["id"],
            text_id=latest["text_id"],
            sop=latest["sop"],
            sop_from_docno=latest["sop_from_docno"],
            npb_label=latest["npb_label"],
            naziv=latest["naziv"],
            title=latest["title"],
            chunk_index=chunk.chunk_index,
            chunk_type="text",
            chunk_text=chunk.chunk_text,
            chunk_text_len=len(chunk.chunk_text),
            block_start_index=chunk.block_start_index,
            block_end_index=chunk.block_end_index,
            block_count=chunk.block_count,
            token_estimate=chunk.token_estimate,
            content_hash=chunk.content_hash,
            is_latest_for_sop=True,
            is_active=True,
            embedding_model=model,
            embedding_dimensions=dimensions,
            collection_name=self.collection,
        )
        return {
            "collection": self.collection,
            "act_id": row.act_id,
            "version_id": row.version_id,
            "text_id": row.text_id,
            "sop": row.sop,
            "sop_from_docno": row.sop_from_docno,
            "npb_label": row.npb_label,
            "naziv": row.naziv,
            "title": row.title,
            "chunk_index": row.chunk_index,
            "chunk_text": row.chunk_text,
            "chunk_text_len": row.chunk_text_len,
            "block_start_index": row.block_start_index,
            "block_end_index": row.block_end_index,
            "block_count": row.block_count,
            "token_estimate": row.token_estimate,
            "content_hash": row.content_hash,
            "model": model,
            "dimensions": dimensions,
            "point_id": row.point_id,
            "payload": Jsonb(canonical_payload(row)),
        }

    def _rows_for_sop(self, cursor: Any, sop: str) -> list[VectorRow]:
        rows = cursor.execute(
            f"SELECT {VECTOR_COLUMNS} FROM pisrs.embedding_chunks "
            "WHERE collection_name = %s AND sop_from_docno = %s ORDER BY id",
            (self.collection, sop),
        ).fetchall()
        return [VectorRow(**row) for row in rows]

    def rows_for_point_ids(self, point_ids: set[str]) -> list[VectorRow]:
        """Read final authoritative rows after every affected SOP transaction."""

        if not point_ids:
            return []
        with self.database.connect(read_only=True) as connection:
            rows = connection.execute(
                f"SELECT {VECTOR_COLUMNS} FROM pisrs.embedding_chunks "
                "WHERE collection_name = %s AND qdrant_point_id = ANY(%s) ORDER BY id",
                (self.collection, sorted(point_ids)),
            ).fetchall()
        return [VectorRow(**row) for row in rows]

    def mark_uploaded(self, rows: list[VectorRow]) -> None:
        if not rows:
            return
        with self.database.connect() as connection, connection.transaction():
            connection.execute(
                """
                UPDATE pisrs.embedding_chunks
                SET qdrant_status = 'uploaded', qdrant_error = NULL,
                    qdrant_upserted_at = now(), updated_at = now()
                WHERE id = ANY(%s) AND qdrant_status IS DISTINCT FROM 'uploaded'
                """,
                ([row.database_id for row in rows],),
            )

    def iter_authoritative_payload_batches(
        self, batch_size: int = 500
    ) -> Iterator[list[VectorRow]]:
        connection = self.database.connect(read_only=True)
        try:
            cursor = connection.cursor(name="pisrs_reconcile_payloads")
            cursor.execute(
                f"SELECT {VECTOR_COLUMNS} FROM pisrs.embedding_chunks "
                "WHERE collection_name = %s AND qdrant_point_id IS NOT NULL ORDER BY id",
                (self.collection,),
            )
            while rows := cursor.fetchmany(batch_size):
                yield [VectorRow(**row) for row in rows]
        finally:
            connection.close()


DEACTIVATE_SOP = """
UPDATE pisrs.embedding_chunks
SET is_latest_for_sop = FALSE, is_active = FALSE,
    payload = payload || '{"is_latest_for_sop": false, "is_active": false}'::jsonb,
    updated_at = now()
WHERE collection_name = %s AND sop_from_docno = %s
  AND (is_latest_for_sop OR is_active)
"""

DEACTIVATE_OLD_VERSIONS = """
UPDATE pisrs.embedding_chunks
SET is_latest_for_sop = FALSE, is_active = FALSE,
    payload = payload || '{"is_latest_for_sop": false, "is_active": false}'::jsonb,
    updated_at = now()
WHERE collection_name = %s AND sop_from_docno = %s AND text_id <> %s
  AND (is_latest_for_sop OR is_active)
"""

DEACTIVATE_OBSOLETE_CHUNKS = """
UPDATE pisrs.embedding_chunks
SET is_latest_for_sop = FALSE, is_active = FALSE,
    payload = payload || '{"is_latest_for_sop": false, "is_active": false}'::jsonb,
    updated_at = now()
WHERE collection_name = %s AND text_id = %s
  AND NOT (chunk_index = ANY(%s))
  AND (is_latest_for_sop OR is_active)
"""

CHUNK_UPSERT = """
INSERT INTO pisrs.embedding_chunks (
    source, collection_name, act_id, version_id, text_id, sop, sop_from_docno,
    npb_label, naziv, title, chunk_index, chunk_type, chunk_text, chunk_text_len,
    block_start_index, block_end_index, block_count, token_estimate, content_hash,
    is_latest_for_sop, is_active, embedding_model, embedding_dimensions,
    qdrant_point_id, qdrant_status, payload
) VALUES (
    'pisrs', %(collection)s, %(act_id)s, %(version_id)s, %(text_id)s, %(sop)s,
    %(sop_from_docno)s, %(npb_label)s, %(naziv)s, %(title)s, %(chunk_index)s,
    'text', %(chunk_text)s, %(chunk_text_len)s, %(block_start_index)s,
    %(block_end_index)s, %(block_count)s, %(token_estimate)s, %(content_hash)s,
    TRUE, TRUE, %(model)s, %(dimensions)s, %(point_id)s, 'pending', %(payload)s
)
ON CONFLICT (collection_name, text_id, chunk_index) DO UPDATE SET
    act_id = EXCLUDED.act_id, version_id = EXCLUDED.version_id, sop = EXCLUDED.sop,
    sop_from_docno = EXCLUDED.sop_from_docno, npb_label = EXCLUDED.npb_label,
    naziv = EXCLUDED.naziv, title = EXCLUDED.title,
    chunk_type = EXCLUDED.chunk_type, chunk_text = EXCLUDED.chunk_text,
    chunk_text_len = EXCLUDED.chunk_text_len,
    block_start_index = EXCLUDED.block_start_index,
    block_end_index = EXCLUDED.block_end_index, block_count = EXCLUDED.block_count,
    token_estimate = EXCLUDED.token_estimate, content_hash = EXCLUDED.content_hash,
    is_latest_for_sop = TRUE, is_active = TRUE,
    embedding_model = EXCLUDED.embedding_model,
    embedding_dimensions = EXCLUDED.embedding_dimensions,
    qdrant_point_id = EXCLUDED.qdrant_point_id,
    qdrant_status = CASE WHEN
        pisrs.embedding_chunks.content_hash IS DISTINCT FROM EXCLUDED.content_hash
        OR pisrs.embedding_chunks.embedding_model IS DISTINCT FROM EXCLUDED.embedding_model
        OR pisrs.embedding_chunks.embedding_dimensions
            IS DISTINCT FROM EXCLUDED.embedding_dimensions
        THEN 'pending' ELSE pisrs.embedding_chunks.qdrant_status END,
    qdrant_error = CASE WHEN
        pisrs.embedding_chunks.content_hash IS DISTINCT FROM EXCLUDED.content_hash
        THEN NULL ELSE pisrs.embedding_chunks.qdrant_error END,
    qdrant_upserted_at = CASE WHEN
        pisrs.embedding_chunks.content_hash IS DISTINCT FROM EXCLUDED.content_hash
        THEN NULL ELSE pisrs.embedding_chunks.qdrant_upserted_at END,
    payload = EXCLUDED.payload, updated_at = now()
WHERE ROW(
    pisrs.embedding_chunks.act_id, pisrs.embedding_chunks.version_id,
    pisrs.embedding_chunks.sop, pisrs.embedding_chunks.sop_from_docno,
    pisrs.embedding_chunks.npb_label, pisrs.embedding_chunks.naziv,
    pisrs.embedding_chunks.title, pisrs.embedding_chunks.content_hash,
    pisrs.embedding_chunks.is_latest_for_sop, pisrs.embedding_chunks.is_active,
    pisrs.embedding_chunks.embedding_model,
    pisrs.embedding_chunks.embedding_dimensions, pisrs.embedding_chunks.payload
) IS DISTINCT FROM ROW(
    EXCLUDED.act_id, EXCLUDED.version_id, EXCLUDED.sop, EXCLUDED.sop_from_docno,
    EXCLUDED.npb_label, EXCLUDED.naziv, EXCLUDED.title, EXCLUDED.content_hash,
    TRUE, TRUE, EXCLUDED.embedding_model, EXCLUDED.embedding_dimensions,
    EXCLUDED.payload
)
"""
