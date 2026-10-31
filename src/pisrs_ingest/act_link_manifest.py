"""Closed, metadata-only act-link operation; deliberately independent of nightly."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy

from psycopg import sql
from psycopg.types.json import Jsonb

from .models import qdrant_point_id
from .postgres import PostgresInvariantError

TABLES = ("act_text_versions", "act_text_blocks", "embedding_chunks")
STAMP = "$TRANSACTION_TIMESTAMP"


def require(condition, message):
    if not condition:
        raise PostgresInvariantError(message)


def encoded(value):
    return (
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def same(left, right):
    """Exact JSON values/types, including bool versus integer."""
    return digest(left) == digest(right)


def validate_manifest(manifest):
    require(
        manifest["database"] == "appdb" and manifest["collection"] == "pisrs_current",
        "wrong manifest destination",
    )
    targets = manifest["targets"]
    ids = [t["version_id"] for t in targets]
    require(
        bool(ids) and ids == sorted(set(ids)) and all(type(i) is int and i > 0 for i in ids),
        "invalid closed version IDs",
    )
    mapping = {t["version_id"]: t["act_id"] for t in targets}
    require(all(type(i) is int and i > 0 for i in mapping.values()), "invalid act IDs")
    before = manifest["before"]
    require(set(before) == set(TABLES), "invalid table scope")
    for table in TABLES:
        rows = before[table]
        row_ids = [r["id"] for r in rows]
        require(row_ids == sorted(set(row_ids)), "duplicate or unordered row IDs")
        for row in rows:
            version = row["id"] if table == TABLES[0] else row["version_id"]
            require(version in mapping and row["act_id"] is None, "non-NULL or foreign link")
    require([r["id"] for r in before[TABLES[0]]] == ids, "parent scope mismatch")
    parents = {r["id"]: r for r in before[TABLES[0]]}
    for t in targets:
        require(
            bool(t["sop"].strip()) and parents[t["version_id"]]["sop_from_docno"] == t["sop"],
            "invalid SOP proof",
        )
    for table in TABLES[1:]:
        for row in before[table]:
            parent = parents[row["version_id"]]
            require(row["text_id"] == parent["text_id"], "child text identity conflict")
            if table == TABLES[2]:
                require(
                    row["collection_name"] == "pisrs_current"
                    and row["sop_from_docno"] == parent["sop_from_docno"]
                    and isinstance(row["payload"], dict)
                    and row["payload"].get("act_id") is None
                    and "act_id" in row["payload"]
                    and row["qdrant_point_id"]
                    == qdrant_point_id("pisrs_current", row["text_id"], row["chunk_index"]),
                    "chunk identity/payload conflict",
                )
    qids = [r["qdrant_point_id"] for r in before[TABLES[2]]]
    require(
        len(set(qids)) == len(qids) and set(qids) == set(manifest["qdrant"]), "point scope mismatch"
    )
    require(digest(before) == manifest["before_sha256"], "before-image hash mismatch")
    require(
        digest(expected_state(manifest, STAMP)) == manifest["expected_template_sha256"],
        "expected-image hash mismatch",
    )
    for row in before[TABLES[2]]:
        point = manifest["qdrant"][row["qdrant_point_id"]]
        require(
            same(point["payload"], row["payload"]) and point["dimensions"] == 3072,
            "PG/Qdrant baseline mismatch",
        )
    require(
        digest(manifest["qdrant"]) == manifest["qdrant_before_sha256"],
        "point before-image hash mismatch",
    )
    require(
        digest(expected_points(manifest)) == manifest["qdrant_expected_sha256"],
        "point expected-image hash mismatch",
    )
    require(
        digest(closed_scope(manifest)) == manifest["scope_sha256"], "closed scope hash mismatch"
    )
    return mapping


def closed_scope(manifest):
    return {
        "targets": manifest["targets"],
        "blocks": [r["id"] for r in manifest["before"][TABLES[1]]],
        "chunks": [
            {"id": r["id"], "point_id": r["qdrant_point_id"]} for r in manifest["before"][TABLES[2]]
        ],
    }


def expected_points(manifest):
    mapping = {t["version_id"]: t["act_id"] for t in manifest["targets"]}
    result = deepcopy(manifest["qdrant"])
    for row in manifest["before"][TABLES[2]]:
        result[row["qdrant_point_id"]]["payload"]["act_id"] = mapping[row["version_id"]]
    return result


def expected_state(manifest, timestamp):
    mapping = {t["version_id"]: t["act_id"] for t in manifest["targets"]}
    after = deepcopy(manifest["before"])
    for table, rows in after.items():
        for row in rows:
            version = row["id"] if table == TABLES[0] else row["version_id"]
            row["act_id"] = mapping[version]
            row["updated_at"] = timestamp
            if table == TABLES[2]:
                row["payload"]["act_id"] = mapping[version]
    return after


def snapshot(connection, manifest, *, lock=False):
    ids = [t["version_id"] for t in manifest["targets"]]
    result = {}
    for table in TABLES:
        column = "id" if table == TABLES[0] else "version_id"
        limit = (
            len(manifest["before"][table]) + 1
            if "before" in manifest
            else {TABLES[0]: 1001, TABLES[1]: 100001, TABLES[2]: 5001}[table]
        )
        query = sql.SQL(
            "SELECT to_jsonb(t) AS row FROM pisrs.{} t WHERE {}=ANY(%s) "
            "ORDER BY id LIMIT %s" + (" FOR UPDATE" if lock else "")
        ).format(sql.Identifier(table), sql.Identifier(column))
        result[table] = [r["row"] for r in connection.execute(query, (ids, limit)).fetchall()]
    return result


def lock_and_validate(connection, manifest):
    validate_manifest(manifest)
    connection.execute("SET LOCAL statement_timeout='30s'")
    connection.execute("SET LOCAL lock_timeout='3s'")
    connection.execute("LOCK TABLE pisrs.acts IN SHARE MODE")
    connection.execute(
        "LOCK TABLE pisrs.act_text_versions, pisrs.act_text_blocks, "
        "pisrs.embedding_chunks IN ROW SHARE MODE"
    )
    for table in TABLES[1:]:
        fk = connection.execute(
            """SELECT count(*) AS n FROM pg_constraint
            WHERE contype='f' AND convalidated AND NOT condeferrable
              AND conrelid=%s::regclass AND confrelid='pisrs.act_text_versions'::regclass
              AND conkey=ARRAY[(SELECT attnum FROM pg_attribute
                  WHERE attrelid=%s::regclass AND attname='version_id')]::smallint[]
              AND confkey=ARRAY[(SELECT attnum FROM pg_attribute
                  WHERE attrelid='pisrs.act_text_versions'::regclass AND attname='id')]::smallint[]
            """,
            ("pisrs." + table, "pisrs." + table),
        ).fetchone()
        require(fk["n"] == 1, "immediate child FK required for closed membership locking")
    actual = snapshot(connection, manifest, lock=True)
    require(same(actual, manifest["before"]), "closed before-state drift")
    # Parent FOR UPDATE locks also block FK-referencing child inserts until commit.
    for target in manifest["targets"]:
        candidates = connection.execute(
            "SELECT id FROM pisrs.acts WHERE sop=%s ORDER BY id", (target["sop"],)
        ).fetchall()
        require([r["id"] for r in candidates] == [target["act_id"]], "SOP proof drift")
    timestamp = connection.execute("SELECT to_jsonb(transaction_timestamp()) AS stamp").fetchone()
    return expected_state(manifest, timestamp["stamp"])


def apply_locked(connection, manifest, expected):
    require(expected == lock_and_validate(connection, manifest), "expected-state drift")
    for table in TABLES:
        rows = expected[table]
        if not rows:
            continue
        payload = ", payload=a.payload" if table == TABLES[2] else ""
        query = sql.SQL(
            "UPDATE pisrs.{table} t SET act_id=a.act_id, updated_at=a.updated_at"
            + payload
            + " FROM jsonb_populate_recordset(NULL::pisrs.{table},%s) a "
            "WHERE t.id=a.id AND t.act_id IS NULL"
        ).format(table=sql.Identifier(table))
        cursor = connection.execute(query, (Jsonb(rows),))
        require(cursor.rowcount == len(rows), "closed update count mismatch")
    require(same(snapshot(connection, manifest), expected), "full precommit state mismatch")


def classify_pg(actual, before, expected):
    if same(actual, expected):
        return "after"
    if same(actual, before):
        return "before"
    raise PostgresInvariantError("mixed or externally changed PG state; no write")


def vector_proof(vector):
    require(
        isinstance(vector, list)
        and len(vector) == 3072
        and all(type(v) in (int, float) and math.isfinite(v) for v in vector),
        "invalid existing vector",
    )
    return digest(vector)


def classify_point(point, before, act_id):
    require(vector_proof(point["vector"]) == before["vector_sha256"], "vector changed")
    if same(point["payload"], {**before["payload"], "act_id": act_id}):
        return "after"
    if same(point["payload"], before["payload"]):
        return "before"
    raise PostgresInvariantError("point payload drift; no write")


def sync_points(manifest, retrieve, patch, *, reverse=False, progress=lambda *_: None):
    """Only patch act_id on explicit existing points. No vector or upsert API is accepted."""
    mapping = {t["version_id"]: t["act_id"] for t in manifest["targets"]}
    chunks = manifest["before"][TABLES[2]]
    states = retrieve([r["qdrant_point_id"] for r in chunks])
    require(set(states) == set(manifest["qdrant"]), "missing/extra retrieved point")
    # Validate the entire point subset before the first patch, also on resume.
    for row in chunks:
        pid = row["qdrant_point_id"]
        classify_point(states[pid], manifest["qdrant"][pid], mapping[row["version_id"]])
    changed = 0
    for row in chunks:
        pid = row["qdrant_point_id"]
        point = retrieve([pid])
        require(set(point) == {pid}, "point disappeared")
        state = classify_point(point[pid], manifest["qdrant"][pid], mapping[row["version_id"]])
        wanted = "before" if reverse else "after"
        if state != wanted:
            patch(pid, None if reverse else mapping[row["version_id"]])
            changed += 1
        readback = retrieve([pid])
        require(
            set(readback) == {pid}
            and classify_point(readback[pid], manifest["qdrant"][pid], mapping[row["version_id"]])
            == wanted,
            "point readback failed",
        )
        progress(pid, wanted)
    final = retrieve([r["qdrant_point_id"] for r in chunks])
    require(set(final) == set(manifest["qdrant"]), "final point subset incomplete")
    for row in chunks:
        pid = row["qdrant_point_id"]
        require(
            classify_point(final[pid], manifest["qdrant"][pid], mapping[row["version_id"]])
            == ("before" if reverse else "after"),
            "final point state drift",
        )
    return changed


def restore_sql(manifest, expected):
    """Narrow privileged recovery, only after all Qdrant points are proved restored.

    The timestamp trigger is bypassed only in this recovery transaction. Full-row
    guards precede all updates. The caller must hold the real application flock.
    """
    validate_manifest(manifest)
    require(
        expected == expected_state(manifest, expected[TABLES[0]][0]["updated_at"]),
        "invalid recovery image",
    )
    require(
        "$restore$" not in encoded(manifest).decode()
        and "$restore$" not in encoded(expected).decode(),
        "recovery delimiter collision",
    )
    parts = [
        "BEGIN; SET LOCAL statement_timeout='30s'; SET LOCAL lock_timeout='3s';",
        "SET LOCAL TIME ZONE 'UTC';",
        "SET LOCAL standard_conforming_strings=on; SET LOCAL session_replication_role=replica;",
        "LOCK TABLE pisrs.acts IN SHARE MODE;",
    ]
    for table in TABLES:
        ids = [t["version_id"] for t in manifest["targets"]]
        col = "id" if table == TABLES[0] else "version_id"
        parts.append(
            f"SELECT id FROM pisrs.{table} WHERE {col}=ANY(ARRAY{ids}::bigint[]) "
            "ORDER BY id FOR UPDATE;"
        )
    for table in TABLES:
        after = encoded(expected[table]).decode().replace("'", "''")
        col = "id" if table == TABLES[0] else "version_id"
        parts.append(f"""DO $restore$
        BEGIN
          IF (SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb)
              FROM pisrs.{table} t WHERE {col}=ANY(ARRAY{ids}::bigint[]))
              IS DISTINCT FROM '{after}'::jsonb THEN RAISE EXCEPTION 'recovery drift'; END IF;
        END $restore$;""")
        # All tables must pass before ANY restore UPDATE (append updates separately below).
    for table in TABLES:
        before = encoded(manifest["before"][table]).decode().replace("'", "''")
        payload = ",payload=a.payload" if table == TABLES[2] else ""
        parts.append(
            f"UPDATE pisrs.{table} t SET act_id=a.act_id,updated_at=a.updated_at{payload} "
            f"FROM jsonb_populate_recordset(NULL::pisrs.{table},'{before}'::jsonb) a "
            "WHERE t.id=a.id;"
        )
    for table in TABLES:
        before = encoded(manifest["before"][table]).decode().replace("'", "''")
        col = "id" if table == TABLES[0] else "version_id"
        parts.append(f"""DO $restore$
        BEGIN
          IF (SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb)
              FROM pisrs.{table} t WHERE {col}=ANY(ARRAY{ids}::bigint[]))
              IS DISTINCT FROM '{before}'::jsonb THEN RAISE EXCEPTION 'restore readback'; END IF;
        END $restore$;""")
    parts.append("COMMIT; SELECT 'RESTORED_COMMITTED';")
    text = "\n".join(parts)
    tag = "$actlink_" + digest(manifest) + "$"
    require(tag not in text, "recovery delimiter collision")
    return text.replace("$restore$", tag)
