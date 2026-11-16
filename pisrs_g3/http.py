"""Bounded, credential-safe PISRS HTTP transport."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import time
from typing import Mapping
from urllib.parse import urlsplit

from .contract import BASE, ContractError


class SourceStopped(RuntimeError):
    def __init__(self, reason: str, status: int | None = None, retry_after: float | None = None):
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.retry_after = retry_after


@dataclass(frozen=True)
class Reply:
    status: int
    body: bytes
    sha256: bytes
    content_type: str
    charset: str | None
    content_encoding: str
    etag: str | None
    last_modified: str | None
    elapsed: float


def decode_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return min(float(value), 86400.0)
    try:
        at = parsedate_to_datetime(value)
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return max(0.0, min((at - datetime.now(timezone.utc)).total_seconds(), 86400.0))
    except (ValueError, TypeError, OverflowError):
        return None


class Client:
    def __init__(self, token: str, *,
                 min_interval: float = 3.0,
                 max_requests: int = 1,
                 max_response_bytes: int = 64 * 1024 * 1024,
                 max_total_bytes: int = 512 * 1024 * 1024,
                 max_seconds: int = 300):
        if not token or any(c.isspace() for c in token):
            raise ValueError("invalid_private_credential")
        if min_interval < 1 or max_requests < 1 or max_response_bytes <= 0 or max_total_bytes <= 0 or max_seconds <= 0:
            raise ValueError("unbounded_source_budget")
        self.token = token
        self.min_interval = min_interval
        self.max_requests = max_requests
        self.max_response_bytes = max_response_bytes
        self.max_total_bytes = max_total_bytes
        self.max_seconds = max_seconds
        self.requests_used = 0
        self.bytes_used = 0
        self.started = time.monotonic()
        self.last_request: float | None = None

    def get(self, path: str, params: Mapping[str, str | int] | None = None) -> Reply:
        """Exactly one GET. Never retries, follows redirects or logs a credential/body."""
        import requests

        if not path.startswith("/") or "?" in path or "#" in path or "//" in path:
            raise ContractError("unsafe_relative_path")
        url = BASE + path
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "pisrs.si":
            raise ContractError("source_origin_mismatch")
        if self.requests_used >= self.max_requests:
            raise SourceStopped("request_budget")
        if self.bytes_used >= self.max_total_bytes:
            raise SourceStopped("byte_budget")
        if time.monotonic() - self.started >= self.max_seconds:
            raise SourceStopped("deadline_budget")
        if self.last_request is not None:
            time.sleep(max(0.0, self.min_interval - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        self.requests_used += 1
        # requests honors the successful operator's proxy environment. TLS verification
        # is always enabled. No unsupported bypass of HTTP 407 is attempted.
        with requests.Session() as session:
            session.trust_env = True
            session.headers.update({
                "Accept": "application/json, text/html",
                "Accept-Encoding": "identity",
                "User-Agent": "OpenLegalCore-PISRS-G1-positive-evidence/2026-11-16",
                "X-API-KEY": self.token,
                "Authorization": "Bearer " + self.token,
            })
            try:
                with session.get(url, params=params, verify=True,
                                 allow_redirects=False, stream=True,
                                 timeout=(8, 30)) as response:
                    status = response.status_code
                    retry_after = decode_retry_after(response.headers.get("Retry-After"))
                    if status != 200:
                        reason = ("rate_limited" if status == 429 else
                                  "auth_or_proxy" if status in (401, 403, 407, 498)
                                  else "redirect" if 300 <= status < 400
                                  else "non_200_response")
                        raise SourceStopped(reason, status, retry_after)
                    coding = response.headers.get("Content-Encoding", "identity").strip().lower()
                    if coding != "identity":
                        raise SourceStopped("content_coding_not_identity", status)
                    mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    if mime not in ("application/json", "text/html"):
                        raise SourceStopped("unexpected_mime", status)
                    charset = None
                    content_type = response.headers.get("Content-Type", "")
                    if "charset=" in content_type.lower():
                        charset = content_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip(" '\"")
                    chunks = bytearray()
                    # iter_content would transparently decompress HTTP content coding.
                    # identity is mandatory; raw.read explicitly preserves octets.
                    response.raw.decode_content = False
                    while True:
                        part = response.raw.read(64 * 1024)
                        if not part:
                            break
                        chunks.extend(part)
                        if len(chunks) > self.max_response_bytes or self.bytes_used + len(chunks) > self.max_total_bytes:
                            raise SourceStopped("body_budget", status)
                        if time.monotonic() - self.started >= self.max_seconds:
                            raise SourceStopped("deadline_budget", status)
                    body = bytes(chunks)
                    self.bytes_used += len(body)
                    return Reply(
                        status=status, body=body, sha256=hashlib.sha256(body).digest(),
                        content_type=mime, charset=charset, content_encoding=coding,
                        etag=response.headers.get("ETag"),
                        last_modified=response.headers.get("Last-Modified"),
                        elapsed=time.monotonic() - self.last_request,
                    )
            except requests.RequestException as exc:
                # Do not include an exception string, which may contain auth/proxy details.
                raise SourceStopped("transport_failure") from None
