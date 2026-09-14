"""Focus engine — §16. Turns a classified session timeline into focus/deep-work sessions.

Operates on `ClassifiedSession` (an `AppSession` plus the category it was classified into) rather
than the pipeline's eventual `activities` rows: the focus math only cares about "what category was
active when", which the raw classified-session timeline already carries, regardless of whether a
later consolidation pass has merged an IDE/Terminal/Browser cluster into one `activities` row.

`goal_alignment_weight` in the quality score is a caller-supplied parameter, not computed here:
`goals` doesn't exist until Phase 6, so today's callers pass 0.0 (the formula's `min`/`max` clamps
mean this never breaks the score, it just means the term contributes nothing yet).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

INTERRUPT_TOLERANCE = timedelta(seconds=90)
INTERRUPTION_MAX_DURATION = timedelta(seconds=120)
INTERRUPTION_CLUSTER_WINDOW = timedelta(minutes=5)
FOCUS_MIN_DURATION = timedelta(minutes=15)
DEEP_WORK_MIN_DURATION = timedelta(minutes=45)
DEEP_WORK_MAX_SWITCH_RATE_PER_HOUR = 2.0
FOCUS_MIN_ATTRIBUTED_RATIO = 0.80
DEEP_WORK_MIN_ATTRIBUTED_RATIO = 0.90
FOCUS_TOLERATED_INTERRUPTIONS_PER_15MIN = 1

COMMUNICATION_CATEGORIES = frozenset({"communication"})


@dataclass(frozen=True, slots=True)
class ClassifiedSession:
    app_key: str
    category_key: str
    start_ts: datetime
    end_ts: datetime

    @property
    def duration_s(self) -> float:
        return (self.end_ts - self.start_ts).total_seconds()


@dataclass(frozen=True, slots=True)
class FocusSession:
    category_key: str
    start_ts: datetime
    end_ts: datetime
    interruption_count: int
    tool_switch_count: int
    attributed_ratio: float
    is_deep_work: bool

    @property
    def duration_s(self) -> float:
        return (self.end_ts - self.start_ts).total_seconds()

    def quality_score(self, goal_alignment_weight: float = 0.0) -> float:
        duration_min = self.duration_s / 60
        switches_per_hour = self.tool_switch_count / max(self.duration_s / 3600, 1 / 3600)
        return (
            0.35 * min(duration_min / 60, 1.0)
            + 0.25 * (1 - self.interruption_count / max(1, duration_min / 15))
            + 0.20 * (1 - min(switches_per_hour / 6, 1.0))
            + 0.20 * goal_alignment_weight
        )


def count_context_switches(sessions: list[ClassifiedSession]) -> tuple[int, int]:
    """Returns (context_switches, tool_switches). A context switch is a category change; a
    same-category app change (IDE<->terminal) is a tool switch, counted separately (§16)."""
    context_switches = 0
    tool_switches = 0
    for prev, nxt in zip(sessions, sessions[1:]):
        if prev.category_key != nxt.category_key:
            context_switches += 1
        elif prev.app_key != nxt.app_key:
            tool_switches += 1
    return context_switches, tool_switches


def _is_interruption(session: ClassifiedSession, focus_category: str) -> bool:
    if session.category_key == focus_category:
        return False
    if session.category_key in COMMUNICATION_CATEGORIES:
        return True
    return timedelta(seconds=session.duration_s) < INTERRUPTION_MAX_DURATION


def build_focus_sessions(
    sessions: list[ClassifiedSession],
    deep_capable_categories: frozenset[str] = frozenset(),
) -> list[FocusSession]:
    """Greedily grows a focus candidate through same-category sessions (tool switches) and
    tolerable interruptions, closing it the moment an interruption exceeds tolerance, then
    keeping the result only if it clears the §16 focus-session thresholds."""
    results: list[FocusSession] = []
    i = 0
    n = len(sessions)

    while i < n:
        anchor = sessions[i]
        block = [anchor]
        interruption_ts: list[datetime] = []
        j = i + 1

        while j < n:
            candidate = sessions[j]
            if candidate.category_key == anchor.category_key:
                block.append(candidate)
                j += 1
                continue

            if not _is_interruption(candidate, anchor.category_key):
                break  # a real, sustained switch away — the block ends here.

            gap_dur = timedelta(seconds=candidate.duration_s)
            too_long = gap_dur > INTERRUPT_TOLERANCE
            clustered = interruption_ts and (candidate.start_ts - interruption_ts[-1]) < INTERRUPTION_CLUSTER_WINDOW
            if too_long or clustered:
                break  # breaks focus continuity per §16's interruption rule.

            interruption_ts.append(candidate.start_ts)
            j += 1  # tolerated: the interruption's own time is excluded from `block` below,
            # which is exactly what keeps it out of attributed/work time.

        start_ts = anchor.start_ts
        end_ts = block[-1].end_ts
        window = timedelta(seconds=(end_ts - start_ts).total_seconds())
        work_s = sum(s.duration_s for s in block)
        attributed_ratio = work_s / window.total_seconds() if window.total_seconds() > 0 else 0.0
        interruption_count = len(interruption_ts)
        tolerated_ok = interruption_count <= FOCUS_TOLERATED_INTERRUPTIONS_PER_15MIN * max(
            1, window / timedelta(minutes=15)
        )
        _ctx_switches, tool_switches = count_context_switches(block)
        switches_per_hour = tool_switches / max(window.total_seconds() / 3600, 1 / 3600)

        if (
            window >= FOCUS_MIN_DURATION
            and tolerated_ok
            and attributed_ratio >= FOCUS_MIN_ATTRIBUTED_RATIO
        ):
            is_deep_work = (
                window >= DEEP_WORK_MIN_DURATION
                and interruption_count <= 1
                and switches_per_hour <= DEEP_WORK_MAX_SWITCH_RATE_PER_HOUR
                and attributed_ratio >= DEEP_WORK_MIN_ATTRIBUTED_RATIO
                and anchor.category_key in deep_capable_categories
            )
            results.append(
                FocusSession(
                    category_key=anchor.category_key,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    interruption_count=interruption_count,
                    tool_switch_count=tool_switches,
                    attributed_ratio=attributed_ratio,
                    is_deep_work=is_deep_work,
                )
            )
            i = j
        else:
            i += 1

    return results


def fragmentation_index(
    switches_per_hour: float,
    focused_time_s: float,
    work_time_s: float,
    median_work_block_min: float,
) -> float:
    """§16 daily fragmentation index (0-1, higher = worse). Caller must only compute this on
    windows with coverage_ratio >= 0.6 (§14.3) — not enforced here since this function has no
    coverage data to check; the daily_metrics pipeline is responsible for the gate."""
    block_term = max(0.0, min(median_work_block_min / 30, 1.0))
    return (
        0.5 * min(switches_per_hour / 12, 1.0)
        + 0.3 * (1 - focused_time_s / max(work_time_s, 1.0))
        + 0.2 * (1 - block_term)
    )
