"""Version and parsed-block persistence for the PISRS PostgreSQL boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from .models import PARSER_VERSION, NpbDocument, ParsedText, SourceInvariantError, article_json
from .postgres import PostgresDatabase, PostgresInvariantError


def resolve_act_id(
    existing_act_id: int | None, candidates: list[dict[str, Any]], sop: str
) -> int | None:
    """Preserve a proven link; otherwise require SOP to identify at most one act."""

    candidate_ids = [row["id"] for row in candidates]
    if existing_act_id is not None:
        if existing_act_id not in candidate_ids:
            raise PostgresInvariantError(
                f"existing act identity {existing_act_id} no longer matches SOP {sop}"
            )
        return existing_act_id
    if len(candidate_ids) > 1:
        raise PostgresInvariantError(
            f"SOP {sop} maps to multiple acts and no stable register_id link is available"
        )
    return candidate_ids[0] if candidate_ids else None


class DocumentStore:
    """Read pending documents and atomically persist one version with its blocks."""

    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database

    def pending(self, limit: int, since: datetime) -> list[NpbDocument]:
        with self.database.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT n.text_id, n.naziv, n.datum_dokumenta, n.stevilka_dokumenta,
                       n.sop_from_docno, n.npb_label, n.raw_item
                FROM pisrs.npb_catalog AS n
                WHERE n.sop_from_docno IS NOT NULL
                  AND n.npb_label IS NOT NULL
                  AND (
                      n.updated_at >= %s
                      OR NOT EXISTS (
                          SELECT 1 FROM pisrs.act_text_versions AS version
                          WHERE version.text_id = n.text_id
                      )
                  )
                ORDER BY n.text_id
                LIMIT %s
                """,
                (since, limit),
            ).fetchall()
        return [
            NpbDocument(
                text_id=row["text_id"],
                naziv=row["naziv"],
                datum_dokumenta=(
                    str(row["datum_dokumenta"]) if row["datum_dokumenta"] is not None else None
                ),
                stevilka_dokumenta=row["stevilka_dokumenta"],
                sop_from_docno=row["sop_from_docno"],
                npb_label=row["npb_label"],
                raw=row["raw_item"],
            )
            for row in rows
        ]

    def synchronize(self, document: NpbDocument, parsed: ParsedText, source_url: str) -> None:
        if not parsed.blocks:
            raise SourceInvariantError(f"text_id={document.text_id} contains no blocks")
        if document.sop_from_docno is None:
            raise SourceInvariantError(f"text_id={document.text_id} has no SOP identity")
        with (
            self.database.connect() as connection,
            connection.transaction(),
            connection.cursor() as cursor,
        ):
            identity = cursor.execute(
                """
                    SELECT catalog.id AS npb_catalog_id,
                           version.act_id AS existing_act_id
                    FROM pisrs.npb_catalog AS catalog
                    LEFT JOIN pisrs.act_text_versions AS version
                      ON version.text_id = catalog.text_id
                    WHERE catalog.text_id = %s
                    FOR UPDATE OF catalog
                    """,
                (document.text_id,),
            ).fetchone()
            if identity is None:
                raise PostgresInvariantError(
                    "NPB catalog identity disappeared during synchronization"
                )
            candidates = cursor.execute(
                "SELECT id FROM pisrs.acts WHERE sop = %s ORDER BY id",
                (document.sop_from_docno,),
            ).fetchall()
            act_id = resolve_act_id(
                identity["existing_act_id"], candidates, document.sop_from_docno
            )
            version_id = self._upsert_version(
                cursor, document, parsed, source_url, identity["npb_catalog_id"], act_id
            )
            cursor.executemany(
                BLOCK_UPSERT,
                [
                    {
                        "version_id": version_id,
                        "act_id": act_id,
                        "text_id": document.text_id,
                        "block_index": block.index,
                        "block_type": block.block_type,
                        "article_no": block.article_no,
                        "article_title": block.article_title,
                        "classes": list(block.classes),
                        "text": block.text,
                        "text_len": len(block.text),
                        "raw": Jsonb(block.raw()),
                    }
                    for block in parsed.blocks
                ],
            )
            cursor.execute(
                "DELETE FROM pisrs.act_text_blocks "
                "WHERE version_id = %s AND NOT (block_index = ANY(%s))",
                (version_id, [block.index for block in parsed.blocks]),
            )
            cursor.execute(
                """
                    UPDATE pisrs.npb_catalog
                    SET status = 'imported', status_reason = NULL, imported_at = now(),
                        last_attempt_at = now(), last_error = NULL, updated_at = now()
                    WHERE id = %s AND status IS DISTINCT FROM 'imported'
                    """,
                (identity["npb_catalog_id"],),
            )

    @staticmethod
    def _upsert_version(
        cursor: Any,
        document: NpbDocument,
        parsed: ParsedText,
        source_url: str,
        npb_catalog_id: int,
        act_id: int | None,
    ) -> int:
        raw_meta = {
            "npb_catalog": document.raw,
            "articles": [article_json(article) for article in parsed.articles],
        }
        row = cursor.execute(
            VERSION_UPSERT,
            {
                "act_id": act_id,
                "npb_catalog_id": npb_catalog_id,
                "text_id": document.text_id,
                "sop": document.sop_from_docno,
                "label": document.npb_label,
                "naziv": document.naziv,
                "title": parsed.title,
                "source_url": source_url,
                "datum": document.datum_dokumenta,
                "docno": document.stevilka_dokumenta,
                "html": parsed.html,
                "html_len": len(parsed.html),
                "plain_text": parsed.plain_text,
                "plain_text_len": len(parsed.plain_text),
                "clen_count": sum(block.block_type == "article_heading" for block in parsed.blocks),
                "odstavek_count": sum(block.block_type == "paragraph" for block in parsed.blocks),
                "block_count": len(parsed.blocks),
                "parser_version": PARSER_VERSION,
                "warnings": Jsonb(list(parsed.warnings)),
                "raw_meta": Jsonb(raw_meta),
            },
        ).fetchone()
        if row is not None:
            return row["id"]
        existing = cursor.execute(
            "SELECT id FROM pisrs.act_text_versions WHERE text_id = %s",
            (document.text_id,),
        ).fetchone()
        if existing is None:
            raise PostgresInvariantError("version upsert returned no identity")
        return existing["id"]


