from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

EXPIRY_GRACE_MS = 1500

ClockFn = Callable[[], datetime]


def utcnow_clock() -> datetime:
    """Default production server UTC clock."""
    return datetime.now(UTC)


def get_clock() -> ClockFn:
    """FastAPI dependency returning the authoritative server UTC clock callable."""
    return utcnow_clock


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Normalize naive or offset datetimes to timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def is_expired(
    now: datetime,
    expires_at: datetime | None,
    *,
    grace_ms: int = EXPIRY_GRACE_MS,
) -> bool:
    """Return True when `now` is strictly past `expires_at + grace_ms`."""
    if expires_at is None:
        return False
    now_utc = ensure_utc(now)
    exp_utc = ensure_utc(expires_at)
    assert now_utc is not None and exp_utc is not None
    deadline = exp_utc + timedelta(milliseconds=grace_ms)
    return now_utc > deadline


def remaining_seconds(now: datetime, expires_at: datetime | None) -> int | None:
    """Compute non-negative whole seconds remaining until `expires_at`."""
    if expires_at is None:
        return None
    now_utc = ensure_utc(now)
    exp_utc = ensure_utc(expires_at)
    assert now_utc is not None and exp_utc is not None
    delta_secs = (exp_utc - now_utc).total_seconds()
    if delta_secs <= 0:
        return 0
    return int(math.ceil(delta_secs))


def compute_elapsed_ms(
    start: datetime | None,
    end: datetime,
    *,
    max_ms: int | None = None,
) -> int:
    """Compute non-negative elapsed milliseconds between two timestamps."""
    if start is None:
        return 0
    start_utc = ensure_utc(start)
    end_utc = ensure_utc(end)
    assert start_utc is not None and end_utc is not None
    elapsed = int((end_utc - start_utc).total_seconds() * 1000)
    if elapsed < 0:
        elapsed = 0
    if max_ms is not None and elapsed > max_ms:
        elapsed = max_ms
    return elapsed
