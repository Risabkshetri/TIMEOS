"""§25 System Health view: /v1/health/collectors."""

import uuid

from tests.factories import create_user_with_password


async def _login(client, password: str) -> None:
    resp = await client.post("/v1/auth/login", json={"password": password})
    assert resp.status_code == 204, resp.text


async def test_requires_authentication(client):
    resp = await client.get("/v1/health/collectors")
    assert resp.status_code == 401


async def test_no_devices_yet_returns_an_empty_list(client):
    _user_id, password = await create_user_with_password()
    await _login(client, password)
    resp = await client.get("/v1/health/collectors")
    assert resp.status_code == 200
    assert resp.json()["collectors"] == []


async def test_reports_an_enrolled_devices_status(client):
    import timeos.db as db
    from timeos.models.device import Device

    user_id, password = await create_user_with_password()
    device_id = uuid.uuid4()
    async with db.async_session_factory() as session:
        session.add(
            Device(
                id=device_id,
                user_id=user_id,
                name="Test Phone",
                platform="android",
                token_hash="irrelevant",
            )
        )
        await session.commit()

    await _login(client, password)
    resp = await client.get("/v1/health/collectors")
    assert resp.status_code == 200
    collectors = resp.json()["collectors"]
    assert len(collectors) == 1
    assert collectors[0]["device_id"] == str(device_id)
    assert collectors[0]["name"] == "Test Phone"
    assert collectors[0]["revoked"] is False
    assert collectors[0]["rejected_batch_count"] == 0
