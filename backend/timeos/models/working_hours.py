"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §18: working_hours.

One row per (user, weekday) the user has declared working hours for; a weekday with no row means
"no declared working hours that day" (§18's time_window_factor then always applies the outside-
hours 0.85 penalty for work-type goals, since there's nothing to be inside of). `weekday` is
0=Monday..6=Sunday, matching Python's `date.weekday()` so no translation is needed when comparing
against an activity's own timestamp.
"""

import uuid
from datetime import time

from sqlalchemy import ForeignKey, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from timeos.models.base import Base


class WorkingHours(Base):
    __tablename__ = "working_hours"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True)  # 0=Monday .. 6=Sunday
    start_local: Mapped[time] = mapped_column(nullable=False)
    end_local: Mapped[time] = mapped_column(nullable=False)
