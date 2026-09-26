"""§21 AI Context Builder: "deterministic, versioned, hash-addressed... a pure function... with a
golden-file test." Like every other module in this package, this has NO DB access — the
DB-touching assembly of these input dataclasses from real rows lives in
`timeos.jobs.build_ai_context`, which calls `build_ai_context` below and then hands the result to
`timeos.privacy.gate.enforce_privacy_gate` before anything downstream ever sees it.

`top_attention` implements §20.4's default identity policy literally: rather than trusting a
caller to only ever pass safely-redacted values, THIS function is what collapses each app's exact
minutes down to a coarse `bucket` string and drops the raw number entirely — the precise duration
never even reaches the `AIContext` model, only a category label, a rank, a bucket, and a session
count (§20.3's ALLOWED app/domain shape). §20.4's `ai_share_app_names` opt-in (raw package names)
is not implemented here — see `timeos/schemas/ai_context.py`'s module docstring for why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type

from timeos.schemas.ai_context import (
    MAX_CATEGORIES,
    MAX_GOALS,
    MAX_PATTERNS,
    AIContext,
    Baselines,
    CategorySummary,
    DataQuality,
    FocusSummary,
    GoalSummary,
    PatternSummary,
    TimeOfDaySlot,
    TopAttentionEntry,
    Totals,
)

MAX_TOP_ATTENTION = MAX_CATEGORIES

_DURATION_BUCKETS: list[tuple[float, str]] = [
    (15, "<15m"),
    (30, "15-30m"),
    (60, "30-60m"),
    (120, "1-2h"),
    (180, "2-3h"),
    (240, "3-4h"),
]
_DURATION_BUCKET_OVERFLOW = "4h+"


def _duration_bucket(minutes: float) -> str:
    for ceiling, label in _DURATION_BUCKETS:
        if minutes < ceiling:
            return label
    return _DURATION_BUCKET_OVERFLOW


@dataclass(frozen=True, slots=True)
class DataQualityInput:
    coverage_ratio: float
    unknown_ratio: float
    devices_reporting: list[str]  # device TYPES/platforms only — never a device id (§20.3)
    unobserved_minutes: int
    offline_minutes: int
    caveats: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TotalsInput:
    day_minutes: int
    observed_minutes: int
    screen_minutes: int
    active_minutes: int


@dataclass(frozen=True, slots=True)
class CategoryInput:
    category: str  # a category LABEL, never its key or id
    minutes: int
    sessions: int
    avg_confidence: float


@dataclass(frozen=True, slots=True)
class TopAttentionInput:
    """One app's aggregate for a day, BEFORE redaction. `category` must already be the app's
    category label (resolved by the caller) — this dataclass never carries an app key/package
    name, so there is nothing for this module to accidentally leak even if a caller misuses it."""

    category: str
    total_minutes: float
    sessions: int


@dataclass(frozen=True, slots=True)
class FocusInput:
    sessions: int
    deep_sessions: int
    longest_minutes: int
    average_minutes: int
    total_focus_minutes: int
    avg_quality: float
    fragmentation_index: float | None
    context_switches: int
    switches_per_hour: float
    interruptions: int


@dataclass(frozen=True, slots=True)
class TimeOfDaySlotInput:
    slot: str
    focus_minutes: int
    distraction_minutes: int


@dataclass(frozen=True, slots=True)
class GoalInput:
    name: str
    priority: int
    target_weekly_minutes: int
    aligned_minutes_today: float
    uncertainty_minutes: float
    week_attainment: float


@dataclass(frozen=True, slots=True)
class PatternInput:
    pattern_type: str
    occurrences: int
    strength: float
    status: str


@dataclass(frozen=True, slots=True)
class BaselinesInput:
    window_days: int
    valid_days: int
    screen_minutes_mean: float
    deep_work_minutes_mean: float
    fragmentation_mean: float
    today_deep_work_minutes: float


@dataclass(frozen=True, slots=True)
class AIContextInputs:
    scope: str
    date: date_type
    data_quality: DataQualityInput
    totals: TotalsInput
    categories: list[CategoryInput]
    top_attention: list[TopAttentionInput]
    focus: FocusInput
    time_of_day: list[TimeOfDaySlotInput]
    goals: list[GoalInput]
    patterns: list[PatternInput]
    baselines: BaselinesInput


def _signed(delta: float, decimals: int) -> str:
    rounded = round(delta, decimals)
    return f"{rounded:+.{decimals}f}"


def build_ai_context(inputs: AIContextInputs) -> AIContext:
    totals = Totals(
        day_minutes=inputs.totals.day_minutes,
        observed_minutes=inputs.totals.observed_minutes,
        screen_minutes=inputs.totals.screen_minutes,
        active_minutes=inputs.totals.active_minutes,
    )

    sorted_categories = sorted(inputs.categories, key=lambda c: c.minutes, reverse=True)[
        :MAX_CATEGORIES
    ]
    categories = [
        CategorySummary(
            category=c.category,
            minutes=c.minutes,
            share=round(c.minutes / totals.screen_minutes, 2) if totals.screen_minutes else 0.0,
            sessions=c.sessions,
            avg_confidence=round(c.avg_confidence, 2),
        )
        for c in sorted_categories
    ]

    sorted_apps = sorted(inputs.top_attention, key=lambda a: a.total_minutes, reverse=True)
    top_attention = [
        TopAttentionEntry(
            rank=rank,
            category=app.category,
            bucket=_duration_bucket(app.total_minutes),
            sessions=app.sessions,
        )
        for rank, app in enumerate(sorted_apps[:MAX_TOP_ATTENTION], start=1)
    ]

    focus = FocusSummary(
        sessions=inputs.focus.sessions,
        deep_sessions=inputs.focus.deep_sessions,
        longest_minutes=inputs.focus.longest_minutes,
        average_minutes=inputs.focus.average_minutes,
        total_focus_minutes=inputs.focus.total_focus_minutes,
        avg_quality=round(inputs.focus.avg_quality, 2),
        fragmentation_index=(
            round(inputs.focus.fragmentation_index, 2)
            if inputs.focus.fragmentation_index is not None
            else None
        ),
        context_switches=inputs.focus.context_switches,
        switches_per_hour=round(inputs.focus.switches_per_hour, 1),
        interruptions=inputs.focus.interruptions,
    )

    today_vs_mean: dict[str, str] = {
        "screen_minutes": _signed(totals.screen_minutes - inputs.baselines.screen_minutes_mean, 0),
        "deep_work_minutes": _signed(
            inputs.baselines.today_deep_work_minutes - inputs.baselines.deep_work_minutes_mean, 0
        ),
    }
    if focus.fragmentation_index is not None:
        today_vs_mean["fragmentation"] = _signed(
            focus.fragmentation_index - inputs.baselines.fragmentation_mean, 2
        )

    return AIContext(
        scope=inputs.scope,
        date=inputs.date.isoformat(),
        weekday=inputs.date.strftime("%A"),
        data_quality=DataQuality(
            coverage_ratio=round(inputs.data_quality.coverage_ratio, 2),
            unknown_ratio=round(inputs.data_quality.unknown_ratio, 2),
            devices_reporting=list(inputs.data_quality.devices_reporting),
            unobserved_minutes=inputs.data_quality.unobserved_minutes,
            offline_minutes=inputs.data_quality.offline_minutes,
            caveats=list(inputs.data_quality.caveats),
        ),
        totals=totals,
        categories=categories,
        focus=focus,
        time_of_day=[
            TimeOfDaySlot(
                slot=slot.slot,
                focus_minutes=slot.focus_minutes,
                distraction_minutes=slot.distraction_minutes,
            )
            for slot in inputs.time_of_day
        ],
        top_attention=top_attention,
        goals=[
            GoalSummary(
                name=g.name,
                priority=g.priority,
                target_weekly_minutes=g.target_weekly_minutes,
                aligned_minutes_today=round(g.aligned_minutes_today),
                uncertainty=round(g.uncertainty_minutes),
                week_attainment=round(g.week_attainment, 2),
            )
            for g in sorted(inputs.goals, key=lambda g: g.priority)[:MAX_GOALS]
        ],
        patterns=[
            PatternSummary(
                type=p.pattern_type,
                occurrences=p.occurrences,
                strength=round(p.strength, 2),
                status=p.status,
            )
            for p in sorted(inputs.patterns, key=lambda p: p.strength, reverse=True)[
                :MAX_PATTERNS
            ]
        ],
        baselines=Baselines(
            window_days=inputs.baselines.window_days,
            valid_days=inputs.baselines.valid_days,
            screen_minutes_mean=round(inputs.baselines.screen_minutes_mean),
            deep_work_minutes_mean=round(inputs.baselines.deep_work_minutes_mean),
            fragmentation_mean=round(inputs.baselines.fragmentation_mean, 2),
            today_vs_mean=today_vs_mean,
        ),
    )
