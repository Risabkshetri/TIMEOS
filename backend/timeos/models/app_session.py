"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §14.1: app_sessions.

One row per `timeos.analytics.sessionize.AppSession` the pipeline persists. `source_event_ids`
preserves provenance back to `raw_events` (§13's relationships list) so a session can always be
traced to the exact events that produced it — required for the correction loop (§15.4) and for
debugging the sessionizer itself against real data.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from timeos.models.base import Base


class AppSession(Base):
    __tablename__ = "app_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    app_key: Mapped[str] = mapped_column(String(255), nullable=False)
    app_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_ts: Mapped[datetime] = mapped_column(nullable=False)
    end_ts: Mapped[datetime] = mapped_column(nullable=False)
    duration_s: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    interaction_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    screen_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
