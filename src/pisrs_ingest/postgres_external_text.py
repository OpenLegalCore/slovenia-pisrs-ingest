"""Bounded local NPB text history; never fabricates unavailable source content."""

from __future__ import annotations

from dataclasses import asdict

from psycopg.types.json import Jsonb

from .models import PARSER_VERSION, NpbDocument, ParsedText, article_json, canonical_content_hash
from .postgres import PostgresDatabase, PostgresInvariantError


class ExternalTextStore:
    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database

    def pending(self, limit: int) -> list[NpbDocument]:
        if limit < 1:
            raise PostgresInvariantError("local text pending limit must be positive")
        with self.database.connect(read_only=True) as connection:
            collision = connection.execute(
                """
                SELECT 1 FROM pisrs.source_catalog_items AS local
                JOIN pisrs.npb_catalog AS state ON state.text_id = local.source_id_int
                WHERE local.namespace = 'LS_NPB' LIMIT 1
                """
            ).fetchone()
            if collision is not None:
                raise PostgresInvariantError(
                    "local and state NPB IDs collide; /besedilo identity is ambiguous"
                )
            rows = connection.execute(
                """
                SELECT local.raw_by_endpoint -> '/npb-ls' AS raw
                FROM pisrs.source_catalog_items AS local
                LEFT JOIN pisrs.source_text_versions AS version
                  ON version.namespace = local.namespace
                 AND version.source_id = local.source_id
                WHERE local.namespace = 'LS_NPB'
                  AND (
                    version.source_id IS NULL
                    OR local.updated_at > version.checked_at
                    OR (version.last_attempt_reason = 'NOT_AVAILABLE_FROM_API:HTTP_404'
                        AND version.checked_at <= now() - interval '1 day')
                  )
                ORDER BY (version.status = 'not_available'), local.source_id_int
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        if any(not isinstance(row["raw"], dict) for row in rows):
            raise PostgresInvariantError("local NPB raw source row is missing")
        return [NpbDocument.from_raw(row["raw"]) for row in rows]

    def synchronize(self, document: NpbDocument, parsed: ParsedText, source_url: str) -> None:
        if not parsed.blocks:
            raise PostgresInvariantError("local NPB text contains no parsed blocks")
        with self.database.connect() as connection, connection.transaction():
            connection.execute(
                IMPORT_TEXT,
                {
                    "source_id": str(document.text_id),
                    "source_url": source_url,
                    "html": parsed.html,
                    "plain_text": parsed.plain_text,
                    "blocks": Jsonb([asdict(block) for block in parsed.blocks]),
                    "articles": Jsonb([article_json(article) for article in parsed.articles]),
                    "warnings": Jsonb(list(parsed.warnings)),
                    "parser_version": PARSER_VERSION,
                    "content_hash": canonical_content_hash(parsed.html),
                },
            )

    def record_unavailable(self, document: NpbDocument, source_url: str) -> None:
        with self.database.connect() as connection, connection.transaction():
            connection.execute(
                RECORD_UNAVAILABLE,
                (str(document.text_id), source_url),
            )


IMPORT_TEXT = """
INSERT INTO pisrs.source_text_versions (
    namespace, source_id, status, last_attempt_reason, source_url,
    html, plain_text, blocks, articles, parser_warnings, parser_version,
    content_hash, checked_at, imported_at
) VALUES (
    'LS_NPB', %(source_id)s, 'imported', NULL, %(source_url)s,
    %(html)s, %(plain_text)s, %(blocks)s, %(articles)s, %(warnings)s,
    %(parser_version)s, %(content_hash)s, now(), now()
)
ON CONFLICT (namespace, source_id) DO UPDATE SET
    status = 'imported', last_attempt_reason = NULL,
    source_url = EXCLUDED.source_url, html = EXCLUDED.html,
    plain_text = EXCLUDED.plain_text, blocks = EXCLUDED.blocks,
    articles = EXCLUDED.articles, parser_warnings = EXCLUDED.parser_warnings,
    parser_version = EXCLUDED.parser_version, content_hash = EXCLUDED.content_hash,
    checked_at = now(), imported_at = now(), updated_at = now()
"""


RECORD_UNAVAILABLE = """
INSERT INTO pisrs.source_text_versions (
    namespace, source_id, status, last_attempt_reason, source_url, checked_at
) VALUES (
    'LS_NPB', %s, 'not_available', 'NOT_AVAILABLE_FROM_API:HTTP_404', %s, now()
)
ON CONFLICT (namespace, source_id) DO UPDATE SET
    last_attempt_reason = 'NOT_AVAILABLE_FROM_API:HTTP_404',
    checked_at = now(), updated_at = now()
"""
