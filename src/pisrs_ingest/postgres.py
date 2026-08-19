"""PostgreSQL connection, schema preflight, and catalog persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Act, NpbDocument

if TYPE_CHECKING:
    from .postgres_chunks import ChunkStore
    from .postgres_documents import DocumentStore


class PostgresInvariantError(RuntimeError):
    """Raised when deployed schema or authoritative state is unsafe."""


REQUIRED_COLUMNS = {
    "act_sync_catalog": {
        "register_id",
        "moped_id",
        "sop",
        "naziv",
        "kratica",
        "endpoint",
        "vrsta_akta",
        "vrsta_akta_id",
        "vrsta_akta_naziv",
        "kazalo_pravnih_aktov",
        "osnovni",
        "datum_sprejetja",
        "datum_objave",
        "datum_zacetka_veljavnosti",
        "datum_prenehanja_veljavnosti",
        "seen_in_endpoints",
        "source_item",
        "raw_register_json",
        "status",
        "status_reason",
        "imported_at",
        "updated_at",
    },
    "acts": {
        "id",
        "register_id",
        "moped_id",
        "sop",
        "naziv",
        "kratica",
        "endpoint",
        "seen_in_endpoints",
        "vrsta_akta_id",
        "vrsta_akta_naziv",
        "vrsta_akta",
        "kazalo_pravnih_aktov",
        "osnovni",
        "datum_sprejetja",
        "datum_objave",
        "datum_zacetka_veljavnosti",
        "datum_prenehanja_veljavnosti",
        "source_item",
        "raw_register_json",
        "sync_status",
        "updated_at",
    },
    "laws": {"register_id", "moped_id", "sop"},
    "npb_catalog": {
        "id",
        "text_id",
        "naziv",
        "datum_dokumenta",
        "stevilka_dokumenta",
        "sop_from_docno",
        "npb_label",
        "raw_item",
        "status",
        "status_reason",
        "last_attempt_at",
        "imported_at",
        "last_error",
        "updated_at",
    },
    "act_text_versions": {
        "id",
        "act_id",
        "npb_catalog_id",
        "text_id",
        "sop",
        "sop_from_docno",
        "npb_label",
        "naziv",
        "title",
        "source_url",
        "datum_dokumenta",
        "stevilka_dokumenta",
        "html",
        "html_len",
        "plain_text",
        "plain_text_len",
        "clen_count",
        "odstavek_count",
        "block_count",
        "parser_version",
        "parser_warnings",
        "raw_meta",
        "imported_at",
        "updated_at",
    },
    "act_text_blocks": {
        "version_id",
        "act_id",
        "text_id",
        "block_index",
        "block_type",
        "article_no",
        "article_title",
        "paragraph_no",
        "class_list",
        "text",
        "text_len",
        "raw_block",
        "updated_at",
    },
    "embedding_chunks": {
        "id",
        "source",
        "collection_name",
        "act_id",
        "version_id",
        "text_id",
        "sop",
        "sop_from_docno",
        "npb_label",
        "naziv",
        "title",
        "chunk_index",
        "chunk_type",
        "chunk_text",
        "chunk_text_len",
        "block_start_index",
        "block_end_index",
        "block_count",
        "token_estimate",
        "content_hash",
        "is_latest_for_sop",
        "is_active",
        "embedding_model",
        "embedding_dimensions",
        "qdrant_point_id",
        "qdrant_status",
        "qdrant_error",
        "qdrant_upserted_at",
        "payload",
        "updated_at",
    },
}

ESSENTIAL_NOT_NULL = {
    "acts": {"register_id", "moped_id", "sync_status"},
    "act_sync_catalog": {
        "naziv",
        "vrsta_akta",
        "kazalo_pravnih_aktov",
        "seen_in_endpoints",
        "raw_register_json",
        "status",
    },
    "npb_catalog": {"text_id", "raw_item", "status"},
    "act_text_versions": {
        "text_id",
        "npb_label",
        "html",
        "plain_text",
        "parser_version",
        "parser_warnings",
        "raw_meta",
    },
    "act_text_blocks": {
        "version_id",
        "text_id",
        "block_index",
        "block_type",
        "class_list",
        "text",
        "raw_block",
    },
    "embedding_chunks": {
        "collection_name",
        "version_id",
        "text_id",
        "npb_label",
        "chunk_index",
        "chunk_text",
        "content_hash",
        "is_latest_for_sop",
        "is_active",
        "embedding_model",
        "embedding_dimensions",
        "qdrant_status",
        "payload",
    },
}

UNIQUE_TARGETS = {
    "act_sync_catalog": "(register_id)",
    "acts": "(register_id)",
    "npb_catalog": "(text_id)",
    "act_text_versions": "(text_id)",
    "act_text_blocks": "(version_id, block_index)",
    "embedding_chunks": "(collection_name, text_id, chunk_index)",
}

ESSENTIAL_FOREIGN_KEYS = {
    (
        "act_text_versions",
        "FOREIGN KEY (act_id) REFERENCES pisrs.acts(id) ON DELETE SET NULL",
    ),
    (
        "act_text_versions",
        "FOREIGN KEY (npb_catalog_id) REFERENCES pisrs.npb_catalog(id) ON DELETE SET NULL",
    ),
    (
        "act_text_blocks",
        "FOREIGN KEY (version_id) REFERENCES pisrs.act_text_versions(id) ON DELETE CASCADE",
    ),
    (
        "act_text_blocks",
        "FOREIGN KEY (act_id) REFERENCES pisrs.acts(id) ON DELETE SET NULL",
    ),
    (
        "embedding_chunks",
        "FOREIGN KEY (version_id) REFERENCES pisrs.act_text_versions(id) ON DELETE CASCADE",
    ),
    (
        "embedding_chunks",
        "FOREIGN KEY (act_id) REFERENCES pisrs.acts(id) ON DELETE SET NULL",
    ),
}


def validate_schema_contract(
    columns: list[dict[str, Any]],
    indexes: list[dict[str, Any]],
    foreign_keys: list[dict[str, Any]],
) -> None:
    """Validate every table/column and key relied upon by write SQL."""

    actual: dict[str, dict[str, bool]] = {}
    for row in columns:
        actual.setdefault(row["table_name"], {})[row["column_name"]] = row["is_nullable"] == "NO"
    missing = {
        table: sorted(required - actual.get(table, {}).keys())
        for table, required in REQUIRED_COLUMNS.items()
        if required - actual.get(table, {}).keys()
    }
    if missing:
        raise PostgresInvariantError(f"pisrs schema contract is missing columns: {missing}")
    wrong_nullability = {
        table: sorted(column for column in required if not actual[table][column])
        for table, required in ESSENTIAL_NOT_NULL.items()
        if any(not actual[table][column] for column in required)
    }
    if wrong_nullability:
        raise PostgresInvariantError(
            f"pisrs schema contract has unsafe nullability: {wrong_nullability}"
        )

    index_definitions: dict[str, list[str]] = {}
    for row in indexes:
        index_definitions.setdefault(row["tablename"], []).append(row["indexdef"])
    missing_unique = {
        table: target
        for table, target in UNIQUE_TARGETS.items()
        if not any(
            "CREATE UNIQUE INDEX" in definition and target in definition
            for definition in index_definitions.get(table, [])
        )
    }
    if missing_unique:
        raise PostgresInvariantError(
            f"pisrs schema contract is missing ON CONFLICT targets: {missing_unique}"
        )

    actual_fks = {(row["table_name"], row["definition"]) for row in foreign_keys}
    missing_fks = sorted(ESSENTIAL_FOREIGN_KEYS - actual_fks)
    if missing_fks:
        raise PostgresInvariantError(
            f"pisrs schema contract is missing essential foreign keys: {missing_fks}"
        )


class PostgresDatabase:
    """Own Psycopg connections and read-only preflight; no domain behavior."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def connect(self, *, read_only: bool = False) -> psycopg.Connection[dict[str, Any]]:
        kwargs: dict[str, Any] = {"row_factory": dict_row}
        if read_only:
            kwargs["options"] = "-c default_transaction_read_only=on"
        return psycopg.connect(self.dsn, **kwargs)

    def preflight(
        self,
        collection: str,
        model: str,
        dimensions: int,
        *,
        expected_database: str,
    ) -> dict[str, Any]:
        with self.connect(read_only=True) as connection:
            identity = connection.execute(
                "SELECT current_database() AS database, "
                "current_setting('transaction_read_only') AS read_only"
            ).fetchone()
            columns = connection.execute(
                "SELECT table_name, column_name, is_nullable "
                "FROM information_schema.columns WHERE table_schema = 'pisrs'"
            ).fetchall()
            indexes = connection.execute(
                "SELECT tablename, indexdef FROM pg_indexes WHERE schemaname = 'pisrs'"
            ).fetchall()
            foreign_keys = connection.execute(
                "SELECT conrelid::regclass::text AS qualified_table, "
                "regexp_replace(conrelid::regclass::text, '^pisrs\\.', '') AS table_name, "
                "pg_get_constraintdef(oid) AS definition FROM pg_constraint "
                "WHERE connamespace = 'pisrs'::regnamespace AND contype = 'f'"
            ).fetchall()
            vector_contracts = connection.execute(
                "SELECT DISTINCT embedding_model, embedding_dimensions "
                "FROM pisrs.embedding_chunks WHERE collection_name = %s",
                (collection,),
            ).fetchall()
        if identity is None or identity["read_only"] != "on":
            raise PostgresInvariantError("PostgreSQL preflight session is not read-only")
        if identity["database"] != expected_database:
            raise PostgresInvariantError(
                "current PostgreSQL database does not match PISRS_EXPECTED_DATABASE"
            )
        validate_schema_contract(columns, indexes, foreign_keys)
        incompatible = [
            row
            for row in vector_contracts
            if row["embedding_model"] != model or row["embedding_dimensions"] != dimensions
        ]
        if incompatible:
            raise PostgresInvariantError(
                "existing PostgreSQL chunks violate the pinned embedding model/dimension contract"
            )
        return {
            "database": identity["database"],
            "read_only": True,
            "schema_contract": "ok",
            "embedding_contract": "ok",
        }


