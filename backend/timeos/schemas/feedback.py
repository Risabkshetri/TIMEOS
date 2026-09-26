"""§13 user_feedback / §15.4 correction loop — Phase 5 only accepted and durably recorded a
correction; Phase 6's ClassificationCorrectionRequest/Response below is what actually applies it
(new activities row, app_classifications Bayesian update, opt-in retroactive recompute)."""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str = Field(min_length=1, max_length=30)
    target_id: uuid.UUID
    correction: dict = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    id: uuid.UUID


class ClassificationCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: uuid.UUID
    corrected_category_key: str = Field(min_length=1, max_length=64)
    # A standing per-app rule (§38 Phase 6 output "per-app rules"): sets app_classifications
    # immediately as an L0 terminal override (source='user', confidence=1.0) rather than one
    # more piece of L1 evidence that only takes effect once >=5 samples accumulate (§15.2).
    apply_as_rule: bool = False
    # §38 Phase 6 output "retroactive recompute (opt-in)": re-runs the pipeline for every OTHER
    # day with an activity from this same app, so the (possibly still-accumulating) updated
    # classification is reflected everywhere it applies — never automatic, and never touches the
    # day being corrected right now (that day's fix is the new activities row itself).
    apply_retroactively: bool = False


class ClassificationCorrectionResponse(BaseModel):
    new_activity_id: uuid.UUID
    app_classification_source: str  # user | learned
    app_classification_confidence: float
    app_classification_sample_count: int
    retroactively_recomputed_dates: list[date]
