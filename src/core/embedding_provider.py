"""Embedding provider abstractions for semantic memory."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Protocol

import httpx

from src.core.config import settings
from src.core.lmstudio_utils import (
    normalize_lmstudio_base_url,
    resolve_lmstudio_api_key,
)

logger = logging.getLogger(__name__)


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
        timeout_seconds: float | None = None,
        max_batch_size: int | None = None,
        max_input_chars: int | None = None,
        slow_request_warning_seconds: float | None = None,
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
        self.timeout_seconds = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else float(getattr(settings, "embedding_timeout_seconds", 60.0))
        )
        configured_batch_size = (
            max_batch_size
            if max_batch_size is not None
            else getattr(settings, "embedding_batch_size", 32)
        )
        self.max_batch_size = max(1, int(configured_batch_size))
        configured_max_chars = (
            max_input_chars
            if max_input_chars is not None
            else getattr(settings, "embedding_max_input_chars", 4000)
        )
        self.max_input_chars = max(0, int(configured_max_chars))
        self.slow_request_warning_seconds = (
            float(slow_request_warning_seconds)
            if slow_request_warning_seconds is not None
            else float(getattr(settings, "embedding_slow_request_warning_seconds", 10.0))
        )
        self.dimensions = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.model_name or self.model_name == "fake-hash-v1":
            raise ValueError("EMBEDDING_MODEL must be set for LM Studio embeddings")

        prepared_texts = [self._prepare_text(text) for text in texts]
        with httpx.Client(timeout=self.timeout_seconds) as client:
            vectors = []
            for batch in self._batches(prepared_texts):
                vectors.extend(self._embed_batch(client, batch))

        if len(vectors) != len(texts):
            raise ValueError("LM Studio embeddings response count mismatch")
        self.dimensions = len(vectors[0]) if vectors else 0
        return vectors

    def _embed_batch(self, client: httpx.Client, batch: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        response = client.post(
            f"{self.base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model_name, "input": batch},
        )
        elapsed = time.perf_counter() - started
        if elapsed >= self.slow_request_warning_seconds:
            logger.warning(
                "LM Studio embeddings request was slow: %.2fs for %s inputs (%s chars)",
                elapsed,
                len(batch),
                sum(len(text) for text in batch),
            )
        response.raise_for_status()
        payload = response.json()

        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("LM Studio embeddings response missing data list")

        vectors: list[list[float]] = []
        for item in data:
            if not isinstance(item, dict) or not isinstance(
                item.get("embedding"), list
            ):
                raise ValueError("LM Studio embeddings response has invalid item")
            vector = [float(value) for value in item["embedding"]]
            vectors.append(vector)

        if len(vectors) != len(batch):
            raise ValueError("LM Studio embeddings response count mismatch")
        return vectors

    def _prepare_text(self, text: str) -> str:
        compacted = " ".join(str(text).split())
        if self.max_input_chars:
            return compacted[: self.max_input_chars]
        return compacted

    def _batches(self, texts: list[str]) -> list[list[str]]:
        return [
            texts[start : start + self.max_batch_size]
            for start in range(0, len(texts), self.max_batch_size)
        ]


def get_embedding_provider(
    provider_name: str | None = None,
    model_name: str | None = None,
    *,
    timeout_seconds: float | None = None,
    max_batch_size: int | None = None,
    max_input_chars: int | None = None,
) -> EmbeddingProvider:
    """Return the configured semantic memory embedding provider."""
    provider = (provider_name or settings.embedding_provider or "fake").strip().lower()
    if provider == "fake":
        return FakeEmbeddingProvider()
    if provider in {"lmstudio", "lm_studio", "lm-studio"}:
        return LMStudioEmbeddingProvider(
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            max_batch_size=max_batch_size,
            max_input_chars=max_input_chars,
        )
    raise ValueError(f"Unsupported embedding provider: {provider}")
