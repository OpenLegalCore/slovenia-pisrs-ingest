"""Additive persistence for official EU and local catalog identities."""

from __future__ import annotations

from itertools import islice

from psycopg.types.json import Jsonb

from .models import Act, ExternalCatalogItem, NpbDocument
from .postgres import PostgresDatabase, PostgresInvariantError


class ExternalCatalogStore:
    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database

    def synchronize(self, items: list[ExternalCatalogItem]) -> None:
        expected_namespaces = ("EU", "LS_ACT", "LS_NPB")
        grouped: dict[str, dict[str, ExternalCatalogItem]] = {
            namespace: {} for namespace in expected_namespaces
        }
        for item in items:
            if item.namespace not in grouped:
                raise PostgresInvariantError("unknown extended catalog namespace")
            key = str(item.source_id)
            if key in grouped[item.namespace]:
                raise PostgresInvariantError("duplicate extended catalog identity")
            grouped[item.namespace][key] = item
        if any(not group for group in grouped.values()):
            raise PostgresInvariantError("refusing an empty EU or local catalog")
        links = local_npb_links(list(grouped["LS_ACT"].values()), list(grouped["LS_NPB"].values()))

        with self.database.connect() as connection, connection.transaction():
            existing = connection.execute(
                "SELECT namespace, source_id, moped_plus_id, eda, sop, linked_act_source_id "
                "FROM pisrs.source_catalog_items"
            ).fetchall()
            for row in existing:
                item = grouped.get(row["namespace"], {}).get(row["source_id"])
                if item is None:
                    raise PostgresInvariantError(
                        "complete extended catalog omitted an existing source identity"
                    )
                for column in ("moped_plus_id", "eda", "sop"):
                    old, new = row[column], getattr(item, column)
                    if old is not None and new is not None and old != new:
                        raise PostgresInvariantError(
                            f"extended source identity has conflicting {column}"
                        )
                if (
                    row["namespace"] == "LS_NPB"
                    and row["linked_act_source_id"] is not None
                    and row["linked_act_source_id"] != links[row["source_id"]][3]
                ):
                    raise PostgresInvariantError("previous local NPB act link changed")
            with connection.cursor() as cursor:
                for group in grouped.values():
                    parameters = (_external_parameters(item, links) for item in group.values())
                    while batch := list(islice(parameters, 1000)):
                        cursor.executemany(EXTERNAL_UPSERT, batch)

    def synchronize_state_raw(self, acts: list[Act]) -> None:
        """Retain every state endpoint variant without changing legacy catalog JSON."""

        with (
            self.database.connect() as connection,
            connection.transaction(),
            connection.cursor() as cursor,
        ):
            batch: list[dict] = []
            for act in acts:
                if set(act.raw_by_endpoint) != set(act.seen_in_endpoints):
                    raise PostgresInvariantError("state raw variants do not match provenance")
                for endpoint, raw in act.raw_by_endpoint.items():
                    batch.append(
                        {
                            "register_id": act.register_id,
                            "endpoint": endpoint,
                            "raw": Jsonb(raw),
                        }
                    )
                    if len(batch) == 1000:
                        cursor.executemany(STATE_RAW_UPSERT, batch)
                        batch.clear()
            if batch:
                cursor.executemany(STATE_RAW_UPSERT, batch)


def local_npb_links(
    acts: list[ExternalCatalogItem], npbs: list[ExternalCatalogItem]
) -> dict[str, tuple[str | None, str | None, str, str | None]]:
    """Use exact SOP only; retain ambiguous and unmatched versions unlinked."""

    by_sop: dict[str, set[str]] = {}
    for act in acts:
        if act.namespace != "LS_ACT":
            raise PostgresInvariantError("local link candidates include a non-local act")
        if act.sop:
            by_sop.setdefault(act.sop, set()).add(str(act.source_id))
    links: dict[str, tuple[str | None, str | None, str, str | None]] = {}
    for item in npbs:
        if item.namespace != "LS_NPB":
            raise PostgresInvariantError("local link input includes a non-local NPB")
        raw = item.raw_by_endpoint.get("/npb-ls")
        if raw is None:
            raise PostgresInvariantError("local NPB has no source row")
        document = NpbDocument.from_raw(raw)
        if document.text_id != item.source_id:
            raise PostgresInvariantError("local NPB source identity changed")
        sop = document.sop_from_docno
        candidates = by_sop.get(sop, set()) if sop else set()
        if not sop:
            status = "NO_PARSED_SOP"
        elif not candidates:
            status = "UNMATCHED_SOP"
        elif len(candidates) > 1:
            status = "AMBIGUOUS_SOP"
        else:
            status = "UNIQUE_SOP"
        links[str(item.source_id)] = (
            sop,
            document.npb_label,
            status,
            next(iter(candidates)) if status == "UNIQUE_SOP" else None,
        )
    return links


