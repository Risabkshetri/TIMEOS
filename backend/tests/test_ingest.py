"""Batch ingestion: idempotency, validation, gap detection, auth, rate limiting.
See docs/TIMEOS_ENGINEERING_SPEC.md §12.3, §38 Phase 3."""

import gzip
import json
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

import timeos.db as db
from tests.factories import create_user_with_enrollment_code
from timeos.api.deps import ingest_rate_limiter
from timeos.models.device import Device
from timeos.models.seq_gap import SeqGap

NOW_MS = int(datetime.now(UTC).timestamp() * 1000)


def make_event(
    device_id: uuid.UUID,
    seq: int,
    ts_utc_millis: int,
    event_type: str = "APP_FOREGROUND",
) -> dict:
    has_package = event_type in ("APP_FOREGROUND", "APP_BACKGROUND")
    payload = {"package": "com.example.app"} if has_package else {}
    return {
        "event_id": str(uuid.uuid4()),
        "device_id": str(device_id),
        "seq": seq,
        "ts_utc": ts_utc_millis,
        "tz_offset_min": 330,
        "tz_id": "Asia/Kolkata",
        "clock_flags": [],
        "uptime_ms": 1_000_000 + seq,
        "type": event_type,
        "source": "android",
        "payload": payload,
        "schema_v": 1,
    }


async def enroll_device(client, device_id: uuid.UUID | None = None) -> tuple[uuid.UUID, str]:
    _, code = await create_user_with_enrollment_code()
    device_id = device_id or uuid.uuid4()
    resp = await client.post(
        "/v1/devices/enroll",
        json={
            "enrollment_code": code,
            "device_id": str(device_id),
            "name": "Test Device",
            "platform": "android",
            "app_version": "0.3.0",
            "os_version": "16",
        },
    )
    assert resp.status_code == 201, resp.text
    return device_id, resp.json()["token"]


class TestGzipRequestBody:
    async def test_gzip_compressed_batch_is_accepted(self, client):
        """The real Android client always sends Content-Encoding: gzip
        (android/core/sync/OkHttpIngestApiClient.kt) — this reproduces that exact shape rather
        than relying on httpx's plain `json=` helper, which never compresses."""
        device_id, token = await enroll_device(client)
        payload = {
            "batch_id": str(uuid.uuid4()),
            "device_id": str(device_id),
            "seq_from": 0,
            "seq_to": 0,
            "events": [make_event(device_id, 0, NOW_MS)],
        }
        compressed = gzip.compress(json.dumps(payload).encode("utf-8"))

        resp = await client.post(
            "/v1/ingest/batch",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
            },
            content=compressed,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["accepted"] == 1


class TestSuccessfulIngest:
    async def test_batch_is_accepted_and_events_are_stored(self, client):
        device_id, token = await enroll_device(client)
        events = [make_event(device_id, i, NOW_MS + i * 1000) for i in range(3)]
        resp = await client.post(
            "/v1/ingest/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(device_id),
                "seq_from": 0,
                "seq_to": 2,
                "events": events,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {
            "accepted": 3,
            "duplicates": 0,
            "batch_id": body["batch_id"],
            "server_seq": 2,
            "next_expected_seq": 3,
        }

    async def test_sync_state_reflects_last_seq(self, client):
        device_id, token = await enroll_device(client)
        headers = {"Authorization": f"Bearer {token}"}
        await client.post(
            "/v1/ingest/batch",
            headers=headers,
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(device_id),
                "seq_from": 0,
                "seq_to": 4,
                "events": [make_event(device_id, i, NOW_MS + i * 1000) for i in range(5)],
            },
        )
        state = await client.get("/v1/sync/state", headers=headers)
        assert state.status_code == 200
        assert state.json() == {"last_seq": 4, "next_expected_seq": 5}


class TestIdempotentReplay:
    async def test_duplicate_batch_id_returns_the_identical_stored_response(self, client):
        device_id, token = await enroll_device(client)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "batch_id": str(uuid.uuid4()),
            "device_id": str(device_id),
            "seq_from": 0,
            "seq_to": 0,
            "events": [make_event(device_id, 0, NOW_MS)],
        }
        first = await client.post("/v1/ingest/batch", headers=headers, json=payload)
        second = await client.post("/v1/ingest/batch", headers=headers, json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()
        assert second.json()["accepted"] == 1  # the ORIGINAL result, replayed — not "0 this time"

    async def test_replay_does_not_advance_last_seq_twice(self, client):
        device_id, token = await enroll_device(client)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "batch_id": str(uuid.uuid4()),
            "device_id": str(device_id),
            "seq_from": 0,
            "seq_to": 2,
            "events": [make_event(device_id, i, NOW_MS + i * 1000) for i in range(3)],
        }
        await client.post("/v1/ingest/batch", headers=headers, json=payload)
        await client.post("/v1/ingest/batch", headers=headers, json=payload)

        state = await client.get("/v1/sync/state", headers=headers)
        assert state.json()["last_seq"] == 2


