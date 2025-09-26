"""Shared helpers for CocoIndex FalkorDB export flows."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Iterable, Sequence, Union

from cocoindex.matrix.embedding import EmbeddingConfig, MatrixEmbeddingClient

_ISO_Z_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$"
)

_EMBED_CLIENT: MatrixEmbeddingClient | None = None
_EMBED_CLIENT_INITIALIZED = False
_EMBED_MAX_CHARS = int(os.environ.get("EMB_MAX_CHARS", "6000"))

logger = logging.getLogger(__name__)


def _ensure_z_timezone(value: str) -> str:
    """Normalise timezone suffix to a trailing 'Z'."""
    if value.endswith("Z"):
        return value
    if value.endswith("+00:00"):
        return value[:-6] + "Z"
    return value


def current_timestamp_iso(*, timespec: str = "milliseconds") -> str:
    """Return the current UTC time as an RFC3339 string."""
    ts = datetime.now(timezone.utc)
    return _ensure_z_timezone(ts.isoformat(timespec=timespec))


def iso_from_epoch_millis(epoch_ms: Union[int, float, str], *, timespec: str = "milliseconds") -> str:
    """Convert an epoch value in milliseconds to an RFC3339 string."""
    if isinstance(epoch_ms, str):
        epoch_ms = float(epoch_ms)
    seconds = float(epoch_ms) / 1000.0
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    return _ensure_z_timezone(dt.isoformat(timespec=timespec))


def is_isoformat_timestamp(value: str) -> bool:
    """Return True if the value matches the expected RFC3339 format."""
    return bool(_ISO_Z_PATTERN.match(value))


def _normalise_embedding_url(provider: str, url: str | None) -> str | None:
    if not url:
        return None
    trimmed = url.strip()
    if not trimmed:
        return None
    trimmed = trimmed.rstrip("/")
    if provider == "ollama":
        for suffix in ("/api/embeddings", "/v1/embeddings"):
            if trimmed.endswith(suffix):
                trimmed = trimmed[: -len(suffix)]
    return trimmed


def get_embedding_client() -> MatrixEmbeddingClient | None:
    """Return a singleton embedding client configured from environment variables."""

    global _EMBED_CLIENT  # pylint: disable=global-statement
    global _EMBED_CLIENT_INITIALIZED  # pylint: disable=global-statement

    if _EMBED_CLIENT_INITIALIZED:
        return _EMBED_CLIENT

    _EMBED_CLIENT_INITIALIZED = True

    provider = os.environ.get("EMB_PROVIDER") or os.environ.get("EMBED_PROVIDER") or "ollama"
    provider = provider.strip().lower()
    url = _normalise_embedding_url(provider, os.environ.get("EMB_URL"))
    model = os.environ.get("EMB_MODEL", "dengcao/Qwen3-Embedding-4B:Q4_K_M")
    api_key = os.environ.get("EMB_KEY") or os.environ.get("EMB_API_KEY")

    config = EmbeddingConfig(
        provider=provider,
        url=url or "",
        model=model,
        api_key=api_key,
    )

    try:
        _EMBED_CLIENT = MatrixEmbeddingClient(config)
    except Exception as exc:  # pragma: no cover - network configuration
        logger.warning("Embedding client initialisation failed: %s", exc)
        _EMBED_CLIENT = None

    return _EMBED_CLIENT


def truncate_for_embedding(text: str | None) -> str | None:
    """Return text truncated for embedding requests."""

    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    if len(stripped) <= _EMBED_MAX_CHARS:
        return stripped
    return stripped[:_EMBED_MAX_CHARS]


def format_vector(vector: Sequence[float]) -> str:
    """Format a vector for Cypher assignments with FalkorDB vecf32 casting."""

    formatted = ", ".join(f"{value:.8f}" for value in vector)
    return f"vecf32([{formatted}])"


def embed_texts(texts: Iterable[str | None]) -> list[list[float] | None]:
    """Embed multiple texts using the configured embedding client (best-effort)."""

    client = get_embedding_client()
    results: list[list[float] | None] = []

    if client is None:
        for _text in texts:
            results.append(None)
        return results

    for text in texts:
        truncated = truncate_for_embedding(text)
        results.append(client.embed(truncated) if truncated else None)

    return results


__all__ = [
    "current_timestamp_iso",
    "iso_from_epoch_millis",
    "is_isoformat_timestamp",
    "get_embedding_client",
    "truncate_for_embedding",
    "format_vector",
    "embed_texts",
]
