from __future__ import annotations

import os
from dataclasses import asdict, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from test_core import vector_row

from pisrs_ingest.models import MANAGED_PAYLOAD_KEYS, canonical_payload
from pisrs_ingest.postgres import PostgresInvariantError
from pisrs_ingest.postgres_chunks import ChunkStore
from pisrs_ingest.postgres_payloads import canonical_payload_sql, refresh_stored_payloads


def test_payload_field_map_preserves_the_existing_contract() -> None:
    row = replace(vector_row(active=False, latest=False, text_id=1), act_id=None)
    expected = asdict(row)
    expected.pop("database_id")
    expected.pop("point_id")
    expected["text"] = expected.pop("chunk_text")
    expected["source"] = "pisrs"
    assert canonical_payload(row) == expected
    assert set(expected) == MANAGED_PAYLOAD_KEYS


@pytest.mark.parametrize(
    "scope",
    [
        {},
        {"sop": ""},
        {"sop": " "},
        {"ids": [True]},
        {"ids": [0]},
        {"ids": ["1"]},
        {"ids": list(range(1, 1002))},
    ],
)
def test_invalid_or_unbounded_scope_never_reaches_sql(scope) -> None:
    cursor = Mock()
    with pytest.raises(ValueError):
        refresh_stored_payloads(cursor, "pisrs_current", **scope)
    cursor.execute.assert_not_called()


def test_empty_ids_never_expand_to_the_sop_or_collection() -> None:
    cursor = Mock()
    assert refresh_stored_payloads(cursor, "pisrs_current", sop="SOP-1", ids=[]) == 0
    cursor.execute.assert_not_called()


@pytest.mark.parametrize("payload_type", [None, "null", "array", "string", "number", "boolean"])
def test_nonobject_payload_blocks_the_entire_selected_batch(payload_type) -> None:
    cursor = Mock()
    cursor.execute.return_value.fetchall.return_value = [
        {"id": 1, "payload_type": "object"},
        {"id": 2, "payload_type": payload_type},
    ]
    with pytest.raises(PostgresInvariantError, match="not an object"):
        refresh_stored_payloads(cursor, "pisrs_current", ids=[1, 2])
    assert cursor.execute.call_count == 1


def test_refresh_locks_the_intersection_and_updates_only_the_selected_ids() -> None:
    cursor = Mock(rowcount=1)
    cursor.execute.return_value.fetchall.return_value = [{"id": 2, "payload_type": "object"}]
    assert refresh_stored_payloads(cursor, "pisrs_current", sop="SOP-1", ids=[1, 2]) == 1
    selection, update = cursor.execute.call_args_list
    assert selection.args[1] == ("pisrs_current", [1, 2], "SOP-1")
    assert selection.args[0].endswith("ORDER BY chunk.id FOR UPDATE")
    assert update.args[1] == ("pisrs_current", [2])


def test_no_selected_rows_cannot_become_a_collection_update() -> None:
    cursor = Mock()
    cursor.execute.return_value.fetchall.return_value = []
    assert refresh_stored_payloads(cursor, "pisrs_current", ids=[1]) == 0
    assert cursor.execute.call_count == 1


@pytest.mark.parametrize("alias", ["chunk; DROP TABLE x", "chunk.id", "x y", ""])
def test_sql_alias_cannot_be_source_data(alias) -> None:
    with pytest.raises(ValueError):
        canonical_payload_sql(alias)


