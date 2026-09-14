"""POST /v1/feedback — §15.4's correction affordance (Phase 5 stub) and §28's CSRF requirement."""

import uuid

from tests.factories import create_user_with_password


async def _login(client, password: str) -> str:
    resp = await client.post("/v1/auth/login", json={"password": password})
    assert resp.status_code == 204, resp.text
    return client.cookies["timeos_csrf"]


def _payload() -> dict:
    return {
        "target_type": "activity",
        "target_id": str(uuid.uuid4()),
        "correction": {"category": "work"},
    }


async def test_requires_authentication(client):
    resp = await client.post("/v1/feedback", json=_payload())
    assert resp.status_code == 401


async def test_rejected_without_a_csrf_header(client):
    _user_id, password = await create_user_with_password()
    await _login(client, password)
    resp = await client.post("/v1/feedback", json=_payload())
    assert resp.status_code == 403


async def test_rejected_with_a_mismatched_csrf_header(client):
    _user_id, password = await create_user_with_password()
    await _login(client, password)
    resp = await client.post(
        "/v1/feedback", json=_payload(), headers={"X-CSRF-Token": "not-the-real-token"}
    )
    assert resp.status_code == 403


async def test_accepted_with_a_matching_csrf_header(client):
    import timeos.db as db
    from timeos.models.user_feedback import UserFeedback

    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.post(
        "/v1/feedback", json=_payload(), headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 201, resp.text
    feedback_id = uuid.UUID(resp.json()["id"])

    async with db.async_session_factory() as session:
        row = await session.get(UserFeedback, feedback_id)
        assert row is not None
        assert row.target_type == "activity"
        assert row.applied_at is None  # Phase 6's job, not Phase 5's
