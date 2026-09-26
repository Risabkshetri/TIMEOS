"""docs/TIMEOS_ENGINEERING_SPEC.md §13(-adjacent), §20.5: privacy_audit_events.

Every `timeos.privacy.gate` invocation writes one row here, whether it allowed or rejected the
payload — "every gate invocation", not just failures, so the dashboard's Privacy page can show a
complete history, and so a rejection is itself evidence the boundary held rather than a silent
no-op. `payload_sha256` lets the exact outbound bytes be proven later "without storing it again"
(§20.5) — the digest, not the payload itself, since storing the payload here would defeat the
point of a privacy boundary. `ai_share_app_names` is a snapshot of that user setting at the moment
of the call (§20.4: "recorded in every privacy_audit_events row so past analyses remain
attributable to the policy in force") — it can change later without rewriting history.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class PrivacyAuditEvent(Base):
    __tablename__ = "privacy_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    # Who asked the gate to check a payload — e.g. "privacy_preview", "ai_analyst" (Phase 8).
    actor: Mapped[str] = mapped_column(String(50), nullable=False)
    allowlist_version: Mapped[str] = mapped_column(String(10), nullable=False)
    ai_share_app_names: Mapped[bool] = mapped_column(nullable=False)
    field_count: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # allowed | rejected
    rejected_fields: Mapped[list[str]] = mapped_column(JSONB, server_default="[]", nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
