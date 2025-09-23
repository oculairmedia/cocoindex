"""Shared helpers for CocoIndex FalkorDB export flows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Union
import re

_ISO_Z_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$"
)


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


__all__ = [
    "current_timestamp_iso",
    "iso_from_epoch_millis",
    "is_isoformat_timestamp",
]
