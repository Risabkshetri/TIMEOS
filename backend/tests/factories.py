"""Test-only helpers for creating a user + enrollment code directly against the DB."""

import uuid
from datetime import UTC, datetime, timedelta

import timeos.db as db
from timeos.models.enrollment_code import EnrollmentCode
from timeos.models.user import User
from timeos.security.tokens import generate_enrollment_code, hash_secret


async def create_user_with_enrollment_code(
    *,
    ttl_minutes: int = 10,
    timezone: str = "UTC",
    day_start_hour: int = 4,
) -> tuple[uuid.UUID, str]:
    async with db.async_session_factory() as session:
        user = User(timezone=timezone, day_start_hour=day_start_hour)
        session.add(user)
        await session.flush()

        code = generate_enrollment_code()
        session.add(
            EnrollmentCode(
                code=code,
                user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
            )
        )
        await session.commit()
        return user.id, code


async def create_user_with_password(
    *, password: str = "correct-horse-battery"
) -> tuple[uuid.UUID, str]:
    async with db.async_session_factory() as session:
        user = User(
            timezone="UTC",
            day_start_hour=4,
            password_hash=hash_secret(password),
            password_changed_at=datetime.now(UTC),
        )
        session.add(user)
        await session.commit()
        return user.id, password
