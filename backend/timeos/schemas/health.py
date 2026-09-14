"""§25's System Health view: per-device collector status."""

from datetime import datetime

from pydantic import BaseModel


class CollectorHealth(BaseModel):
    device_id: str
    name: str
    platform: str
    last_seen_at: datetime | None
    last_seq: int
    revoked: bool
    rejected_batch_count: int


class CollectorsHealthResponse(BaseModel):
    collectors: list[CollectorHealth]