def _external_parameters(
    item: ExternalCatalogItem,
    links: dict[str, tuple[str | None, str | None, str, str | None]],
) -> dict:
    link = links[str(item.source_id)] if item.namespace == "LS_NPB" else None
    return {
        "namespace": item.namespace,
        "source_id": str(item.source_id),
        "source_id_int": item.source_id if isinstance(item.source_id, int) else None,
        "title": item.title,
        "moped_plus_id": item.moped_plus_id,
        "eda": item.eda,
        "sop": item.sop,
        "sop_from_docno": link[0] if link else None,
        "npb_label": link[1] if link else None,
        "link_status": link[2] if link else None,
        "linked_act_namespace": "LS_ACT" if link and link[3] is not None else None,
        "linked_act_source_id": link[3] if link else None,
        "seen": list(item.seen_in_endpoints),
        "raw": Jsonb(item.raw_by_endpoint),
    }


EXTERNAL_UPSERT = """
INSERT INTO pisrs.source_catalog_items (
    namespace, source_id, source_id_int, title, moped_plus_id, eda, sop,
    sop_from_docno, npb_label, linked_act_namespace, linked_act_source_id, link_status,
    seen_in_endpoints, raw_by_endpoint
) VALUES (
    %(namespace)s, %(source_id)s, %(source_id_int)s, %(title)s,
    %(moped_plus_id)s, %(eda)s, %(sop)s,
    %(sop_from_docno)s, %(npb_label)s, %(linked_act_namespace)s,
    %(linked_act_source_id)s, %(link_status)s, %(seen)s, %(raw)s
)
ON CONFLICT (namespace, source_id) DO UPDATE SET
    source_id_int = EXCLUDED.source_id_int,
    title = EXCLUDED.title,
    moped_plus_id = COALESCE(pisrs.source_catalog_items.moped_plus_id, EXCLUDED.moped_plus_id),
    eda = COALESCE(pisrs.source_catalog_items.eda, EXCLUDED.eda),
    sop = COALESCE(pisrs.source_catalog_items.sop, EXCLUDED.sop),
    sop_from_docno = EXCLUDED.sop_from_docno,
    npb_label = EXCLUDED.npb_label,
    linked_act_namespace = EXCLUDED.linked_act_namespace,
    linked_act_source_id = EXCLUDED.linked_act_source_id,
    link_status = EXCLUDED.link_status,
    seen_in_endpoints = EXCLUDED.seen_in_endpoints,
    raw_by_endpoint = EXCLUDED.raw_by_endpoint,
    updated_at = now()
WHERE ROW(
    pisrs.source_catalog_items.source_id_int, pisrs.source_catalog_items.title,
    pisrs.source_catalog_items.moped_plus_id, pisrs.source_catalog_items.eda,
    pisrs.source_catalog_items.sop, pisrs.source_catalog_items.seen_in_endpoints,
    pisrs.source_catalog_items.sop_from_docno, pisrs.source_catalog_items.npb_label,
    pisrs.source_catalog_items.linked_act_namespace,
    pisrs.source_catalog_items.linked_act_source_id,
    pisrs.source_catalog_items.link_status,
    pisrs.source_catalog_items.raw_by_endpoint
) IS DISTINCT FROM ROW(
    EXCLUDED.source_id_int, EXCLUDED.title,
    COALESCE(pisrs.source_catalog_items.moped_plus_id, EXCLUDED.moped_plus_id),
    COALESCE(pisrs.source_catalog_items.eda, EXCLUDED.eda),
    COALESCE(pisrs.source_catalog_items.sop, EXCLUDED.sop),
    EXCLUDED.seen_in_endpoints, EXCLUDED.sop_from_docno, EXCLUDED.npb_label,
    EXCLUDED.linked_act_namespace, EXCLUDED.linked_act_source_id,
    EXCLUDED.link_status, EXCLUDED.raw_by_endpoint
)
"""


STATE_RAW_UPSERT = """
INSERT INTO pisrs.state_raw_variants (register_id, endpoint, raw_item)
VALUES (%(register_id)s, %(endpoint)s, %(raw)s)
ON CONFLICT (register_id, endpoint) DO UPDATE SET
    raw_item = EXCLUDED.raw_item, updated_at = now()
WHERE pisrs.state_raw_variants.raw_item IS DISTINCT FROM EXCLUDED.raw_item
"""
