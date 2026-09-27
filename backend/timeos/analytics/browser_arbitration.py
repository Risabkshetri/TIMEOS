"""§11.4's cross-browser arbitration: "Sort all browser-sourced intervals by start time across
all three devices. Where intervals from different `browser_family` values overlap, the
later-starting interval wins from its start instant and the earlier one is truncated... Total
browser time is the union of the arbitrated intervals, never the sum."

Why this is needed at all: each browser's extension independently observes its OWN focus
gain/loss, with no coordination possible between sandboxed extensions (§11.4's own framing). Focus
events are delivered asynchronously and each browser has its own clock-of-record, so adjacent
intervals from DIFFERENT browsers can overlap by a few hundred milliseconds, and a browser killed
without a focus-loss event can leave its interval open until the next heartbeat truncates it
(`browser_sessionize.py`'s own end-of-stream rule). This module resolves those overlaps
deterministically; it is a pure function of `(sessions)` — no DB — like every other analytics
module in this package.

A LATER start winning (rather than an EARLIER close) is deliberate: a focus-GAIN event is a more
reliable signal than a focus-LOSS event, because the loss event for the browser that's about to
lose focus may never arrive (§11.4).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ArbitrationInterval:
    """One browser's already-sessionized domain-focus interval, tagged with the `browser_family`
    it came from — arbitration only ever compares intervals from DIFFERENT families; two
    intervals from the SAME family never need arbitrating against each other, since a single
    browser's own sessionizer already guarantees its own timeline doesn't overlap itself."""

    browser_family: str
    domain: str
    start_ts: datetime
    end_ts: datetime
    truncated: bool = False


def arbitrate_browser_sessions(
    sessions: list[ArbitrationInterval],
) -> list[ArbitrationInterval]:
    """Returns the arbitrated interval set: for any two overlapping intervals from different
    `browser_family` values, the later-starting one is kept whole and the earlier one is
    truncated to end exactly at the later one's start. Zero-or-negative-duration results (a fully
    swallowed earlier interval) are dropped rather than kept as a degenerate row."""
    if not sessions:
        return []

    ordered = sorted(sessions, key=lambda s: s.start_ts)
    accepted: list[ArbitrationInterval] = []

    for session in ordered:
        adjusted: list[ArbitrationInterval] = []
        for prior in accepted:
            if prior.browser_family != session.browser_family and prior.end_ts > session.start_ts:
                adjusted.append(replace(prior, end_ts=session.start_ts, truncated=True))
            else:
                adjusted.append(prior)
        accepted = adjusted
        accepted.append(session)

    return [s for s in accepted if s.end_ts > s.start_ts]


def union_duration_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    """The total duration covered by a set of (possibly overlapping) intervals, counted once each
    — never the sum of their individual durations. Used both to report total arbitrated browser
    time and, independently of whether `arbitrate_browser_sessions` itself has a bug, to make the
    "browser time never exceeds screen-on time" property genuinely airtight: even a residual
    overlap here still can't be double-counted."""
    if not intervals:
        return 0.0

    ordered = sorted(intervals, key=lambda pair: pair[0])
    total = 0.0
    current_start, current_end = ordered[0]

    for start, end in ordered[1:]:
        if start > current_end:
            total += (current_end - current_start).total_seconds()
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)

    total += (current_end - current_start).total_seconds()
    return total
