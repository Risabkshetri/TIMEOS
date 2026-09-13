"""Device coverage reconstruction — the "honesty engine", §14.3.

Builds a gapless interval cover of a time window so every later metric can be annotated with how
much of its window was actually observed. Never invents activity for time the device wasn't
reporting: a long silence with no shutdown marker is `UNOBSERVED`, not `TRACKED`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from timeos.analytics.types import AnalyticsEvent

DEFAULT_POLL_INTERVAL = timedelta(minutes=15)
IDLE_THRESHOLD = timedelta(minutes=5)

TRACKED = "TRACKED"
IDLE = "IDLE"
DEVICE_OFFLINE = "DEVICE_OFFLINE"
UNOBSERVED = "UNOBSERVED"


@dataclass(frozen=True, slots=True)
class CoverageInterval:
    start_ts: datetime
    end_ts: datetime
    state: str

    @property
    def duration_s(self) -> float:
        return (self.end_ts - self.start_ts).total_seconds()


@dataclass
class _State:
    screen_on: bool = False
    screen_on_since: datetime | None = None
    last_interaction_ts: datetime | None = None
    shutdown: bool = False
    collector_alive: bool = True
    # False until the first event in this window: an untouched default of screen_on=False must
    # NOT be read as a confirmed "screen off, tracked" — before we've heard from the device at
    # all, we have no evidence of anything, which is UNOBSERVED, not an assumed steady state.
    has_signal: bool = False


def build_coverage(
    events: list[AnalyticsEvent],
    window_start: datetime,
    window_end: datetime,
    poll_interval: timedelta = DEFAULT_POLL_INTERVAL,
    idle_threshold: timedelta = IDLE_THRESHOLD,
) -> list[CoverageInterval]:
    if window_end <= window_start:
        return []

    unobserved_gap = 2 * poll_interval
    state = _State()
    raw: list[CoverageInterval] = []
    cursor = window_start

    def flush(start: datetime, end: datetime) -> None:
        if end <= start:
            return
        if not state.collector_alive:
            raw.append(CoverageInterval(start, end, UNOBSERVED))
            return
        if state.shutdown:
            raw.append(CoverageInterval(start, end, DEVICE_OFFLINE))
            return
        if not state.has_signal:
            raw.append(CoverageInterval(start, end, UNOBSERVED))
            return
        if not state.screen_on:
            # Screen-off is a stable, self-confirming state per the spec's table (no time
            # qualifier) — unlike screen-on, it doesn't need renewed evidence to stay valid, so
            # the unobserved-gap check below must never override it. A long, quiet overnight
            # screen-off period is the expected common case, not a sign the collector died.
            raw.append(CoverageInterval(start, end, TRACKED))
            return
        if end - start >= unobserved_gap:
            raw.append(CoverageInterval(start, end, UNOBSERVED))
            return

        anchor = state.last_interaction_ts or state.screen_on_since or start
        idle_at = anchor + idle_threshold
        if idle_at <= start:
            raw.append(CoverageInterval(start, end, IDLE))
        elif idle_at >= end:
            raw.append(CoverageInterval(start, end, TRACKED))
        else:
            raw.append(CoverageInterval(start, idle_at, TRACKED))
            raw.append(CoverageInterval(idle_at, end, IDLE))

    for event in sorted(events, key=lambda e: e.ts_utc):
        if event.ts_utc < window_start or event.ts_utc > window_end:
            continue
        flush(cursor, event.ts_utc)
        cursor = event.ts_utc
        state.has_signal = True

        match event.type:
            case "SCREEN_ON":
                state.screen_on = True
                state.screen_on_since = event.ts_utc
                state.last_interaction_ts = None
            case "SCREEN_OFF" | "DEVICE_LOCK":
                state.screen_on = False
                state.screen_on_since = None
                state.last_interaction_ts = None
            case "DEVICE_SHUTDOWN":
                state.shutdown = True
                state.screen_on = False
            case "DEVICE_STARTUP":
                state.shutdown = False
            case "USER_INTERACTION":
                state.last_interaction_ts = event.ts_utc
            case "COLLECTOR_STOP":
                state.collector_alive = False
            case "COLLECTOR_START":
                state.collector_alive = True
            case _:
                pass  # APP_FOREGROUND/APP_BACKGROUND/DEVICE_UNLOCK/HEALTH don't affect coverage.

    flush(cursor, window_end)
    return _coalesce(raw)


def _coalesce(intervals: list[CoverageInterval]) -> list[CoverageInterval]:
    if not intervals:
        return []
    merged = [intervals[0]]
    for interval in intervals[1:]:
        prev = merged[-1]
        if interval.state == prev.state and interval.start_ts == prev.end_ts:
            merged[-1] = CoverageInterval(prev.start_ts, interval.end_ts, prev.state)
        else:
            merged.append(interval)
    return merged


def coverage_ratio(intervals: list[CoverageInterval], window_seconds: float) -> float:
    """`(tracked + idle) / day_duration` — the ratio that gates every other metric (§14.3)."""
    if window_seconds <= 0:
        return 0.0
    observed = sum(i.duration_s for i in intervals if i.state in (TRACKED, IDLE))
    return observed / window_seconds
