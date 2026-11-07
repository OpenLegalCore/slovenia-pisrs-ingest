"""TLS-verifying PISRS HTTP client with bounded transient retry."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests

from .models import (
    Act,
    CatalogListObservation,
    ExternalCatalogItem,
    NpbDocument,
    SourceInvariantError,
)

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
LOGGER = logging.getLogger(__name__)


class HttpError(RuntimeError):
    """Permanent HTTP or response-contract failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    initial_backoff: float = 0.5
    max_backoff: float = 4.0


class HttpClient:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.policy = policy or RetryPolicy()
        self.sleep = sleep

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        phase = str(kwargs.pop("phase", "http_request"))
        request_path = urlsplit(url).path or "/"
        kwargs.setdefault("timeout", (10, 90))
        kwargs["verify"] = True
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                response = self.session.request(method, url, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self.policy.max_attempts:
                    raise
                classification = (
                    "timeout" if isinstance(exc, requests.Timeout) else "connection_error"
                )
                self._retry(phase, request_path, attempt, classification)
                continue
            if response.status_code in TRANSIENT_STATUSES:
                if attempt == self.policy.max_attempts:
                    response.close()
                    raise HttpError(
                        f"transient HTTP status {response.status_code} persisted "
                        f"after {attempt} attempts",
                        status_code=response.status_code,
                    )
                response.close()
                classification = "rate_limited" if response.status_code == 429 else "server_error"
                self._retry(phase, request_path, attempt, classification)
                continue
            if response.status_code < 200 or response.status_code >= 300:
                response.close()
                raise HttpError(
                    f"permanent HTTP status {response.status_code} for {request_path}",
                    status_code=response.status_code,
                )
            return response
        raise AssertionError("retry loop did not return or raise")

    def _retry(self, phase: str, request_path: str, attempt: int, classification: str) -> None:
        delay = min(self.policy.max_backoff, self.policy.initial_backoff * (2 ** (attempt - 1)))
        LOGGER.warning(
            json.dumps(
                {
                    "event": "http_retry",
                    "phase": phase,
                    "request_path": request_path,
                    "attempt": attempt,
                    "maximum": self.policy.max_attempts,
                    "classification": classification,
                    "next_delay_seconds": delay,
                },
                sort_keys=True,
            )
        )
        self.sleep(delay)


class PisrsClient:
    ACT_ENDPOINTS = (
        "/predpis/register-predpisov",
        "/predpis/neveljavni-predpisi",
        "/predpis/obsoletni-in-konzumirani-predpisi",
        "/predpis/evidenca-normodajalcev",
        "/predpis/predpisi-v-pripravi",
        "/predpis/drugi-splosni-in-posamicni-akti",
        "/predpis/splosni-akti-za-izvrsevanje-javnih-pooblastil",
    )
    LOCAL_ACT_ENDPOINTS = (
        "/akt-ls/veljavni-akti",
        "/akt-ls/neveljavni-akti",
        "/akt-ls/akti-v-pripravi",
    )

    def __init__(self, base_url: str, token: str, http: HttpClient | None = None) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.http = http or HttpClient()
        self.headers = {
            "Accept": "application/json, text/html",
            "User-Agent": "OpenLegalCore-pisrs-ingest/0.1.0",
            "X-API-KEY": token,
            "x-api-key": token,
            "Authorization": f"Bearer {token}",
        }

    def discover_acts(self) -> list[Act]:
        by_id: dict[int, Act] = {}
        for endpoint in self.ACT_ENDPOINTS:
            for row in self._pages(endpoint, total_key="totalCount"):
                act = Act.from_raw(row, endpoint)
                by_id[act.register_id] = (
                    by_id[act.register_id].merge(act) if act.register_id in by_id else act
                )
        return sorted(by_id.values(), key=lambda item: item.register_id)

    def discover_npbs(self) -> list[NpbDocument]:
        by_id: dict[int, NpbDocument] = {}
        for row in self._pages("/npb", total_key="totalCount"):
            document = NpbDocument.from_raw(row)
            previous = by_id.get(document.text_id)
            if previous is not None and previous != document:
                raise SourceInvariantError("one text_id maps to inconsistent NPB metadata")
            by_id[document.text_id] = document
        return sorted(by_id.values(), key=lambda item: item.text_id)

    def discover_eu_acts(self) -> list[ExternalCatalogItem]:
        return [
            ExternalCatalogItem.from_raw(row, "/predpis-eu", "EU")
            for row in self._pages("/predpis-eu", total_key="totalCount", identity_key="celex")
        ]

    def discover_local_acts(self) -> list[ExternalCatalogItem]:
        by_id: dict[int, ExternalCatalogItem] = {}
        for endpoint in self.LOCAL_ACT_ENDPOINTS:
            # The observed local totalCount is shared with unrelated catalogs or zero.
            # An empty page, with duplicate-ID and page-limit checks, ends this source.
            for row in self._pages(endpoint, total_key=None):
                item = ExternalCatalogItem.from_raw(row, endpoint, "LS_ACT")
                previous = by_id.get(item.source_id)
                by_id[item.source_id] = previous.merge(item) if previous else item
        return [by_id[key] for key in sorted(by_id)]

    def discover_local_npbs(self) -> list[ExternalCatalogItem]:
        return [
            ExternalCatalogItem.from_raw(row, "/npb-ls", "LS_NPB")
            for row in self._pages("/npb-ls", total_key="totalCount")
        ]

    def discover_list_observations(self) -> list[CatalogListObservation]:
        """Collect /seznam evidence without inventing full acts from sparse rows."""

        by_id: dict[tuple[str, int], CatalogListObservation] = {}
        for catalog in (*self.ACT_ENDPOINTS, *self.LOCAL_ACT_ENDPOINTS):
            endpoint = catalog + "/seznam"
            namespace = "RS_LIST" if catalog in self.ACT_ENDPOINTS else "LS_LIST"
            response = self.http.request(
                "GET",
                urljoin(self.base_url, endpoint.lstrip("/")),
                headers=self.headers,
                phase="catalog_list_discovery",
            )
            rows = response.json()
            if not isinstance(rows, list):
                raise SourceInvariantError(f"PISRS {endpoint} did not return a list")
            seen_on_endpoint: set[int] = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise SourceInvariantError(f"PISRS {endpoint} contains a non-object row")
                item = CatalogListObservation.from_raw(row, endpoint, namespace)
                if item.source_id in seen_on_endpoint:
                    raise SourceInvariantError(f"PISRS {endpoint} contains a duplicate id")
                seen_on_endpoint.add(item.source_id)
                key = (namespace, item.source_id)
                previous = by_id.get(key)
                by_id[key] = previous.merge(item) if previous else item
        return [by_id[key] for key in sorted(by_id)]

    def fetch_text(self, text_id: int) -> str:
        response = self.http.request(
            "GET",
            urljoin(self.base_url, f"besedilo/{text_id}"),
            headers=self.headers,
            phase="document_fetch",
        )
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower() or "<html" not in response.text.lower():
            raise HttpError(f"PISRS text {text_id} did not return HTML")
        return response.text

    def source_url(self, text_id: int) -> str:
        return urljoin(self.base_url, f"besedilo/{text_id}")

    def probe(self) -> None:
        response = self.http.request(
            "GET",
            urljoin(self.base_url, "npb"),
            headers=self.headers,
            params={"page": 1, "pageSize": 1},
            phase="preflight_portal_probe",
        )
        payload = response.json()
        if not isinstance(payload.get("data"), list):
            raise HttpError("PISRS probe response does not contain a data list")

    def _pages(
        self, endpoint: str, *, total_key: str | None, identity_key: str = "id"
    ) -> list[dict[str, Any]]:
        page = 1
        page_size = 1000
        result: list[dict[str, Any]] = []
        seen_ids: set[int | str] = set()
        expected_total: int | None = None
        while page <= 1000:
            response = self.http.request(
                "GET",
                urljoin(self.base_url, endpoint.lstrip("/")),
                headers=self.headers,
                params={"page": page, "pageSize": page_size},
                phase=(
                    "act_discovery"
                    if endpoint in self.ACT_ENDPOINTS
                    else "local_act_discovery"
                    if endpoint in self.LOCAL_ACT_ENDPOINTS
                    else "eu_act_discovery"
                    if endpoint == "/predpis-eu"
                    else "npb_discovery"
                ),
            )
            payload = response.json()
            if not isinstance(payload, dict):
                raise HttpError(f"PISRS {endpoint} response is not an object")
            rows = payload.get("data")
            if not isinstance(rows, list):
                raise HttpError(f"PISRS {endpoint} response does not contain a data list")
            if total_key is not None:
                reported = payload.get(total_key)
                if type(reported) is not int or reported < 0:
                    raise SourceInvariantError(f"PISRS {endpoint} has no valid {total_key} total")
                if expected_total is None:
                    expected_total = reported
                elif reported != expected_total:
                    raise SourceInvariantError(
                        f"PISRS {endpoint} reported total changed during paging"
                    )
            if len(rows) > page_size:
                raise SourceInvariantError(f"PISRS {endpoint} exceeded the requested page size")
            for row in rows:
                if not isinstance(row, dict):
                    raise SourceInvariantError(f"PISRS {endpoint} contains a non-object row")
                identity = row.get(identity_key)
                if identity_key == "celex":
                    valid_identity = (
                        isinstance(identity, str)
                        and bool(identity.strip())
                        and identity == identity.strip()
                    )
                else:
                    valid_identity = type(identity) is int and identity > 0
                if not valid_identity:
                    raise SourceInvariantError(
                        f"PISRS {endpoint} contains an invalid {identity_key}"
                    )
                if identity in seen_ids:
                    raise SourceInvariantError(f"PISRS {endpoint} contains a duplicate id")
                seen_ids.add(identity)
            result.extend(rows)
            if expected_total is not None and len(result) > expected_total:
                raise SourceInvariantError(f"PISRS {endpoint} exceeded its reported total")
            if total_key is None and not rows:
                return result
            if len(result) == expected_total and len(rows) < page_size:
                return result
            if not rows:
                raise SourceInvariantError(f"PISRS {endpoint} stopped before its reported total")
            page += 1
        raise SourceInvariantError(f"PISRS {endpoint} exceeded the page safety limit")
