"""GET /v1/goals/{id}/alignment — §18's Goal Alignment Engine, wired to a real endpoint over
real recomputed activities (not mocked): exercises timeos.analytics.goals.compute_alignment
through the same DB path the dashboard will use."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.factories import create_user_with_password
from timeos.ingest.service import day_window_utc
from timeos.jobs.pipeline import recompute_day
from timeos.models.device import Device
from timeos.models.raw_event import RawEvent
from timeos.models.user import User

LOCAL_DATE = (datetime.now(UTC) - timedelta(days=1)).date()
DAY_START, _ = day_window_utc(LOCAL_DATE, "UTC", 4)
CHROME_APP_KEY = "com.android.chrome"


async def _login(client, password: str) -> str:
    resp = await client.post("/v1/auth/login", json={"password": password})
    assert resp.status_code == 204, resp.text
    return client.cookies["timeos_csrf"]


async def _seed_chrome_activity(user_id: uuid.UUID) -> None:
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
                    (2, 5, "APP_FOREGROUND", {"package": CHROME_APP_KEY}),
                    (3, 605, "APP_BACKGROUND", {"package": CHROME_APP_KEY}),
                ]
            ]
        )
        await session.commit()
        await recompute_day(session, user, LOCAL_DATE)


async def _create_goal(client, csrf_token: str, **overrides) -> dict:
    payload = {
        "name": "Limit browsing",
        "priority": 3,
        "target_minutes_per_week": 60,
        "active_from": LOCAL_DATE.isoformat(),
        "mappings": [{"category_id": None, "app_key": CHROME_APP_KEY, "weight": 1.0}],
    }
    payload.update(overrides)
    resp = await client.post("/v1/goals", json=payload, headers={"X-CSRF-Token": csrf_token})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_requires_authentication(client):
    resp = await client.get(f"/v1/goals/{uuid.uuid4()}/alignment")
    assert resp.status_code == 401


async def test_unknown_goal_is_a_404(client):
    _user_id, password = await create_user_with_password()
    await _login(client, password)
    resp = await client.get(f"/v1/goals/{uuid.uuid4()}/alignment")
    assert resp.status_code == 404


async def test_invalid_window_is_rejected(client):
    user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)
    goal = await _create_goal(client, csrf_token)

    resp = await client.get(f"/v1/goals/{goal['id']}/alignment", params={"window": 14})
    assert resp.status_code == 422


async def test_alignment_reflects_real_recomputed_activity(client):
    user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)
    await _seed_chrome_activity(user_id)
    goal = await _create_goal(client, csrf_token)

    resp = await client.get(f"/v1/goals/{goal['id']}/alignment", params={"window": 7})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["label"] == "INFERENCE"
    assert body["window_days"] == 7
    assert body["target_minutes"] == pytest.approx(60.0)
    # 600s chrome session * confidence 0.60 (seed catalogue) * weight 1.0 / 60 = 6.0 minutes.
    assert body["aligned_minutes"] == pytest.approx(6.0, abs=0.01)
    assert body["range_low_minutes"] <= body["aligned_minutes"] <= body["range_high_minutes"]
    assert 0.0 <= body["coverage_ratio"] <= 1.0
    assert body["attainment_ratio"] == pytest.approx(6.0 / 60.0, abs=0.001)


async def test_goal_with_no_matching_activity_reports_zero_not_a_crash(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)
    goal = await _create_goal(
        client,
        csrf_token,
        mappings=[{"category_id": None, "app_key": "com.example.never-used", "weight": 1.0}],
    )

    resp = await client.get(f"/v1/goals/{goal['id']}/alignment", params={"window": 7})
    assert resp.status_code == 200, resp.text
    assert resp.json()["aligned_minutes"] == 0.0
