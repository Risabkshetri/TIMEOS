"""CLI: set (or rotate) the dashboard login password for the single personal-use user (§25, §28).

    docker compose exec api python -m timeos.jobs.set_dashboard_password

Prompted interactively rather than accepted as a CLI argument, so it never lands in shell
history or `ps`. Setting `password_changed_at` invalidates every session token issued before this
moment (see timeos/security/sessions.py's module docstring) — this is what makes "rotate the
dashboard password" in §28's stolen-laptop runbook an actual revocation, not just a future login
requiring the new password while old sessions stay valid.
"""

import asyncio
from datetime import UTC, datetime
from getpass import getpass

from sqlalchemy import select

from timeos.db import async_session_factory
from timeos.models.user import User
from timeos.security.tokens import hash_secret

MIN_PASSWORD_LENGTH = 12


async def main() -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if user is None:
            user = User()
            session.add(user)
            await session.flush()

        password = getpass("New dashboard password: ")
        confirm = getpass("Confirm: ")
        if password != confirm:
            print("Passwords did not match; nothing changed.")
            return
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters; nothing changed.")
            return

        user.password_hash = hash_secret(password)
        user.password_changed_at = datetime.now(UTC)
        await session.commit()
        print("Dashboard password set. Every existing browser session is now signed out.")


if __name__ == "__main__":
    asyncio.run(main())
