"""Qdrant vector and payload adapter."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from .client import HttpClient, HttpError
from .models import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, MANAGED_PAYLOAD_KEYS, VectorRow


class QdrantInvariantError(RuntimeError):
    """Raised when the collection or point contract is inconsistent."""


@dataclass(frozen=True)
class PointState:
    point_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class PayloadInspection:
    patch: dict[str, Any]
    unexpected_keys: frozenset[str]


def inspect_payload(expected: dict[str, Any], actual: dict[str, Any]) -> PayloadInspection:
    """Compare every managed value using exact JSON/Python types."""

    if set(expected) != MANAGED_PAYLOAD_KEYS:
        raise QdrantInvariantError("authoritative payload does not match the managed contract")
    patch = {
        key: value
        for key, value in expected.items()
        if key not in actual or type(actual[key]) is not type(value) or actual[key] != value
    }
    return PayloadInspection(patch, frozenset(set(actual) - MANAGED_PAYLOAD_KEYS))


def payload_patch(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """Return only authoritative keys whose value or JSON type differs."""

    inspection = inspect_payload(expected, actual)
    if inspection.unexpected_keys:
        raise QdrantInvariantError(
            "unexpected payload keys require a separate explicitly approved removal procedure"
        )
    return inspection.patch


class QdrantStore:
    def __init__(self, base_url: str, collection: str, http: HttpClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.http = http or HttpClient()

    def validate_collection(
        self,
        dimensions: int | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        expected_model = model if model is not None else EMBEDDING_MODEL
        if expected_model != EMBEDDING_MODEL:
            raise QdrantInvariantError(
                "embedding model change requires a separately reviewed full reindex"
            )
        response = self.http.request(
            "GET",
            f"{self.base_url}/collections/{self.collection}",
            timeout=(5, 30),
            phase="qdrant_collection_preflight",
        )
        result = response.json().get("result")
        if not isinstance(result, dict):
            raise QdrantInvariantError("Qdrant collection response has no result object")
        vectors = ((result.get("config") or {}).get("params") or {}).get("vectors") or {}
        expected_dimensions = dimensions if dimensions is not None else EMBEDDING_DIMENSIONS
        if expected_dimensions != EMBEDDING_DIMENSIONS:
            raise QdrantInvariantError(
                "embedding dimension change requires a separately reviewed full reindex"
            )
        if vectors.get("size") != expected_dimensions or vectors.get("distance") != "Cosine":
            raise QdrantInvariantError("Qdrant collection violates the 3072/Cosine contract")
        if result.get("status") != "green":
            raise QdrantInvariantError("Qdrant collection is not green")
        return result

    def get_point(self, point_id: str) -> PointState | None:
        try:
            response = self.http.request(
                "GET",
                f"{self.base_url}/collections/{self.collection}/points/{point_id}",
                params={"with_payload": "true", "with_vector": "false"},
                timeout=(5, 30),
                phase="qdrant_point_reuse",
            )
        except HttpError as exc:
            if exc.status_code == 404:
                return None
            raise
        result = response.json().get("result")
        if not isinstance(result, dict):
            return None
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise QdrantInvariantError(f"point {point_id} has a non-object payload")
        return PointState(point_id=str(result.get("id")), payload=payload)

    def retrieve_points(self, point_ids: list[str]) -> dict[str, PointState]:
        if not point_ids:
            return {}
        response = self.http.request(
            "POST",
            f"{self.base_url}/collections/{self.collection}/points",
            json={"ids": point_ids, "with_payload": True, "with_vector": False},
            timeout=(5, 60),
            phase="qdrant_reconcile_retrieve",
        )
        result = response.json().get("result")
        if not isinstance(result, list):
            raise QdrantInvariantError("Qdrant point retrieval has no result list")
        points: dict[str, PointState] = {}
        for item in result:
            payload = item.get("payload")
            if not isinstance(payload, dict):
                raise QdrantInvariantError("Qdrant returned a non-object payload")
            point = PointState(point_id=str(item.get("id")), payload=payload)
            points[point.point_id] = point
        return points

    def iter_point_batches(self, batch_size: int = 500) -> Iterator[list[PointState]]:
        """Completely scroll one collection without vectors, rejecting pagination cycles."""

        offset: Any = None
        seen_offsets: set[str] = set()
        while True:
            request: dict[str, Any] = {
                "limit": batch_size,
                "with_payload": True,
                "with_vector": False,
            }
            if offset is not None:
                request["offset"] = offset
            response = self.http.request(
                "POST",
                f"{self.base_url}/collections/{self.collection}/points/scroll",
                json=request,
                timeout=(5, 60),
                phase="qdrant_reconcile_scroll",
            )
            result = response.json().get("result")
            if not isinstance(result, dict) or not isinstance(result.get("points"), list):
                raise QdrantInvariantError("Qdrant scroll response is incomplete")
            batch: list[PointState] = []
            for item in result["points"]:
                payload = item.get("payload")
                if not isinstance(payload, dict):
                    raise QdrantInvariantError("Qdrant scroll returned a non-object payload")
                batch.append(PointState(str(item.get("id")), payload))
            if batch:
                yield batch
            next_offset = result.get("next_page_offset")
            if next_offset is None:
                return
            marker = repr(next_offset)
            if marker in seen_offsets or not batch:
                raise QdrantInvariantError("Qdrant scroll pagination did not make progress")
            seen_offsets.add(marker)
            offset = next_offset

    def upsert(self, rows: list[VectorRow], vectors: list[list[float]]) -> None:
        if len(rows) != len(vectors):
            raise ValueError("row/vector counts differ")
        points = [
            {"id": row.point_id, "vector": vector, "payload": row.payload()}
            for row, vector in zip(rows, vectors, strict=True)
        ]
        self.http.request(
            "PUT",
            f"{self.base_url}/collections/{self.collection}/points",
            params={"wait": "true"},
            json={"points": points},
            timeout=(10, 240),
            phase="qdrant_vector_upsert",
        )

    def set_payload(self, point_id: str, patch: dict[str, Any]) -> None:
        if not patch:
            return
        self.http.request(
            "POST",
            f"{self.base_url}/collections/{self.collection}/points/payload",
            params={"wait": "true"},
            json={"payload": patch, "points": [point_id]},
            timeout=(5, 60),
            phase="qdrant_payload_update",
        )