# Real PostgreSQL tests are opt-in; no production DSN or installed schema is used.
@pytest.fixture
def pg():
    dsn = os.environ.get("PISRS_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("requires a dedicated pisrs_test_* PostgreSQL database")
    with (
        psycopg.connect(dsn, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        assert connection.info.dbname.startswith("pisrs_test_"), "dedicated test DB required"
        assert cursor.execute("SELECT to_regnamespace('pisrs') AS n").fetchone()["n"] is None
        cursor.execute("SET LOCAL statement_timeout = '10s'")
        cursor.execute("SET LOCAL lock_timeout = '2s'")
        cursor.execute("CREATE SCHEMA pisrs")
        cursor.execute(
            """
            CREATE TABLE pisrs.embedding_chunks (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                source text, collection_name text, act_id bigint, version_id bigint,
                text_id bigint, sop text, sop_from_docno text, npb_label text,
                naziv text, title text, chunk_index integer, chunk_type text,
                chunk_text text, chunk_text_len integer, block_start_index integer,
                block_end_index integer, block_count integer, token_estimate integer,
                content_hash text, is_latest_for_sop boolean, is_active boolean,
                embedding_model text, embedding_dimensions integer, qdrant_point_id text,
                qdrant_status text, qdrant_error text, qdrant_upserted_at timestamptz,
                payload jsonb, updated_at timestamptz DEFAULT now(),
                UNIQUE (collection_name, text_id, chunk_index)
            )
            """
        )
        try:
            yield cursor
        finally:
            connection.rollback()


def seed(cursor, *, text_id=1, collection="pisrs_current", sop="SOP-1", payload=None):
    row = replace(
        vector_row(active=False, latest=False, text_id=text_id),
        collection_name=collection,
        sop_from_docno=sop,
        act_id=None,
    )
    values = asdict(row)
    values.pop("database_id")
    values["qdrant_point_id"] = values.pop("point_id")
    values.update(
        payload=Jsonb({} if payload is None else payload),
        source="pisrs",
        qdrant_status="uploaded",
        updated_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    names = ", ".join(values)
    parameters = ", ".join(f"%({name})s" for name in values)
    return cursor.execute(
        f"INSERT INTO pisrs.embedding_chunks ({names}) VALUES ({parameters}) RETURNING id",
        values,
    ).fetchone()["id"], row


def read_chunk(cursor, identity):
    return cursor.execute(
        "SELECT * FROM pisrs.embedding_chunks WHERE id = %s", (identity,)
    ).fetchone()


def test_pg_refresh_preserves_provenance_nulls_and_all_nonpayload_columns(pg) -> None:
    identity, row = seed(
        pg,
        payload={"act_id": 999, "is_latest_for_sop": True, "provenance": {"legacy": [1, "keep"]}},
    )
    before = read_chunk(pg, identity)
    assert refresh_stored_payloads(pg, "pisrs_current", ids=[identity]) == 1
    after = read_chunk(pg, identity)
    assert after["payload"] == {**row.payload(), "provenance": {"legacy": [1, "keep"]}}
    for key in before.keys() - {"payload", "updated_at"}:
        assert before[key] == after[key]
    # A second pass is a true no-op, including updated_at.
    assert refresh_stored_payloads(pg, "pisrs_current", ids=[identity]) == 0
    assert read_chunk(pg, identity) == after


def test_pg_scopes_never_touch_other_ids_sops_or_collections(pg) -> None:
    selected, _ = seed(pg)
    other_id, _ = seed(pg, text_id=2)
    other_sop, _ = seed(pg, text_id=3, sop="SOP-2")
    other_collection, _ = seed(pg, text_id=4, collection="another_collection")
    untouched = {
        identity: read_chunk(pg, identity) for identity in (other_id, other_sop, other_collection)
    }
    assert (
        refresh_stored_payloads(
            pg, "pisrs_current", sop="SOP-1", ids=[selected, other_sop, other_collection]
        )
        == 1
    )
    for identity, before in untouched.items():
        assert read_chunk(pg, identity) == before
    assert refresh_stored_payloads(pg, "pisrs_current", ids=[]) == 0


@pytest.mark.parametrize("bad_payload", [Jsonb(None), Jsonb([]), Jsonb("scalar"), None])
def test_pg_malformed_payload_prevents_partial_batch_updates(pg, bad_payload) -> None:
    good_id, _ = seed(pg)
    bad_id, _ = seed(pg, text_id=2)
    pg.execute(
        "UPDATE pisrs.embedding_chunks SET payload = %s WHERE id = %s", (bad_payload, bad_id)
    )
    before = read_chunk(pg, good_id)
    with pytest.raises(PostgresInvariantError, match="not an object"):
        refresh_stored_payloads(pg, "pisrs_current", ids=[good_id, bad_id])
    assert read_chunk(pg, good_id) == before


def test_pg_upsert_retains_provenance_and_repeated_rollover_is_noop(pg) -> None:
    from pisrs_ingest.models import Block, make_chunks
    from pisrs_ingest.postgres_chunks import CHUNK_UPSERT

    identity, row = seed(pg, payload={"provenance": {"keep": True}})
    chunk = make_chunks((Block(1, "p", (), row.chunk_text, "paragraph"),))[0]
    latest = {
        "id": row.version_id,
        "act_id": row.act_id,
        "text_id": row.text_id,
        "sop": row.sop,
        "sop_from_docno": row.sop_from_docno,
        "npb_label": row.npb_label,
        "naziv": row.naziv,
        "title": row.title,
    }
    store = ChunkStore(None, "pisrs_current")
    parameters = store._chunk_parameters(
        latest, chunk, row.embedding_model, row.embedding_dimensions
    )
    pg.execute(CHUNK_UPSERT, parameters)
    assert read_chunk(pg, identity)["payload"]["provenance"] == {"keep": True}
    assert refresh_stored_payloads(pg, "pisrs_current", sop="SOP-1") == 0
    before = read_chunk(pg, identity)
    pg.execute(CHUNK_UPSERT, parameters)
    assert pg.rowcount == 0
    assert read_chunk(pg, identity) == before


@pytest.fixture
def rollover_store(pg):
    from contextlib import contextmanager

    @contextmanager
    def connection(**kwargs):
        yield pg.connection

    pg.execute(
        "CREATE TABLE pisrs.act_text_versions (id bigint, act_id bigint, text_id bigint, "
        "sop text, sop_from_docno text, npb_label text, naziv text, title text)"
    )
    pg.execute(
        "CREATE TABLE pisrs.act_text_blocks (version_id bigint, block_index integer, "
        "block_type text, article_no text, article_title text, class_list text[], text text)"
    )
    return ChunkStore(SimpleNamespace(connect=connection), "pisrs_current")


def test_pg_rollover_refreshes_an_already_inactive_sop_without_versions(pg, rollover_store) -> None:
    identity, row = seed(pg, payload={"is_latest_for_sop": True, "provenance": "keep"})
    store = rollover_store
    rows = store.prepare_rollover("SOP-1", row.embedding_model, row.embedding_dimensions)
    assert len(rows) == 1
    assert read_chunk(pg, identity)["payload"] == {**row.payload(), "provenance": "keep"}


def test_pg_rollover_failure_rolls_back_deactivation_and_payload_changes(pg, rollover_store):
    good_id, row = seed(pg, payload={"provenance": "keep"})
    bad_id, _ = seed(pg, text_id=2)
    pg.execute("UPDATE pisrs.embedding_chunks SET is_active = true, is_latest_for_sop = true")
    pg.execute("UPDATE pisrs.embedding_chunks SET payload = '[]'::jsonb WHERE id = %s", (bad_id,))
    before = {identity: read_chunk(pg, identity) for identity in (good_id, bad_id)}
    with pytest.raises(PostgresInvariantError, match="not an object"):
        rollover_store.prepare_rollover("SOP-1", row.embedding_model, row.embedding_dimensions)
    for identity, expected in before.items():
        assert read_chunk(pg, identity) == expected


def test_pg_latest_rollover_also_refreshes_untouched_inactive_chunks(pg, rollover_store):
    old_id, old = seed(pg, payload={"is_latest_for_sop": True, "provenance": "old"})
    latest_id, latest = seed(pg, text_id=2, payload={"provenance": "latest"})
    pg.execute(
        "INSERT INTO pisrs.act_text_versions VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            latest.version_id,
            latest.act_id,
            latest.text_id,
            latest.sop,
            latest.sop_from_docno,
            "npb02",
            latest.naziv,
            latest.title,
        ),
    )
    pg.execute(
        "INSERT INTO pisrs.act_text_blocks VALUES (%s, 1, 'paragraph', NULL, NULL, '{}', %s)",
        (latest.version_id, latest.chunk_text),
    )
    rows = rollover_store.prepare_rollover(
        "SOP-1", latest.embedding_model, latest.embedding_dimensions
    )
    assert len(rows) == 2
    assert read_chunk(pg, old_id)["payload"] == {**old.payload(), "provenance": "old"}
    assert read_chunk(pg, latest_id)["payload"]["provenance"] == "latest"
    for row in rows:
        assert read_chunk(pg, row.database_id)["payload"] == {
            **row.payload(),
            "provenance": "old" if row.text_id == 1 else "latest",
        }
    before = {row.database_id: read_chunk(pg, row.database_id) for row in rows}
    rollover_store.prepare_rollover("SOP-1", latest.embedding_model, latest.embedding_dimensions)
    for identity, expected in before.items():
        assert read_chunk(pg, identity) == expected
