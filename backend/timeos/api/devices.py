"""Device enrollment and token rotation (§12.2, §28, §38 Phase 3).

Enrollment codes are created via the CLI (timeos/jobs/create_enrollment_code.py) until Phase 5's
dashboard can generate them from a button click.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import _SlidingWindowRateLimiter, get_current_device, get_db
from timeos.models.device import Device
from timeos.models.enrollment_code import EnrollmentCode
from timeos.schemas.devices import (
    EnrollRequest,
    EnrollResponse,
    TokenRotateRequest,
    TokenRotateResponse,
)
from timeos.security.tokens import generate_device_token, hash_secret

router = APIRouter(prefix="/v1/devices", tags=["devices"])

# §28: auth-adjacent endpoints get a tighter limit than ingest.
enroll_rate_limiter = _SlidingWindowRateLimiter(limit=5, window_seconds=60.0)


@router.post("/enroll", response_model=EnrollResponse, status_code=status.HTTP_201_CREATED)
async def enroll(
    body: EnrollRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> EnrollResponse:
    client_ip = request.client.host if request.client else "unknown"
    if not enroll_rate_limiter.check(client_ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")

    code_row = await db.get(EnrollmentCode, body.enrollment_code)
    now = datetime.now(UTC)
    if (
        code_row is None
        or code_row.used_at is not None
        or code_row.expires_at.replace(tzinfo=UTC) < now
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired enrollment code")

    existing = await db.get(Device, body.device_id)
    if existing is not None and existing.revoked_at is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "device already enrolled; use token rotation instead of re-enrolling",
        )

    token, secret = generate_device_token(body.device_id)
    token_hash = hash_secret(secret)

    if existing is not None:
        # Re-enrolling a previously revoked device: fresh token, cleared revocation.
        existing.name = body.name
        existing.platform = body.platform.value
        existing.browser_family = body.browser_family
        existing.app_version = body.app_version
        existing.os_version = body.os_version
        existing.token_hash = token_hash
        existing.token_created_at = now
        existing.token_rotated_at = None
        existing.previous_token_hash = None
        existing.previous_token_expires_at = None
        existing.revoked_at = None
    else:
        db.add(
            Device(
                id=body.device_id,
                user_id=code_row.user_id,
                name=body.name,
                platform=body.platform.value,
                browser_family=body.browser_family,
                app_version=body.app_version,
                os_version=body.os_version,
                token_hash=token_hash,
                token_created_at=now,
            )
        )

    code_row.used_at = now
    code_row.used_by_device_id = body.device_id

    await db.commit()
    return EnrollResponse(device_id=body.device_id, token=token)


@router.post("/token/rotate", response_model=TokenRotateResponse)
async def rotate_token(
    _body: TokenRotateRequest,
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
) -> TokenRotateResponse:
    token, secret = generate_device_token(device.id)
    now = datetime.now(UTC)

    device.previous_token_hash = device.token_hash
    device.previous_token_expires_at = now + timedelta(hours=24)
    device.token_hash = hash_secret(secret)
    device.token_rotated_at = now

    await db.commit()
    return TokenRotateResponse(token=token)
