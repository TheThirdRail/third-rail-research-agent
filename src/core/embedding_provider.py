"""Embedding provider abstractions for semantic memory."""

from __future__ import annotations

import hashlib
import os
from typing import Protocol

import httpx

from src.core.config import settings
from src.core.lmstudio_utils import (
    normalize_lmstudio_base_url,
    resolve_lmstudio_api_key,
)


class EmbeddingProvider(Protocol):
    """Minimal embedding interface used by semantic memory services."""

    provider_name: str
    model_name: str
    dimensions: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed text inputs into fixed-size vectors."""


class FakeEmbeddingProvider:
    """Deterministic test embedding provider with no network dependency."""

    provider_name = "fake"
    model_name = "fake-hash-v1"
    dimensions = 16

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        for index in range(self.dimensions):
            raw = digest[index] / 255.0
            values.append(round((raw * 2.0) - 1.0, 6))
        return values


class LMStudioEmbeddingProvider:
    """OpenAI-compatible embeddings client for a local LM Studio server."""

    provider_name = "lmstudio"

    def __init__(
        self,
        *,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model_name = model_name or settings.embedding_model
        self.base_url = normalize_lmstudio_base_url(
            base_url
            or os.getenv("LM_STUDIO_API_BASE")
            or os.getenv("LM_STUDIO_BASE_URL")
            or os.getenv("LMSTUDIO_BASE_URL")
            or settings.lmstudio_base_url
        )
        self.api_key = resolve_lmstudio_api_key(
            api_key,
            os.getenv("LM_STUDIO_API_KEY"),
            os.getenv("LMSTUDIO_API_KEY"),
            settings.lmstudio_api_key,
        )
        self.timeout_seconds = timeout_seconds
        self.dimensions = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.model_name or self.model_name == "fake-hash-v1":
            raise ValueError("EMBEDDING_MODEL must be set for LM Studio embeddings")

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model_name, "input": texts},
            )
            response.raise_for_status()
            payload = response.json()

        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("LM Studio embeddings response missing data list")

        vectors: list[list[float]] = []
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise ValueError("LM Studio embeddings response has invalid item")
            vector = [float(value) for value in item["embedding"]]
            vectors.append(vector)

        if len(vectors) != len(texts):
            raise ValueError("LM Studio embeddings response count mismatch")
        self.dimensions = len(vectors[0]) if vectors else 0
        return vectors


def get_embedding_provider(
    provider_name: str | None = None,
    model_name: str | None = None,
) -> EmbeddingProvider:
    """Return the configured semantic memory embedding provider."""
    provider = (provider_name or settings.embedding_provider or "fake").strip().lower()
    if provider == "fake":
        return FakeEmbeddingProvider()
    if provider in {"lmstudio", "lm_studio", "lm-studio"}:
        return LMStudioEmbeddingProvider(model_name=model_name)
    raise ValueError(f"Unsupported embedding provider: {provider}")
