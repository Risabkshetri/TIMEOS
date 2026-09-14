"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §15.2, §15.4: app_classifications.

The L1 "learned prior" layer's storage: an empirical, per-user distribution over categories for
each app, updated by a Bayesian update with a 60-day recency half-life whenever a correction
arrives (§15.4). Composite primary key (not a surrogate id) because the table's whole meaning is
"the current classification for (user, app)" — there is exactly one live row per pair by
definition, never a history to preserve here (that's what `activities.superseded_by` is for).
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class AppClassification(Base):
    __tablename__ = "app_classifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    app_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # seed|learned|user
    sample_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
