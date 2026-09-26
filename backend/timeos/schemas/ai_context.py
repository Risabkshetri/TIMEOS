"""§21 AI Context Builder — the `AIContext` Pydantic model, §20.2's "Allowlist + schema
validation" enforcement layer. Every model in this file sets `extra="forbid"`: a field
accidentally added anywhere in this tree fails validation before it can reach
`timeos.privacy.gate`, let alone an LLM.

This module has NO SQLAlchemy import and NO DB access — it is pure schema, deliberately kept
importable from `timeos.ai` per §20.2's structural isolation contract ("`timeos.ai` may import
only `timeos.schemas.ai_context` and `timeos.privacy`"). The DB-touching assembly of a real
`AIContext` lives in `timeos.jobs.build_ai_context` (which gathers real rows) calling
`timeos.analytics.ai_context` (a pure function, matching every other analytics module's
DB-free convention) — neither of those two modules is `timeos.ai` itself, since Phase 7's own
objective is "build the boundary before any LLM code exists": nothing here calls an LLM yet.

Per-app/per-domain identity (§20.4's `ai_share_app_names` opt-in, which would let a user allow
raw package names into `top_attention`) is deliberately NOT implemented in this phase — `label_type`
appears in §20.3's prose description of that opt-in shape but not in §21's own worked JSON example,
and adding a pathway that can carry a raw package name into an LLM-bound payload is exactly the
kind of change the spec says should be "a deliberate allowlist edit, which is a reviewable diff",
not something bundled into the initial boundary. `top_attention` here is always category-level,
matching §21's literal example.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_CATEGORIES = 15
MAX_PATTERNS = 10
MAX_GOALS = 10

# today_vs_mean is a free-form dict[str, str] in §21's example ({"fragmentation": "+0.10"}); a
# Pydantic dict type has no extra="forbid" of its own, so its keys are restricted here to keep
# this schema airtight on its own, independent of the gate's separate allowlist walk.
TODAY_VS_MEAN_KEYS = frozenset({"screen_minutes", "deep_work_minutes", "fragmentation"})


class _Forbid(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataQuality(_Forbid):
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    unknown_ratio: float = Field(ge=0.0, le=1.0)
    devices_reporting: list[str]
    unobserved_minutes: int = Field(ge=0)
    offline_minutes: int = Field(ge=0)
    caveats: list[str] = Field(default_factory=list)


class Totals(_Forbid):
    day_minutes: int = Field(ge=0)
    observed_minutes: int = Field(ge=0)
    screen_minutes: int = Field(ge=0)
    active_minutes: int = Field(ge=0)


class CategorySummary(_Forbid):
    category: str
    minutes: int = Field(ge=0)
    share: float = Field(ge=0.0, le=1.0)
    sessions: int = Field(ge=0)
    avg_confidence: float = Field(ge=0.0, le=1.0)


class FocusSummary(_Forbid):
    sessions: int = Field(ge=0)
    deep_sessions: int = Field(ge=0)
    longest_minutes: int = Field(ge=0)
    average_minutes: int = Field(ge=0)
    total_focus_minutes: int = Field(ge=0)
    avg_quality: float = Field(ge=0.0, le=1.0)
    # None mirrors daily_metrics.fragmentation_index: computed only when coverage_ratio >= 0.6.
    fragmentation_index: float | None = Field(default=None, ge=0.0, le=1.0)
    context_switches: int = Field(ge=0)
    switches_per_hour: float = Field(ge=0.0)
    interruptions: int = Field(ge=0)


class TimeOfDaySlot(_Forbid):
    slot: str
    focus_minutes: int = Field(ge=0)
    distraction_minutes: int = Field(ge=0)


class TopAttentionEntry(_Forbid):
    rank: int = Field(ge=1)
    category: str
    bucket: str
    sessions: int = Field(ge=0)


class GoalSummary(_Forbid):
    name: str = Field(max_length=60)  # §19/§38: user-authored, already length-capped at creation
    priority: int = Field(ge=1, le=5)
    target_weekly_minutes: int = Field(ge=0)
    aligned_minutes_today: int = Field(ge=0)
    uncertainty: int = Field(ge=0)
    week_attainment: float = Field(ge=0.0)


class PatternSummary(_Forbid):
    type: str
    occurrences: int = Field(ge=0)
    strength: float = Field(ge=0.0, le=1.0)
    status: str


class Baselines(_Forbid):
    window_days: int = Field(ge=0)
    valid_days: int = Field(ge=0)
    screen_minutes_mean: int = Field(ge=0)
    deep_work_minutes_mean: int = Field(ge=0)
    fragmentation_mean: float = Field(ge=0.0, le=1.0)
    today_vs_mean: dict[str, str] = Field(default_factory=dict)

    @field_validator("today_vs_mean")
    @classmethod
    def _known_keys_only(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = set(value) - TODAY_VS_MEAN_KEYS
        if unknown:
            raise ValueError(f"unknown today_vs_mean key(s): {sorted(unknown)}")
        return value


class AIContext(_Forbid):
    """§21's deterministic, versioned, hash-addressed context. `context_hash` itself is NOT a
    field here — it's computed by the caller over this model's canonical serialization (the same
    inputs must always produce the same hash, which a self-referential field would break)."""

    context_version: str = "1.0"
    scope: str
    date: str
    weekday: str
    data_quality: DataQuality
    totals: Totals
    categories: list[CategorySummary] = Field(default_factory=list, max_length=MAX_CATEGORIES)
    focus: FocusSummary
    time_of_day: list[TimeOfDaySlot] = Field(default_factory=list)
    top_attention: list[TopAttentionEntry] = Field(default_factory=list)
    goals: list[GoalSummary] = Field(default_factory=list, max_length=MAX_GOALS)
    patterns: list[PatternSummary] = Field(default_factory=list, max_length=MAX_PATTERNS)
    baselines: Baselines


def context_hash(context: AIContext) -> str:
    """§21: "same inputs -> same context -> same context_hash -> cached analysis reused instead
    of a new LLM call." A plain SHA-256 over the canonical (sorted-key, no whitespace) JSON
    serialization — the same recipe `timeos.privacy.gate` uses for its own payload digest, kept as
    a separate small function here rather than imported from there so Phase 7's already-tested
    gate module never has to change for a Phase 8 caching need it doesn't itself have."""
    canonical = json.dumps(context.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
