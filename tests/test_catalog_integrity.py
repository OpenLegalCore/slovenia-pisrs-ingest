from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from pisrs_ingest.checkpoint import CheckpointStore
from pisrs_ingest.client import PisrsClient
from pisrs_ingest.models import SourceInvariantError
from pisrs_ingest.pipeline import run_nightly


class CatalogHttp:
    def __init__(self, pages: dict[str, list[dict]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, int]] = []

    def request(self, method: str, url: str, **kwargs):
        assert method == "GET"
        path = urlsplit(url).path.removeprefix("/extapi")
        page = kwargs["params"]["page"]
        self.calls.append((path, page))
        payload = self.pages[path][page - 1]
        return type("Response", (), {"json": lambda _: deepcopy(payload)})()


def act(register_id: int) -> dict:
    return {"id": register_id, "mopedId": f"ZAKO{register_id}", "naziv": f"Act {register_id}"}


def client(pages: dict[str, list[dict]]) -> PisrsClient:
    return PisrsClient("https://example.invalid/extapi", "fixture", CatalogHttp(pages))


def test_discovery_includes_acts_found_only_in_each_missing_state_catalog() -> None:
    endpoints = [
        "/predpis/register-predpisov",
        "/predpis/neveljavni-predpisi",
        "/predpis/obsoletni-in-konzumirani-predpisi",
        "/predpis/evidenca-normodajalcev",
        "/predpis/predpisi-v-pripravi",
        "/predpis/drugi-splosni-in-posamicni-akti",
        "/predpis/splosni-akti-za-izvrsevanje-javnih-pooblastil",
    ]
    pages = {
        endpoint: [{"data": [act(index)], "total": 1}]
        for index, endpoint in enumerate(endpoints, start=1)
    }
    discovered = client(pages).discover_acts()
    assert [item.register_id for item in discovered] == list(range(1, 8))
    assert [item.seen_in_endpoints for item in discovered] == [(path,) for path in endpoints]


def test_overlapping_catalogs_preserve_one_identity_and_all_provenance() -> None:
    pages = {endpoint: [{"data": [act(1)], "total": 1}] for endpoint in PisrsClient.ACT_ENDPOINTS}
    discovered = client(pages).discover_acts()
    assert len(discovered) == 1
    assert discovered[0].seen_in_endpoints == PisrsClient.ACT_ENDPOINTS


def test_duplicate_pages_cannot_hide_a_missing_identity_behind_reported_total() -> None:
    first = [act(index) for index in range(1, 1001)]
    second = [act(index) for index in range(1000, 2000)]
    pages = {endpoint: [{"data": [], "total": 0}] for endpoint in PisrsClient.ACT_ENDPOINTS}
    pages["/predpis/register-predpisov"] = [
        {"data": first, "total": 2000},
        {"data": second, "total": 2000},
        {"data": [], "total": 2000},
    ]
    source = client(pages)
    with pytest.raises(SourceInvariantError, match="duplicate"):
        source.discover_acts()


def test_reported_total_must_remain_stable_between_pages() -> None:
    source = client(
        {
            "/npb": [
                {"data": [{"id": index} for index in range(1, 1001)], "totalCount": 1002},
                {"data": [{"id": 1001}], "totalCount": 1001},
            ]
        }
    )
    with pytest.raises(SourceInvariantError, match="total.*changed"):
        source.discover_npbs()


@pytest.mark.parametrize("reported", [None, True, -1, "1", 1.5])
def test_unknown_or_invalid_total_cannot_be_reported_as_complete(reported) -> None:
    source = client({"/npb": [{"data": [{"id": 1}], "totalCount": reported}]})
    with pytest.raises(SourceInvariantError, match="total"):
        source.discover_npbs()


def test_more_unique_rows_than_reported_total_is_not_a_complete_catalog() -> None:
    source = client({"/npb": [{"data": [{"id": 1}, {"id": 2}], "totalCount": 1}]})
    with pytest.raises(SourceInvariantError, match="total"):
        source.discover_npbs()


def test_server_page_size_cap_does_not_truncate_catalog() -> None:
    source = client(
        {
            "/npb": [
                {"data": [{"id": 1}], "totalCount": 2},
                {"data": [{"id": 2}], "totalCount": 2},
            ]
        }
    )
    assert [item.text_id for item in source.discover_npbs()] == [1, 2]


def test_empty_page_before_total_blocks_catalog() -> None:
    source = client({"/npb": [{"data": [], "totalCount": 1}]})
    with pytest.raises(SourceInvariantError, match="total"):
        source.discover_npbs()


def test_genuinely_empty_catalog_is_valid() -> None:
    assert client({"/npb": [{"data": [], "totalCount": 0}]}).discover_npbs() == []


def test_full_last_page_requires_a_verified_end() -> None:
    rows = [{"id": index} for index in range(1, 1001)]
    source = client(
        {
            "/npb": [
                {"data": rows, "totalCount": 1000},
                {"data": [], "totalCount": 1000},
            ]
        }
    )
    assert len(source.discover_npbs()) == 1000
    assert source.http.calls == [("/npb", 1), ("/npb", 2)]


def test_unreported_extra_page_is_not_silently_accepted() -> None:
    source = client(
        {
            "/npb": [
                {"data": [{"id": index} for index in range(1, 1001)], "totalCount": 1000},
                {"data": [{"id": 1001}], "totalCount": 1000},
            ]
        }
    )
    with pytest.raises(SourceInvariantError, match="total"):
        source.discover_npbs()


@pytest.mark.parametrize("identity", [None, True, 0, -1, "1", 1.5])
def test_invalid_source_id_is_not_coerced_to_another_identity(identity) -> None:
    source = client({"/npb": [{"data": [{"id": identity}], "totalCount": 1}]})
    with pytest.raises(SourceInvariantError, match="invalid id"):
        source.discover_npbs()


def test_late_catalog_failure_never_reaches_database_or_checkpoint(tmp_path) -> None:
    pages = {
        endpoint: [{"data": [act(index)], "total": 1}]
        for index, endpoint in enumerate(PisrsClient.ACT_ENDPOINTS, start=1)
    }
    pages[PisrsClient.ACT_ENDPOINTS[-1]][0]["total"] = None
    checkpoint_path = tmp_path / "checkpoint.json"
    writes = []
    postgres = SimpleNamespace(
        catalogs=SimpleNamespace(synchronize=lambda *args: writes.append(args))
    )
    with pytest.raises(SourceInvariantError, match="total"):
        run_nightly(
            client=client(pages),
            postgres=postgres,
            embedder=object(),
            qdrant=object(),
            checkpoint=CheckpointStore(checkpoint_path, datetime(2026, 1, 1, tzinfo=UTC)),
            model="text-embedding-3-large",
            dimensions=3072,
            max_documents=100,
            embed_batch_size=10,
            max_embedding_input_bytes=1000,
            now=datetime(2026, 1, 2, tzinfo=UTC),
        )
    assert writes == []
    assert not checkpoint_path.exists()
