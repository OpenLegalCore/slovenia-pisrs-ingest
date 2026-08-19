from __future__ import annotations

from contextlib import nullcontext
from typing import Any

import pytest

import pisrs_ingest.postgres as postgres_module
from pisrs_ingest.models import Act, NpbDocument, parse_html
from pisrs_ingest.postgres import (
    ACT_CATALOG_UPSERT,
    ACT_STATUS_RECONCILIATION,
    ESSENTIAL_FOREIGN_KEYS,
    ESSENTIAL_NOT_NULL,
    REQUIRED_COLUMNS,
    UNIQUE_TARGETS,
    CatalogStore,
    PostgresDatabase,
    PostgresInvariantError,
    validate_schema_contract,
)
from pisrs_ingest.postgres_chunks import ChunkStore
from pisrs_ingest.postgres_documents import DocumentStore, resolve_act_id


class Result:
    def __init__(self, rows: list[dict[str, Any]] = ()) -> None:
        self.rows = list(rows)

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class ReadConnection:
    def __init__(self, existing_ids: set[int]) -> None:
        self.existing_ids = existing_ids

    def __enter__(self) -> ReadConnection:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, sql: str, parameters: object = None) -> Result:
        assert "SELECT register_id" in sql
        return Result([{"register_id": value} for value in sorted(self.existing_ids)])


class IdentityConnection:
    def __init__(self, database: str) -> None:
        self.database = database

    def __enter__(self) -> IdentityConnection:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, sql: str, parameters: object = None) -> Result:
        if "current_database()" in sql:
            return Result([{"database": self.database, "read_only": "on"}])
        return Result()


class FaithfulCursor:
    """DB-API surface: executemany deliberately exists only here, not on connection."""

    def __init__(self) -> None:
        self.batch_calls: list[tuple[str, list[dict[str, Any]]]] = []
        self.execute_calls: list[str] = []

    def __enter__(self) -> FaithfulCursor:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def executemany(self, sql: str, parameters: list[dict[str, Any]]) -> None:
        self.batch_calls.append((sql, parameters))

    def execute(self, sql: str, parameters: object = None) -> Result:
        self.execute_calls.append(sql)
        return Result()


