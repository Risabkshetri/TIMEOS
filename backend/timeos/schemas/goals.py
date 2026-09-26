"""§12.2's `GET/POST/PATCH /v1/goals` and §18's goal-mapping shape.

The spec names no separate mapping endpoint, so a goal's `goal_activity_mapping` rows are managed
as part of the goal itself: POST/PATCH accept a full `mappings` list that REPLACES whatever a goal
currently has, rather than incremental add/remove calls — simplest correct behaviour for a
personal-scale list of a handful of mappings per goal.

`name`/`target_behavior` are user-authored free text (§38 security note: "goal names ... scanned
by privacy gate before AI context"). The privacy gate itself doesn't exist yet (`timeos/privacy`
is still an empty package — that scan is Phase 7's job, when AI context assembly is built); this
schema only enforces the length cap the spec names now.
"""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from timeos.models.goal import GOAL_NAME_MAX_LENGTH


class GoalMappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    app_key: str | None = Field(default=None, max_length=255)
    weight: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "GoalMappingIn":
        # Mirrors the DB's ck_goal_activity_mapping_exactly_one_target CHECK constraint —
        # validated here too so a bad request gets a 422 instead of surfacing as a raw
        # IntegrityError from the commit.
        if (self.category_id is None) == (self.app_key is None):
            raise ValueError("exactly one of category_id or app_key must be set")
        return self


class GoalMappingOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID | None
    app_key: str | None
    weight: float


class GoalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=GOAL_NAME_MAX_LENGTH)
    priority: int = Field(ge=1, le=5)
    target_minutes_per_week: float = Field(ge=0.0)
    target_behavior: str | None = Field(default=None, max_length=500)
    active_from: date
    active_to: date | None = None
    mappings: list[GoalMappingIn] = Field(default_factory=list)


class GoalUpdateRequest(BaseModel):
    """All fields optional: PATCH only touches what's supplied. `mappings`, if supplied, replaces
    the goal's full mapping set (see module docstring). `archived` is a convenience over directly
    setting `archived_at` — true archives (sets it to now, if not already set), false un-archives
    (clears it)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=GOAL_NAME_MAX_LENGTH)
    priority: int | None = Field(default=None, ge=1, le=5)
    target_minutes_per_week: float | None = Field(default=None, ge=0.0)
    target_behavior: str | None = Field(default=None, max_length=500)
    active_from: date | None = None
    active_to: date | None = None
    mappings: list[GoalMappingIn] | None = None
    archived: bool | None = None


class GoalResponse(BaseModel):
    id: uuid.UUID
    name: str
    priority: int
    target_minutes_per_week: float
    target_behavior: str | None
    active_from: date
    active_to: date | None
    archived: bool
    mappings: list[GoalMappingOut]


class GoalAlignmentResponse(BaseModel):
    """§18's "Reported per goal" fields, computed over a trailing window ending today. Always
    `label: "INFERENCE"` per §18's "Mandatory honesty" — this is an estimate, never a fact, and
    the dashboard must render it as such. `trend vs 4-week mean` from the spec's list isn't
    included: computing it needs a decision about how a goal's OWN target changing mid-window
    should be handled that the spec doesn't make, so it's deferred rather than guessed."""

    label: str = "INFERENCE"
    goal_id: uuid.UUID
    window_days: int
    target_minutes: float
    aligned_minutes: float
    range_low_minutes: float
    range_high_minutes: float
    attainment_ratio: float
    coverage_ratio: float
