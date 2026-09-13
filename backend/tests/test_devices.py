"""Enrollment and token rotation (§12.2, §28, §38 Phase 3)."""

import uuid

from tests.factories import create_user_with_enrollment_code


def enroll_payload(device_id: uuid.UUID, code: str) -> dict:
    return {
        "enrollment_code": code,
        "device_id": str(device_id),
        "name": "Test Phone",
        "platform": "android",
        "app_version": "0.3.0",
        "os_version": "16",
    }


class TestEnroll:
    async def test_successful_enroll_returns_token(self, client):
        _, code = await create_user_with_enrollment_code()
        device_id = uuid.uuid4()
        resp = await client.post("/v1/devices/enroll", json=enroll_payload(device_id, code))
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["device_id"] == str(device_id)
        assert body["token"].startswith(str(device_id))

    async def test_invalid_code_is_rejected(self, client):
        device_id = uuid.uuid4()
        resp = await client.post("/v1/devices/enroll", json=enroll_payload(device_id, "NOTREAL1"))
        assert resp.status_code == 400

    async def test_expired_code_is_rejected(self, client):
        _, code = await create_user_with_enrollment_code(ttl_minutes=-1)  # already expired
        device_id = uuid.uuid4()
        resp = await client.post("/v1/devices/enroll", json=enroll_payload(device_id, code))
        assert resp.status_code == 400

    async def test_code_is_single_use(self, client):
        _, code = await create_user_with_enrollment_code()
        first_device = uuid.uuid4()
        second_device = uuid.uuid4()

        first = await client.post("/v1/devices/enroll", json=enroll_payload(first_device, code))
        assert first.status_code == 201

        second = await client.post("/v1/devices/enroll", json=enroll_payload(second_device, code))
        assert second.status_code == 400

    async def test_reenrolling_an_active_device_is_rejected(self, client):
        _, code1 = await create_user_with_enrollment_code()
        device_id = uuid.uuid4()
        await client.post("/v1/devices/enroll", json=enroll_payload(device_id, code1))

        _, code2 = await create_user_with_enrollment_code()
        resp = await client.post("/v1/devices/enroll", json=enroll_payload(device_id, code2))
        assert resp.status_code == 409

    async def test_extra_field_is_rejected(self, client):
        _, code = await create_user_with_enrollment_code()
        payload = enroll_payload(uuid.uuid4(), code)
        payload["unexpected_field"] = "should not be allowed"
        resp = await client.post("/v1/devices/enroll", json=payload)
        assert resp.status_code == 422


class TestTokenRotation:
    async def test_rotate_requires_valid_auth(self, client):
        resp = await client.post("/v1/devices/token/rotate", json={})
        assert resp.status_code == 401

    async def test_rotate_issues_a_working_new_token(self, client):
        _, code = await create_user_with_enrollment_code()
        device_id = uuid.uuid4()
        enroll_resp = await client.post("/v1/devices/enroll", json=enroll_payload(device_id, code))
        old_token = enroll_resp.json()["token"]

        rotate_resp = await client.post(
            "/v1/devices/token/rotate",
            headers={"Authorization": f"Bearer {old_token}"},
            json={},
        )
        assert rotate_resp.status_code == 200
        new_token = rotate_resp.json()["token"]
        assert new_token != old_token

        # the new token authenticates successfully
        state = await client.get(
            "/v1/sync/state", headers={"Authorization": f"Bearer {new_token}"}
        )
        assert state.status_code == 200

    async def test_old_token_still_works_immediately_after_rotation(self, client):
        """§28: the previous token is honored for 24h post-rotation, so a client that hasn't
        yet received the new token isn't locked out mid-rotation."""
        _, code = await create_user_with_enrollment_code()
        device_id = uuid.uuid4()
        enroll_resp = await client.post("/v1/devices/enroll", json=enroll_payload(device_id, code))
        old_token = enroll_resp.json()["token"]

        await client.post(
            "/v1/devices/token/rotate",
            headers={"Authorization": f"Bearer {old_token}"},
            json={},
        )

        state = await client.get(
            "/v1/sync/state", headers={"Authorization": f"Bearer {old_token}"}
        )
        assert state.status_code == 200
