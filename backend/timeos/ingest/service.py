"""The idempotent batch-ingestion algorithm (§12.3).

    1. Claim batch_id (INSERT ... ON CONFLICT DO NOTHING). Zero rows -> replay the stored
       response verbatim, 200 — this is what makes a client-side retry of an already-processed
       batch indistinguishable from first delivery.
    2. (Schema validation already happened in FastAPI/Pydantic before this function is called —
       an invalid event fails the WHOLE batch atomically, 422, before any row is touched.)
    3. INSERT raw_events, ON CONFLICT (id, ts_utc) DO NOTHING — idempotent per event too.
    4. Advance devices.last_seq; detect and record a seq gap.
    5. Mark each local calendar day the batch touches as dirty, for Phase 4 to recompute.
    6. Persist the final response onto the sync_batches row and commit — everything above is one
       transaction, so a failure at any step leaves nothing committed and the batch can be
       legitimately retried.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.models.device import Device
from timeos.models.dirty_day import DirtyDay
from timeos.models.raw_event import RawEvent
from timeos.models.seq_gap import SeqGap
from timeos.models.sync_batch import SyncBatch
from timeos.models.user import User
from timeos.schemas.events import IngestBatchRequest, IngestBatchResponse


class DeviceMismatchError(Exception):
    """Raised when the batch's device_id doesn't match the authenticated device's own id."""


def local_date_for_event(ts_utc_millis: int, tz_name: str, day_start_hour: int) -> date:
    """§13's day boundary: [local day_start_hour, next day_start_hour)."""
    dt = datetime.fromtimestamp(ts_utc_millis / 1000, tz=ZoneInfo(tz_name))
    return (dt - timedelta(hours=day_start_hour)).date()


async def ingest_batch(
    db: AsyncSession,
    device: Device,
    request: IngestBatchRequest,
) -> tuple[IngestBatchResponse, bool]:
    """Returns (response, was_replay). was_replay=True means this batch_id was already
    processed and the stored response was returned without redoing any work."""
    if request.device_id != device.id:
        raise DeviceMismatchError(
            f"batch device_id {request.device_id} does not match authenticated device {device.id}"
        )

    claim = (
        pg_insert(SyncBatch)
        .values(
            batch_id=request.batch_id,
            device_id=device.id,
            event_count=len(request.events),
            seq_from=request.seq_from,
            seq_to=request.seq_to,
            response={},
            status="processing",
        )
        .on_conflict_do_nothing(index_elements=["batch_id"])
    )
    claim_result = await db.execute(claim)

    if claim_result.rowcount == 0:  # type: ignore[attr-defined]  # CursorResult at runtime
        existing = await db.get(SyncBatch, request.batch_id)
        assert existing is not None  # ON CONFLICT fired, so a row must exist
        # Read the stored response into a plain dict BEFORE rollback: rollback expires ORM
        # attributes, and accessing an expired attribute afterward would need an async reload
        # that this synchronous attribute access can't perform (MissingGreenlet).
        stored_response = dict(existing.response)
        await db.rollback()
        return IngestBatchResponse(**stored_response), True

    now = datetime.now(UTC)

    event_rows = [
        {
            "id": e.event_id,
            "ts_utc": datetime.fromtimestamp(e.ts_utc / 1000, tz=UTC),
            "device_id": device.id,
            "user_id": device.user_id,
            "seq": e.seq,
            "tz_offset_min": e.tz_offset_min,
            "tz_id": e.tz_id,
            "uptime_ms": e.uptime_ms,
            "type": e.type.value,
            "payload": e.payload,
            "clock_suspect": False,
            "schema_v": e.schema_v,
            "ingested_at": now,
        }
        for e in request.events
    ]
    raw_insert = (
        pg_insert(RawEvent)
        .values(event_rows)
        .on_conflict_do_nothing(index_elements=["id", "ts_utc"])
    )
    raw_result = await db.execute(raw_insert)
    accepted = raw_result.rowcount  # type: ignore[attr-defined]  # CursorResult at runtime
    duplicates = len(request.events) - accepted

    if request.seq_from > device.last_seq + 1:
        db.add(
            SeqGap(
                device_id=device.id,
                expected_seq=device.last_seq + 1,
                received_seq_from=request.seq_from,
            )
        )
    device.last_seq = max(device.last_seq, request.seq_to)
    device.last_seen_at = now

    user = await db.get(User, device.user_id)
    assert user is not None
    touched_dates = {
        local_date_for_event(e.ts_utc, user.timezone, user.day_start_hour) for e in request.events
    }
    for local_date in touched_dates:
        dirty_upsert = (
            pg_insert(DirtyDay)
            .values(user_id=user.id, local_date=local_date)
            .on_conflict_do_update(
                index_elements=["user_id", "local_date"],
                set_={"marked_at": now},
            )
        )
        await db.execute(dirty_upsert)

    response = IngestBatchResponse(
        accepted=accepted,
        duplicates=duplicates,
        batch_id=request.batch_id,
        server_seq=request.seq_to,
        next_expected_seq=request.seq_to + 1,
    )
    await db.execute(
        update(SyncBatch)
        .where(SyncBatch.batch_id == request.batch_id)
        .values(response=response.model_dump(mode="json"), status="accepted")
    )

    await db.commit()
    return response, False
