"""Browser session construction — §11.2, mirroring §14.1's app-session rules exactly (max 4h
session, 3s minimum, 30s same-domain bounce merge) but applied to a browser's `DOMAIN_FOCUS_START`/
`DOMAIN_FOCUS_END` events instead of an Android app's `APP_FOREGROUND`/`APP_BACKGROUND`. A pure
function of `(events)` — no DB, re-runnable, byte-identical output for the same input, exactly
like `timeos.analytics.sessionize.build_sessions`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from timeos.analytics.types import AnalyticsEvent

MAX_SESSION = timedelta(hours=4)
MIN_SESSION = timedelta(seconds=3)
MERGE_GAP = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class BrowserSession:
    domain: str
    start_ts: datetime
    end_ts: datetime
    truncated: bool = False
    merged_from: int = 1

    @property
    def duration_s(self) -> float:
        return (self.end_ts - self.start_ts).total_seconds()


@dataclass
class _OpenDomainSession:
    domain: str
    start_ts: datetime


def build_browser_sessions(events: list[AnalyticsEvent]) -> list[BrowserSession]:
    if not events:
        return []

    raw = _build_raw_sessions(events)
    kept = [s for s in raw if s.duration_s >= MIN_SESSION.total_seconds()]
    return _merge_bounces(kept)


def _build_raw_sessions(events: list[AnalyticsEvent]) -> list[BrowserSession]:
    sessions: list[BrowserSession] = []
    open_session: _OpenDomainSession | None = None

    def close(end_ts: datetime, end_of_stream: bool = False) -> None:
        nonlocal open_session
        if open_session is None:
            return
        # Same rule 3 as app sessions: a domain focus interval left "open" more than 4h almost
        # certainly means a lost DOMAIN_FOCUS_END event (e.g. the browser was killed), not 14
        # real hours of continuous focus on one tab.
        cap_end = open_session.start_ts + MAX_SESSION
        if end_ts > cap_end:
            actual_end, truncated = cap_end, True
        else:
            actual_end, truncated = end_ts, end_of_stream
        sessions.append(
            BrowserSession(
                domain=open_session.domain,
                start_ts=open_session.start_ts,
                end_ts=actual_end,
                truncated=truncated,
            )
        )
        open_session = None

    for event in events:
        match event.type:
            case "DOMAIN_FOCUS_START":
                domain = event.domain
                if domain is None:
                    continue
                if open_session is not None and open_session.domain == domain:
                    continue  # already open; a duplicate/spurious re-focus
                close(event.ts_utc)
                open_session = _OpenDomainSession(domain=domain, start_ts=event.ts_utc)
            case "DOMAIN_FOCUS_END":
                if open_session is not None and open_session.domain == event.domain:
                    close(event.ts_utc)
                # else: stray end for a domain we never saw start — ignore.
            case _:
                pass  # heartbeat/health events: reconciliation's concern, not sessionizing's.

    if open_session is not None:
        # Never extend to "now" — the last event we actually observed is the only evidence we
        # have that the extension was still alive at all (mirrors sessionize.py's own rule 3).
        close(events[-1].ts_utc, end_of_stream=True)

    return sessions


def _merge_bounces(sessions: list[BrowserSession]) -> list[BrowserSession]:
    if not sessions:
        return []

    merged: list[BrowserSession] = [sessions[0]]
    for session in sessions[1:]:
        prev = merged[-1]
        if session.domain == prev.domain and session.start_ts - prev.end_ts < MERGE_GAP:
            merged[-1] = BrowserSession(
                domain=prev.domain,
                start_ts=prev.start_ts,
                end_ts=session.end_ts,
                truncated=session.truncated,
                merged_from=prev.merged_from + session.merged_from,
            )
        else:
            merged.append(session)
    return merged
