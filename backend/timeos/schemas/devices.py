"""Device enrollment / token rotation schemas (§12.2, §28)."""

import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Platform(StrEnum):
    android = "android"
    desktop = "desktop"
    browser = "browser"


class BrowserFamily(StrEnum):
    """§11.4: "Three browsers therefore produce three `devices` rows with `platform = "browser"`
    and `browser_family ∈ {brave, chromium, firefox}`." Brave and Chromium share a byte-identical
    extension build (§11.1) but still enroll as distinct families — arbitration (§11.4) and the
    System Health page need to tell them apart even though their telemetry code is identical."""

    brave = "brave"
    chromium = "chromium"
    firefox = "firefox"


class EnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enrollment_code: str = Field(min_length=8, max_length=8)
    device_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    platform: Platform
    browser_family: BrowserFamily | None = Field(default=None)
    app_version: str | None = Field(default=None, max_length=50)
    os_version: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _browser_family_matches_platform(self) -> "EnrollRequest":
        if self.platform == Platform.browser and self.browser_family is None:
            raise ValueError("browser_family is required when platform is 'browser'")
        if self.platform != Platform.browser and self.browser_family is not None:
            raise ValueError("browser_family is only valid when platform is 'browser'")
        return self


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
