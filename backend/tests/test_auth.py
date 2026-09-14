"""§25/§28 dashboard login/logout."""

from tests.factories import create_user_with_password


class TestLogin:
    async def test_correct_password_succeeds_and_sets_cookies(self, client):
        _, password = await create_user_with_password()
        resp = await client.post("/v1/auth/login", json={"password": password})
        assert resp.status_code == 204
        assert "timeos_session" in resp.cookies
        assert "timeos_csrf" in resp.cookies

    async def test_wrong_password_is_rejected(self, client):
        await create_user_with_password(password="the-real-password")
        resp = await client.post("/v1/auth/login", json={"password": "wrong-password"})
        assert resp.status_code == 401
        assert "timeos_session" not in resp.cookies

    async def test_login_before_any_password_is_set_is_rejected_not_500(self, client):
        # No user exists at all yet — must not crash or leak "no account exists".
        resp = await client.post("/v1/auth/login", json={"password": "anything"})
        assert resp.status_code == 401

    async def test_session_cookie_is_httponly_and_samesite_strict(self, client):
        _, password = await create_user_with_password()
        resp = await client.post("/v1/auth/login", json={"password": password})
        set_cookie_headers = resp.headers.get_list("set-cookie")
        session_header = next(h for h in set_cookie_headers if h.startswith("timeos_session="))
        assert "HttpOnly" in session_header
        assert "SameSite=strict" in session_header

    async def test_csrf_cookie_is_not_httponly(self, client):
        _, password = await create_user_with_password()
        resp = await client.post("/v1/auth/login", json={"password": password})
        set_cookie_headers = resp.headers.get_list("set-cookie")
        csrf_header = next(h for h in set_cookie_headers if h.startswith("timeos_csrf="))
        assert "HttpOnly" not in csrf_header


class TestLogout:
    async def test_logout_requires_authentication(self, client):
        resp = await client.post("/v1/auth/logout")
        assert resp.status_code == 401

    async def test_logout_clears_the_session(self, client):
        _, password = await create_user_with_password()
        login_resp = await client.post("/v1/auth/login", json={"password": password})
        assert login_resp.status_code == 204, login_resp.text

        resp = await client.post("/v1/auth/logout")
        assert resp.status_code == 204

        # A request depending on the (now-cleared) session cookie must be rejected.
        followup = await client.get("/v1/health/collectors")
        assert followup.status_code == 401


class TestRateLimit:
    async def test_exceeding_five_per_minute_returns_429(self, client):
        _, password = await create_user_with_password()
        for _ in range(5):
            await client.post("/v1/auth/login", json={"password": "wrong"})
        resp = await client.post("/v1/auth/login", json={"password": password})
        assert resp.status_code == 429