VERSION_UPSERT = """
INSERT INTO pisrs.act_text_versions (
    act_id, npb_catalog_id, text_id, sop, sop_from_docno, npb_label, naziv,
    title, source_url, datum_dokumenta, stevilka_dokumenta, html, html_len,
    plain_text, plain_text_len, clen_count, odstavek_count, block_count,
    parser_version, parser_warnings, raw_meta, imported_at
) VALUES (
    %(act_id)s, %(npb_catalog_id)s, %(text_id)s, %(sop)s, %(sop)s, %(label)s,
    %(naziv)s, %(title)s, %(source_url)s, %(datum)s, %(docno)s, %(html)s,
    %(html_len)s, %(plain_text)s, %(plain_text_len)s, %(clen_count)s,
    %(odstavek_count)s, %(block_count)s, %(parser_version)s, %(warnings)s,
    %(raw_meta)s, now()
)
ON CONFLICT (text_id) DO UPDATE SET
    act_id = EXCLUDED.act_id, npb_catalog_id = EXCLUDED.npb_catalog_id,
    sop = EXCLUDED.sop, sop_from_docno = EXCLUDED.sop_from_docno,
    npb_label = EXCLUDED.npb_label, naziv = EXCLUDED.naziv, title = EXCLUDED.title,
    source_url = EXCLUDED.source_url, datum_dokumenta = EXCLUDED.datum_dokumenta,
    stevilka_dokumenta = EXCLUDED.stevilka_dokumenta, html = EXCLUDED.html,
    html_len = EXCLUDED.html_len, plain_text = EXCLUDED.plain_text,
    plain_text_len = EXCLUDED.plain_text_len, clen_count = EXCLUDED.clen_count,
    odstavek_count = EXCLUDED.odstavek_count, block_count = EXCLUDED.block_count,
    parser_version = EXCLUDED.parser_version,
    parser_warnings = EXCLUDED.parser_warnings, raw_meta = EXCLUDED.raw_meta,
    imported_at = now(), updated_at = now()
WHERE ROW(
    pisrs.act_text_versions.act_id, pisrs.act_text_versions.npb_catalog_id,
    pisrs.act_text_versions.sop, pisrs.act_text_versions.sop_from_docno,
    pisrs.act_text_versions.npb_label, pisrs.act_text_versions.naziv,
    pisrs.act_text_versions.title, pisrs.act_text_versions.source_url,
    pisrs.act_text_versions.datum_dokumenta,
    pisrs.act_text_versions.stevilka_dokumenta, pisrs.act_text_versions.html,
    pisrs.act_text_versions.plain_text, pisrs.act_text_versions.parser_version,
    pisrs.act_text_versions.parser_warnings, pisrs.act_text_versions.raw_meta
) IS DISTINCT FROM ROW(
    EXCLUDED.act_id, EXCLUDED.npb_catalog_id, EXCLUDED.sop,
    EXCLUDED.sop_from_docno, EXCLUDED.npb_label, EXCLUDED.naziv, EXCLUDED.title,
    EXCLUDED.source_url, EXCLUDED.datum_dokumenta, EXCLUDED.stevilka_dokumenta,
    EXCLUDED.html, EXCLUDED.plain_text, EXCLUDED.parser_version,
    EXCLUDED.parser_warnings, EXCLUDED.raw_meta
)
RETURNING id
"""

BLOCK_UPSERT = """
INSERT INTO pisrs.act_text_blocks (
    version_id, act_id, text_id, block_index, block_type, article_no,
    article_title, paragraph_no, class_list, text, text_len, raw_block
) VALUES (
    %(version_id)s, %(act_id)s, %(text_id)s, %(block_index)s, %(block_type)s,
    %(article_no)s, %(article_title)s, NULL, %(classes)s, %(text)s,
    %(text_len)s, %(raw)s
)
ON CONFLICT (version_id, block_index) DO UPDATE SET
    act_id = EXCLUDED.act_id, text_id = EXCLUDED.text_id,
    block_type = EXCLUDED.block_type, article_no = EXCLUDED.article_no,
    article_title = EXCLUDED.article_title, class_list = EXCLUDED.class_list,
    text = EXCLUDED.text, text_len = EXCLUDED.text_len,
    raw_block = EXCLUDED.raw_block, updated_at = now()
WHERE ROW(
    pisrs.act_text_blocks.act_id, pisrs.act_text_blocks.text_id,
    pisrs.act_text_blocks.block_type, pisrs.act_text_blocks.article_no,
    pisrs.act_text_blocks.article_title, pisrs.act_text_blocks.class_list,
    pisrs.act_text_blocks.text, pisrs.act_text_blocks.raw_block
) IS DISTINCT FROM ROW(
    EXCLUDED.act_id, EXCLUDED.text_id, EXCLUDED.block_type, EXCLUDED.article_no,
    EXCLUDED.article_title, EXCLUDED.class_list, EXCLUDED.text, EXCLUDED.raw_block
)
"""