@dataclass(frozen=True)
class PostgresBoundary:
    """Explicit composition of the three PostgreSQL persistence responsibilities."""

    database: PostgresDatabase
    catalogs: CatalogStore
    documents: DocumentStore
    chunks: ChunkStore

    @classmethod
    def create(cls, dsn: str, collection: str) -> PostgresBoundary:
        from .postgres_chunks import ChunkStore
        from .postgres_documents import DocumentStore

        database = PostgresDatabase(dsn)
        return cls(
            database=database,
            catalogs=CatalogStore(database),
            documents=DocumentStore(database),
            chunks=ChunkStore(database, collection),
        )


class CatalogStore:
    """Persist complete act/NPB catalogs and synchronize proven status semantics."""

    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database

    def synchronize(self, acts: list[Act], npbs: list[NpbDocument]) -> None:
        if not acts:
            raise PostgresInvariantError("refusing to synchronize an empty complete act catalog")
        incoming_ids = [act.register_id for act in acts]
        if len(incoming_ids) != len(set(incoming_ids)):
            raise PostgresInvariantError(
                "complete act catalog contains duplicate register_id values"
            )
        with self.database.connect(read_only=True) as connection:
            existing_ids = {
                row["register_id"]
                for row in connection.execute(
                    "SELECT register_id FROM pisrs.act_sync_catalog "
                    "WHERE register_id IS NOT NULL "
                    "UNION SELECT register_id FROM pisrs.acts WHERE register_id IS NOT NULL"
                ).fetchall()
            }
        disappeared = existing_ids - set(incoming_ids)
        if disappeared:
            raise PostgresInvariantError(
                "complete act catalog omitted existing authoritative rows; "
                "no proven deactivation status exists, so synchronization is blocked "
                f"(count={len(disappeared)})"
            )

        act_parameters = [self._act_parameters(act) for act in acts]
        npb_parameters = [self._npb_parameters(item) for item in npbs]
        with (
            self.database.connect() as connection,
            connection.transaction(),
            connection.cursor() as cursor,
        ):
            cursor.executemany(ACT_CATALOG_UPSERT, act_parameters)
            cursor.executemany(ACTS_UPSERT, act_parameters)
            cursor.executemany(NPB_CATALOG_UPSERT, npb_parameters)
            cursor.execute(ACT_STATUS_RECONCILIATION)

    @staticmethod
    def _act_parameters(act: Act) -> dict[str, Any]:
        provenance = act.provenance()
        return {
            "register_id": act.register_id,
            "moped_id": act.moped_id,
            "sop": act.sop,
            "naziv": act.naziv,
            "kratica": act.kratica,
            "osnovni": act.osnovni,
            "vrsta_akta_id": act.vrsta_akta_id,
            "vrsta_akta_naziv": act.vrsta_akta_naziv,
            "datum_sprejetja": act.datum_sprejetja,
            "datum_objave": act.datum_objave,
            "datum_zacetka_veljavnosti": act.datum_zacetka_veljavnosti,
            "datum_prenehanja_veljavnosti": act.datum_prenehanja_veljavnosti,
            "seen": list(act.seen_in_endpoints),
            "endpoint": act.seen_in_endpoints[0],
            "source_item": Jsonb(provenance),
            "raw": Jsonb(act.raw),
            "vrsta_akta": Jsonb(act.raw.get("vrstaAkta") or {}),
            "kazalo": Jsonb(act.raw.get("kazaloPravnihAktov") or []),
        }

    @staticmethod
    def _npb_parameters(item: NpbDocument) -> dict[str, Any]:
        return {
            "text_id": item.text_id,
            "naziv": item.naziv,
            "datum": item.datum_dokumenta,
            "docno": item.stevilka_dokumenta,
            "sop": item.sop_from_docno,
            "label": item.npb_label,
            "raw": Jsonb(item.raw),
        }


