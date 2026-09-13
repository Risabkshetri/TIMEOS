"""Shared FastAPI dependencies: DB session, device authentication, rate limiting.

Scope separation (§28): get_current_device is the ONLY way a device token authenticates, and it
is wired only onto ingest/sync routes (see api/ingest.py). A device token is structurally unable
to reach any read endpoint — there is no dependency here that would let it.
"""

import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.db import get_session
from timeos.models.device import Device
from timeos.security.tokens import parse_token, verify_secret

DbSession = AsyncSession


async def get_db():
    async for session in get_session():
        yield session


async def get_current_device(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Device:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing device token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not authorization or not authorization.startswith("Bearer "):
        raise unauthorized
    token = authorization.removeprefix("Bearer ").strip()

    parsed = parse_token(token)
    if parsed is None:
        raise unauthorized
    device_id, secret = parsed

    device = await db.get(Device, device_id)
    if device is None or device.revoked_at is not None:
        raise unauthorized

    now = datetime.now(UTC)

    if verify_secret(secret, device.token_hash):
        return device

    # §28: the previous token stays valid for 24h after rotation, so a client that hasn't yet
    # received the new one isn't locked out mid-rotation.
    if (
        device.previous_token_hash is not None
        and device.previous_token_expires_at is not None
        and device.previous_token_expires_at.replace(tzinfo=UTC) > now
        and verify_secret(secret, device.previous_token_hash)
    ):
        return device

    raise unauthorized


class _SlidingWindowRateLimiter:
    """In-process sliding-window limiter — adequate for a single-worker, single-user deployment
    (§28: 60 req/min/device). Redis is deliberately not used here per ADR-004."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        """Test-only: clears all tracked state so a rate-limit test doesn't depend on how many
        requests earlier tests happened to send against the same shared, module-level limiter."""
        self._hits.clear()


ingest_rate_limiter = _SlidingWindowRateLimiter(limit=60, window_seconds=60.0)


async def enforce_ingest_rate_limit(device: Device = Depends(get_current_device)) -> Device:
    if not ingest_rate_limiter.check(str(device.id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": "5"},
        )
    return device
