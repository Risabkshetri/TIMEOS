"""Marks a (user, local_date) as needing recomputation (§12.3 step 5).

Written by ingestion whenever a batch touches events on that day; consumed by Phase 4's
sessionization pipeline. Nothing reads this table yet — it exists now so ingestion doesn't need a
later migration to start writing it.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class DirtyDay(Base):
    __tablename__ = "dirty_days"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    marked_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
