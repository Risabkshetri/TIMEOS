"""§23.1's `AIAnalysisOutput` shape: the JSON schema the LLM's response is validated against
before anything in it can be persisted as an `ai_insights` row. §22.3: "Output must be valid JSON
against `AIAnalysisOutput`. Invalid → one repair attempt... second failure → discard." This module
is pure schema (no DB), importable from `timeos.ai` for exactly that validation step.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

MAX_INSIGHTS_PER_SECTION = 4
MAX_GOAL_ALIGNMENT_INSIGHTS = 5
MAX_RECOMMENDATIONS = 3
MAX_TOMORROW_PRIORITIES = 3
MAX_DATA_CAVEATS = 10
MAX_SUMMARY_LENGTH = 600


class EpistemicStatus(StrEnum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "med"
    HIGH = "high"


class _Forbid(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(_Forbid):
    """§23.3 rule 1: every path in `fields` must resolve in the source `AIContext` — checked by
    `timeos.ai.validate`, not by this schema (which has no access to the context to check
    against). `values` is the LLM's own restatement of what it read at those paths — kept so the
    numeric cross-check (§23.3 rule 2) has literal numbers to compare against `narrative`/`claim`,
    and so a human reviewing `ai_insights.evidence` later can see what the model claimed to see
    without re-deriving it from the context."""

    fields: list[str] = Field(min_length=1)
    values: dict[str, float | int | str]
    narrative: str = Field(max_length=500)


class Insight(_Forbid):
    claim: str = Field(min_length=1, max_length=500)
    evidence: Evidence
    confidence: float = Field(ge=0.0, le=1.0)
    epistemic_status: EpistemicStatus


class Recommendation(_Forbid):
    action: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=500)
    expected_effect: str = Field(min_length=1, max_length=300)
    effort: Effort
    measurable_check: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)


class AIAnalysisOutput(_Forbid):
    day_score: int = Field(ge=0, le=100)
    score_rationale: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_LENGTH)
    data_caveats: list[str] = Field(default_factory=list, max_length=MAX_DATA_CAVEATS)
    wins: list[Insight] = Field(default_factory=list, max_length=MAX_INSIGHTS_PER_SECTION)
    problems: list[Insight] = Field(default_factory=list, max_length=MAX_INSIGHTS_PER_SECTION)
    patterns: list[Insight] = Field(default_factory=list, max_length=MAX_INSIGHTS_PER_SECTION)
    distractions: list[Insight] = Field(default_factory=list, max_length=MAX_INSIGHTS_PER_SECTION)
    goal_alignment: list[Insight] = Field(
        default_factory=list, max_length=MAX_GOAL_ALIGNMENT_INSIGHTS
    )
    recommendations: list[Recommendation] = Field(
        default_factory=list, max_length=MAX_RECOMMENDATIONS
    )
    tomorrow_priorities: list[str] = Field(
        default_factory=list, max_length=MAX_TOMORROW_PRIORITIES
    )
    overall_confidence: float = Field(ge=0.0, le=1.0)


# The six §23.1 insight-shaped sections, each independently validated/trimmed by
# timeos.ai.validate — kept as one tuple so validation code doesn't have to spell out all six
# names twice (once to read, once to write back the survivors).
INSIGHT_SECTIONS: tuple[str, ...] = (
    "wins",
    "problems",
    "patterns",
    "distractions",
    "goal_alignment",
)
