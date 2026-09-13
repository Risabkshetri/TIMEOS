"""Database engine/session management.

Per docs/TIMEOS_ENGINEERING_SPEC.md ADR-006: `timeos.ai` must never import this module. That
boundary is enforced by the import-linter contract in pyproject.toml and by
tests/test_privacy_isolation.py — do not weaken either to make this module more convenient to use
from timeos.ai.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from timeos.config import get_settings

_settings = get_settings()

engine = create_async_engine(_settings.database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def check_ready() -> bool:
    """Used by /v1/health/ready: DB reachable and migrations at head."""
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
