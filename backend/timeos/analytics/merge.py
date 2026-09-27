"""Cross-device timeline merge — §14.3's "honesty engine" extended across devices, §38 Phase 10.

Turns each device's own gapless coverage timeline (`timeos.analytics.coverage.build_coverage`)
into ONE unified picture: day totals use the UNION of observed (`TRACKED`/`IDLE`) intervals across
devices — two devices both reporting `TRACKED` for the same minute is one observed minute, not
two — and genuine overlap becomes its own signal (`dual_device_s`) rather than being silently
discarded or double-counted. A pure function of `(intervals_by_device)` — no DB — matching every
other analytics module in this package.

Written as an N-way sweep-line, not a two-device special case, so a third source (Phase 12's
desktop collector) needs no rework here (§38 Phase 10's own stated input note).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from timeos.analytics.browser_arbitration import union_duration_seconds
from timeos.analytics.coverage import IDLE, TRACKED, CoverageInterval

OBSERVED_STATES = frozenset({TRACKED, IDLE})

# §38 Phase 10: "cross-device activity clustering (phone + laptop as one work block)". No exact
# gap is given by the spec (the same kind of silence as §18's uncertainty-range formula, §21's own
# gap-size choices, etc. elsewhere in this codebase) — 5 minutes mirrors sessionize.py's own
# same-app MERGE_GAP-adjacent reasoning: short enough that it's clearly the same stretch of work,
# long enough to survive a brief context switch (checking a message, glancing at a notification)
# without losing the cluster.
CLUSTER_GAP = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class UnifiedCoverageResult:
    observed_s: float
    dual_device_s: float


def _observed_spans(intervals: list[CoverageInterval]) -> list[tuple[datetime, datetime]]:
    return [(i.start_ts, i.end_ts) for i in intervals if i.state in OBSERVED_STATES]


def merge_device_coverage(
    intervals_by_device: dict[str, list[CoverageInterval]],
) -> UnifiedCoverageResult:
    """Sweep-line union across however many devices are given.

    `observed_s` is the UNION of every device's observed time — it can never exceed the span of
    time the inputs cover (§33's own property-test requirement: unified observed time never
    exceeds day duration). `dual_device_s` is the portion of that union where 2+ devices were
    simultaneously observed — itself never exceeding `observed_s` — §14.3: "Simultaneous phone +
    laptop use is itself a signal and is recorded as `dual_device_s`."
    """
    boundaries: list[tuple[datetime, int]] = []
    for intervals in intervals_by_device.values():
        for start, end in _observed_spans(intervals):
            if end <= start:
                continue
            boundaries.append((start, 1))
            boundaries.append((end, -1))

    if not boundaries:
        return UnifiedCoverageResult(observed_s=0.0, dual_device_s=0.0)

    boundaries.sort(key=lambda b: b[0])

    observed_s = 0.0
    dual_device_s = 0.0
    active = 0
    cursor = boundaries[0][0]

    for ts, delta in boundaries:
        if ts > cursor and active > 0:
            span = (ts - cursor).total_seconds()
            observed_s += span
            if active >= 2:
                dual_device_s += span
        active += delta
        cursor = ts

    return UnifiedCoverageResult(observed_s=observed_s, dual_device_s=dual_device_s)


@dataclass(frozen=True, slots=True)
class DeviceActivity:
    """One already-classified activity from ONE device — the input to cross-device clustering.
    Deliberately not `timeos.models.activity.Activity` itself: this module stays DB-free, like
    every other analytics module, and only needs the fields clustering actually reasons about."""

    device_id: uuid.UUID
    category_key: str
    start_ts: datetime
    end_ts: datetime
    duration_s: float
    confidence: float
    source_session_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True, slots=True)
class ClusteredActivity:
    category_key: str
    start_ts: datetime
    end_ts: datetime
    duration_s: float  # the UNION of the constituent spans, never their sum
    confidence: float
    device_ids: tuple[uuid.UUID, ...]
    source_session_ids: tuple[uuid.UUID, ...]
    is_cross_device: bool


def _overlaps_or_within_gap(a: DeviceActivity, b: DeviceActivity, gap: timedelta) -> bool:
    latest_start = max(a.start_ts, b.start_ts)
    earliest_end = min(a.end_ts, b.end_ts)
    if latest_start <= earliest_end:
        return True  # genuinely overlapping
    if a.end_ts <= b.start_ts:
        return (b.start_ts - a.end_ts) <= gap
    return (a.start_ts - b.end_ts) <= gap


def cluster_cross_device_activities(
    activities: list[DeviceActivity], gap: timedelta = CLUSTER_GAP
) -> list[ClusteredActivity]:
    """§38 Phase 10: "cross-device activity clustering (phone + laptop as one work block)".
    Activities from DIFFERENT devices sharing the same `category_key`, whose intervals overlap or
    are within `gap` of each other, merge into one `ClusteredActivity` spanning both devices.

    Clustering is greedy (each activity joins the first existing cluster any of its members
    matches against) rather than a full transitive-closure union-find — a documented
    simplification proportional to personal-scale activity counts (tens per day, not thousands),
    where a pathological three-way near-miss is vanishingly unlikely to matter in practice.
    """
    if not activities:
        return []

    ordered = sorted(activities, key=lambda a: a.start_ts)
    clusters: list[list[DeviceActivity]] = []

    for activity in ordered:
        joined = False
        for cluster in clusters:
            if any(
                member.category_key == activity.category_key
                and member.device_id != activity.device_id
                and _overlaps_or_within_gap(member, activity, gap)
                for member in cluster
            ):
                cluster.append(activity)
                joined = True
                break
        if not joined:
            clusters.append([activity])

    results: list[ClusteredActivity] = []
    for cluster in clusters:
        if len(cluster) == 1:
            a = cluster[0]
            results.append(
                ClusteredActivity(
                    category_key=a.category_key,
                    start_ts=a.start_ts,
                    end_ts=a.end_ts,
                    duration_s=a.duration_s,
                    confidence=a.confidence,
                    device_ids=(a.device_id,),
                    source_session_ids=a.source_session_ids,
                    is_cross_device=False,
                )
            )
            continue

        total_weight = sum(m.duration_s for m in cluster)
        confidence = (
            sum(m.confidence * m.duration_s for m in cluster) / total_weight
            if total_weight > 0
            else 0.0
        )
        results.append(
            ClusteredActivity(
                category_key=cluster[0].category_key,
                start_ts=min(m.start_ts for m in cluster),
                end_ts=max(m.end_ts for m in cluster),
                duration_s=union_duration_seconds([(m.start_ts, m.end_ts) for m in cluster]),
                confidence=confidence,
                device_ids=tuple(dict.fromkeys(m.device_id for m in cluster)),
                source_session_ids=tuple(sid for m in cluster for sid in m.source_session_ids),
                is_cross_device=True,
            )
        )

    return results