ACT_CATALOG_UPSERT = """
INSERT INTO pisrs.act_sync_catalog (
    register_id, moped_id, sop, naziv, kratica, endpoint, osnovni, vrsta_akta_id,
    vrsta_akta_naziv, datum_sprejetja, datum_objave, datum_zacetka_veljavnosti,
    datum_prenehanja_veljavnosti, seen_in_endpoints, source_item,
    raw_register_json, vrsta_akta, kazalo_pravnih_aktov
) VALUES (
    %(register_id)s, %(moped_id)s, %(sop)s, %(naziv)s, %(kratica)s, %(endpoint)s,
    %(osnovni)s, %(vrsta_akta_id)s, %(vrsta_akta_naziv)s, %(datum_sprejetja)s,
    %(datum_objave)s, %(datum_zacetka_veljavnosti)s,
    %(datum_prenehanja_veljavnosti)s, %(seen)s, %(source_item)s, %(raw)s,
    %(vrsta_akta)s, %(kazalo)s
)
ON CONFLICT (register_id) DO UPDATE SET
    moped_id = EXCLUDED.moped_id, sop = EXCLUDED.sop, naziv = EXCLUDED.naziv,
    kratica = EXCLUDED.kratica, endpoint = EXCLUDED.endpoint,
    osnovni = EXCLUDED.osnovni, vrsta_akta_id = EXCLUDED.vrsta_akta_id,
    vrsta_akta_naziv = EXCLUDED.vrsta_akta_naziv,
    datum_sprejetja = EXCLUDED.datum_sprejetja,
    datum_objave = EXCLUDED.datum_objave,
    datum_zacetka_veljavnosti = EXCLUDED.datum_zacetka_veljavnosti,
    datum_prenehanja_veljavnosti = EXCLUDED.datum_prenehanja_veljavnosti,
    seen_in_endpoints = EXCLUDED.seen_in_endpoints,
    source_item = EXCLUDED.source_item, raw_register_json = EXCLUDED.raw_register_json,
    vrsta_akta = EXCLUDED.vrsta_akta,
    kazalo_pravnih_aktov = EXCLUDED.kazalo_pravnih_aktov,
    status = CASE
        WHEN pisrs.act_sync_catalog.status IN
            ('imported', 'skipped_no_npb', 'skipped_no_text', 'failed')
        THEN pisrs.act_sync_catalog.status ELSE 'pending'
    END,
    updated_at = now()
WHERE ROW(
    pisrs.act_sync_catalog.moped_id, pisrs.act_sync_catalog.sop,
    pisrs.act_sync_catalog.naziv, pisrs.act_sync_catalog.kratica,
    pisrs.act_sync_catalog.endpoint, pisrs.act_sync_catalog.osnovni,
    pisrs.act_sync_catalog.vrsta_akta_id, pisrs.act_sync_catalog.vrsta_akta_naziv,
    pisrs.act_sync_catalog.datum_sprejetja, pisrs.act_sync_catalog.datum_objave,
    pisrs.act_sync_catalog.datum_zacetka_veljavnosti,
    pisrs.act_sync_catalog.datum_prenehanja_veljavnosti,
    pisrs.act_sync_catalog.seen_in_endpoints, pisrs.act_sync_catalog.source_item,
    pisrs.act_sync_catalog.raw_register_json, pisrs.act_sync_catalog.vrsta_akta,
    pisrs.act_sync_catalog.kazalo_pravnih_aktov
) IS DISTINCT FROM ROW(
    EXCLUDED.moped_id, EXCLUDED.sop, EXCLUDED.naziv, EXCLUDED.kratica,
    EXCLUDED.endpoint, EXCLUDED.osnovni, EXCLUDED.vrsta_akta_id,
    EXCLUDED.vrsta_akta_naziv, EXCLUDED.datum_sprejetja, EXCLUDED.datum_objave,
    EXCLUDED.datum_zacetka_veljavnosti, EXCLUDED.datum_prenehanja_veljavnosti,
    EXCLUDED.seen_in_endpoints, EXCLUDED.source_item, EXCLUDED.raw_register_json,
    EXCLUDED.vrsta_akta, EXCLUDED.kazalo_pravnih_aktov
)
"""

