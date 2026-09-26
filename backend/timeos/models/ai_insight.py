"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §23: ai_insights.

`kind` covers all six §23.1 arrays (win|problem|pattern|distraction|goal_alignment|recommendation)
— the spec's own compact DDL comment names only "win|problem|pattern|recommendation" as examples,
not an exhaustive enum, since §23.1's worked JSON shape clearly has six distinct sections. A
`Recommendation`'s shape differs from `Insight`'s (`action`/`rationale`/`expected_effect`/`effort`/
`measurable_check` vs `claim`/`evidence`/`epistemic_status`) — rather than a second table for one
extra shape, `claim` holds `action`, `evidence` holds the rest as JSONB, and `epistemic_status`
stays NULL (a recommended action isn't a claim with a truth status). `evidence_verified` is set by
`timeos.ai.validate`'s §23.3 numeric cross-check; `user_reaction` is in the spec's own DDL for a
future feedback affordance this phase doesn't build a UI for yet.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_analysis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    evidence_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    epistemic_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    user_reaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
