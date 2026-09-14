"""focus_sessions — persists timeos.analytics.focus.FocusSession output (§16).

Not in the spec's compact §13 schema listing: the pipeline (timeos/jobs/pipeline.py) originally
only used FocusSession objects in-memory to feed daily_metrics' aggregates
(longest_focus_s/avg_focus_s/focus_session_count/interruptions) and threw them away. That's
insufficient for §25's Focus view, which needs "session list, longest session, best focus
window, interruption timeline" — genuinely per-session detail, not just the daily aggregate.
Added when building that view surfaced the gap, mirroring how `activities.source_session_ids`
got added earlier for a similar reason.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from timeos.models.base import Base


class FocusSessionRow(Base):
    __tablename__ = "focus_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    start_ts: Mapped[datetime] = mapped_column(nullable=False)
    end_ts: Mapped[datetime] = mapped_column(nullable=False)
    duration_s: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    interruption_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_switch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    attributed_ratio: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    is_deep_work: Mapped[bool] = mapped_column(Boolean, nullable=False)
