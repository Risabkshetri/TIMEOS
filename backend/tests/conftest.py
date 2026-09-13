"""Session-wide testcontainers Postgres for Phase 3's integration tests.

timeos.db creates its async engine at MODULE IMPORT TIME from TIMEOS_DATABASE_URL, so the
container must start and the env var must be set in pytest_configure — which runs before pytest
collects (imports) any test module — rather than in an ordinary fixture, which would run too
late to affect an engine already constructed from the wrong URL.
"""

import os
import subprocess

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

_container: PostgresContainer | None = None


def pytest_configure(config: pytest.Config) -> None:
    global _container
    if os.environ.get("TIMEOS_SKIP_TESTCONTAINERS"):
        return  # allows running the non-DB unit tests without Docker available

    _container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
    _container.start()

    async_url = _container.get_connection_url()  # postgresql+psycopg2://... by default
    async_url = async_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    os.environ["TIMEOS_DATABASE_URL"] = async_url

    # alembic/env.py always builds an async engine (asyncio.run(run_migrations_online())), so
    # this needs the same +asyncpg URL, not a sync one.
    subprocess.run(
        ["alembic", "upgrade", "head"],
        env={**os.environ, "TIMEOS_DATABASE_URL": async_url},
        check=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


def pytest_unconfigure(config: pytest.Config) -> None:
    global _container
    if _container is not None:
        _container.stop()
        _container = None


@pytest.fixture(autouse=True)
async def _clean_tables():
    """Truncates every app table between tests so they can each use small, readable seq/seq
    ranges without colliding on prior tests' rows."""
    yield
    if os.environ.get("TIMEOS_SKIP_TESTCONTAINERS"):
        return
    from sqlalchemy import text

    from timeos.db import engine

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, devices, enrollment_codes, sync_batches, raw_events, "
                "seq_gaps, dirty_days RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture(scope="session", autouse=True)
async def _use_nullpool_engine_for_tests():
    """timeos/db.py's module-level engine is constructed once at import time; its pooled
    connections can end up bound to whichever event loop was running on first use, which then
    conflicts with a *different* loop on a later use ("attached to a different loop"). Tests
    replace it with a NullPool engine — every checkout opens a fresh connection and closes it
    immediately after, so no connection is ever reused across a loop boundary. Production still
    uses the real pooled engine from timeos/db.py; this override is test-only.
    """
    import timeos.db as db_module

    await db_module.engine.dispose()
    test_engine = create_async_engine(os.environ["TIMEOS_DATABASE_URL"], poolclass=NullPool)
    db_module.engine = test_engine
    db_module.async_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    yield
    await test_engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """The rate limiters in api/deps.py and api/devices.py are module-level singletons (by
    design — they track real request history across the process's lifetime). Without a reset,
    any test suite with more than a handful of enroll/ingest calls trips the limiter purely from
    test volume, which is a test-isolation bug, not a product one."""
    from timeos.api.deps import ingest_rate_limiter
    from timeos.api.devices import enroll_rate_limiter

    ingest_rate_limiter.reset()
    enroll_rate_limiter.reset()


@pytest.fixture
async def client():
    """httpx client over the ASGI app directly — no real network, no separate server process.
    The app's lifespan (partition maintenance) is skipped here since the migration already
    created the needed partitions; nothing in these tests depends on it re-running."""
    from timeos.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
