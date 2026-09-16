"""§25 /v1/days/{date} and /v1/days/{date}/timeline."""

from datetime import UTC, date, datetime, timedelta

from tests.factories import create_user_with_password


async def _login(client, password: str) -> None:
    resp = await client.post("/v1/auth/login", json={"password": password})
    assert resp.status_code == 204, resp.text


class TestAuthRequired:
    async def test_get_day_without_a_session_is_rejected(self, client):
        resp = await client.get(f"/v1/days/{date.today().isoformat()}")
        assert resp.status_code == 401

    async def test_get_timeline_without_a_session_is_rejected(self, client):
        resp = await client.get(f"/v1/days/{date.today().isoformat()}/timeline")
        assert resp.status_code == 401

    async def test_get_focus_without_a_session_is_rejected(self, client):
        resp = await client.get(f"/v1/days/{date.today().isoformat()}/focus")
        assert resp.status_code == 401


class TestGetDay:
    async def test_a_day_with_no_events_computes_a_valid_all_unobserved_response(self, client):
        _user_id, password = await create_user_with_password()
        await _login(client, password)

        # A day comfortably within raw_events' partition coverage but with zero real events —
        # must return a valid (if empty) result, not a crash, matching Phase 4's own failure case.
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()
        resp = await client.get(f"/v1/days/{target_date.isoformat()}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["metrics"]["local_date"] == target_date.isoformat()
        assert body["metrics"]["coverage_ratio"] == 0.0
        assert body["categories"] == []

    async def test_a_second_request_serves_the_cached_row_without_recomputing(self, client):
        # Not dirty (no new events arrived) -> _ensure_computed must return the cached row as-is
        # rather than recomputing, so `revised` stays False on both calls (a real recompute would
        # flip it to True — see the pipeline's own idempotency test for that behavior directly).
        _user_id, password = await create_user_with_password()
        await _login(client, password)
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()

        first = await client.get(f"/v1/days/{target_date.isoformat()}")
        second = await client.get(f"/v1/days/{target_date.isoformat()}")
        assert first.status_code == second.status_code == 200
        assert first.json()["metrics"]["screen_time_s"] == second.json()["metrics"]["screen_time_s"]
        assert first.json()["metrics"]["revised"] is False
        assert second.json()["metrics"]["revised"] is False


    async def test_a_dirty_day_is_recomputed_not_served_from_cache(self, client):
        import timeos.db as db
        from timeos.models.dirty_day import DirtyDay

        _user_id, password = await create_user_with_password()
        await _login(client, password)
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()

        first = await client.get(f"/v1/days/{target_date.isoformat()}")
        assert first.json()["metrics"]["revised"] is False

        async with db.async_session_factory() as session:
            session.add(DirtyDay(user_id=_user_id, local_date=target_date))
            await session.commit()

        second = await client.get(f"/v1/days/{target_date.isoformat()}")
        assert second.status_code == 200
        assert second.json()["metrics"]["revised"] is True  # a real recompute happened this time


class TestGetTimeline:
    async def test_a_day_with_no_devices_returns_an_empty_device_list(self, client):
        _user_id, password = await create_user_with_password()
        await _login(client, password)
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()

        resp = await client.get(f"/v1/days/{target_date.isoformat()}/timeline")
        assert resp.status_code == 200, resp.text
        assert resp.json()["devices"] == []


class TestGetFocus:
    async def test_a_day_with_no_focus_sessions_returns_an_empty_list(self, client):
        _user_id, password = await create_user_with_password()
        await _login(client, password)
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()

        resp = await client.get(f"/v1/days/{target_date.isoformat()}/focus")
        assert resp.status_code == 200, resp.text
        assert resp.json()["sessions"] == []

    async def test_a_real_focus_session_is_returned_with_its_category_label(self, client):
        import uuid

        import timeos.db as db
        from timeos.ingest.service import day_window_utc
        from timeos.models.device import Device
        from timeos.models.raw_event import RawEvent

        user_id, password = await create_user_with_password()
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()
        window_start, _window_end = day_window_utc(target_date, "UTC", 4)

        async with db.async_session_factory() as session:
            device = Device(
                id=uuid.uuid4(),
                user_id=user_id,
                name="Test Phone",
                platform="android",
                token_hash="irrelevant",
            )
            session.add(device)
            await session.flush()
            session.add_all(
                [
                    RawEvent(
                        id=uuid.uuid4(),
                        ts_utc=window_start,
                        device_id=device.id,
                        user_id=user_id,
                        seq=1,
                        tz_offset_min=0,
                        tz_id="UTC",
                        uptime_ms=0,
                        type="APP_FOREGROUND",
                        payload={"package": "com.android.chrome"},
                        schema_v=1,
                    ),
                    RawEvent(
                        id=uuid.uuid4(),
                        ts_utc=window_start + timedelta(minutes=20),
                        device_id=device.id,
                        user_id=user_id,
                        seq=2,
                        tz_offset_min=0,
                        tz_id="UTC",
                        uptime_ms=1_200_000,
                        type="APP_BACKGROUND",
                        payload={"package": "com.android.chrome"},
                        schema_v=1,
                    ),
                ]
            )
            await session.commit()

        await _login(client, password)
        resp = await client.get(f"/v1/days/{target_date.isoformat()}/focus")
        assert resp.status_code == 200, resp.text
        sessions = resp.json()["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["category_key"] == "browsing"
        assert sessions[0]["category_label"] == "Browsing"
        assert sessions[0]["duration_s"] == 20 * 60


class TestGetActivities:
    async def test_a_day_with_no_activities_returns_an_empty_list(self, client):
        _user_id, password = await create_user_with_password()
        await _login(client, password)
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()

        resp = await client.get(f"/v1/days/{target_date.isoformat()}/activities")
        assert resp.status_code == 200, resp.text
        assert resp.json()["activities"] == []

    async def test_a_real_activity_resolves_its_app_key_via_source_session_ids(self, client):
        import uuid

        import timeos.db as db
        from timeos.ingest.service import day_window_utc
        from timeos.models.device import Device
        from timeos.models.raw_event import RawEvent

        user_id, password = await create_user_with_password()
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()
        window_start, _window_end = day_window_utc(target_date, "UTC", 4)

        async with db.async_session_factory() as session:
            device = Device(
                id=uuid.uuid4(),
                user_id=user_id,
                name="Test Phone",
                platform="android",
                token_hash="irrelevant",
            )
            session.add(device)
            await session.flush()
            session.add_all(
                [
                    RawEvent(
                        id=uuid.uuid4(),
                        ts_utc=window_start,
                        device_id=device.id,
                        user_id=user_id,
                        seq=1,
                        tz_offset_min=0,
                        tz_id="UTC",
                        uptime_ms=0,
                        type="APP_FOREGROUND",
                        payload={"package": "com.android.chrome"},
                        schema_v=1,
                    ),
                    RawEvent(
                        id=uuid.uuid4(),
                        ts_utc=window_start + timedelta(minutes=5),
                        device_id=device.id,
                        user_id=user_id,
                        seq=2,
                        tz_offset_min=0,
                        tz_id="UTC",
                        uptime_ms=300_000,
                        type="APP_BACKGROUND",
                        payload={"package": "com.android.chrome"},
                        schema_v=1,
                    ),
                ]
            )
            await session.commit()

        await _login(client, password)
        resp = await client.get(f"/v1/days/{target_date.isoformat()}/activities")
        assert resp.status_code == 200, resp.text
        activities = resp.json()["activities"]
        assert len(activities) == 1
        assert activities[0]["category_key"] == "browsing"
        assert activities[0]["app_keys"] == ["com.android.chrome"]
        assert activities[0]["classification_source"] == "seed"
        uuid.UUID(activities[0]["id"])  # a real, parseable activity id
