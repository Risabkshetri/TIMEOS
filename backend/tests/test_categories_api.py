"""GET/POST/PATCH /v1/categories — §38 Phase 6 output "custom taxonomy"."""

import uuid

from tests.factories import create_user_with_password
from timeos.jobs.seed_categories import ensure_system_categories


async def _login(client, password: str) -> str:
    resp = await client.post("/v1/auth/login", json={"password": password})
    assert resp.status_code == 204, resp.text
    return client.cookies["timeos_csrf"]


async def test_requires_authentication(client):
    resp = await client.get("/v1/categories")
    assert resp.status_code == 401


async def test_list_includes_seeded_system_categories(client):
    user_id, password = await create_user_with_password()
    await _login(client, password)

    import timeos.db as db

    async with db.async_session_factory() as session:
        await ensure_system_categories(session, user_id)

    resp = await client.get("/v1/categories")
    assert resp.status_code == 200
    keys = {row["key"] for row in resp.json()}
    assert "unknown" in keys
    assert any(row["key"] == "unknown" and row["is_system"] for row in resp.json())


async def test_create_a_custom_category(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.post(
        "/v1/categories",
        json={"key": "side_project", "label": "Side Project"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_system"] is False
    assert body["label"] == "Side Project"


async def test_duplicate_key_is_a_conflict(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    payload = {"key": "side_project", "label": "Side Project"}
    resp = await client.post(
        "/v1/categories", json=payload, headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 201

    resp = await client.post(
        "/v1/categories", json=payload, headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 409


async def test_rename_a_custom_category(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    created = (
        await client.post(
            "/v1/categories",
            json={"key": "side_project", "label": "Side Project"},
            headers={"X-CSRF-Token": csrf_token},
        )
    ).json()

    resp = await client.patch(
        f"/v1/categories/{created['id']}",
        json={"label": "Side Hustle"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["label"] == "Side Hustle"


async def test_system_categories_are_immutable(client):
    user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    import timeos.db as db

    async with db.async_session_factory() as session:
        key_to_id = await ensure_system_categories(session, user_id)

    resp = await client.patch(
        f"/v1/categories/{key_to_id['unknown']}",
        json={"label": "Renamed"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 403


async def test_updating_a_nonexistent_category_is_a_404(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.patch(
        f"/v1/categories/{uuid.uuid4()}",
        json={"label": "Renamed"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 404
