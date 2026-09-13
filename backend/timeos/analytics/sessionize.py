"""App session construction — docs/TIMEOS_ENGINEERING_SPEC.md §14.1.

A pure function of `(events, config)`: same input always produces the same output, so the
sessionizer can be re-run over a window (e.g. after a dirty-day recompute) and produce
byte-identical results. It never looks at wall-clock "now" — only at the events it's given, which
is what makes rule 3 (never extend an unterminated session to the present) enforceable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from timeos.analytics.types import AnalyticsEvent

MAX_SESSION = timedelta(hours=4)
MIN_SESSION = timedelta(seconds=3)
MERGE_GAP = timedelta(seconds=30)

_CLOSES_ANY_OPEN_SESSION = frozenset(
    {"SCREEN_OFF", "DEVICE_LOCK", "DEVICE_SHUTDOWN", "COLLECTOR_STOP"}
)


@dataclass(frozen=True, slots=True)
class AppSession:
    app_key: str
    start_ts: datetime
    end_ts: datetime
    interaction_count: int
    truncated: bool = False
    # Number of raw open/close cycles collapsed into this session by the rule-5 same-app-bounce
    # merge. 1 means no merge happened. Kept so a later context-switch count still knows a switch
    # away-and-back occurred even though it's now one session (§14.1 rule 5's explicit carve-out).
    merged_from: int = 1

    @property
    def duration_s(self) -> float:
        return (self.end_ts - self.start_ts).total_seconds()


@dataclass
class _OpenSession:
    app_key: str
    start_ts: datetime
    interaction_count: int = 0


def build_sessions(events: list[AnalyticsEvent]) -> list[AppSession]:
    if not events:
        return []

    raw = _build_raw_sessions(events)
    kept = [s for s in raw if s.duration_s >= MIN_SESSION.total_seconds()]
    return _merge_bounces(kept)


def _build_raw_sessions(events: list[AnalyticsEvent]) -> list[AppSession]:
    sessions: list[AppSession] = []
    open_session: _OpenSession | None = None

    def close(end_ts: datetime, end_of_stream: bool = False) -> None:
        nonlocal open_session
        if open_session is None:
            return
        # Rule 3's cap applies regardless of *why* we're closing: a session still open more than
        # 4h after it started is capped there even if the closing evidence (e.g. another app's
        # foreground) arrives much later — that gap almost certainly means a lost background
        # event, not 14 real hours in one app.
        cap_end = open_session.start_ts + MAX_SESSION
        if end_ts > cap_end:
            actual_end, truncated = cap_end, True
        else:
            actual_end, truncated = end_ts, end_of_stream
        sessions.append(
            AppSession(
                app_key=open_session.app_key,
                start_ts=open_session.start_ts,
                end_ts=actual_end,
                interaction_count=open_session.interaction_count,
                truncated=truncated,
            )
        )
        open_session = None

    for event in events:
        match event.type:
            case "APP_FOREGROUND":
                pkg = event.package
                if pkg is None:
                    continue
                if open_session is not None and open_session.app_key == pkg:
                    continue  # already open; a duplicate/spurious re-foreground
                close(event.ts_utc)
                open_session = _OpenSession(app_key=pkg, start_ts=event.ts_utc)
            case "APP_BACKGROUND":
                if open_session is not None and open_session.app_key == event.package:
                    close(event.ts_utc)
                # else: stray background for an app we never saw foreground — ignore.
            case t if t in _CLOSES_ANY_OPEN_SESSION:
                close(event.ts_utc)
            case "USER_INTERACTION":
                if open_session is not None:
                    open_session.interaction_count += 1
            case _:
                pass  # SCREEN_ON / DEVICE_UNLOCK / DEVICE_STARTUP / HEALTH: coverage's concern.

    if open_session is not None:
        # Rule 3: never extend to "now" — the last event we actually observed is the only
        # evidence we have that the device was still alive at all.
        close(events[-1].ts_utc, end_of_stream=True)

    return sessions


def _merge_bounces(sessions: list[AppSession]) -> list[AppSession]:
    if not sessions:
        return []

    merged: list[AppSession] = [sessions[0]]
    for session in sessions[1:]:
        prev = merged[-1]
        if session.app_key == prev.app_key and session.start_ts - prev.end_ts < MERGE_GAP:
            merged[-1] = AppSession(
                app_key=prev.app_key,
                start_ts=prev.start_ts,
                end_ts=session.end_ts,
                interaction_count=prev.interaction_count + session.interaction_count,
                truncated=session.truncated,
                merged_from=prev.merged_from + session.merged_from,
            )
        else:
            merged.append(session)
    return merged
