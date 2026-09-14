"""Phase 4 pipeline: recomputes device_coverage/app_sessions/activities/focus_sessions/
daily_metrics/behavioral_patterns for one (user, local_date) from raw_events (§14's
"delete-then-rewrite the affected window" rule — this makes recompute_day idempotent and safe to
call again on a dirty day).

Scope note: coverage/screen-time/unlock-count are aggregated across a user's devices by SUMMING
each device's independently-computed values. This is exactly correct with the single real device
this system has today (the Android phone — desktop is deferred and the browser extension is
Phase 9), but is NOT the true interval UNION §14.3 calls for when two devices are simultaneously
tracked ("phone and laptop can be simultaneously TRACKED... day totals use the union of tracked
intervals"). Implementing and testing that union against a scenario with no second device to
verify it against would be guessing, not engineering — deferred until there's a real multi-device
day to validate against, and flagged here rather than silently approximated.

Pattern promotion (§17: "a pattern stays candidate until >=3 occurrences across >=3 distinct
days") isn't given an exact matching key by the spec, so this module defines one: patterns are
deduplicated per (user, pattern_type, support_key), where support_key is the app_key for
HABITUAL_CHECKING (inherently per-app) and None for the other three detectors (whole-timeline
patterns). `support["_days_seen"]` tracks distinct calendar dates an occurrence was detected on;
`occurrences` counts detections; a row is promoted to 'confirmed' once both are >=3.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.analytics.classify import LearnedPrior, classify_session, load_seed_catalogue
from timeos.analytics.coverage import build_coverage, screen_on_seconds
from timeos.analytics.distraction import (
    PatternOccurrence,
    detect_distraction_burst,
    detect_habitual_checking,
    detect_post_task_avoidance,
    detect_switch_storm,
)
from timeos.analytics.focus import ClassifiedSession, build_focus_sessions
from timeos.analytics.metrics import WORK_CATEGORY_KEYS, compute_daily_metrics
from timeos.analytics.sessionize import AppSession, build_sessions
from timeos.analytics.types import AnalyticsEvent
from timeos.ingest.service import day_window_utc
from timeos.jobs.seed_categories import ensure_system_categories
from timeos.models.activity import Activity
from timeos.models.app_classification import AppClassification
from timeos.models.app_session import AppSession as AppSessionRow
from timeos.models.behavioral_pattern import BehavioralPattern
from timeos.models.daily_metric import DailyMetric
from timeos.models.device_coverage import DeviceCoverage
from timeos.models.focus_session import FocusSessionRow
from timeos.models.raw_event import RawEvent
from timeos.models.user import User

PIPELINE_VERSION = "4.0.0"


async def recompute_day(db: AsyncSession, user: User, local_date: date) -> DailyMetric:
    window_start, window_end = day_window_utc(local_date, user.timezone, user.day_start_hour)
    category_key_to_id = await ensure_system_categories(db, user.id)

    rows = (
        (
            await db.execute(
                select(RawEvent)
                .where(
                    RawEvent.user_id == user.id,
                    RawEvent.ts_utc >= window_start,
                    RawEvent.ts_utc < window_end,
                )
                .order_by(RawEvent.ts_utc)
            )
        )
        .scalars()
        .all()
    )

    events_by_device: dict[uuid.UUID, list[AnalyticsEvent]] = {}
    for row in rows:
        events_by_device.setdefault(row.device_id, []).append(
            AnalyticsEvent(ts_utc=row.ts_utc, type=row.type, payload=row.payload)
        )

    seed_catalogue = load_seed_catalogue()
    priors_by_app = await _load_priors(db, user.id, category_key_to_id)

    device_ids = list(events_by_device.keys())
    await _clear_previous_computation(db, user.id, device_ids, window_start, window_end)

    all_classified: list[ClassifiedSession] = []
    screen_time_s = 0.0
    unlock_count = 0

    for device_id, device_events in events_by_device.items():
        coverage = build_coverage(device_events, window_start, window_end)
        for interval in coverage:
            db.add(
                DeviceCoverage(
                    device_id=device_id,
                    start_ts=interval.start_ts,
                    end_ts=interval.end_ts,
                    state=interval.state,
                )
            )
        screen_time_s += screen_on_seconds(device_events, window_start, window_end)
        unlock_count += sum(1 for e in device_events if e.type == "DEVICE_UNLOCK")

        sessions = build_sessions(device_events)
        for i, session in enumerate(sessions):
            user_rule, learned_prior = priors_by_app.get(session.app_key, (None, None))
            # A small lookahead window is enough for §15.2's L3 "followed by work" check — it
            # only ever looks 15 minutes ahead. Uses L0-L2 only (no following_sessions of its
            # own): resolving what a session further down the timeline eventually gets
            # reclassified to isn't needed just to know whether it currently reads as work.
            category_by_app = {
                s.app_key: _classify_key_only(s, seed_catalogue, priors_by_app)
                for s in sessions[i + 1 : i + 6]
            }
            result = classify_session(
                session,
                user_rule=user_rule,
                learned_prior=learned_prior,
                seed_catalogue=seed_catalogue,
                following_sessions=sessions[i + 1 :],
                category_by_app=category_by_app,
            )
            classified = ClassifiedSession(
                app_key=session.app_key,
                category_key=result.category_key,
                start_ts=session.start_ts,
                end_ts=session.end_ts,
            )
            all_classified.append(classified)

            app_session_row = AppSessionRow(
                user_id=user.id,
                device_id=device_id,
                app_key=session.app_key,
                start_ts=session.start_ts,
                end_ts=session.end_ts,
                duration_s=session.duration_s,
                interaction_count=session.interaction_count,
                source_event_ids=[],  # provenance to individual raw_events not plumbed through
            )
            db.add(app_session_row)
            await db.flush()

            db.add(
                Activity(
                    user_id=user.id,
                    start_ts=session.start_ts,
                    end_ts=session.end_ts,
                    duration_s=session.duration_s,
                    category_id=category_key_to_id[result.category_key],
                    confidence=result.confidence,
                    classification_source=result.source,
                    evidence={"rules": list(result.evidence)},
                    devices=[str(device_id)],
                    source_session_ids=[app_session_row.id],
                )
            )

    all_classified.sort(key=lambda s: s.start_ts)
    focus_sessions = build_focus_sessions(
        all_classified, deep_capable_categories=WORK_CATEGORY_KEYS
    )
    for focus_session in focus_sessions:
        db.add(
            FocusSessionRow(
                user_id=user.id,
                category_id=category_key_to_id[focus_session.category_key],
                start_ts=focus_session.start_ts,
                end_ts=focus_session.end_ts,
                duration_s=focus_session.duration_s,
                interruption_count=focus_session.interruption_count,
                tool_switch_count=focus_session.tool_switch_count,
                attributed_ratio=focus_session.attributed_ratio,
                is_deep_work=focus_session.is_deep_work,
            )
        )

    bursts = detect_distraction_burst(all_classified, WORK_CATEGORY_KEYS)

    metrics = compute_daily_metrics(
        window_start=window_start,
        window_end=window_end,
        coverage_intervals=[
            i for device_events in events_by_device.values()
            for i in build_coverage(device_events, window_start, window_end)
        ],
        screen_time_s=screen_time_s,
        classified_sessions=all_classified,
        focus_sessions=focus_sessions,
        distraction_bursts=bursts,
        unlock_count=unlock_count,
    )

    all_occurrences = [
        *bursts,
        *detect_habitual_checking(all_classified),
        *detect_switch_storm(all_classified),
        *detect_post_task_avoidance(all_classified, WORK_CATEGORY_KEYS),
    ]
    for occurrence in all_occurrences:
        await _record_pattern_occurrence(db, user.id, occurrence, local_date)

    existing = await db.get(DailyMetric, (user.id, local_date))
    row = DailyMetric(
        user_id=user.id,
        local_date=local_date,
        day_start_utc=window_start,
        day_end_utc=window_end,
        duration_seconds=metrics.duration_seconds,
        observed_s=metrics.observed_s,
        tracked_s=metrics.tracked_s,
        idle_s=metrics.idle_s,
        unobserved_s=metrics.unobserved_s,
        offline_s=metrics.offline_s,
        coverage_ratio=metrics.coverage_ratio,
        screen_time_s=metrics.screen_time_s,
        active_time_s=metrics.active_time_s,
        deep_work_s=metrics.deep_work_s,
        focused_work_s=metrics.focused_work_s,
        shallow_work_s=metrics.shallow_work_s,
        communication_s=metrics.communication_s,
        learning_s=metrics.learning_s,
        entertainment_s=metrics.entertainment_s,
        social_s=metrics.social_s,
        distraction_s=metrics.distraction_s,
        unknown_s=metrics.unknown_s,
        unknown_ratio=metrics.unknown_ratio,
        context_switches=metrics.context_switches,
        switches_per_hour=metrics.switches_per_hour,
        interruptions=metrics.interruptions,
        fragmentation_index=metrics.fragmentation_index,
        longest_focus_s=metrics.longest_focus_s,
        avg_focus_s=metrics.avg_focus_s,
        focus_session_count=metrics.focus_session_count,
        unlock_count=metrics.unlock_count,
        tz_transition=False,  # not yet derived from raw tz_offset_min — see module docstring
        revised=existing is not None,
        pipeline_version=PIPELINE_VERSION,
    )
    if existing is not None:
        await db.delete(existing)
        await db.flush()
    db.add(row)

    await db.commit()
    return row


def _classify_key_only(
    session: AppSession,
    seed_catalogue: dict,
    priors_by_app: dict[str, tuple[str | None, LearnedPrior | None]],
) -> str:
    user_rule, learned_prior = priors_by_app.get(session.app_key, (None, None))
    return classify_session(
        session, user_rule=user_rule, learned_prior=learned_prior, seed_catalogue=seed_catalogue
    ).category_key


async def _load_priors(
    db: AsyncSession, user_id: uuid.UUID, category_key_to_id: dict[str, uuid.UUID]
) -> dict[str, tuple[str | None, LearnedPrior | None]]:
    """app_key -> (user_rule_category_key, learned_prior). Both are always None today — nothing
    populates app_classifications with source='user'/'learned' until Phase 6/7's correction loop
    exists — but the read is real, so classification starts honoring corrections immediately once
    that loop lands, with no change needed here."""
    rows = (
        (await db.execute(select(AppClassification).where(AppClassification.user_id == user_id)))
        .scalars()
        .all()
    )
    id_to_key = {v: k for k, v in category_key_to_id.items()}
    result: dict[str, tuple[str | None, LearnedPrior | None]] = {}
    for row in rows:
        category_key = id_to_key.get(row.category_id)
        if row.source == "user":
            result[row.app_key] = (category_key, None)
        elif row.source == "learned":
            result[row.app_key] = (
                None,
                LearnedPrior(category_key or "unknown", float(row.confidence), row.sample_count),
            )
    return result


async def _clear_previous_computation(
    db: AsyncSession,
    user_id: uuid.UUID,
    device_ids: list[uuid.UUID],
    window_start: datetime,
    window_end: datetime,
) -> None:
    if device_ids:
        await db.execute(
            delete(DeviceCoverage).where(
                DeviceCoverage.device_id.in_(device_ids),
                DeviceCoverage.start_ts >= window_start,
                DeviceCoverage.start_ts < window_end,
            )
        )
        await db.execute(
            delete(AppSessionRow).where(
                AppSessionRow.device_id.in_(device_ids),
                AppSessionRow.start_ts >= window_start,
                AppSessionRow.start_ts < window_end,
            )
        )
    await db.execute(
        delete(Activity).where(
            Activity.user_id == user_id,
            Activity.start_ts >= window_start,
            Activity.start_ts < window_end,
        )
    )
    await db.execute(
        delete(FocusSessionRow).where(
            FocusSessionRow.user_id == user_id,
            FocusSessionRow.start_ts >= window_start,
            FocusSessionRow.start_ts < window_end,
        )
    )


async def _record_pattern_occurrence(
    db: AsyncSession, user_id: uuid.UUID, occurrence: PatternOccurrence, local_date: date
) -> None:
    is_habitual_checking = occurrence.pattern_type == "HABITUAL_CHECKING"
    support_key = occurrence.support.get("app_key") if is_habitual_checking else None

    existing = (
        (
            await db.execute(
                select(BehavioralPattern).where(
                    BehavioralPattern.user_id == user_id,
                    BehavioralPattern.pattern_type == occurrence.pattern_type,
                )
            )
        )
        .scalars()
        .all()
    )
    match = next(
        (p for p in existing if p.support.get("_match_key") == support_key),
        None,
    )

    day_str = local_date.isoformat()
    if match is None:
        pattern = BehavioralPattern(
            user_id=user_id,
            pattern_type=occurrence.pattern_type,
            first_seen=occurrence.start_ts,
            last_seen=occurrence.end_ts,
            occurrences=1,
            strength=occurrence.strength,
            support={**occurrence.support, "_match_key": support_key, "_days_seen": [day_str]},
            status="candidate",
        )
        db.add(pattern)
        return

    days_seen = set(match.support.get("_days_seen", []))
    days_seen.add(day_str)
    match.occurrences += 1
    match.last_seen = occurrence.end_ts
    match.strength = max(match.strength, occurrence.strength)
    match.support = {**match.support, **occurrence.support, "_days_seen": sorted(days_seen)}
    if match.occurrences >= 3 and len(days_seen) >= 3:
        match.status = "confirmed"
