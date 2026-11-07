"""Synthetic API contracts for the three source identity namespaces."""

from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlsplit

import pytest

from pisrs_ingest.client import PisrsClient
from pisrs_ingest.models import ExternalCatalogItem, SourceInvariantError
from pisrs_ingest.postgres import PostgresInvariantError
from pisrs_ingest.postgres_external import (
    EXTERNAL_UPSERT,
    STATE_RAW_UPSERT,
    ExternalCatalogStore,
    local_npb_links,
)


class Pages:
    def __init__(self, pages: dict[str, list[dict]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, int]] = []

    def request(self, method: str, url: str, **kwargs):
        assert method == "GET"
        path = urlsplit(url).path.removeprefix("/extapi")
        page = kwargs.get("params", {}).get("page", 1)
        self.calls.append((path, page))
        payload = self.pages[path][page - 1] if not path.endswith("/seznam") else self.pages[path]
        return type("Response", (), {"json": lambda _: deepcopy(payload)})()


def source(pages: dict[str, list[dict]]) -> PisrsClient:
    return PisrsClient("https://example.invalid/extapi", "fixture", Pages(pages))


def local_pages() -> dict[str, list[dict]]:
    paths = PisrsClient.LOCAL_ACT_ENDPOINTS
    return {
        paths[0]: [
            {
                "data": [{"id": 7, "mopedPlusId": "LS7", "eda": "EDA7", "sop": "S7", "naziv": "A"}],
                "totalCount": 0,
            },
            {"data": [], "totalCount": 65271},
        ],
        paths[1]: [
            {
                "data": [
                    {
                        "id": 7,
                        "mopedPlusId": "LS7",
                        "eda": "EDA7",
                        "sop": "S7",
                        "naziv": "A",
                        "other": 1,
                    }
                ],
                "totalCount": 65271,
            },
            {"data": [], "totalCount": 0},
        ],
        paths[2]: [{"data": [], "totalCount": 0}],
    }


def test_local_acts_use_empty_page_and_preserve_overlap_variants() -> None:
    reader = source(local_pages())
    items = reader.discover_local_acts()
    assert len(items) == 1
    assert items[0].namespace == "LS_ACT"
    assert items[0].source_id == 7
    assert items[0].eda == "EDA7"
    assert items[0].seen_in_endpoints == PisrsClient.LOCAL_ACT_ENDPOINTS[:2]
    assert len(items[0].raw_by_endpoint) == 2
    assert reader.http.calls == [
        (PisrsClient.LOCAL_ACT_ENDPOINTS[0], 1),
        (PisrsClient.LOCAL_ACT_ENDPOINTS[0], 2),
        (PisrsClient.LOCAL_ACT_ENDPOINTS[1], 1),
        (PisrsClient.LOCAL_ACT_ENDPOINTS[1], 2),
        (PisrsClient.LOCAL_ACT_ENDPOINTS[2], 1),
    ]


@pytest.mark.parametrize(
    "field,value", [("mopedPlusId", "OTHER"), ("eda", "OTHER"), ("sop", "OTHER")]
)
def test_local_overlap_conflicts_fail_closed(field: str, value: str) -> None:
    pages = local_pages()
    pages[PisrsClient.LOCAL_ACT_ENDPOINTS[1]][0]["data"][0][field] = value
    with pytest.raises(SourceInvariantError, match="conflicting"):
        source(pages).discover_local_acts()


def test_eu_celex_is_exact_and_not_coerced_to_numeric_id() -> None:
    reader = source(
        {"/predpis-eu": [{"data": [{"celex": "32024R0001", "naziv": "Rule"}], "totalCount": 1}]}
    )
    item = reader.discover_eu_acts()[0]
    assert (item.namespace, item.source_id) == ("EU", "32024R0001")


def test_local_npb_keeps_separate_namespace_from_state_text_id() -> None:
    reader = source({"/npb-ls": [{"data": [{"id": 7, "naziv": "Version"}], "totalCount": 1}]})
    item = reader.discover_local_npbs()[0]
    assert (item.namespace, item.source_id) == ("LS_NPB", 7)


def test_eu_missing_celex_and_local_duplicate_page_fail_closed() -> None:
    with pytest.raises(SourceInvariantError, match="celex"):
        source({"/predpis-eu": [{"data": [{"id": 7}], "totalCount": 1}]}).discover_eu_acts()
    pages = local_pages()
    pages[PisrsClient.LOCAL_ACT_ENDPOINTS[0]][1]["data"] = pages[
        PisrsClient.LOCAL_ACT_ENDPOINTS[0]
    ][0]["data"]
    with pytest.raises(SourceInvariantError, match="duplicate"):
        source(pages).discover_local_acts()


def test_sparse_seznam_rows_remain_observations_in_their_own_namespace() -> None:
    pages = {
        endpoint + "/seznam": [{"id": 7}]
        for endpoint in (*PisrsClient.ACT_ENDPOINTS, *PisrsClient.LOCAL_ACT_ENDPOINTS)
    }
    reader = source(pages)
    observations = reader.discover_list_observations()
    assert [(item.namespace, item.source_id) for item in observations] == [
        ("LS_LIST", 7),
        ("RS_LIST", 7),
    ]
    assert len(observations[0].raw_by_endpoint) == 3
    assert len(observations[1].raw_by_endpoint) == 7