class FaithfulConnection:
    def __init__(self, cursor: FaithfulCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> FaithfulConnection:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def transaction(self):
        return nullcontext()

    def cursor(self) -> FaithfulCursor:
        return self._cursor


class ContractDatabase:
    def __init__(self, existing_ids: set[int] = frozenset()) -> None:
        self.existing_ids = existing_ids
        self.cursor = FaithfulCursor()
        self.write_connections = 0

    def connect(self, *, read_only: bool = False):
        if read_only:
            return ReadConnection(self.existing_ids)
        self.write_connections += 1
        return FaithfulConnection(self.cursor)


def act(raw: dict[str, Any] | None = None) -> Act:
    raw = raw or {
        "id": 10,
        "mopedId": "M-10",
        "sop": "2026-01-0010",
        "naziv": "Fixture act",
        "vrstaAkta": {"id": 2, "naziv": "Act"},
    }
    return Act.from_raw(raw, "/predpis/register-predpisov")


class RoutingCursor(FaithfulCursor):
    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode

    def execute(self, sql: str, parameters: object = None) -> Result:
        self.execute_calls.append(sql)
        normalized = " ".join(sql.split())
        if self.mode == "document":
            if "SELECT catalog.id AS npb_catalog_id" in normalized:
                return Result([{"npb_catalog_id": 7, "existing_act_id": None}])
            return Result()
        if "FROM pisrs.act_text_versions" in normalized and "FOR UPDATE" in normalized:
            return Result(
                [
                    {
                        "id": 8,
                        "act_id": None,
                        "text_id": 9,
                        "sop": "2026-01-0009",
                        "sop_from_docno": "2026-01-0009",
                        "npb_label": "osnovno",
                        "naziv": "Fixture",
                        "title": "Fixture",
                    }
                ]
            )
        if "FROM pisrs.act_text_blocks" in normalized:
            return Result(
                [
                    {
                        "block_index": 1,
                        "block_type": "paragraph",
                        "article_no": None,
                        "article_title": None,
                        "class_list": ["odstavek"],
                        "text": "Fixture block",
                    }
                ]
            )
        return Result()


class WriteOnlyDatabase:
    def __init__(self, mode: str) -> None:
        self.cursor = RoutingCursor(mode)

    def connect(self, *, read_only: bool = False) -> FaithfulConnection:
        assert not read_only
        return FaithfulConnection(self.cursor)


def test_all_five_batch_paths_use_cursor_executemany(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog_database = ContractDatabase()
    CatalogStore(catalog_database).synchronize([act()], [])

    document_database = WriteOnlyDatabase("document")
    monkeypatch.setattr(DocumentStore, "_upsert_version", lambda *args: 8)
    document = NpbDocument(
        9, "Fixture", "2026-01-01", "2026-01-0009", "2026-01-0009", "osnovno", {}
    )
    parsed = parse_html("<html><body><p class='odstavek'>Fixture</p></body></html>")
    DocumentStore(document_database).synchronize(document, parsed, "https://example.invalid/9")

    chunk_database = WriteOnlyDatabase("chunk")
    monkeypatch.setattr(ChunkStore, "_rows_for_sop", lambda *args: [])
    ChunkStore(chunk_database, "pisrs_current").prepare_rollover(
        "2026-01-0009", "text-embedding-3-large", 3072
    )

    cursors = [catalog_database.cursor, document_database.cursor, chunk_database.cursor]
    assert sum(len(cursor.batch_calls) for cursor in cursors) == 5
    assert catalog_database.cursor.execute_calls == [ACT_STATUS_RECONCILIATION]
    assert all(not hasattr(FaithfulConnection(cursor), "executemany") for cursor in cursors)


def test_preflight_requires_actual_database_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    database = PostgresDatabase("postgresql://example.invalid/production_db")
    monkeypatch.setattr(postgres_module, "validate_schema_contract", lambda *args: None)
    monkeypatch.setattr(
        database, "connect", lambda *, read_only: IdentityConnection("production_db")
    )
    result = database.preflight(
        "pisrs_current",
        "text-embedding-3-large",
        3072,
        expected_database="production_db",
    )
    assert result["database"] == "production_db"

    monkeypatch.setattr(database, "connect", lambda *, read_only: IdentityConnection("wrong_db"))
    with pytest.raises(PostgresInvariantError, match="PISRS_EXPECTED_DATABASE"):
        database.preflight(
            "pisrs_current",
            "text-embedding-3-large",
            3072,
            expected_database="production_db",
        )


def test_provenance_envelope_is_distinct_from_raw_and_semantically_stable() -> None:
    first = act()
    reordered_raw = {
        "vrstaAkta": {"naziv": "Act", "id": 2},
        "naziv": "Fixture act",
        "sop": "2026-01-0010",
        "mopedId": "M-10",
        "id": 10,
    }
    second = act(reordered_raw)
    first_parameters = CatalogStore._act_parameters(first)
    second_parameters = CatalogStore._act_parameters(second)
    source = first_parameters["source_item"].obj
    assert source["unique_key"] == "register_id:10"
    assert source["endpoint"] == "/predpis/register-predpisov"
    assert source["seen_in_endpoints"] == ["/predpis/register-predpisov"]
    assert source["raw"] == first.raw
    assert source != first_parameters["raw"].obj
    assert source == second_parameters["source_item"].obj
    assert "IS DISTINCT FROM" in ACT_CATALOG_UPSERT

    merged = first.merge(Act.from_raw(reordered_raw, "/predpis/neveljavni-predpisi"))
    assert merged.raw is first.raw
    assert merged.seen_in_endpoints == (
        "/predpis/register-predpisov",
        "/predpis/neveljavni-predpisi",
    )


def test_catalog_status_sync_matches_donor_and_disappearance_fails_closed() -> None:
    assert "FROM pisrs.laws" in ACT_STATUS_RECONCILIATION
    assert "law.register_id = catalog.register_id" in ACT_STATUS_RECONCILIATION
    assert "law.sop = catalog.sop" in ACT_STATUS_RECONCILIATION
    assert "law.moped_id = catalog.moped_id" in ACT_STATUS_RECONCILIATION
    assert "('imported', 'skipped_no_npb', 'skipped_no_text', 'failed')" in (
        " ".join(ACT_CATALOG_UPSERT.split())
    )
    database = ContractDatabase(existing_ids={10, 11})
    with pytest.raises(PostgresInvariantError, match="no proven deactivation status"):
        CatalogStore(database).synchronize([act()], [])
    assert database.write_connections == 0


def test_duplicate_sop_never_selects_an_arbitrary_act() -> None:
    candidates = [{"id": 59644}, {"id": 59645}]
    assert resolve_act_id(59645, candidates, "2024-01-2748") == 59645
    with pytest.raises(PostgresInvariantError, match="multiple acts"):
        resolve_act_id(None, candidates, "2024-01-2748")
    with pytest.raises(PostgresInvariantError, match="no longer matches"):
        resolve_act_id(99999, candidates, "2024-01-2748")


def complete_schema_fixture():
    columns = [
        {
            "table_name": table,
            "column_name": column,
            "is_nullable": "NO" if column in ESSENTIAL_NOT_NULL.get(table, set()) else "YES",
        }
        for table, names in REQUIRED_COLUMNS.items()
        for column in names
    ]
    indexes = [
        {
            "tablename": table,
            "indexdef": f"CREATE UNIQUE INDEX fixture ON pisrs.{table} USING btree {target}",
        }
        for table, target in UNIQUE_TARGETS.items()
    ]
    foreign_keys = [
        {"table_name": table, "definition": definition}
        for table, definition in ESSENTIAL_FOREIGN_KEYS
    ]
    return columns, indexes, foreign_keys


def test_schema_preflight_covers_columns_nullability_unique_targets_and_fks() -> None:
    columns, indexes, foreign_keys = complete_schema_fixture()
    validate_schema_contract(columns, indexes, foreign_keys)
    with pytest.raises(PostgresInvariantError, match="essential foreign keys"):
        validate_schema_contract(columns, indexes, foreign_keys[1:])
    bad_columns = [dict(row) for row in columns]
    next(
        row
        for row in bad_columns
        if row["table_name"] == "embedding_chunks" and row["column_name"] == "payload"
    )["is_nullable"] = "YES"
    with pytest.raises(PostgresInvariantError, match="unsafe nullability"):
        validate_schema_contract(bad_columns, indexes, foreign_keys)
