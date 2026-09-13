"""Device enrollment / token rotation schemas (§12.2, §28)."""

import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Platform(StrEnum):
    android = "android"
    desktop = "desktop"
    browser = "browser"


class EnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enrollment_code: str = Field(min_length=8, max_length=8)
    device_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    platform: Platform
    browser_family: str | None = Field(default=None, max_length=20)
    app_version: str | None = Field(default=None, max_length=50)
    os_version: str | None = Field(default=None, max_length=50)


class EnrollResponse(BaseModel):
    device_id: uuid.UUID
    token: str


class TokenRotateRequest(BaseModel):
    """Empty body: rotation requires proof of the CURRENT token (§28), which is exactly what
    normal request authentication already establishes via the Authorization header — no separate
    body field is needed to prove the same thing twice."""

    model_config = ConfigDict(extra="forbid")


class TokenRotateResponse(BaseModel):
    token: str


class SyncStateResponse(BaseModel):
    last_seq: int
    next_expected_seq: int
