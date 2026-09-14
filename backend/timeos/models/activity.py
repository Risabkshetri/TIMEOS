"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §15: activities.

`goal_id`/`goal_confidence` from the full §13 schema are deliberately omitted here — `goals`
doesn't exist until Phase 6, and pointing a FK at a nonexistent table would be worse than adding
the column when it's actually needed. `superseded_by` is self-referential and nullable: a
correction (§15.4) never mutates or deletes a row, it inserts a new one and points the old row at
it, so `activities` history is append-only even under correction.

`source_session_ids` isn't in the spec's compact §13 schema listing, but the prose right below it
("app_sessions N-1 activities... preserving provenance") requires SOME join key between the two
tables, and `app_sessions` has no `activity_id` column either — this mirrors `app_sessions.
source_event_ids`'s existing provenance pattern (an array of ids on the "many" side's parent
would be backwards; an array of child ids on the "one" side is the natural fit here since a
single activity can consolidate several app_sessions, e.g. an IDE/Terminal/Browser cluster).
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from timeos.models.base import Base


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_ts: Mapped[datetime] = mapped_column(nullable=False)
    end_ts: Mapped[datetime] = mapped_column(nullable=False)
    duration_s: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    intent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    # rule|history|user|ai_assist
    classification_source: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    devices: Mapped[list[str]] = mapped_column(
        ARRAY(String(120)), server_default="{}", nullable=False
    )
    source_session_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), server_default="{}", nullable=False
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
