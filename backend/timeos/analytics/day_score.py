"""§23.3 rule 3: "`day_score` must be within ±15 of a deterministic reference score computed by
the analytics engine; outside that band → reject the score, keep the narrative." The spec names
this requirement but not a formula (like §18's alignment uncertainty range, and §21's own
uncertainty band, before it) — this module is that documented interpretation.

This is a SANITY-CHECK band, not a feature: the reference score is never shown to the user
directly (the LLM's own `day_score`, once it survives this check, is what the UI displays). It's
built entirely from `AIContext` fields — the same sanitized, already-computed aggregates the LLM
itself sees — so the check is self-consistent: an LLM inventing an implausible score gets caught
against the exact numbers it was given, not some other, richer view of the day it never had access
to.

Design: start at a neutral 50, move up for uninterrupted focus time and being on pace against
declared goals, move down for fragmentation and interruptions, and pull the whole score toward
neutral when data quality is too poor to judge the day confidently either way (mirrors §22.6's own
"lower confidence under poor coverage" principle, applied to this score instead of an insight's
confidence).
"""

from __future__ import annotations

import statistics

from timeos.schemas.ai_context import AIContext

NEUTRAL_SCORE = 50.0
LOW_COVERAGE_THRESHOLD = 0.6
DEEP_SESSION_POINTS = 8.0
MAX_DEEP_SESSION_POINTS = 24.0
FOCUS_MINUTES_DIVISOR = 10.0
MAX_FOCUS_MINUTES_POINTS = 15.0
FRAGMENTATION_PENALTY_SCALE = 20.0
INTERRUPTION_PENALTY_PER = 1.5
MAX_INTERRUPTION_PENALTY = 15.0
UNKNOWN_RATIO_PENALTY_SCALE = 15.0
GOAL_ATTAINMENT_PIVOT = 0.5  # "on pace" for the week
GOAL_ATTAINMENT_SCALE = 10.0
MAX_GOAL_ATTAINMENT_RATIO = 1.5


def compute_reference_day_score(context: AIContext) -> int:
    score = NEUTRAL_SCORE

    score += min(context.focus.deep_sessions * DEEP_SESSION_POINTS, MAX_DEEP_SESSION_POINTS)
    score += min(
        context.focus.total_focus_minutes / FOCUS_MINUTES_DIVISOR, MAX_FOCUS_MINUTES_POINTS
    )

    if context.focus.fragmentation_index is not None:
        score -= context.focus.fragmentation_index * FRAGMENTATION_PENALTY_SCALE
    score -= min(context.focus.interruptions * INTERRUPTION_PENALTY_PER, MAX_INTERRUPTION_PENALTY)

    score -= context.data_quality.unknown_ratio * UNKNOWN_RATIO_PENALTY_SCALE

    if context.goals:
        avg_attainment = statistics.mean(g.week_attainment for g in context.goals)
        capped_attainment = min(avg_attainment, MAX_GOAL_ATTAINMENT_RATIO)
        score += (capped_attainment - GOAL_ATTAINMENT_PIVOT) * GOAL_ATTAINMENT_SCALE

    if context.data_quality.coverage_ratio < LOW_COVERAGE_THRESHOLD:
        # Can't confidently say the day was good OR bad on this little data — pull halfway to
        # neutral rather than let a handful of observed minutes swing the score either direction.
        score = (score + NEUTRAL_SCORE) / 2

    return round(max(0.0, min(100.0, score)))
