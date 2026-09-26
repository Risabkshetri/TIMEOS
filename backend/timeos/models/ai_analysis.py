"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §21, §22, §23: ai_analysis.

One row per (user, scope, scope_key, context_hash) attempt — `raw_output` is always stored, even
when `validation_status="failed"` (§22.3: "Never store unvalidated output" is about never
promoting unvalidated content to `ai_insights` rows, not about losing the raw attempt entirely;
the spec's own DDL lists `raw_output JSONB` unconditionally). `day_score`/`summary` are nullable:
§23.3 rule 3 can reject a fabricated or out-of-band score while keeping the narrative, and a
`validation_status="failed"` row has neither. `context_hash` is what makes §21's "same inputs ->
same context -> same context_hash -> cached analysis reused" caching possible — computed from the
`AIContext` itself, before this row exists, so a later day with identical inputs (e.g. a rerun
after a correction that didn't actually change anything) can find and reuse this row instead of
spending another LLM call.

`triggered_by` isn't in the spec's compact §13 DDL sketch — added because §22.9's rate limits
("1 automatic daily call... manual triggers capped at 5/day") are two DIFFERENT limits that need
to be counted separately, which requires knowing which path created each row. No scheduled
automatic job exists yet (mirrors timeos/jobs/pipeline.py's own documented gap: this project has
no running APScheduler process to register one against), so every row today has
`triggered_by="manual"` — the column exists so that gap can close later without a migration.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class AIAnalysis(Base):
    __tablename__ = "ai_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(10), nullable=False)  # day | week | month
    scope_key: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2026-09-13"
    triggered_by: Mapped[str] = mapped_column(String(10), nullable=False)  # manual | scheduled

    context_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    context_version: Mapped[str] = mapped_column(String(10), nullable=False)

    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(10), nullable=False)

    day_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Not in the spec's compact §13 DDL sketch either — the LLM's own overall_confidence is part
    # of AIAnalysisOutput, but §22.6's confidence-ceiling enforcement can lower it during
    # validation, and that SANITIZED value (not the raw one buried in raw_output) is what
    # GET /v1/insights/{date} should actually report.
    overall_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    # §23.1's two plain-string-list fields — surfaced as their own columns (rather than left
    # buried inside raw_output) so the dashboard's Diagnosis page can render them without parsing
    # the raw LLM JSON. Sanitized the same way summary/score_rationale are (§22.7's rejection
    # list can drop individual entries without failing the whole analysis).
    data_caveats: Mapped[list[str]] = mapped_column(JSONB, server_default="[]", nullable=False)
    tomorrow_priorities: Mapped[list[str]] = mapped_column(
        JSONB, server_default="[]", nullable=False
    )
    raw_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # ok (score + all insights survived) | partial (some insights/the score were dropped) |
    # failed (invalid JSON even after one repair attempt — no insights, no score, no summary)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False)

    token_in: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    token_out: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(8, 4), server_default="0", nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
