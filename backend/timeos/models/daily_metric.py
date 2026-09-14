"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §14.3, §16: daily_metrics.

One row per (user, local_date), fully replaced (not appended) on each recompute — the pipeline is
required to be idempotent and re-runnable (§14), so `computed_at`/`pipeline_version` exist to make
a recompute's effect visible, not to version history. `coverage_ratio` gates every other metric on
this row per §14.3: a dashboard MUST render everything else as a range, not a point value, when it
is below 0.6, and this column is what that check reads.

`fragmentation_index` is nullable: `timeos.analytics.metrics.compute_daily_metrics` returns None
for it when `coverage_ratio < 0.6`, per §16's "both are computed only on windows with
coverage_ratio >= 0.6" — a NOT NULL default of 0 here would be indistinguishable from a real
perfect-fragmentation-free day.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base

_SECONDS = Numeric(10, 2)
_RATIO = Numeric(4, 3)


class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    local_date: Mapped[date] = mapped_column(primary_key=True)

    day_start_utc: Mapped[datetime] = mapped_column(nullable=False)
    day_end_utc: Mapped[datetime] = mapped_column(nullable=False)
    duration_seconds: Mapped[float] = mapped_column(_SECONDS, nullable=False)

    observed_s: Mapped[float] = mapped_column(_SECONDS, nullable=False)
    tracked_s: Mapped[float] = mapped_column(_SECONDS, nullable=False)
    idle_s: Mapped[float] = mapped_column(_SECONDS, nullable=False)
    unobserved_s: Mapped[float] = mapped_column(_SECONDS, nullable=False)
    offline_s: Mapped[float] = mapped_column(_SECONDS, nullable=False)
    coverage_ratio: Mapped[float] = mapped_column(_RATIO, nullable=False)

    screen_time_s: Mapped[float] = mapped_column(_SECONDS, nullable=False)
    active_time_s: Mapped[float] = mapped_column(_SECONDS, nullable=False)

    deep_work_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    focused_work_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    shallow_work_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    communication_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    learning_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    entertainment_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    social_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    distraction_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    unknown_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    unknown_ratio: Mapped[float] = mapped_column(_RATIO, server_default="0", nullable=False)

    context_switches: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    switches_per_hour: Mapped[float] = mapped_column(
        Numeric(6, 2), server_default="0", nullable=False
    )
    interruptions: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    fragmentation_index: Mapped[float | None] = mapped_column(_RATIO, nullable=True)

    longest_focus_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    avg_focus_s: Mapped[float] = mapped_column(_SECONDS, server_default="0", nullable=False)
    focus_session_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    unlock_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    tz_transition: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    revised: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)

    computed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(20), nullable=False)
