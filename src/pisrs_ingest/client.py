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

from .models import Act, NpbDocument, SourceInvariantError

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
            for row in self._pages(endpoint, total_key="total"):
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

    def _pages(self, endpoint: str, *, total_key: str) -> list[dict[str, Any]]:
        page = 1
        page_size = 1000
        result: list[dict[str, Any]] = []
        while page <= 1000:
            response = self.http.request(
                "GET",
                urljoin(self.base_url, endpoint.lstrip("/")),
                headers=self.headers,
                params={"page": page, "pageSize": page_size},
                phase=("act_discovery" if endpoint in self.ACT_ENDPOINTS else "npb_discovery"),
            )
            payload = response.json()
            rows = payload.get("data")
            if not isinstance(rows, list):
                raise HttpError(f"PISRS {endpoint} response does not contain a data list")
            result.extend(rows)
            if not rows or len(rows) < page_size:
                reported = payload.get(total_key)
                if isinstance(reported, int) and reported > len(result):
                    raise SourceInvariantError(
                        f"PISRS {endpoint} stopped before its reported total"
                    )
                return result
            page += 1
        raise SourceInvariantError(f"PISRS {endpoint} exceeded the page safety limit")
