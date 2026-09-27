"""§11.2/§11.4/§38 Phase 9: real end-to-end browser telemetry through timeos.jobs.pipeline.
recompute_day against real Postgres — raw DOMAIN_FOCUS_START/END events, through per-device
sessionization, through cross-browser arbitration, into persisted `browser_sessions` rows. This is
the real-pipeline counterpart to the pure-function tests in tests/analytics/test_browser_
sessionize.py and test_browser_arbitration.py.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from timeos.ingest.service import day_window_utc
from timeos.jobs.pipeline import recompute_day
from timeos.models.activity import Activity
from timeos.models.app_session import AppSession
from timeos.models.browser_session import BrowserSession
from timeos.models.device import Device
from timeos.models.raw_event import RawEvent
from timeos.models.user import User

LOCAL_DATE = (datetime.now(UTC) - timedelta(days=1)).date()
DAY_START, _ = day_window_utc(LOCAL_DATE, "UTC", 4)


def ev(device_id, user_id, seq, offset_s, type_, payload=None):
    return RawEvent(
        id=uuid.uuid4(),
        ts_utc=DAY_START + timedelta(seconds=offset_s),
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


async def _make_user(session) -> User:
    user = User(timezone="UTC", day_start_hour=4)
    session.add(user)
    await session.flush()
    return user


async def _make_browser_device(session, user, browser_family: str) -> Device:
    device = Device(
        id=uuid.uuid4(),
        user_id=user.id,
        name=f"{browser_family}-browser",
        platform="browser",
        browser_family=browser_family,
        token_hash="x",
    )
    session.add(device)
    await session.flush()
    return device


async def test_a_single_browsers_domain_focus_becomes_a_browser_session():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user = await _make_user(session)
        brave = await _make_browser_device(session, user, "brave")

        session.add_all(
            [
                ev(brave.id, user.id, 1, 0, "DOMAIN_FOCUS_START", {"domain": "github.com"}),
                ev(brave.id, user.id, 2, 600, "DOMAIN_FOCUS_END", {"domain": "github.com"}),
            ]
        )
        await session.commit()

        await recompute_day(session, user, LOCAL_DATE)

        rows = (
            (await session.execute(select(BrowserSession).where(BrowserSession.user_id == user.id)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].domain == "github.com"
        assert rows[0].browser_family == "brave"
        assert rows[0].device_id == brave.id
        assert float(rows[0].duration_s) == 600.0
        assert rows[0].truncated is False


async def test_overlapping_focus_from_two_browsers_is_arbitrated_end_to_end():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user = await _make_user(session)
        brave = await _make_browser_device(session, user, "brave")
        firefox = await _make_browser_device(session, user, "firefox")

        session.add_all(
            [
                ev(brave.id, user.id, 1, 0, "DOMAIN_FOCUS_START", {"domain": "github.com"}),
                ev(brave.id, user.id, 2, 100, "DOMAIN_FOCUS_END", {"domain": "github.com"}),
                # Firefox gains focus at t=60s, overlapping Brave's still-open interval — Brave
                # must be truncated to end at t=60s (§11.4: later start wins).
                ev(firefox.id, user.id, 1, 60, "DOMAIN_FOCUS_START", {"domain": "youtube.com"}),
                ev(firefox.id, user.id, 2, 150, "DOMAIN_FOCUS_END", {"domain": "youtube.com"}),
            ]
        )
        await session.commit()

        await recompute_day(session, user, LOCAL_DATE)

        rows = (
            (
                await session.execute(
                    select(BrowserSession)
                    .where(BrowserSession.user_id == user.id)
                    .order_by(BrowserSession.start_ts)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2
        assert rows[0].browser_family == "brave"
        assert rows[0].end_ts == DAY_START + timedelta(seconds=60)
        assert rows[0].truncated is True
        assert rows[1].browser_family == "firefox"
        assert rows[1].start_ts == DAY_START + timedelta(seconds=60)
        assert rows[1].truncated is False


async def test_recompute_day_is_idempotent_for_browser_sessions():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user = await _make_user(session)
        brave = await _make_browser_device(session, user, "brave")
        session.add_all(
            [
                ev(brave.id, user.id, 1, 0, "DOMAIN_FOCUS_START", {"domain": "github.com"}),
                ev(brave.id, user.id, 2, 600, "DOMAIN_FOCUS_END", {"domain": "github.com"}),
            ]
        )
        await session.commit()

        await recompute_day(session, user, LOCAL_DATE)
        await recompute_day(session, user, LOCAL_DATE)

        rows = (
            (await session.execute(select(BrowserSession).where(BrowserSession.user_id == user.id)))
            .scalars()
            .all()
        )
        assert len(rows) == 1


async def test_a_browser_device_never_produces_app_sessions_but_now_produces_an_activity():
    # §38 Phase 10 supersedes Phase 9's "browser never produces an Activity" boundary: a browser
    # domain is still never an AppSession (that stays Android-only provenance), but it IS now
    # classified (via domain_priors.yaml) and clustered into the unified `activities` timeline.
    import timeos.db as db

    async with db.async_session_factory() as session:
        user = await _make_user(session)
        brave = await _make_browser_device(session, user, "brave")
        session.add(ev(brave.id, user.id, 1, 0, "DOMAIN_FOCUS_START", {"domain": "github.com"}))
        session.add(ev(brave.id, user.id, 2, 600, "DOMAIN_FOCUS_END", {"domain": "github.com"}))
        await session.commit()

        await recompute_day(session, user, LOCAL_DATE)

        app_sessions = (
            (await session.execute(select(AppSession).where(AppSession.device_id == brave.id)))
            .scalars()
            .all()
        )
        activities = (
            (await session.execute(select(Activity).where(Activity.user_id == user.id)))
            .scalars()
            .all()
        )
        assert app_sessions == []
        assert len(activities) == 1
        assert activities[0].devices == [str(brave.id)]
        assert activities[0].classification_source == "seed"


async def test_android_and_browser_devices_coexist_independently_on_the_same_day():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user = await _make_user(session)
        phone = Device(
            id=uuid.uuid4(),
            user_id=user.id,
            name="phone",
            platform="android",
            token_hash="x",
        )
        session.add(phone)
        await session.flush()
        brave = await _make_browser_device(session, user, "brave")

        session.add_all(
            [
                ev(phone.id, user.id, 1, 0, "SCREEN_ON"),
                ev(phone.id, user.id, 2, 5, "APP_FOREGROUND", {"package": "com.android.chrome"}),
                ev(phone.id, user.id, 3, 605, "APP_BACKGROUND", {"package": "com.android.chrome"}),
                ev(brave.id, user.id, 1, 0, "DOMAIN_FOCUS_START", {"domain": "github.com"}),
                ev(brave.id, user.id, 2, 600, "DOMAIN_FOCUS_END", {"domain": "github.com"}),
            ]
        )
        await session.commit()

        await recompute_day(session, user, LOCAL_DATE)

        activities = (
            (await session.execute(select(Activity).where(Activity.user_id == user.id)))
            .scalars()
            .all()
        )
        browser_sessions = (
            (await session.execute(select(BrowserSession).where(BrowserSession.user_id == user.id)))
            .scalars()
            .all()
        )
        # §38 Phase 10: two independent Activity rows, not one merged cross-device cluster — the
        # phone's chrome app session and Brave's github.com domain session overlap in time but
        # classify to DIFFERENT categories (browsing vs. development), and
        # cluster_cross_device_activities only merges same-category activities across devices.
        assert len(activities) == 2
        assert len(browser_sessions) == 1  # from Brave's github.com domain session
        assert browser_sessions[0].domain == "github.com"


async def test_cross_device_activity_clusters_and_dual_device_s_reflects_real_overlap():
    # §38 Phase 10's own headline case: a phone using a development-classified Android app
    # (com.github.android) while a browser has a development-classified domain (github.com) in
    # focus, overlapping in time — same category, different devices — should collapse into ONE
    # cross-device Activity (union duration, not summed), and the day's dual_device_s should
    # reflect the real overlap between the phone's real coverage and the browser's virtual one.
    import timeos.db as db

    async with db.async_session_factory() as session:
        user = await _make_user(session)
        phone = Device(
            id=uuid.uuid4(), user_id=user.id, name="phone", platform="android", token_hash="x"
        )
        session.add(phone)
        await session.flush()
        brave = await _make_browser_device(session, user, "brave")

        session.add_all(
            [
                ev(phone.id, user.id, 1, 0, "SCREEN_ON"),
                ev(phone.id, user.id, 2, 5, "APP_FOREGROUND", {"package": "com.github.android"}),
                ev(phone.id, user.id, 3, 305, "APP_BACKGROUND", {"package": "com.github.android"}),
                # Overlaps the phone's [5, 305) session from t=50 to t=350.
                ev(brave.id, user.id, 1, 50, "DOMAIN_FOCUS_START", {"domain": "github.com"}),
                ev(brave.id, user.id, 2, 350, "DOMAIN_FOCUS_END", {"domain": "github.com"}),
            ]
        )
        await session.commit()

        daily_metric = await recompute_day(session, user, LOCAL_DATE)

        activities = (
            (await session.execute(select(Activity).where(Activity.user_id == user.id)))
            .scalars()
            .all()
        )
        assert len(activities) == 1
        cluster = activities[0]
        assert set(cluster.devices) == {str(phone.id), str(brave.id)}
        assert len(cluster.source_session_ids) == 2
        # Union of [5, 305) and [50, 350) is [5, 350) = 345s, not their sum (600s).
        assert float(cluster.duration_s) == 345.0
        assert "cross_device_members" in cluster.evidence

        # The phone's real coverage and the browser's virtual coverage ([50, 350)) genuinely
        # overlap — some positive dual_device_s, not the 0s a same-device-only union would give.
        assert float(daily_metric.dual_device_s) > 0.0
