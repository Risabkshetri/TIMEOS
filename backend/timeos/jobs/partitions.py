"""Monthly partition maintenance for raw_events (§13, §29).

Called at API startup and safe to call any number of times — each partition is created with
`IF NOT EXISTS`, so this never fails on an existing partition, it just ensures the next few
months are always ready before events for them arrive.
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

MONTHS_AHEAD = 2


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month + 1:02d}-01"
    return start, end


def _partition_name(year: int, month: int) -> str:
    return f"raw_events_{year:04d}_{month:02d}"


async def ensure_partitions(conn: AsyncConnection, months_ahead: int = MONTHS_AHEAD) -> list[str]:
    """Ensures a partition exists for the current month through `months_ahead` months out
    (idempotent — CREATE TABLE IF NOT EXISTS). Returns the partition names checked/ensured."""
    ensured: list[str] = []
    now = datetime.now(UTC)
    year, month = now.year, now.month

    for _ in range(months_ahead + 1):
        name = _partition_name(year, month)
        start, end = _month_bounds(year, month)
        # Postgres/asyncpg reject bind parameters in CREATE TABLE ... PARTITION OF (same
        # restriction the hand-written migration SQL works around with a PL/pgSQL format()
        # call) — values are inlined directly. Safe here: start/end/name are all derived from
        # this function's own integer year/month loop variables, never from external input.
        await conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {name}
                PARTITION OF raw_events
                FOR VALUES FROM ('{start}') TO ('{end}')
                """  # noqa: S608 - values are our own generated date strings, not user input
            )
        )
        ensured.append(name)

        month += 1
        if month > 12:
            month = 1
            year += 1

    return ensured
