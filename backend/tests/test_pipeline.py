"""Integration test for timeos.jobs.pipeline.recompute_day against a real Postgres: exercises
the full sessionize -> classify -> coverage -> focus -> distraction -> metrics chain and its
persistence (device_coverage, app_sessions, activities, daily_metrics)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from timeos.ingest.service import day_window_utc
from timeos.jobs.pipeline import recompute_day
from timeos.models.activity import Activity
from timeos.models.app_session import AppSession
from timeos.models.daily_metric import DailyMetric
from timeos.models.device import Device
from timeos.models.device_coverage import DeviceCoverage
from timeos.models.focus_session import FocusSessionRow
from timeos.models.raw_event import RawEvent
from timeos.models.user import User

# "Yesterday" rather than a hardcoded date: raw_events is a partitioned table (§13, §29) and only
# has partitions for months near "now" (ensure_partitions creates the current month + 2 ahead) —
# a fixed past/future date would hit "no partition of relation raw_events found for row" against
# whichever real month the test happens to run in.
LOCAL_DATE = (datetime.now(UTC) - timedelta(days=1)).date()
DAY_START, _DAY_END = day_window_utc(LOCAL_DATE, "UTC", 4)


def ev(device_id, user_id, seq, offset_s, type_, payload=None):
    ts = DAY_START + timedelta(seconds=offset_s)
    return RawEvent(
        id=uuid.uuid4(),
        ts_utc=ts,
        device_id=device_id,
        user_id=user_id,
        seq=seq,
        tz_offset_min=0,
        tz_id="UTC",
        uptime_ms=int(offset_s * 1000),
        type=type_,
        payload=payload or {},
        schema_v=1,
    )


async def _make_user_and_device(session) -> tuple[User, Device]:
    user = User(timezone="UTC", day_start_hour=4)
    session.add(user)
    await session.flush()
    device = Device(
        id=uuid.uuid4(),
        user_id=user.id,
        name="test-phone",
        platform="android",
        token_hash="irrelevant",
    )
    session.add(device)
    await session.flush()
    return user, device


async def test_recompute_day_produces_a_daily_metrics_row():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        session.add_all(
            [
                ev(device.id, user.id, 1, 0, "SCREEN_ON"),
                ev(device.id, user.id, 2, 5, "APP_FOREGROUND", {"package": "com.android.chrome"}),
                ev(device.id, user.id, 3, 605, "APP_BACKGROUND", {"package": "com.android.chrome"}),
                ev(device.id, user.id, 4, 610, "SCREEN_OFF"),
            ]
        )
        await session.commit()

        result = await recompute_day(session, user, LOCAL_DATE)

        assert result.user_id == user.id
        assert result.local_date == LOCAL_DATE
        assert result.screen_time_s == 610
        assert result.pipeline_version


async def test_recompute_day_persists_coverage_sessions_and_activities():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        session.add_all(
            [
                ev(device.id, user.id, 1, 0, "SCREEN_ON"),
                ev(device.id, user.id, 2, 5, "APP_FOREGROUND", {"package": "com.android.chrome"}),
                ev(device.id, user.id, 3, 605, "APP_BACKGROUND", {"package": "com.android.chrome"}),
            ]
        )
        await session.commit()

        await recompute_day(session, user, LOCAL_DATE)

        coverage_query = select(DeviceCoverage).where(DeviceCoverage.device_id == device.id)
        coverage = (await session.execute(coverage_query)).scalars().all()
        assert len(coverage) > 0

        sessions = (
            (await session.execute(select(AppSession).where(AppSession.device_id == device.id)))
            .scalars()
            .all()
        )
        assert len(sessions) == 1
        assert sessions[0].app_key == "com.android.chrome"

        activities_query = select(Activity).where(Activity.user_id == user.id)
        activities = (await session.execute(activities_query)).scalars().all()
        assert len(activities) == 1
        assert activities[0].source_session_ids == [sessions[0].id]
        assert activities[0].classification_source == "seed"  # chrome is in the seed catalogue


async def test_recompute_day_is_idempotent_and_replaces_the_existing_row():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        session.add(ev(device.id, user.id, 1, 0, "SCREEN_ON"))
        await session.commit()

        first = await recompute_day(session, user, LOCAL_DATE)
        assert not first.revised

        second = await recompute_day(session, user, LOCAL_DATE)
        assert second.revised
        assert second.screen_time_s == first.screen_time_s

        rows = (
            (
                await session.execute(
                    select(DailyMetric).where(
                        DailyMetric.user_id == user.id, DailyMetric.local_date == LOCAL_DATE
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1  # replaced, not duplicated


async def test_recompute_day_does_not_duplicate_app_sessions_on_rerun():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        session.add_all(
            [
                ev(device.id, user.id, 1, 0, "APP_FOREGROUND", {"package": "com.android.chrome"}),
                ev(device.id, user.id, 2, 600, "APP_BACKGROUND", {"package": "com.android.chrome"}),
            ]
        )
        await session.commit()

        await recompute_day(session, user, LOCAL_DATE)
        await recompute_day(session, user, LOCAL_DATE)

        sessions = (
            (await session.execute(select(AppSession).where(AppSession.device_id == device.id)))
            .scalars()
            .all()
        )
        assert len(sessions) == 1


async def test_events_outside_the_day_window_are_excluded():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        session.add_all(
            [
                ev(device.id, user.id, 1, 0, "SCREEN_ON"),  # inside the window
                # 1 second before the window starts (day boundary is exclusive on the low end
                # relative to the PREVIOUS day) -> belongs to the previous local day.
                ev(device.id, user.id, 2, -1, "APP_FOREGROUND", {"package": "com.android.chrome"}),
            ]
        )
        await session.commit()

        await recompute_day(session, user, LOCAL_DATE)

        sessions = (
            (await session.execute(select(AppSession).where(AppSession.device_id == device.id)))
            .scalars()
            .all()
        )
        assert sessions == []  # the chrome session belongs to the previous day, not this one


async def test_recompute_day_persists_a_real_focus_session():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        # com.android.chrome is in the seed catalogue as "browsing" — a single 20-minute
        # uninterrupted session clears §16's 15-minute focus threshold.
        chrome = {"package": "com.android.chrome"}
        session.add_all(
            [
                ev(device.id, user.id, 1, 0, "APP_FOREGROUND", chrome),
                ev(device.id, user.id, 2, 20 * 60, "APP_BACKGROUND", chrome),
            ]
        )
        await session.commit()

        result = await recompute_day(session, user, LOCAL_DATE)
        assert result.focus_session_count == 1
        assert result.longest_focus_s == 20 * 60

        focus_query = select(FocusSessionRow).where(FocusSessionRow.user_id == user.id)
        rows = (await session.execute(focus_query)).scalars().all()
        assert len(rows) == 1
        assert rows[0].duration_s == 20 * 60
        assert rows[0].interruption_count == 0


async def test_concurrent_recompute_of_same_day_does_not_violate_coverage_exclusion_constraint():
    """Regression: two near-simultaneous callers recomputing the same (user, local_date) — e.g.
    two dashboard pages loading before either has a cached row — used to interleave their
    delete-then-insert cycles and trip device_coverage's exclusion constraint with a real
    IntegrityError. Each call here uses its OWN session, mirroring two separate HTTP requests."""
    import asyncio

    import timeos.db as db

    async with db.async_session_factory() as setup_session:
        user, device = await _make_user_and_device(setup_session)
        chrome = {"package": "com.android.chrome"}
        setup_session.add_all(
            [
                ev(device.id, user.id, 1, 0, "APP_FOREGROUND", chrome),
                ev(device.id, user.id, 2, 20 * 60, "APP_BACKGROUND", chrome),
            ]
        )
        await setup_session.commit()
        user_id = user.id

    async def run_once():
        async with db.async_session_factory() as session:
            fresh_user = await session.get(User, user_id)
            return await recompute_day(session, fresh_user, LOCAL_DATE)

    results = await asyncio.gather(run_once(), run_once())
    assert all(r.local_date == LOCAL_DATE for r in results)

    async with db.async_session_factory() as check_session:
        coverage_query = select(DeviceCoverage).where(DeviceCoverage.device_id == device.id)
        coverage_rows = (await check_session.execute(coverage_query)).scalars().all()
        # Exactly one contiguous set of coverage rows, not doubled by the two racing calls.
        assert len({(c.start_ts, c.end_ts, c.state) for c in coverage_rows}) == len(coverage_rows)

        metrics_query = select(DailyMetric).where(
            DailyMetric.user_id == user_id, DailyMetric.local_date == LOCAL_DATE
        )
        metrics_rows = (await check_session.execute(metrics_query)).scalars().all()
        assert len(metrics_rows) == 1
