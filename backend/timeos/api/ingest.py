"""Ingestion endpoints (§12.2, §12.3, §38 Phase 3)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import enforce_ingest_rate_limit, get_db
from timeos.ingest.service import DeviceMismatchError, ingest_batch
from timeos.models.device import Device
from timeos.schemas.devices import SyncStateResponse
from timeos.schemas.events import IngestBatchRequest, IngestBatchResponse

router = APIRouter(tags=["ingest"])


@router.post("/v1/ingest/batch", response_model=IngestBatchResponse)
async def post_batch(
    body: IngestBatchRequest,
    device: Device = Depends(enforce_ingest_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        response, was_replay = await ingest_batch(db, device, body)
    except DeviceMismatchError:
        # 403, not 422: the payload is well-formed, but this device is not authorized to submit
        # events under a different device's identity.
        return JSONResponse(
            status_code=403,
            content={"error": "batch device_id does not match the authenticated device"},
        )

    # A replayed (already-processed) batch and a freshly-processed one both return 200 with the
    # identical response body — that indistinguishability is the whole point of idempotent replay.
    return JSONResponse(status_code=200, content=response.model_dump(mode="json"))


@router.get("/v1/sync/state", response_model=SyncStateResponse)
async def sync_state(device: Device = Depends(enforce_ingest_rate_limit)) -> SyncStateResponse:
    return SyncStateResponse(last_seq=device.last_seq, next_expected_seq=device.last_seq + 1)
