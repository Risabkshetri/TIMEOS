"""GET /v1/insights/{date}, POST /v1/ai/analyze/{date} — §12.2, Phase 8."""

from datetime import UTC, datetime, timedelta

from tests.factories import create_user_with_password

LOCAL_DATE = (datetime.now(UTC) - timedelta(days=1)).date()


async def _login(client, password: str) -> str:
    resp = await client.post("/v1/auth/login", json={"password": password})
    assert resp.status_code == 204, resp.text
    return client.cookies["timeos_csrf"]


async def test_requires_authentication(client):
    resp = await client.get(f"/v1/insights/{LOCAL_DATE}")
    assert resp.status_code == 401

    resp = await client.post(f"/v1/ai/analyze/{LOCAL_DATE}")
    assert resp.status_code == 401


async def test_get_insights_404s_when_nothing_exists_yet(client):
    _user_id, password = await create_user_with_password()
    await _login(client, password)

    resp = await client.get(f"/v1/insights/{LOCAL_DATE}")
    assert resp.status_code == 404


async def test_post_analyze_rejected_without_csrf(client):
    _user_id, password = await create_user_with_password()
    await _login(client, password)

    resp = await client.post(f"/v1/ai/analyze/{LOCAL_DATE}")
    assert resp.status_code == 403


async def test_post_analyze_creates_an_analysis_with_the_zero_config_null_provider(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    resp = await client.post(
        f"/v1/ai/analyze/{LOCAL_DATE}", headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["provider"] == "null"
    assert body["insights"] == []

    # And it's now retrievable via GET.
    resp = await client.get(f"/v1/insights/{LOCAL_DATE}")
    assert resp.status_code == 200
    assert resp.json()["id"] == body["id"]


async def test_manual_trigger_is_rate_limited_at_5_per_day(client):
    _user_id, password = await create_user_with_password()
    csrf_token = await _login(client, password)

    for i in range(5):
        target_date = LOCAL_DATE - timedelta(days=i)
        resp = await client.post(
            f"/v1/ai/analyze/{target_date}", headers={"X-CSRF-Token": csrf_token}
        )
        assert resp.status_code == 201, resp.text

    sixth_date = LOCAL_DATE - timedelta(days=5)
    resp = await client.post(
        f"/v1/ai/analyze/{sixth_date}", headers={"X-CSRF-Token": csrf_token}
    )
    assert resp.status_code == 429
