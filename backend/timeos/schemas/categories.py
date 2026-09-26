"""§38 Phase 6 output "custom taxonomy" — user-authored additions/renames to
`activity_categories` on top of §15.3's seeded default set. Not in §12.2's endpoint table; see
timeos.schemas.working_hours's docstring for the same spec-silence this fills. System categories
(`is_system=True`: Idle, Unobserved, Offline, Unknown) are immutable (§15.3) and never touched
here — the pipeline hard-depends on their keys always existing."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=100)
    parent_id: uuid.UUID | None = None


class CategoryUpdateRequest(BaseModel):
    """Renames/reparents only — `key` is a stable identifier other rows (app_classifications
    priors, goal_activity_mapping) don't reference by key, only by id, but changing it would still
    make a user's own seed-catalogue/rule history harder to reason about, so it's fixed at
    creation."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: uuid.UUID | None = None


class CategoryResponse(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    parent_id: uuid.UUID | None
    is_system: bool
