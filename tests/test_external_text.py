"""Synthetic local text selection checks; no production PostgreSQL access."""

from __future__ import annotations

import pytest

from pisrs_ingest.postgres import PostgresInvariantError
from pisrs_ingest.postgres_external_text import ExternalTextStore


class Connection:
    def __init__(self, *, collision: bool, rows: list[dict]) -> None:
        self.collision = collision
        self.rows = rows
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query: str, params=None):
        self.calls += 1
        if self.calls == 1:
            assert "JOIN pisrs.npb_catalog" in query
        else:
            assert "source_text_versions" in query
            assert params == (2,)
        return self

    def fetchone(self):
        return {"one": 1} if self.collision else None

    def fetchall(self):
        return self.rows


class Database:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def connect(self, *, read_only: bool):
        assert read_only is True
        return self.connection


def test_local_text_selection_rejects_numeric_id_collision_before_fetch() -> None:
    connection = Connection(collision=True, rows=[])
    with pytest.raises(PostgresInvariantError, match="collide"):
        ExternalTextStore(Database(connection)).pending(2)
    assert connection.calls == 1


def test_local_text_selection_preserves_exact_source_id_and_metadata() -> None:
    connection = Connection(
        collision=False,
        rows=[{"raw": {"id": 9, "naziv": "Local version", "stevilkaDokumenta": None}}],
    )
    documents = ExternalTextStore(Database(connection)).pending(2)
    assert [(item.text_id, item.naziv) for item in documents] == [(9, "Local version")]
    assert connection.calls == 2


def test_local_text_selection_rejects_missing_raw_record() -> None:
    connection = Connection(collision=False, rows=[{"raw": None}])
    with pytest.raises(PostgresInvariantError, match="raw source"):
        ExternalTextStore(Database(connection)).pending(2)
