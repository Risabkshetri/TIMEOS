"""CLI: create a device enrollment code for the (single) personal user.

Phase 5's dashboard will eventually generate these from a button click (§29). Until then:

    docker compose exec api python -m timeos.jobs.create_enrollment_code

Bootstraps the single user row on first run (personal-use system — see §13's users table note).
Prints the code; it is valid for 10 minutes and single-use (§28).
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from timeos.db import async_session_factory
from timeos.models.enrollment_code import EnrollmentCode
from timeos.models.user import User
from timeos.security.tokens import generate_enrollment_code

ENROLLMENT_CODE_TTL_MINUTES = 10


async def _ensure_default_user(session) -> User:
    result = await session.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User()
    session.add(user)
    await session.flush()
    return user


async def main() -> None:
    async with async_session_factory() as session:
        user = await _ensure_default_user(session)

        code = generate_enrollment_code()
        now = datetime.now(UTC)
        session.add(
            EnrollmentCode(
                code=code,
                user_id=user.id,
                expires_at=now + timedelta(minutes=ENROLLMENT_CODE_TTL_MINUTES),
            )
        )
        await session.commit()

        print(f"Enrollment code: {code}")
        print(f"Expires: {(now + timedelta(minutes=ENROLLMENT_CODE_TTL_MINUTES)).isoformat()}")
        print(f"User ID: {user.id}")


if __name__ == "__main__":
    asyncio.run(main())
