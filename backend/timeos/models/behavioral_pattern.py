"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §17: behavioral_patterns.

A pattern stays `candidate` until it has >=3 occurrences across >=3 distinct days; only
`confirmed` patterns are allowed into the AI context (§17) — enforced by the pipeline/AI-context
builder reading `status`, not by a DB constraint, since "3 distinct days" isn't expressible as a
column check.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from timeos.models.base import Base


class BehavioralPattern(Base):
    __tablename__ = "behavioral_patterns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pattern_type: Mapped[str] = mapped_column(String(40), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(nullable=False)
    last_seen: Mapped[datetime] = mapped_column(nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    strength: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    support: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="candidate", nullable=False)
