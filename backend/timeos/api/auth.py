"""Dashboard login/logout (§25, §28).

The personal-use system has exactly one user row (§13's users table note) — login checks the
submitted password against whichever user exists, there is no username/email lookup step.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import (
    _SlidingWindowRateLimiter,
    clear_session_cookies,
    get_current_user_no_refresh,
    get_db,
    set_session_cookies,
)
from timeos.models.user import User
from timeos.schemas.auth import LoginRequest
from timeos.security.tokens import verify_secret

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# §28: "auth 5/min/IP" — tighter than ingest, matching devices.py's enroll_rate_limiter.
auth_rate_limiter = _SlidingWindowRateLimiter(limit=5, window_seconds=60.0)


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not auth_rate_limiter.check(client_ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")

    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid password")

    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if user is None or user.password_hash is None:
        # No dashboard password has been set yet (timeos.jobs.set_dashboard_password) — this is
        # indistinguishable from a wrong password on purpose, so an attacker can't use the login
        # endpoint to probe whether the system has been set up yet.
        raise unauthorized
    if not verify_secret(body.password, user.password_hash):
        raise unauthorized

    set_session_cookies(response, user.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, _user: User = Depends(get_current_user_no_refresh)) -> None:
    clear_session_cookies(response)