class TestValidation:
    async def test_invalid_event_rejects_the_whole_batch_atomically(self, client):
        device_id, token = await enroll_device(client)
        headers = {"Authorization": f"Bearer {token}"}
        good_event = make_event(device_id, 0, NOW_MS)
        bad_event = {**make_event(device_id, 1, NOW_MS + 1000), "type": "NOT_A_REAL_TYPE"}

        resp = await client.post(
            "/v1/ingest/batch",
            headers=headers,
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(device_id),
                "seq_from": 0,
                "seq_to": 1,
                "events": [good_event, bad_event],
            },
        )
        assert resp.status_code == 422

        # nothing committed -- not even the valid event in the same batch.
        state = await client.get("/v1/sync/state", headers=headers)
        assert state.json()["last_seq"] == 0

    async def test_unknown_field_is_rejected(self, client):
        device_id, token = await enroll_device(client)
        event = make_event(device_id, 0, NOW_MS)
        event["unexpected_field"] = "must not be silently accepted"
        resp = await client.post(
            "/v1/ingest/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(device_id),
                "seq_from": 0,
                "seq_to": 0,
                "events": [event],
            },
        )
        assert resp.status_code == 422

    async def test_empty_events_list_is_rejected(self, client):
        device_id, token = await enroll_device(client)
        resp = await client.post(
            "/v1/ingest/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(device_id),
                "seq_from": 0,
                "seq_to": 0,
                "events": [],
            },
        )
        assert resp.status_code == 422


class TestAuth:
    async def test_missing_token_returns_401(self, client):
        resp = await client.post(
            "/v1/ingest/batch",
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(uuid.uuid4()),
                "seq_from": 0,
                "seq_to": 0,
                "events": [],
            },
        )
        assert resp.status_code == 401

    async def test_malformed_token_returns_401(self, client):
        resp = await client.get(
            "/v1/sync/state", headers={"Authorization": "Bearer not-a-valid-token-shape"}
        )
        assert resp.status_code == 401

    async def test_wrong_secret_returns_401(self, client):
        device_id, _ = await enroll_device(client)
        resp = await client.get(
            "/v1/sync/state", headers={"Authorization": f"Bearer {device_id}.wrong-secret"}
        )
        assert resp.status_code == 401

    async def test_batch_device_id_must_match_authenticated_device(self, client):
        device_id, token = await enroll_device(client)
        other_device_id = uuid.uuid4()
        resp = await client.post(
            "/v1/ingest/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(other_device_id),
                "seq_from": 0,
                "seq_to": 0,
                "events": [make_event(other_device_id, 0, NOW_MS)],
            },
        )
        assert resp.status_code == 403

    async def test_revoked_device_is_rejected(self, client):
        device_id, token = await enroll_device(client)
        async with db.async_session_factory() as session:
            device = await session.get(Device, device_id)
            device.revoked_at = datetime.now(UTC)
            await session.commit()

        resp = await client.get("/v1/sync/state", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


class TestSeqGapDetection:
    async def test_gap_is_recorded_when_seq_jumps_ahead(self, client):
        device_id, token = await enroll_device(client)
        headers = {"Authorization": f"Bearer {token}"}

        await client.post(
            "/v1/ingest/batch",
            headers=headers,
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(device_id),
                "seq_from": 0,
                "seq_to": 0,
                "events": [make_event(device_id, 0, NOW_MS)],
            },
        )
        # jumps from expecting seq=1 straight to seq=5 -- a real gap.
        resp = await client.post(
            "/v1/ingest/batch",
            headers=headers,
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(device_id),
                "seq_from": 5,
                "seq_to": 5,
                "events": [make_event(device_id, 5, NOW_MS + 5000)],
            },
        )
        assert resp.status_code == 200

        async with db.async_session_factory() as session:
            result = await session.execute(select(SeqGap).where(SeqGap.device_id == device_id))
            gaps = result.scalars().all()
        assert len(gaps) == 1
        assert gaps[0].expected_seq == 1
        assert gaps[0].received_seq_from == 5

    async def test_contiguous_batches_record_no_gap(self, client):
        device_id, token = await enroll_device(client)
        headers = {"Authorization": f"Bearer {token}"}
        await client.post(
            "/v1/ingest/batch",
            headers=headers,
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(device_id),
                "seq_from": 0,
                "seq_to": 1,
                "events": [make_event(device_id, i, NOW_MS + i * 1000) for i in range(2)],
            },
        )
        await client.post(
            "/v1/ingest/batch",
            headers=headers,
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(device_id),
                "seq_from": 2,
                "seq_to": 2,
                "events": [make_event(device_id, 2, NOW_MS + 2000)],
            },
        )
        async with db.async_session_factory() as session:
            result = await session.execute(select(SeqGap).where(SeqGap.device_id == device_id))
            gaps = result.scalars().all()
        assert len(gaps) == 0


class TestRateLimit:
    async def test_exceeding_the_per_minute_limit_returns_429(self, client):
        ingest_rate_limiter.reset()
        device_id, token = await enroll_device(client)
        headers = {"Authorization": f"Bearer {token}"}

        statuses = []
        for _ in range(65):
            resp = await client.get("/v1/sync/state", headers=headers)
            statuses.append(resp.status_code)

        assert statuses[:60] == [200] * 60
        assert 429 in statuses[60:]


class TestPerformance:
    async def test_1000_event_batch_completes_quickly(self, client):
        """§38 Phase 3's p95 < 300ms target is a production expectation validated against a
        real deployment; this asserts a generous sanity bound suited to a shared CI/test
        environment rather than re-asserting the exact production SLO here."""
        device_id, token = await enroll_device(client)
        events = [make_event(device_id, i, NOW_MS + i * 100) for i in range(1000)]

        start = time.monotonic()
        resp = await client.post(
            "/v1/ingest/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "batch_id": str(uuid.uuid4()),
                "device_id": str(device_id),
                "seq_from": 0,
                "seq_to": 999,
                "events": events,
            },
        )
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert resp.json()["accepted"] == 1000
        assert elapsed < 5.0, f"1000-event batch took {elapsed:.2f}s"