def test_duplicate_seznam_id_in_one_endpoint_is_rejected() -> None:
    pages = {endpoint + "/seznam": [] for endpoint in PisrsClient.ACT_ENDPOINTS}
    pages[PisrsClient.ACT_ENDPOINTS[0] + "/seznam"] = [{"id": 7}, {"id": 7}]
    with pytest.raises(SourceInvariantError, match="duplicate"):
        source(pages).discover_list_observations()


class CatalogConnection:
    def __init__(self, existing: list[dict]) -> None:
        self.existing = existing
        self.written: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return self

    def cursor(self):
        return self

    def execute(self, sql: str):
        assert "FROM pisrs.source_catalog_items" in sql
        return self

    def fetchall(self):
        return self.existing

    def executemany(self, sql: str, params: list[dict]):
        assert sql in {EXTERNAL_UPSERT, STATE_RAW_UPSERT}
        self.written.extend(params)


class CatalogDatabase:
    def __init__(self, existing: list[dict] = ()) -> None:
        self.connection = CatalogConnection(list(existing))

    def connect(self):
        return self.connection


def three_items():
    return [
        source(
            {"/predpis-eu": [{"data": [{"celex": "32024R0001"}], "totalCount": 1}]}
        ).discover_eu_acts()[0],
        source(local_pages()).discover_local_acts()[0],
        source({"/npb-ls": [{"data": [{"id": 9}], "totalCount": 1}]}).discover_local_npbs()[0],
    ]


def test_external_store_accepts_three_disjoint_namespaces() -> None:
    database = CatalogDatabase()
    ExternalCatalogStore(database).synchronize(three_items())
    assert {(row["namespace"], row["source_id"]) for row in database.connection.written} == {
        ("EU", "32024R0001"),
        ("LS_ACT", "7"),
        ("LS_NPB", "9"),
    }


def test_external_store_fails_before_upsert_on_missing_or_conflicting_identity() -> None:
    cases = [
        [
            {
                "namespace": "EU",
                "source_id": "MISSING",
                "moped_plus_id": None,
                "eda": None,
                "sop": None,
            }
        ],
        [
            {
                "namespace": "LS_ACT",
                "source_id": "7",
                "moped_plus_id": "OTHER",
                "eda": "EDA7",
                "sop": "S7",
            }
        ],
        [
            {
                "namespace": "LS_NPB",
                "source_id": "9",
                "moped_plus_id": None,
                "eda": None,
                "sop": None,
                "linked_act_source_id": "999",
            }
        ],
    ]
    for existing in cases:
        database = CatalogDatabase(existing)
        with pytest.raises(PostgresInvariantError):
            ExternalCatalogStore(database).synchronize(three_items())
        assert database.connection.written == []


def test_state_raw_variants_are_preserved_without_changing_legacy_envelope() -> None:
    act = {"id": 7, "mopedId": "ZAKO7", "naziv": "State act"}
    pages = {endpoint: [{"data": [act], "totalCount": 1}] for endpoint in PisrsClient.ACT_ENDPOINTS}
    pages[PisrsClient.ACT_ENDPOINTS[1]][0]["data"] = [{**act, "other_source_field": "kept"}]
    reader = source(pages)
    item = reader.discover_acts()[0]
    assert "raw_by_endpoint" not in item.provenance()
    database = CatalogDatabase()
    ExternalCatalogStore(database).synchronize_state_raw([item])
    assert len(database.connection.written) == 7
    assert database.connection.written[1]["raw"].obj["other_source_field"] == "kept"


def test_local_npb_links_choose_only_a_unique_exact_sop() -> None:
    act_rows = [
        {"id": 1, "mopedPlusId": "L1", "sop": "abc-2026-1"},
        {"id": 2, "mopedPlusId": "L2", "sop": "abc-2026-2"},
        {"id": 3, "mopedPlusId": "L3", "sop": "abc-2026-2"},
    ]
    acts = [
        ExternalCatalogItem.from_raw(row, "/akt-ls/veljavni-akti", "LS_ACT") for row in act_rows
    ]
    docnos = [
        "x-y-z-abc-2026-1-npb01",
        "x-y-z-abc-2026-2-npb01",
        "x-y-z-abc-2026-9-npb01",
        "bad number",
    ]
    npbs = [
        ExternalCatalogItem.from_raw(
            {"id": 10 + index, "stevilkaDokumenta": docno}, "/npb-ls", "LS_NPB"
        )
        for index, docno in enumerate(docnos)
    ]
    links = local_npb_links(acts, npbs)
    assert [links[str(10 + index)][2] for index in range(4)] == [
        "UNIQUE_SOP",
        "AMBIGUOUS_SOP",
        "UNMATCHED_SOP",
        "NO_PARSED_SOP",
    ]
    assert links["10"][3] == "1"
    assert all(links[str(index)][3] is None for index in (11, 12, 13))
