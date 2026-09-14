"""§13 user_feedback / §15.4 correction loop — Phase 5 only accepts and durably records a
correction; Phase 6 is what actually applies it (new activities row, app_classifications
Bayesian update, dirty-day recompute)."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str = Field(min_length=1, max_length=30)
    target_id: uuid.UUID
    correction: dict = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    id: uuid.UUID
