"""Plan and atomically append state-catalog provenance; no other ingest stages."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from psycopg import sql

from .client import PisrsClient
from .models import Act
from .postgres import PostgresDatabase

TABLES = ("act_sync_catalog", "acts")
ENDPOINTS = PisrsClient.ACT_ENDPOINTS
ADDITIONAL_ENDPOINTS = frozenset(ENDPOINTS[4:])
METADATA = (
    "moped_id",
    "sop",
    "naziv",
    "kratica",
    "osnovni",
    "vrsta_akta_id",
    "vrsta_akta_naziv",
    "datum_sprejetja",
    "datum_objave",
    "datum_zacetka_veljavnosti",
    "datum_prenehanja_veljavnosti",
)
WARNING = (
    "APPLY requires separately approved activation of the seven-catalog code. "
    "The old four-catalog nightly overwrites and removes this provenance."
)


class CatalogScopeError(RuntimeError):
    """A reviewed identity, database, or write boundary no longer holds."""


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass
class ProvenancePlan:
    sha256: str
    identities: int
    endpoint_counts: dict[str, int]
    rows: dict[str, list[dict[str, Any]]]
    changes: dict[str, list[dict[str, Any]]]
    links_added: dict[str, int]

    def summary(self) -> dict[str, Any]:
        return {
            "plan_sha256": self.sha256,
            "identities": self.identities,
            "endpoint_counts": self.endpoint_counts,
            "rows_to_update": {t: len(self.changes[t]) for t in TABLES},
            "links_to_add_per_table": self.links_added,
            "allowed_columns": ["seen_in_endpoints", "source_item.seen_in_endpoints", "updated_at"],
            "inserts": 0,
            "deletes": 0,
            "sequence_calls": 0,
            "npb_writes": 0,
            "version_block_chunk_writes": 0,
            "qdrant_calls": 0,
            "embedding_calls": 0,
            "checkpoint_writes": 0,
            "warning": WARNING,
        }


def _source(acts: list[Act]) -> dict[int, Act]:
    by_id = {a.register_id: a for a in acts}
    if not acts or len(by_id) != len(acts):
        raise CatalogScopeError("empty or duplicate source identities")
    observed: set[str] = set()
    for a in acts:
        if type(a.register_id) is not int or a.register_id <= 0:
            raise CatalogScopeError("invalid source identity")
        seen = a.seen_in_endpoints
        if not seen or len(seen) != len(set(seen)) or set(seen) - set(ENDPOINTS):
            raise CatalogScopeError("invalid source provenance")
        observed.update(seen)
    if observed != set(ENDPOINTS):
        raise CatalogScopeError("all seven nonempty state catalogs must be represented")
    return by_id


def _boundary(cursor: Any, expected_database: str, *, apply: bool) -> dict[str, Any]:
    identity = cursor.execute(
        "SELECT current_database() AS database,"
        "current_setting('transaction_read_only') AS read_only"
    ).fetchone()
    if identity["database"] != expected_database:
        raise CatalogScopeError("unexpected database identity")
    if identity["read_only"] != ("off" if apply else "on"):
        raise CatalogScopeError("unexpected transaction read-only state")
    tables = cursor.execute(
        "SELECT c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='pisrs' AND c.relname=ANY(%s) ORDER BY c.relname",
        (list(TABLES),),
    ).fetchall()
    if len(tables) != 2 or any(
        t["relkind"] != "r" or t["relrowsecurity"] or t["relforcerowsecurity"] for t in tables
    ):
        raise CatalogScopeError("expected ordinary catalog tables without RLS")
    # Reject unreviewed server-side write paths, rather than disabling triggers/rules.
    custom = cursor.execute(
        "SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='pisrs' "
        "AND c.relname=ANY(%s) AND NOT t.tgisinternal AND t.tgenabled<>'D' "
        "UNION ALL SELECT r.rulename FROM pg_rewrite r "
        "JOIN pg_class c ON c.oid=r.ev_class JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='pisrs' AND c.relname=ANY(%s)",
        (list(TABLES), list(TABLES)),
    ).fetchall()
    if custom:
        raise CatalogScopeError("catalog triggers or rules require separate review")
    return {"database": identity["database"], "tables": tables}


def _read(cursor: Any) -> dict[str, list[dict[str, Any]]]:
    result = {}
    fields = sql.SQL(",").join(sql.Identifier(k) for k in METADATA)
    for table in TABLES:
        result[table] = cursor.execute(
            sql.SQL(
                "SELECT id,register_id,{fields},endpoint,seen_in_endpoints,"
                "source_item-'raw' AS envelope,"
                "md5(to_jsonb(t)::text) AS row_hash,"
                "md5((to_jsonb(t)-'seen_in_endpoints'-'source_item'-'updated_at')::text) "
                "AS other_hash,md5((source_item-'seen_in_endpoints')::text) AS source_rest_hash "
                "FROM pisrs.{table} t ORDER BY register_id"
            ).format(fields=fields, table=sql.Identifier(table))
        ).fetchall()
    return result


def _plan(
    acts: list[Act], rows: dict[str, list[dict[str, Any]]], boundary: dict[str, Any]
) -> ProvenancePlan:
    source = _source(acts)
    changes: dict[str, list[dict[str, Any]]] = {}
    links: Counter[str] = Counter()
    for table in TABLES:
        existing = rows[table]
        if len(existing) != len(source) or {r["register_id"] for r in existing} != set(source):
            raise CatalogScopeError("source and both stored identity sets must match exactly")
        changes[table] = []
        for row in existing:
            act = source[row["register_id"]]
            for key in METADATA:
                value = row[key]
                if key.startswith("datum_") and value is not None:
                    value = str(value)
                if value != getattr(act, key):
                    raise CatalogScopeError("non-provenance metadata drift requires review")
            before = row["seen_in_endpoints"]
            envelope = row["envelope"]
            if (
                not isinstance(before, list)
                or not before
                or any(not isinstance(e, str) for e in before)
                or len(before) != len(set(before))
                or set(before) - set(ENDPOINTS)
                or not isinstance(envelope, dict)
                or envelope.get("seen_in_endpoints") != before
                or envelope.get("register_id") != act.register_id
                or envelope.get("moped_id") != act.moped_id
                or row["endpoint"] not in before
            ):
                raise CatalogScopeError("malformed or conflicting stored provenance")
            missing = [e for e in ENDPOINTS if e in act.seen_in_endpoints and e not in before]
            if set(missing) - ADDITIONAL_ENDPOINTS:
                raise CatalogScopeError("missing legacy-catalog provenance requires review")
            if missing:
                changes[table].append(
                    {"id": row["id"], "register_id": act.register_id, "seen": before + missing}
                )
                if table == "acts":
                    links.update(missing)
    # The two authoritative representations must agree, even for an empty plan.
    if [r["seen_in_endpoints"] for r in rows[TABLES[0]]] != [
        r["seen_in_endpoints"] for r in rows[TABLES[1]]
    ]:
        raise CatalogScopeError("stored catalog provenance sets disagree")
    source_state = [
        (a.register_id, list(a.seen_in_endpoints))
        for a in sorted(acts, key=lambda a: a.register_id)
    ]
    fingerprint = {
        "format": 1,
        "boundary": boundary,
        "source": source_state,
        "rows": {t: [(r["id"], r["register_id"], r["row_hash"]) for r in rows[t]] for t in TABLES},
        "changes": changes,
    }
    return ProvenancePlan(
        _digest(fingerprint),
        len(source),
        {e: sum(e in a.seen_in_endpoints for a in acts) for e in ENDPOINTS},
        rows,
        changes,
        dict(links),
    )


def catalog_provenance(
    database: PostgresDatabase,
    acts: list[Act],
    expected_database: str,
    *,
    apply: bool = False,
    expected_plan: str | None = None,
    before_write: Callable[[ProvenancePlan], None] | None = None,
) -> ProvenancePlan:
    """Apply only a reviewed plan; caller supplies approval and the application lock."""
    _source(acts)  # Reject incomplete discovery before opening any write connection.
    if apply and (not expected_plan or len(expected_plan) != 64):
        raise CatalogScopeError("apply requires the reviewed dry-run plan SHA-256")
    with (
        database.connect(read_only=not apply) as connection,
        connection.transaction(),
        connection.cursor() as cursor,
    ):
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cursor.execute("SET LOCAL timezone='UTC'")
        cursor.execute("SET LOCAL statement_timeout='60s'")
        cursor.execute("SET LOCAL lock_timeout='1s'")
        if apply:
            cursor.execute(
                "LOCK TABLE pisrs.act_sync_catalog,pisrs.acts IN SHARE ROW EXCLUSIVE MODE"
            )
        boundary = _boundary(cursor, expected_database, apply=apply)
        plan = _plan(acts, _read(cursor), boundary)
        if not apply:
            return plan
        if plan.sha256 != expected_plan:
            raise CatalogScopeError("reviewed plan no longer matches; no updates performed")
        if before_write is not None:
            before_write(plan)
        for table in TABLES:
            if not plan.changes[table]:
                continue
            cursor.executemany(
                sql.SQL(
                    "UPDATE pisrs.{table} SET seen_in_endpoints=%(seen)s::text[],"
                    "source_item=jsonb_set(source_item,'{{seen_in_endpoints}}',"
                    "to_jsonb(%(seen)s::text[]),true),updated_at=now() "
                    "WHERE id=%(id)s AND register_id=%(register_id)s"
                ).format(table=sql.Identifier(table)),
                plan.changes[table],
            )
            if cursor.rowcount != len(plan.changes[table]):
                raise CatalogScopeError("update count mismatch; rolling back")
        after = _read(cursor)
        post = _plan(acts, after, boundary)
        if any(post.changes.values()):
            raise CatalogScopeError("postflight provenance mismatch; rolling back")
        for table in TABLES:
            targets = {r["id"]: r["seen"] for r in plan.changes[table]}
            for old, new in zip(plan.rows[table], after[table], strict=True):
                if old["id"] not in targets:
                    valid = old == new
                else:
                    valid = (
                        old["id"] == new["id"]
                        and old["other_hash"] == new["other_hash"]
                        and old["source_rest_hash"] == new["source_rest_hash"]
                        and new["seen_in_endpoints"] == targets[old["id"]]
                    )
                if not valid:
                    raise CatalogScopeError("unapproved row drift; rolling back")
        return plan
