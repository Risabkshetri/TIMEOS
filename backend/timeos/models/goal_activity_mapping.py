"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §18: goal_activity_mapping.

Maps a goal to the categories and/or apps whose time counts toward it, each with its own weight
in [0, 1] (§18's `aligned_minutes` formula). `category_id` and `app_key` are both nullable but a
row must set exactly one — a mapping keyed by neither (or both) has no well-defined meaning, so
that's enforced with a CHECK constraint rather than left to application code to remember.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from timeos.models.base import Base


class GoalActivityMapping(Base):
    __tablename__ = "goal_activity_mapping"
    __table_args__ = (
        # Naming convention (models/base.py) already prepends "ck_goal_activity_mapping_" —
        # this name is just the suffix, not the full constraint name.
        CheckConstraint(
            "(category_id IS NOT NULL) != (app_key IS NOT NULL)",
            name="exactly_one_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_categories.id", ondelete="CASCADE"), nullable=True
    )
    app_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
