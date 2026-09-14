"""Shared FastAPI dependencies: DB session, device authentication, session authentication,
CSRF, rate limiting.

Scope separation (§28): get_current_device is the ONLY way a device token authenticates, and it
is wired only onto ingest/sync routes (see api/ingest.py). A device token is structurally unable
to reach any read endpoint — there is no dependency here that would let it. Symmetrically,
get_current_user (a dashboard session cookie) is wired only onto read/dashboard routes and is
never accepted on ingest/sync routes.
"""

import hmac
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.config import get_settings
from timeos.db import get_session
from timeos.models.device import Device
from timeos.models.user import User
from timeos.security.sessions import SESSION_MAX_AGE, create_session_token, verify_session_token
from timeos.security.tokens import parse_token, verify_secret

DbSession = AsyncSession

SESSION_COOKIE_NAME = "timeos_session"
CSRF_COOKIE_NAME = "timeos_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


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


def _cookie_is_secure() -> bool:
    # Secure=False only in local development (plain http://localhost) — every other environment
    # gets Secure, matching §25's "httpOnly session cookies... no device tokens in the browser".
    return get_settings().environment != "development"


def set_session_cookies(response: Response, user_id: uuid.UUID) -> None:
    """Issues both the httpOnly session cookie and the JS-readable CSRF cookie (§28's
    double-submit pattern: a mutation must echo the CSRF cookie's value back in a header, which
    a cross-site page cannot read due to browser same-origin policy even though it CAN cause the
    browser to send the cookie itself)."""
    settings = get_settings()
    now = datetime.now(UTC)
    session_token = create_session_token(user_id, settings.session_secret, now)
    max_age = int(SESSION_MAX_AGE.total_seconds())
    secure = _cookie_is_secure()

    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        secrets.token_urlsafe(32),
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="strict",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)
    response.delete_cookie(CSRF_COOKIE_NAME)


async def _authenticate_session(request: Request, db: AsyncSession) -> User:
    """The actual check, with no side effects — shared by get_current_user (which additionally
    refreshes the cookie for sliding expiry) and get_current_user_no_refresh (used by /logout,
    which must not reissue a valid cookie in the same response it's trying to clear)."""
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise unauthorized

    settings = get_settings()
    now = datetime.now(UTC)

    # Pass 1: signature/format/expiry only. The signature already proves the token wasn't
    # forged, which is what makes it safe to trust the embedded user_id for the DB lookup below
    # — password_changed_at can't be checked yet since it requires knowing which user this is.
    provisional_user_id = verify_session_token(token, settings.session_secret, now, None)
    if provisional_user_id is None:
        raise unauthorized

    user = await db.get(User, provisional_user_id)
    if user is None:
        raise unauthorized

    # Pass 2: the real check, now that we have the user's password_changed_at.
    if verify_session_token(token, settings.session_secret, now, user.password_changed_at) is None:
        raise unauthorized

    return user


async def get_current_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _authenticate_session(request, db)
    # Sliding expiry (§28): every authenticated request pushes the 30-day window forward.
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(user.id, settings.session_secret, datetime.now(UTC)),
        max_age=int(SESSION_MAX_AGE.total_seconds()),
        httponly=True,
        secure=_cookie_is_secure(),
        samesite="strict",
    )
    return user


async def get_current_user_no_refresh(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Same authentication as get_current_user, without the sliding-expiry cookie refresh —
    for /logout, where reissuing a fresh valid cookie in the same response that's about to
    delete it would race the deletion (both are Set-Cookie headers on one response)."""
    return await _authenticate_session(request, db)


async def enforce_csrf(request: Request) -> None:
    """§28: CSRF token on all mutations. Double-submit: the cookie (set at login, JS-readable)
    must match a header the client attaches itself — a cross-site request can make the browser
    send the cookie automatically, but cannot read its value to also set the header."""
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    header_value = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing or invalid CSRF token")
