"""§20.5, §12.2: GET /v1/privacy/audit, GET /v1/privacy/preview/{date}."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class PrivacyAuditEventOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor: str
    allowlist_version: str
    ai_share_app_names: bool
    field_count: int
    outcome: str
    rejected_fields: list[str]
    payload_sha256: str


class PrivacyPreviewResponse(BaseModel):
    """§20.5: "renders the exact last payload sent (reconstructable from the context hash +
    stored aggregates)". `context` is exactly the dict that would cross the boundary to an LLM —
    nothing more, nothing redacted further for display, since the whole point of this endpoint is
    that what the owner sees here IS what would be sent."""

    date: str
    context: dict
    payload_sha256: str
