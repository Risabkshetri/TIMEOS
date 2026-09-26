"""GET/PUT /v1/working-hours — §38 Phase 6 output "working hours"."""

from tests.factories import create_user_with_password


async def _login(client, password: str) -> str:
    resp = await client.post("/v1/auth/login", json={"password": password})
    assert resp.status_code == 204, resp.text
    return client.cookies["timeos_csrf"]


async def test_requires_authentication(client):
    resp = await client.get("/v1/working-hours")
    assert resp.status_code == 401


async def test_defaults_to_empty(client):
    _user_id, password = await create_user_with_password()
    await _login(client, password)
    resp = await client.get("/v1/working-hours")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_put_replaces_the_whole_week(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    entries = [
        {"weekday": weekday, "start_local": "09:00:00", "end_local": "17:00:00"}
        for weekday in range(5)
    ]
    resp = await client.put(
        "/v1/working-hours",
        json={"entries": entries},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 5

    resp = await client.get("/v1/working-hours")
    assert len(resp.json()) == 5

    # A second PUT with fewer days fully replaces the first — no leftover rows.
    resp = await client.put(
        "/v1/working-hours",
        json={"entries": [{"weekday": 0, "start_local": "08:00:00", "end_local": "12:00:00"}]},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 200
    resp = await client.get("/v1/working-hours")
    assert len(resp.json()) == 1
    assert resp.json()[0]["weekday"] == 0


async def test_start_must_be_before_end(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.put(
        "/v1/working-hours",
        json={"entries": [{"weekday": 0, "start_local": "17:00:00", "end_local": "09:00:00"}]},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 422


async def test_duplicate_weekday_is_rejected(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.put(
        "/v1/working-hours",
        json={
            "entries": [
                {"weekday": 0, "start_local": "09:00:00", "end_local": "17:00:00"},
                {"weekday": 0, "start_local": "18:00:00", "end_local": "20:00:00"},
            ]
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 422
