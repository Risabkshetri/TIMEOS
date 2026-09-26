"""§21's AI Context Builder, DB-touching half (timeos.jobs.build_ai_context), against real
Postgres: exercises real recomputed activities, a real goal, and feeds the result straight through
the real privacy gate — the strongest regression guard this phase has, since a future field that
accidentally carried a raw identifier would fail this test via PrivacyViolation, not just look
wrong in a review."""

import uuid
from datetime import UTC, datetime, timedelta

from timeos.ingest.service import day_window_utc
from timeos.jobs.build_ai_context import build_ai_context_for_day
from timeos.jobs.pipeline import recompute_day
from timeos.jobs.seed_categories import ensure_system_categories
from timeos.models.device import Device
from timeos.models.goal import Goal
from timeos.models.goal_activity_mapping import GoalActivityMapping
from timeos.models.raw_event import RawEvent
from timeos.models.user import User
from timeos.privacy.gate import enforce_privacy_gate
from timeos.schemas.ai_context import AIContext

LOCAL_DATE = (datetime.now(UTC) - timedelta(days=1)).date()
DAY_START, _ = day_window_utc(LOCAL_DATE, "UTC", 4)
CHROME_APP_KEY = "com.android.chrome"


async def _make_user_and_device(session) -> tuple[User, Device]:
    user = User(timezone="UTC", day_start_hour=4)
    session.add(user)
    await session.flush()
    device = Device(
        id=uuid.uuid4(), user_id=user.id, name="phone", platform="android", token_hash="x"
    )
    session.add(device)
    await session.flush()
    return user, device


async def _seed_chrome_session(session, user, device) -> None:
    session.add_all(
        [
            RawEvent(
                id=uuid.uuid4(),
                ts_utc=DAY_START + timedelta(seconds=offset),
                device_id=device.id,
                user_id=user.id,
                seq=seq,
                tz_offset_min=0,
                tz_id="UTC",
                uptime_ms=int(offset * 1000),
                type=type_,
                payload=payload,
                schema_v=1,
            )
            for seq, offset, type_, payload in [
                (1, 0, "SCREEN_ON", {}),
                (2, 5, "APP_FOREGROUND", {"package": CHROME_APP_KEY}),
                (3, 605, "APP_BACKGROUND", {"package": CHROME_APP_KEY}),
            ]
        ]
    )
    await session.commit()


async def test_builds_a_clean_context_from_real_data_and_passes_the_privacy_gate():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _seed_chrome_session(session, user, device)
        await recompute_day(session, user, LOCAL_DATE)

        category_key_to_id = await ensure_system_categories(session, user.id)
        goal = Goal(
            user_id=user.id,
            name="Limit browsing",
            priority=2,
            target_minutes_per_week=100,
            active_from=LOCAL_DATE - timedelta(days=30),
        )
        session.add(goal)
        await session.flush()
        session.add(
            GoalActivityMapping(
                goal_id=goal.id, category_id=category_key_to_id["browsing"], weight=1.0
            )
        )
        await session.commit()

        context = await build_ai_context_for_day(session, user, LOCAL_DATE)

        assert isinstance(context, AIContext)
        assert context.scope == "day"
        assert context.date == LOCAL_DATE.isoformat()
        assert context.totals.observed_minutes == 10  # 600s / 60

        assert len(context.categories) == 1
        assert context.categories[0].category == "Browsing"
        assert context.categories[0].minutes == 10

        assert len(context.top_attention) == 1
        assert context.top_attention[0].category == "Browsing"
        assert context.top_attention[0].bucket == "<15m"

        assert len(context.goals) == 1
        assert context.goals[0].name == "Limit browsing"
        assert context.goals[0].aligned_minutes_today == 6  # 10 min * 0.60 seed confidence

        assert context.patterns == []
        assert context.baselines.valid_days == 0

        # The real end-to-end guarantee: this real, DB-derived payload clears the actual gate.
        payload = await enforce_privacy_gate(
            session,
            user_id=user.id,
            context=context,
            actor="test",
            ai_share_app_names=False,
        )
        assert payload["categories"][0]["category"] == "Browsing"


async def test_a_day_with_no_activity_still_builds_a_valid_context():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, _device = await _make_user_and_device(session)
        await ensure_system_categories(session, user.id)

        context = await build_ai_context_for_day(session, user, LOCAL_DATE)

        assert context.categories == []
        assert context.top_attention == []
        assert context.goals == []
        assert context.focus.sessions == 0
