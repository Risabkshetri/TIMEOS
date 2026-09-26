"""§15.4's correction loop, actually applied (Phase 6): timeos.jobs.apply_correction against a
real Postgres, exercising the full recompute_day -> correct -> (optionally) recompute_day again
chain so the interaction with the real classifier/pipeline is real, not mocked."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from timeos.ingest.service import day_window_utc
from timeos.jobs.apply_correction import (
    ActivityNotFoundError,
    UnknownCategoryError,
    apply_classification_correction,
)
from timeos.jobs.pipeline import recompute_day
from timeos.jobs.seed_categories import ensure_system_categories
from timeos.models.activity import Activity
from timeos.models.app_classification import AppClassification
from timeos.models.device import Device
from timeos.models.raw_event import RawEvent
from timeos.models.user import User
from timeos.models.user_feedback import UserFeedback

TODAY = (datetime.now(UTC) - timedelta(days=1)).date()
YESTERDAY = TODAY - timedelta(days=1)
CHROME_APP_KEY = "com.android.chrome"


def ev(device_id, user_id, seq, day_start, offset_s, type_, payload=None):
    return RawEvent(
        id=uuid.uuid4(),
        ts_utc=day_start + timedelta(seconds=offset_s),
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
        id=uuid.uuid4(), user_id=user.id, name="test-phone", platform="android", token_hash="x"
    )
    session.add(device)
    await session.flush()
    return user, device


async def _add_chrome_session(session, device, user, local_date, seq_start=1):
    day_start, _ = day_window_utc(local_date, "UTC", 4)
    session.add_all(
        [
            ev(device.id, user.id, seq_start, day_start, 0, "SCREEN_ON"),
            ev(
                device.id,
                user.id,
                seq_start + 1,
                day_start,
                5,
                "APP_FOREGROUND",
                {"package": CHROME_APP_KEY},
            ),
            ev(
                device.id,
                user.id,
                seq_start + 2,
                day_start,
                605,
                "APP_BACKGROUND",
                {"package": CHROME_APP_KEY},
            ),
        ]
    )
    await session.commit()


async def _sole_activity(session, user) -> Activity:
    rows = (
        (await session.execute(select(Activity).where(Activity.user_id == user.id)))
        .scalars()
        .all()
    )
    live = [row for row in rows if row.superseded_by is None]
    assert len(live) == 1
    return live[0]


async def test_correction_creates_a_new_activity_row_and_preserves_history():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _add_chrome_session(session, device, user, TODAY)
        await recompute_day(session, user, TODAY)

        category_key_to_id = await ensure_system_categories(session, user.id)
        old_activity = await _sole_activity(session, user)
        assert old_activity.classification_source == "seed"

        result = await apply_classification_correction(
            session,
            user,
            activity_id=old_activity.id,
            corrected_category_key="development",
            apply_as_rule=False,
            apply_retroactively=False,
        )

        assert result.new_activity_id != old_activity.id

        refreshed_old = await session.get(Activity, old_activity.id)
        assert refreshed_old.superseded_by == result.new_activity_id
        # The old row's own fields are untouched — history preserved, not mutated.
        assert refreshed_old.category_id != category_key_to_id["development"]

        new_activity = await session.get(Activity, result.new_activity_id)
        assert new_activity.category_id == category_key_to_id["development"]
        assert new_activity.classification_source == "user"
        assert float(new_activity.confidence) == 1.0
        assert new_activity.start_ts == refreshed_old.start_ts
        assert new_activity.end_ts == refreshed_old.end_ts
        assert new_activity.source_session_ids == refreshed_old.source_session_ids

        feedback_rows = (
            (
                await session.execute(
                    select(UserFeedback).where(UserFeedback.target_id == old_activity.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(feedback_rows) == 1
        assert feedback_rows[0].applied_at is not None


async def test_correction_without_apply_as_rule_records_a_learned_prior():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _add_chrome_session(session, device, user, TODAY)
        await recompute_day(session, user, TODAY)
        old_activity = await _sole_activity(session, user)

        result = await apply_classification_correction(
            session,
            user,
            activity_id=old_activity.id,
            corrected_category_key="development",
            apply_as_rule=False,
            apply_retroactively=False,
        )

        assert result.app_classification_source == "learned"
        assert result.app_classification_sample_count == 1

        row = await session.get(AppClassification, (user.id, CHROME_APP_KEY))
        assert row.source == "learned"
        assert row.sample_count == 1


async def test_correction_with_apply_as_rule_sets_a_terminal_user_rule():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _add_chrome_session(session, device, user, TODAY)
        await recompute_day(session, user, TODAY)
        old_activity = await _sole_activity(session, user)

        result = await apply_classification_correction(
            session,
            user,
            activity_id=old_activity.id,
            corrected_category_key="development",
            apply_as_rule=True,
            apply_retroactively=False,
        )

        assert result.app_classification_source == "user"
        assert result.app_classification_confidence == 1.0

        row = await session.get(AppClassification, (user.id, CHROME_APP_KEY))
        assert row.source == "user"


async def test_unknown_category_key_is_rejected():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _add_chrome_session(session, device, user, TODAY)
        await recompute_day(session, user, TODAY)
        old_activity = await _sole_activity(session, user)

        with pytest.raises(UnknownCategoryError):
            await apply_classification_correction(
                session,
                user,
                activity_id=old_activity.id,
                corrected_category_key="not-a-real-category",
                apply_as_rule=False,
                apply_retroactively=False,
            )


async def test_correcting_a_nonexistent_activity_is_rejected():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, _device = await _make_user_and_device(session)
        await ensure_system_categories(session, user.id)

        with pytest.raises(ActivityNotFoundError):
            await apply_classification_correction(
                session,
                user,
                activity_id=uuid.uuid4(),
                corrected_category_key="development",
                apply_as_rule=False,
                apply_retroactively=False,
            )


async def test_apply_retroactively_recomputes_other_days_but_never_the_corrected_day():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _add_chrome_session(session, device, user, YESTERDAY, seq_start=1)
        await _add_chrome_session(session, device, user, TODAY, seq_start=101)
        await recompute_day(session, user, YESTERDAY)
        await recompute_day(session, user, TODAY)

        category_key_to_id = await ensure_system_categories(session, user.id)

        today_start, today_end = day_window_utc(TODAY, "UTC", 4)
        live_activities = (
            (
                await session.execute(
                    select(Activity).where(
                        Activity.user_id == user.id, Activity.superseded_by.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(live_activities) == 2
        today_activity = next(
            a for a in live_activities if today_start <= a.start_ts < today_end
        )

        result = await apply_classification_correction(
            session,
            user,
            activity_id=today_activity.id,
            corrected_category_key="development",
            apply_as_rule=True,  # so the retroactive recompute's classify_session sees an L0 rule
            apply_retroactively=True,
        )

        assert result.retroactively_recomputed_dates == [YESTERDAY]

        # The just-corrected day's activity is untouched by the retroactive recompute — still
        # exactly the manually-corrected row, not reverted or duplicated.
        still_live = (
            (
                await session.execute(
                    select(Activity).where(
                        Activity.user_id == user.id, Activity.superseded_by.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert result.new_activity_id in {a.id for a in still_live}

        # Yesterday's activity picked up the new L0 rule via the real recompute.
        yesterday_start, yesterday_end = day_window_utc(YESTERDAY, "UTC", 4)
        yesterday_activity = next(
            a for a in still_live if yesterday_start <= a.start_ts < yesterday_end
        )
        assert yesterday_activity.category_id == category_key_to_id["development"]
        assert yesterday_activity.classification_source == "user"
