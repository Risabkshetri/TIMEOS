"""docs/TIMEOS_ENGINEERING_SPEC.md §13: user_feedback.

Created in Phase 5 (the dashboard's correction affordance writes here) but consumed in Phase 6 —
that's a job queue table, not a completed feature: `applied_at` stays NULL until Phase 6's
correction-application logic (§15.4: a new `activities` row, `superseded_by` set on the old one,
`app_classifications` Bayesian update) actually processes it. Phase 5 only needs to accept and
durably record the correction; doing anything with it is explicitly out of scope here.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. "activity"
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    correction: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(nullable=True)
