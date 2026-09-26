"""GET /v1/privacy/audit, GET /v1/privacy/preview/{date} — §12.2, §20.5."""

import uuid
from datetime import UTC, datetime, timedelta

from tests.factories import create_user_with_password
from timeos.ingest.service import day_window_utc

LOCAL_DATE = (datetime.now(UTC) - timedelta(days=1)).date()
DAY_START, _ = day_window_utc(LOCAL_DATE, "UTC", 4)


async def _login(client, password: str) -> str:
    resp = await client.post("/v1/auth/login", json={"password": password})
    assert resp.status_code == 204, resp.text
    return client.cookies["timeos_csrf"]


async def test_requires_authentication(client):
    resp = await client.get("/v1/privacy/audit")
    assert resp.status_code == 401

    resp = await client.get(f"/v1/privacy/preview/{LOCAL_DATE}")
    assert resp.status_code == 401


async def test_audit_starts_empty(client):
    _user_id, password = await create_user_with_password()
    await _login(client, password)
    resp = await client.get("/v1/privacy/audit")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_preview_on_an_empty_day_is_clean_and_writes_an_audit_row(client):
    _user_id, password = await create_user_with_password()
    await _login(client, password)

    resp = await client.get(f"/v1/privacy/preview/{LOCAL_DATE}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["date"] == LOCAL_DATE.isoformat()
    assert body["context"]["scope"] == "day"
    assert len(body["payload_sha256"]) == 64

    # §20.3: no UUIDs, no device identifiers, anywhere in the payload actually sent.
    raw_payload = str(body["context"])
    assert str(_user_id) not in raw_payload

    audit_resp = await client.get("/v1/privacy/audit")
    audit_rows = audit_resp.json()
    assert len(audit_rows) == 1
    assert audit_rows[0]["outcome"] == "allowed"
    assert audit_rows[0]["actor"] == "privacy_preview"
    assert audit_rows[0]["payload_sha256"] == body["payload_sha256"]


async def test_preview_reflects_real_activity(client):
    import timeos.db as db
    from timeos.jobs.pipeline import recompute_day
    from timeos.models.device import Device
    from timeos.models.raw_event import RawEvent
    from timeos.models.user import User

    user_id, password = await create_user_with_password()
    await _login(client, password)

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
        await recompute_day(session, user, LOCAL_DATE)

    resp = await client.get(f"/v1/privacy/preview/{LOCAL_DATE}")
    assert resp.status_code == 200, resp.text
    categories = resp.json()["context"]["categories"]
    assert any(c["category"] == "Browsing" for c in categories)
    # The raw package name must never appear in what's actually sent.
    assert "com.android.chrome" not in str(resp.json()["context"])
