"""§12.2: GET /v1/insights/{date}, POST /v1/ai/analyze/{date}."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class InsightOut(BaseModel):
    id: uuid.UUID
    kind: str  # wins | problems | patterns | distractions | goal_alignment | recommendation
    claim: str
    evidence: dict
    confidence: float
    evidence_verified: bool
    epistemic_status: str | None


class AnalysisOut(BaseModel):
    id: uuid.UUID
    scope: str
    scope_key: str
    provider: str
    model: str
    day_score: int | None
    score_rationale: str | None
    summary: str | None
    overall_confidence: float | None
    data_caveats: list[str]
    tomorrow_priorities: list[str]
    validation_status: str  # ok | partial | failed
    created_at: datetime
    insights: list[InsightOut]
