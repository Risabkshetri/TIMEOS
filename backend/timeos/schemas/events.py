"""Ingest contract schemas (§9.1, §9.2, §12.3).

Field names here match exactly what the Android client sends (see
android/core/sync/IngestJson.kt) — `ts_utc`/`uptime_ms` are epoch-millisecond integers, not ISO
datetime strings, because that's the wire format already shipped in Phase 2.

`extra="forbid"` on every model is a deliberate privacy control (§20.2, §38 Phase 3 security): a
future client field can never silently start flowing into the database without a reviewable
schema change here first.
"""

import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_EVENTS_PER_BATCH = 1000
MAX_PAYLOAD_FIELDS = 20
MAX_PAYLOAD_KEY_LEN = 100
MAX_PAYLOAD_VALUE_LEN = 1000


class EventType(StrEnum):
    APP_FOREGROUND = "APP_FOREGROUND"
    APP_BACKGROUND = "APP_BACKGROUND"
    SCREEN_ON = "SCREEN_ON"
    SCREEN_OFF = "SCREEN_OFF"
    DEVICE_LOCK = "DEVICE_LOCK"
    DEVICE_UNLOCK = "DEVICE_UNLOCK"
    USER_INTERACTION = "USER_INTERACTION"
    DEVICE_STARTUP = "DEVICE_STARTUP"
    DEVICE_SHUTDOWN = "DEVICE_SHUTDOWN"
    COLLECTOR_START = "COLLECTOR_START"
    COLLECTOR_STOP = "COLLECTOR_STOP"
    HEALTH = "HEALTH"


class IngestEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: uuid.UUID
    device_id: uuid.UUID
    seq: int = Field(ge=0)
    ts_utc: int  # epoch milliseconds
    tz_offset_min: int = Field(ge=-720, le=840)
    tz_id: str = Field(min_length=1, max_length=64)
    clock_flags: list[str] = Field(default_factory=list, max_length=10)
    uptime_ms: int = Field(ge=0)
    type: EventType
    source: str = Field(min_length=1, max_length=20)
    payload: dict[str, str] = Field(default_factory=dict)
    schema_v: int = Field(ge=1, le=100)

    @field_validator("payload")
    @classmethod
    def bounded_payload(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > MAX_PAYLOAD_FIELDS:
            raise ValueError(f"payload has more than {MAX_PAYLOAD_FIELDS} fields")
        for key, value in v.items():
            if len(key) > MAX_PAYLOAD_KEY_LEN or len(value) > MAX_PAYLOAD_VALUE_LEN:
                raise ValueError("payload field exceeds size limit")
        return v


class IngestBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: uuid.UUID
    device_id: uuid.UUID
    seq_from: int = Field(ge=0)
    seq_to: int = Field(ge=0)
    events: list[IngestEvent] = Field(min_length=1, max_length=MAX_EVENTS_PER_BATCH)

    @model_validator(mode="after")
    def check_consistency(self) -> "IngestBatchRequest":
        if self.seq_to < self.seq_from:
            raise ValueError("seq_to must be >= seq_from")
        mismatched = [e.event_id for e in self.events if e.device_id != self.device_id]
        if mismatched:
            raise ValueError(f"event device_id does not match batch device_id: {mismatched[:3]}")
        return self


class IngestBatchResponse(BaseModel):
    accepted: int
    duplicates: int
    batch_id: uuid.UUID
    server_seq: int
    next_expected_seq: int
