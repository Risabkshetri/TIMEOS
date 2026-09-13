"""ensure_partitions actually runs DDL against a real connection — no pytest test previously
exercised this (the ASGITransport-based `client` fixture skips the app's lifespan entirely, so
this path only ran for real inside Docker, where it broke: asyncpg/Postgres reject bind
parameters in CREATE TABLE ... PARTITION OF). This is a direct regression test for that.
"""

from sqlalchemy import text

from timeos.jobs.partitions import ensure_partitions


async def test_ensure_partitions_creates_expected_tables():
    import timeos.db as db

    async with db.engine.begin() as conn:
        names = await ensure_partitions(conn, months_ahead=2)
        assert len(names) == 3

        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE tablename = ANY(:names)"),
            {"names": names},
        )
        found = {row[0] for row in result}
        assert found == set(names)


async def test_ensure_partitions_is_idempotent():
    import timeos.db as db

    async with db.engine.begin() as conn:
        first = await ensure_partitions(conn, months_ahead=1)
        second = await ensure_partitions(conn, months_ahead=1)
        assert first == second  # re-running doesn't error or duplicate
