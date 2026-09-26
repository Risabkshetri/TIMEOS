"""GET/POST/PATCH /v1/goals — §12.2's Goal CRUD."""

import uuid
from datetime import date

from tests.factories import create_user_with_password

TODAY = date(2026, 9, 20)


async def _login(client, password: str) -> str:
    resp = await client.post("/v1/auth/login", json={"password": password})
    assert resp.status_code == 204, resp.text
    return client.cookies["timeos_csrf"]


def _create_payload(**overrides) -> dict:
    payload = {
        "name": "Ship TimeOS",
        "priority": 1,
        "target_minutes_per_week": 600,
        "target_behavior": "Deep, uninterrupted engineering work",
        "active_from": TODAY.isoformat(),
        "mappings": [],
    }
    payload.update(overrides)
    return payload


async def test_requires_authentication(client):
    resp = await client.post("/v1/goals", json=_create_payload())
    assert resp.status_code == 401

    resp = await client.get("/v1/goals")
    assert resp.status_code == 401


async def test_create_rejected_without_csrf(client):
    _user_id, password = await create_user_with_password()
    await _login(client, password)
    resp = await client.post("/v1/goals", json=_create_payload())
    assert resp.status_code == 403


async def test_create_and_list_a_goal(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.post(
        "/v1/goals", json=_create_payload(), headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Ship TimeOS"
    assert body["archived"] is False
    assert body["mappings"] == []

    resp = await client.get("/v1/goals")
    assert resp.status_code == 200
    goals = resp.json()
    assert len(goals) == 1
    assert goals[0]["id"] == body["id"]


async def test_name_over_60_chars_is_rejected(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.post(
        "/v1/goals",
        json=_create_payload(name="x" * 61),
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 422


async def test_mapping_must_target_exactly_one_of_category_or_app(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.post(
        "/v1/goals",
        json=_create_payload(mappings=[{"category_id": None, "app_key": None, "weight": 1.0}]),
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/v1/goals",
        json=_create_payload(
            mappings=[
                {
                    "category_id": str(uuid.uuid4()),
                    "app_key": "com.example.app",
                    "weight": 1.0,
                }
            ]
        ),
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 422


async def test_create_with_app_key_mapping(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.post(
        "/v1/goals",
        json=_create_payload(
            mappings=[{"category_id": None, "app_key": "com.example.ide", "weight": 0.8}]
        ),
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 201, resp.text
    mappings = resp.json()["mappings"]
    assert len(mappings) == 1
    assert mappings[0]["app_key"] == "com.example.ide"
    assert mappings[0]["weight"] == 0.8


async def test_unknown_category_id_in_mapping_is_rejected(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.post(
        "/v1/goals",
        json=_create_payload(
            mappings=[{"category_id": str(uuid.uuid4()), "app_key": None, "weight": 1.0}]
        ),
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 422


async def test_archived_goals_excluded_from_default_list_but_included_when_requested(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    created = (
        await client.post(
            "/v1/goals", json=_create_payload(), headers={"X-CSRF-Token": csrf_token}
        )
    ).json()

    resp = await client.patch(
        f"/v1/goals/{created['id']}",
        json={"archived": True},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["archived"] is True

    resp = await client.get("/v1/goals")
    assert resp.json() == []

    resp = await client.get("/v1/goals", params={"include_archived": True})
    assert len(resp.json()) == 1
    assert resp.json()[0]["archived"] is True


async def test_patch_can_replace_mappings(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    created = (
        await client.post(
            "/v1/goals",
            json=_create_payload(
                mappings=[{"category_id": None, "app_key": "com.example.ide", "weight": 1.0}]
            ),
            headers={"X-CSRF-Token": csrf_token},
        )
    ).json()

    resp = await client.patch(
        f"/v1/goals/{created['id']}",
        json={
            "mappings": [
                {"category_id": None, "app_key": "com.example.editor", "weight": 0.5}
            ]
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 200, resp.text
    mappings = resp.json()["mappings"]
    assert len(mappings) == 1
    assert mappings[0]["app_key"] == "com.example.editor"


async def test_patching_a_nonexistent_goal_is_a_404(client):
    # The personal-use system has exactly one user (§13, mirroring timeos/api/auth.py's own
    # note), so there's no cross-user ownership scenario to test here — only that a goal id
    # that simply doesn't exist for THIS user 404s rather than 500ing or silently no-opping.
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.patch(
        f"/v1/goals/{uuid.uuid4()}",
        json={"archived": True},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 404
