"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §18: goals.

`name` is user-authored free text — §38 Phase 6's security note caps it at 60 chars and requires
it be scanned by the privacy gate (Phase 7) before ever entering an AI context; the length cap is
enforced here at the schema level so it can never silently grow past what Phase 7 assumes.
`target_behavior` is explicitly "used only for AI interpretation" (§18) — never read by any
deterministic code path, only ever handed to Phase 8's AI analyst as context.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, Numeric, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base

GOAL_NAME_MAX_LENGTH = 60


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(GOAL_NAME_MAX_LENGTH), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1 (highest) - 5 (lowest)
    target_minutes_per_week: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    target_behavior: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active_from: Mapped[date] = mapped_column(nullable=False)
    active_to: Mapped[date | None] = mapped_column(nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
