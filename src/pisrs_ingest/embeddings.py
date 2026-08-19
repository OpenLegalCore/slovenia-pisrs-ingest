"""Embedding provider adapter."""

from __future__ import annotations

from typing import Any

from .client import HttpClient, HttpError
from .models import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL


class EmbeddingClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int,
        http: HttpClient | None = None,
    ) -> None:
        if model != EMBEDDING_MODEL or dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError(
                "embedding contract change requires a separately reviewed full reindex"
            )
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.http = http or HttpClient()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not value for value in texts):
            raise ValueError("embedding input must contain non-empty texts")
        response = self.http.request(
            "POST",
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": texts, "dimensions": self.dimensions},
            timeout=(10, 180),
            phase="embedding_request",
        )
        payload: dict[str, Any] = response.json()
        data = payload.get("data")
        if not isinstance(data, list):
            raise HttpError("embedding response does not contain a data list")
        ordered = sorted(data, key=lambda item: item.get("index", -1))
        vectors = [item.get("embedding") for item in ordered]
        if len(vectors) != len(texts):
            raise HttpError("embedding response count does not match the request")
        if any(
            not isinstance(vector, list) or len(vector) != self.dimensions for vector in vectors
        ):
            raise HttpError("embedding response violates the dimension contract")
        return vectors
