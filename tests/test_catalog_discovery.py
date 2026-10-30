from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit

import pytest

from pisrs_ingest.client import HttpClient, HttpError, PisrsClient
from pisrs_ingest.models import Act, SourceInvariantError
from pisrs_ingest.postgres import CatalogStore

ENDPOINTS = (
    "/predpis/register-predpisov",
    "/predpis/neveljavni-predpisi",
    "/predpis/obsoletni-in-konzumirani-predpisi",
    "/predpis/evidenca-normodajalcev",
    "/predpis/predpisi-v-pripravi",
    "/predpis/drugi-splosni-in-posamicni-akti",
    "/predpis/splosni-akti-za-izvrsevanje-javnih-pooblastil",
)


def act_row(identity: int) -> dict[str, Any]:
    return {"id": identity, "mopedId": f"M-{identity}", "naziv": f"Fixture {identity}"}


def page(rows: list[Any], total: int, number: int = 1) -> dict[str, Any]:
    return {
        "data": rows,
        "totalCount": total,
        "page": number,
        "requestedPageSize": 1000,
        "realPageSize": len(rows),
        "error": None,
    }


def catalog_pages(count: int) -> list[dict[str, Any]]:
    rows = [act_row(identity) for identity in range(1, count + 1)]
    return [
        page(rows[start : start + 1000], count, start // 1000 + 1)
        for start in range(0, count, 1000)
    ] or [page([], 0)]


class FixtureResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.closed = False

    def json(self) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return deepcopy(self.payload)

    def close(self) -> None:
        self.closed = True


class FixtureHttp(HttpClient):
    def __init__(self, routes: dict[str, list[Any]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, int]] = []
        self.responses: list[FixtureResponse] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FixtureResponse:
        assert method == "GET"
        parsed = urlsplit(url)
        assert parsed.hostname == "pisrs.example.invalid"
        endpoint = parsed.path.removeprefix("/extapi")
        number = kwargs["params"]["page"]
        assert kwargs["params"] == {"page": number, "pageSize": 1000}
        assert kwargs["phase"] == ("act_discovery" if endpoint in ENDPOINTS else "npb_discovery")
        self.calls.append((endpoint, number))
        response = FixtureResponse(self.routes[endpoint][number - 1])
        self.responses.append(response)
        return response


def fixture_client(
    overrides: dict[str, list[Any]] | None = None,
) -> tuple[PisrsClient, FixtureHttp]:
    routes = {endpoint: [page([], 0)] for endpoint in ENDPOINTS}
    routes["/npb"] = [page([], 0)]
    routes.update(overrides or {})
    http = FixtureHttp(routes)
    return PisrsClient("https://pisrs.example.invalid/extapi", "fixture", http), http


def test_exactly_seven_state_catalogs_preserve_original_precedence() -> None:
    assert PisrsClient.ACT_ENDPOINTS == ENDPOINTS
    rows = [act_row(identity) for identity in range(1, 8)]
    client, http = fixture_client(
        {endpoint: [page([row], 1)] for endpoint, row in zip(ENDPOINTS, rows, strict=True)}
    )
    acts = client.discover_acts()
    assert [item.register_id for item in acts] == list(range(1, 8))
    assert http.calls == [(endpoint, 1) for endpoint in ENDPOINTS]
    assert all(response.closed for response in http.responses)
    for act, endpoint, raw in zip(acts, ENDPOINTS, rows, strict=True):
        assert act.sop is None
        parameters = CatalogStore._act_parameters(act)
        source = parameters["source_item"].obj
        assert parameters["sop"] is None
        assert source["raw_by_endpoint"] == {endpoint: raw}
        assert parameters["raw"].obj == raw
        assert not {"is_active", "is_latest_for_sop", "status"} & source.keys()


@pytest.mark.parametrize("endpoint", ENDPOINTS + ("/npb",))
@pytest.mark.parametrize("count", [1001, 2001])
def test_all_catalogs_enumerate_multiple_pages(endpoint: str, count: int) -> None:
    client, http = fixture_client({endpoint: catalog_pages(count)})
    found = client.discover_npbs() if endpoint == "/npb" else client.discover_acts()
    identities = [item.text_id if endpoint == "/npb" else item.register_id for item in found]
    assert identities == list(range(1, count + 1))
    assert [number for path, number in http.calls if path == endpoint] == list(
        range(1, (count + 999) // 1000 + 1)
    )
    assert all(response.closed for response in http.responses)


@pytest.mark.parametrize("count", [0, 1, 999, 1000, 2000])
def test_enumeration_stops_at_exact_total_without_extra_page(count: int) -> None:
    client, http = fixture_client({ENDPOINTS[0]: catalog_pages(count)})
    assert len(client.discover_acts()) == count
    assert len([call for call in http.calls if call[0] == ENDPOINTS[0]]) == max(
        1, (count + 999) // 1000
    )


def test_total_count_is_used_even_when_legacy_total_disagrees() -> None:
    pages = catalog_pages(1001)
    for payload in pages:
        payload["total"] = 0
    client, _ = fixture_client({ENDPOINTS[0]: pages})
    assert len(client.discover_acts()) == 1001


@pytest.mark.parametrize("reported", [None, True, False, -1, 1.0, "1"])
def test_invalid_total_count_fails_closed(reported: Any) -> None:
    payload = page([act_row(1)], 1)
    payload["totalCount"] = reported
    client, _ = fixture_client({ENDPOINTS[0]: [payload]})
    with pytest.raises(SourceInvariantError, match="valid totalCount"):
        client.discover_acts()


def test_legacy_total_cannot_replace_missing_total_count() -> None:
    payload = page([act_row(1)], 1)
    del payload["totalCount"]
    payload["total"] = 1
    client, _ = fixture_client({ENDPOINTS[0]: [payload]})
    with pytest.raises(SourceInvariantError, match="valid totalCount"):
        client.discover_acts()


@pytest.mark.parametrize("reported", [1000, 2000, 2002])
def test_total_count_changes_between_pages_fail(reported: int) -> None:
    pages = catalog_pages(2001)
    pages[1]["totalCount"] = reported
    client, _ = fixture_client({ENDPOINTS[0]: pages})
    with pytest.raises(SourceInvariantError, match="changed between pages"):
        client.discover_acts()


@pytest.mark.parametrize("first_size", [0, 1, 999])
def test_short_page_before_reported_end_fails(first_size: int) -> None:
    payload = page([act_row(i) for i in range(first_size)], 1001)
    client, _ = fixture_client({ENDPOINTS[0]: [payload]})
    with pytest.raises(SourceInvariantError, match="stopped before"):
        client.discover_acts()


def test_empty_second_page_before_end_fails() -> None:
    pages = catalog_pages(1001)
    pages[1] = page([], 1001, 2)
    client, _ = fixture_client({ENDPOINTS[0]: pages})
    with pytest.raises(SourceInvariantError, match="stopped before"):
        client.discover_acts()


@pytest.mark.parametrize("count,total", [(2, 1), (1, 0), (1001, 1001)])
def test_oversized_page_or_total_overrun_fails(count: int, total: int) -> None:
    payload = page([act_row(i) for i in range(count)], total)
    client, _ = fixture_client({ENDPOINTS[0]: [payload]})
    with pytest.raises(SourceInvariantError, match="exceeded its page size or totalCount"):
        client.discover_acts()


@pytest.mark.parametrize(
    "key,value",
    [
        ("page", 0),
        ("page", 2),
        ("page", True),
        ("page", 1.0),
        ("page", "1"),
        ("page", None),
        ("requestedPageSize", 10),
        ("realPageSize", 0),
        ("realPageSize", True),
    ],
)
def test_inconsistent_page_echo_fails(key: str, value: Any) -> None:
    payload = page([act_row(1)], 1)
    payload[key] = value
    client, _ = fixture_client({ENDPOINTS[0]: [payload]})
    with pytest.raises(SourceInvariantError, match=f"inconsistent {key}"):
        client.discover_acts()


def test_optional_echo_fields_may_be_absent() -> None:
    client, _ = fixture_client({ENDPOINTS[0]: [{"data": [act_row(1)], "totalCount": 1}]})
    assert len(client.discover_acts()) == 1


@pytest.mark.parametrize("different_metadata", [False, True])
def test_duplicate_within_page_is_not_silently_merged(different_metadata: bool) -> None:
    first = act_row(1)
    second = {**first, "naziv": "Conflicting"} if different_metadata else first
    client, _ = fixture_client({ENDPOINTS[0]: [page([first, second], 2)]})
    with pytest.raises(SourceInvariantError, match="repeated an identity"):
        client.discover_acts()


@pytest.mark.parametrize("repeat_whole_page", [False, True])
def test_repeated_identity_or_page_across_pages_fails(repeat_whole_page: bool) -> None:
    count = 2000 if repeat_whole_page else 1001
    pages = catalog_pages(count)
    rows = pages[0]["data"] if repeat_whole_page else [act_row(1)]
    pages[1] = page(rows, count, 2)
    client, _ = fixture_client({ENDPOINTS[0]: pages})
    with pytest.raises(SourceInvariantError, match="repeated an identity"):
        client.discover_acts()


@pytest.mark.parametrize("payload", [[], None, {"data": None}, {"data": {}}])
def test_malformed_envelope_fails(payload: Any) -> None:
    client, http = fixture_client({ENDPOINTS[0]: [payload]})
    with pytest.raises(HttpError):
        client.discover_acts()
    assert http.responses[0].closed


@pytest.mark.parametrize("error", ["upstream error", {"message": "error"}, False, 0])
def test_error_envelope_cannot_be_counted_as_success(error: Any) -> None:
    payload = page([], 0)
    payload["error"] = error
    client, _ = fixture_client({ENDPOINTS[0]: [payload]})
    with pytest.raises(HttpError, match="reports an error"):
        client.discover_acts()


def test_invalid_json_fails_and_closes_response() -> None:
    client, http = fixture_client({ENDPOINTS[0]: [ValueError("fixture JSON failure")]})
    with pytest.raises(HttpError, match="not valid JSON"):
        client.discover_acts()
    assert http.responses[0].closed


@pytest.mark.parametrize("row", [None, [], {}, {"id": True}, {"id": 1.0}, {"id": "1"}])
def test_malformed_row_identity_fails(row: Any) -> None:
    client, _ = fixture_client({ENDPOINTS[0]: [page([row], 1)]})
    with pytest.raises(SourceInvariantError, match="integer identity"):
        client.discover_acts()


def test_page_safety_limit_raises_instead_of_returning_partial_catalog(monkeypatch) -> None:
    client, http = fixture_client({ENDPOINTS[0]: catalog_pages(1001)})
    monkeypatch.setattr(client, "MAX_PAGES", 1)
    with pytest.raises(SourceInvariantError, match="page safety limit"):
        client.discover_acts()
    assert http.calls == [(ENDPOINTS[0], 1)]


def test_overlap_keeps_each_sources_raw_and_first_nonempty_normalized_values() -> None:
    rows = [
        {**act_row(1), "naziv": f"Source {i}", "posegiVPredpis": [{"mopedID": f"R-{i}"}]}
        for i in range(7)
    ]
    snapshot = deepcopy(rows)
    client, http = fixture_client(
        {endpoint: [page([row], 1)] for endpoint, row in zip(ENDPOINTS, rows, strict=True)}
    )
    [act] = client.discover_acts()
    assert (act.register_id, act.moped_id, act.naziv) == (1, "M-1", "Source 0")
    assert act.seen_in_endpoints == ENDPOINTS
    source = CatalogStore._act_parameters(act)["source_item"].obj
    assert source["raw_by_endpoint"] == dict(zip(ENDPOINTS, snapshot, strict=True))
    assert act.raw == snapshot[0]
    assert rows == snapshot
    assert act.merge(act).provenance() == act.provenance()
    assert len(http.calls) == 7  # No text fetch, export, embedding or vector operation.


def test_same_sop_does_not_merge_different_register_ids() -> None:
    rows = [{**act_row(i), "sop": "2026-01-0001"} for i in [1, 2]]
    client, _ = fixture_client({ENDPOINTS[0]: [page(rows, 2)]})
    assert [act.register_id for act in client.discover_acts()] == [1, 2]


def test_conflicting_moped_id_across_catalogs_fails() -> None:
    client, _ = fixture_client(
        {
            ENDPOINTS[0]: [page([act_row(1)], 1)],
            ENDPOINTS[4]: [page([{**act_row(1), "mopedId": "OTHER"}], 1)],
        }
    )
    with pytest.raises(SourceInvariantError, match="multiple moped_id"):
        client.discover_acts()


@pytest.mark.parametrize("moped", [None, "", " ", True, 1, {}])
def test_missing_or_malformed_moped_id_fails(moped: Any) -> None:
    row = {**act_row(1), "mopedId": moped}
    client, _ = fixture_client({ENDPOINTS[4]: [page([row], 1)]})
    with pytest.raises(SourceInvariantError, match="missing the established"):
        client.discover_acts()


def test_direct_merge_refuses_different_identity_or_loss_of_same_source_metadata() -> None:
    act = Act.from_raw(act_row(1), ENDPOINTS[0])
    with pytest.raises(SourceInvariantError, match="different act identities"):
        act.merge(Act.from_raw(act_row(2), ENDPOINTS[0]))
    changed = Act.from_raw({**act_row(1), "naziv": "Changed"}, ENDPOINTS[0])
    with pytest.raises(SourceInvariantError, match="inconsistent raw metadata"):
        act.merge(changed)