ACTS_UPSERT = """
INSERT INTO pisrs.acts (
    register_id, moped_id, sop, naziv, kratica, endpoint, seen_in_endpoints,
    vrsta_akta_id, vrsta_akta_naziv, vrsta_akta, kazalo_pravnih_aktov, osnovni,
    datum_sprejetja, datum_objave, datum_zacetka_veljavnosti,
    datum_prenehanja_veljavnosti, source_item, raw_register_json, sync_status
) VALUES (
    %(register_id)s, %(moped_id)s, %(sop)s, %(naziv)s, %(kratica)s, %(endpoint)s,
    %(seen)s, %(vrsta_akta_id)s, %(vrsta_akta_naziv)s, %(vrsta_akta)s,
    %(kazalo)s, %(osnovni)s, %(datum_sprejetja)s, %(datum_objave)s,
    %(datum_zacetka_veljavnosti)s, %(datum_prenehanja_veljavnosti)s,
    %(source_item)s, %(raw)s, 'metadata_only'
)
ON CONFLICT (register_id) DO UPDATE SET
    moped_id = EXCLUDED.moped_id, sop = EXCLUDED.sop, naziv = EXCLUDED.naziv,
    kratica = EXCLUDED.kratica, endpoint = EXCLUDED.endpoint,
    seen_in_endpoints = EXCLUDED.seen_in_endpoints,
    vrsta_akta_id = EXCLUDED.vrsta_akta_id,
    vrsta_akta_naziv = EXCLUDED.vrsta_akta_naziv,
    vrsta_akta = EXCLUDED.vrsta_akta,
    kazalo_pravnih_aktov = EXCLUDED.kazalo_pravnih_aktov,
    osnovni = EXCLUDED.osnovni, datum_sprejetja = EXCLUDED.datum_sprejetja,
    datum_objave = EXCLUDED.datum_objave,
    datum_zacetka_veljavnosti = EXCLUDED.datum_zacetka_veljavnosti,
    datum_prenehanja_veljavnosti = EXCLUDED.datum_prenehanja_veljavnosti,
    source_item = EXCLUDED.source_item, raw_register_json = EXCLUDED.raw_register_json,
    updated_at = now()
WHERE ROW(
    pisrs.acts.moped_id, pisrs.acts.sop, pisrs.acts.naziv, pisrs.acts.kratica,
    pisrs.acts.endpoint, pisrs.acts.seen_in_endpoints, pisrs.acts.vrsta_akta_id,
    pisrs.acts.vrsta_akta_naziv, pisrs.acts.vrsta_akta,
    pisrs.acts.kazalo_pravnih_aktov, pisrs.acts.osnovni,
    pisrs.acts.datum_sprejetja, pisrs.acts.datum_objave,
    pisrs.acts.datum_zacetka_veljavnosti, pisrs.acts.datum_prenehanja_veljavnosti,
    pisrs.acts.source_item, pisrs.acts.raw_register_json
) IS DISTINCT FROM ROW(
    EXCLUDED.moped_id, EXCLUDED.sop, EXCLUDED.naziv, EXCLUDED.kratica,
    EXCLUDED.endpoint, EXCLUDED.seen_in_endpoints, EXCLUDED.vrsta_akta_id,
    EXCLUDED.vrsta_akta_naziv, EXCLUDED.vrsta_akta, EXCLUDED.kazalo_pravnih_aktov,
    EXCLUDED.osnovni, EXCLUDED.datum_sprejetja, EXCLUDED.datum_objave,
    EXCLUDED.datum_zacetka_veljavnosti, EXCLUDED.datum_prenehanja_veljavnosti,
    EXCLUDED.source_item, EXCLUDED.raw_register_json
)
"""

