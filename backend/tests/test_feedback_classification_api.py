"""POST /v1/feedback/classification — Phase 6's real correction-application endpoint. Auth/CSRF
behaviour mirrors tests/test_feedback.py; the correction logic itself is covered end-to-end
against real Postgres in tests/test_apply_correction.py."""

import uuid
from datetime import UTC, datetime, timedelta

from tests.factories import create_user_with_password
from timeos.ingest.service import day_window_utc
from timeos.jobs.pipeline import recompute_day
from timeos.jobs.seed_categories import ensure_system_categories
from timeos.models.activity import Activity
from timeos.models.device import Device
from timeos.models.raw_event import RawEvent
from timeos.models.user import User

LOCAL_DATE = (datetime.now(UTC) - timedelta(days=1)).date()
DAY_START, _ = day_window_utc(LOCAL_DATE, "UTC", 4)


async def _login(client, password: str) -> str:
    resp = await client.post("/v1/auth/login", json={"password": password})
    assert resp.status_code == 204, resp.text
    return client.cookies["timeos_csrf"]


async def _seed_one_chrome_activity(user_id: uuid.UUID) -> uuid.UUID:
    import timeos.db as db

    async with db.async_session_factory() as session:
        user = await session.get(User, user_id)
        device = Device(
            id=uuid.uuid4(), user_id=user.id, name="phone", platform="android", token_hash="x"
        )
        session.add(device)
        await session.flush()
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
                    (2, 5, "APP_FOREGROUND", {"package": "com.android.chrome"}),
                    (3, 605, "APP_BACKGROUND", {"package": "com.android.chrome"}),
                ]
            ]
        )
        await session.commit()
        await ensure_system_categories(session, user.id)
        await recompute_day(session, user, LOCAL_DATE)

        from sqlalchemy import select

        activity = (
            await session.execute(
                select(Activity).where(
                    Activity.user_id == user.id, Activity.superseded_by.is_(None)
                )
            )
        ).scalar_one()
        return activity.id


def _payload(activity_id: uuid.UUID) -> dict:
    return {
        "activity_id": str(activity_id),
        "corrected_category_key": "development",
        "apply_as_rule": False,
        "apply_retroactively": False,
    }


async def test_requires_authentication(client):
    resp = await client.post(
        "/v1/feedback/classification", json=_payload(uuid.uuid4())
    )
    assert resp.status_code == 401


async def test_rejected_without_a_csrf_header(client):
    user_id, password = await create_user_with_password()
    await _login(client, password)
    resp = await client.post("/v1/feedback/classification", json=_payload(uuid.uuid4()))
    assert resp.status_code == 403


async def test_unknown_activity_is_a_404(client):
    user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)
    resp = await client.post(
        "/v1/feedback/classification",
        json=_payload(uuid.uuid4()),
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 404


async def test_unknown_category_key_is_a_422(client):
    user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)
    activity_id = await _seed_one_chrome_activity(user_id)

    payload = _payload(activity_id)
    payload["corrected_category_key"] = "not-a-real-category"
    resp = await client.post(
        "/v1/feedback/classification", json=payload, headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 422


async def test_accepted_correction_applies_and_returns_the_new_activity(client):
    user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)
    activity_id = await _seed_one_chrome_activity(user_id)

    resp = await client.post(
        "/v1/feedback/classification",
        json=_payload(activity_id),
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["new_activity_id"] != str(activity_id)
    assert body["app_classification_source"] == "learned"
    assert body["retroactively_recomputed_dates"] == []
