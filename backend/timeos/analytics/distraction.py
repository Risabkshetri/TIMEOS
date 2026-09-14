"""Distraction engine — §17. "Distraction is a pattern in the sequence, never a property of an
app": every detector here looks at the SHAPE of a classified-session timeline, never at which
app is involved.

Only 4 of the spec's 7 v1 detectors are implemented in this phase — the other 3 need
infrastructure that doesn't exist yet and can't be faked without inventing data:

- TASK_START_AVOIDANCE needs `working_hours` (Phase 6) and >=4-of-7-days history.
- TIME_OF_DAY_SINK needs a 30-day rolling mean/stddev per time-of-day slot — that's rolling
  baselines, which is explicitly Phase 11's job ("Historical Behavioural Intelligence"), not
  Phase 4's.
- LATE_NIGHT_DRIFT needs a declared wind-down hour (Phase 6 settings) and >=3x/week history.

Each detector here returns per-day `PatternOccurrence`s; promoting an occurrence to a persisted
`behavioral_patterns` row with `status='confirmed'` only after >=3 occurrences across >=3 distinct
days (§17) is the pipeline's job, not this module's — a single day has no way to know how many
distinct days a pattern has shown up on.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

from timeos.analytics.focus import ClassifiedSession, count_context_switches

DISTRACTION_BURST_WINDOW = timedelta(minutes=15)
DISTRACTION_BURST_MIN_SESSIONS = 3
DISTRACTION_BURST_MIN_TOTAL = timedelta(minutes=5)

HABITUAL_CHECKING_WINDOW = timedelta(minutes=30)
HABITUAL_CHECKING_MIN_OPENS = 5
HABITUAL_CHECKING_MAX_MEDIAN = timedelta(seconds=90)

SWITCH_STORM_WINDOW = timedelta(minutes=20)
SWITCH_STORM_MIN_SWITCHES = 20

POST_TASK_WORK_MIN_DURATION = timedelta(minutes=20)
POST_TASK_FOLLOWUP_WINDOW = timedelta(minutes=3)
POST_TASK_FOLLOWUP_MIN_DURATION = timedelta(minutes=10)
POST_TASK_RESUME_WINDOW = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class PatternOccurrence:
    pattern_type: str
    start_ts: datetime
    end_ts: datetime
    strength: float
    support: dict


def detect_distraction_burst(
    sessions: list[ClassifiedSession], work_categories: frozenset[str]
) -> list[PatternOccurrence]:
    non_work = [s for s in sessions if s.category_key not in work_categories]
    occurrences: list[PatternOccurrence] = []
    left = 0
    n = len(non_work)

    while left < n:
        right = left
        while (
            right + 1 < n
            and non_work[right + 1].start_ts - non_work[left].start_ts <= DISTRACTION_BURST_WINDOW
        ):
            right += 1
        window_sessions = non_work[left : right + 1]
        total = sum((s.duration_s for s in window_sessions), 0.0)
        if len(window_sessions) >= DISTRACTION_BURST_MIN_SESSIONS and total >= DISTRACTION_BURST_MIN_TOTAL.total_seconds():
            occurrences.append(
                PatternOccurrence(
                    pattern_type="DISTRACTION_BURST",
                    start_ts=window_sessions[0].start_ts,
                    end_ts=window_sessions[-1].end_ts,
                    strength=min(total / (2 * DISTRACTION_BURST_MIN_TOTAL.total_seconds()), 1.0),
                    support={"session_count": len(window_sessions), "total_s": total},
                )
            )
            left = right + 1  # don't re-report the same cluster piecemeal
        else:
            left += 1

    return occurrences


def detect_habitual_checking(sessions: list[ClassifiedSession]) -> list[PatternOccurrence]:
    by_app: dict[str, list[ClassifiedSession]] = {}
    for s in sessions:
        by_app.setdefault(s.app_key, []).append(s)

    occurrences: list[PatternOccurrence] = []
    for app_key, app_sessions in by_app.items():
        app_sessions.sort(key=lambda s: s.start_ts)
        left = 0
        n = len(app_sessions)
        while left < n:
            right = left
            while (
                right + 1 < n
                and app_sessions[right + 1].start_ts - app_sessions[left].start_ts <= HABITUAL_CHECKING_WINDOW
            ):
                right += 1
            window_sessions = app_sessions[left : right + 1]
            median = statistics.median(s.duration_s for s in window_sessions)
            if (
                len(window_sessions) >= HABITUAL_CHECKING_MIN_OPENS
                and median <= HABITUAL_CHECKING_MAX_MEDIAN.total_seconds()
            ):
                occurrences.append(
                    PatternOccurrence(
                        pattern_type="HABITUAL_CHECKING",
                        start_ts=window_sessions[0].start_ts,
                        end_ts=window_sessions[-1].end_ts,
                        strength=min(len(window_sessions) / (2 * HABITUAL_CHECKING_MIN_OPENS), 1.0),
                        support={"app_key": app_key, "open_count": len(window_sessions), "median_s": median},
                    )
                )
                left = right + 1
            else:
                left += 1

    return occurrences


def detect_switch_storm(sessions: list[ClassifiedSession]) -> list[PatternOccurrence]:
    occurrences: list[PatternOccurrence] = []
    n = len(sessions)
    left = 0

    while left < n:
        right = left
        while (
            right + 1 < n
            and sessions[right + 1].start_ts - sessions[left].start_ts <= SWITCH_STORM_WINDOW
        ):
            right += 1
        window_sessions = sessions[left : right + 1]
        context_switches, _tool_switches = count_context_switches(window_sessions)
        if context_switches >= SWITCH_STORM_MIN_SWITCHES:
            occurrences.append(
                PatternOccurrence(
                    pattern_type="SWITCH_STORM",
                    start_ts=window_sessions[0].start_ts,
                    end_ts=window_sessions[-1].end_ts,
                    strength=min(context_switches / (2 * SWITCH_STORM_MIN_SWITCHES), 1.0),
                    support={"context_switches": context_switches},
                )
            )
            left = right + 1
        else:
            left += 1

    return occurrences


def detect_post_task_avoidance(
    sessions: list[ClassifiedSession], work_categories: frozenset[str]
) -> list[PatternOccurrence]:
    occurrences: list[PatternOccurrence] = []

    for i, session in enumerate(sessions):
        if session.category_key not in work_categories:
            continue
        if timedelta(seconds=session.duration_s) < POST_TASK_WORK_MIN_DURATION:
            continue

        # "non-work >=10 min begins within 3 min" reads as the very next thing that happens,
        # not any later non-work session — if work resumes or continues immediately, there's
        # nothing to detect here regardless of what happens further down the timeline.
        if i + 1 >= len(sessions):
            continue
        followup = sessions[i + 1]
        if followup.category_key in work_categories:
            continue
        if followup.start_ts - session.end_ts > POST_TASK_FOLLOWUP_WINDOW:
            continue
        if timedelta(seconds=followup.duration_s) < POST_TASK_FOLLOWUP_MIN_DURATION:
            continue

        resume_deadline = session.end_ts + POST_TASK_RESUME_WINDOW
        resumed = any(
            other.category_key in work_categories and other.start_ts <= resume_deadline
            for other in sessions[i + 1 :]
        )
        if resumed:
            continue

        occurrences.append(
            PatternOccurrence(
                pattern_type="POST_TASK_AVOIDANCE",
                start_ts=session.end_ts,
                end_ts=followup.end_ts,
                strength=0.7,
                support={
                    "work_session_duration_s": session.duration_s,
                    "followup_category": followup.category_key,
                    "followup_duration_s": followup.duration_s,
                },
            )
        )

    return occurrences