NPB_CATALOG_UPSERT = """
INSERT INTO pisrs.npb_catalog (
    text_id, naziv, datum_dokumenta, stevilka_dokumenta, sop_from_docno,
    npb_label, raw_item
) VALUES (
    %(text_id)s, %(naziv)s, %(datum)s, %(docno)s, %(sop)s, %(label)s, %(raw)s
)
ON CONFLICT (text_id) DO UPDATE SET
    naziv = EXCLUDED.naziv, datum_dokumenta = EXCLUDED.datum_dokumenta,
    stevilka_dokumenta = EXCLUDED.stevilka_dokumenta,
    sop_from_docno = EXCLUDED.sop_from_docno, npb_label = EXCLUDED.npb_label,
    raw_item = EXCLUDED.raw_item, updated_at = now()
WHERE ROW(
    pisrs.npb_catalog.naziv, pisrs.npb_catalog.datum_dokumenta,
    pisrs.npb_catalog.stevilka_dokumenta, pisrs.npb_catalog.sop_from_docno,
    pisrs.npb_catalog.npb_label, pisrs.npb_catalog.raw_item
) IS DISTINCT FROM ROW(
    EXCLUDED.naziv, EXCLUDED.datum_dokumenta, EXCLUDED.stevilka_dokumenta,
    EXCLUDED.sop_from_docno, EXCLUDED.npb_label, EXCLUDED.raw_item
)
"""

ACT_STATUS_RECONCILIATION = """
UPDATE pisrs.act_sync_catalog AS catalog
SET status = 'imported', imported_at = COALESCE(catalog.imported_at, now()),
    status_reason = COALESCE(catalog.status_reason, 'already present in pisrs.laws'),
    updated_at = now()
WHERE catalog.status IS DISTINCT FROM 'imported'
  AND EXISTS (
      SELECT 1 FROM pisrs.laws AS law
      WHERE law.register_id = catalog.register_id
         OR (catalog.sop IS NOT NULL AND law.sop = catalog.sop)
         OR (catalog.moped_id IS NOT NULL AND law.moped_id = catalog.moped_id)
  )
"""
