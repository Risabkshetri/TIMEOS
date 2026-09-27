"""Phase 4 pipeline: recomputes device_coverage/app_sessions/activities/focus_sessions/
daily_metrics/behavioral_patterns for one (user, local_date) from raw_events (§14's
"delete-then-rewrite the affected window" rule — this makes recompute_day idempotent and safe to
call again on a dirty day).

Scope note: coverage/screen-time/unlock-count are aggregated across a user's non-browser devices
by SUMMING each device's independently-computed values (desktop is still deferred). This is
exactly correct with a single real Android device, and is now unioned rather than summed once a
browser device is also present (§38 Phase 10, via `timeos.analytics.merge.merge_device_coverage`)
— but still just summed across multiple simultaneous NON-browser devices (e.g. two Android
phones), since there is still no real multi-Android-device day to validate that union against.
Flagged here rather than silently approximated.

Browser devices (§38 Phase 9) are sessionized separately into `browser_sessions`, arbitrated
across all of a user's browser devices at once (§11.4). §38 Phase 10 folds their result into the
rest of the day: a synthesized TRACKED-only virtual coverage stream feeds the cross-device
coverage union (`observed_s`/`coverage_ratio`/`dual_device_s` on `daily_metrics`), each arbitrated
browser session is classified against `domain_priors.yaml` and contributes to `classified_sessions`
(so browser time counts toward category-time totals like `communication_s`), and its resulting
`DeviceActivity` is combined with Android's own per-session activities and run through
`cluster_cross_device_activities` before `Activity` rows are persisted — so a genuinely
cross-device stretch of work (phone + laptop, same category, overlapping or nearly so) becomes one
`Activity` row spanning both devices instead of two independent ones. `focus_sessions`/distraction
detection stay Android-only (see `cluster_cross_device_activities`' docstring and this function's
own comments for why: focus/switch semantics assume one continuous stream of attention, and two
concurrently-active devices are not a sequence).

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

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.analytics.browser_arbitration import ArbitrationInterval, arbitrate_browser_sessions
from timeos.analytics.browser_sessionize import build_browser_sessions
from timeos.analytics.classify import (
    LearnedPrior,
    classify_session,
    load_domain_seed_catalogue,
    load_seed_catalogue,
)
from timeos.analytics.coverage import TRACKED, CoverageInterval, build_coverage, screen_on_seconds
from timeos.analytics.distraction import (
    PatternOccurrence,
    detect_distraction_burst,
    detect_habitual_checking,
    detect_post_task_avoidance,
    detect_switch_storm,
)
from timeos.analytics.focus import ClassifiedSession, build_focus_sessions
from timeos.analytics.merge import (
    DeviceActivity,
    cluster_cross_device_activities,
    merge_device_coverage,
)
from timeos.analytics.metrics import WORK_CATEGORY_KEYS, compute_daily_metrics
from timeos.analytics.sessionize import AppSession, build_sessions
from timeos.analytics.types import AnalyticsEvent
from timeos.ingest.service import day_window_utc
from timeos.jobs.seed_categories import ensure_system_categories
from timeos.models.activity import Activity
from timeos.models.app_classification import AppClassification
from timeos.models.app_session import AppSession as AppSessionRow
from timeos.models.behavioral_pattern import BehavioralPattern
from timeos.models.browser_session import BrowserSession
from timeos.models.daily_metric import DailyMetric
from timeos.models.device import Device
from timeos.models.device_coverage import DeviceCoverage
from timeos.models.dirty_day import DirtyDay
from timeos.models.focus_session import FocusSessionRow
from timeos.models.raw_event import RawEvent
from timeos.models.user import User

PIPELINE_VERSION = "4.0.0"


async def recompute_day(db: AsyncSession, user: User, local_date: date) -> DailyMetric:
    # Serializes concurrent recomputes of the SAME (user, date) — e.g. two dashboard pages
    # loading at once, both finding no cached row yet. Without this, two overlapping delete-then-
    # insert cycles can interleave (one's DELETE, then both INSERT the same coverage interval)
    # and trip device_coverage's exclusion constraint with a real IntegrityError, caught live
    # against the real dashboard.
    #
    # Deliberately NOT acquired via `db` (the ORM session passed in): this function calls
    # ensure_system_categories, which commits internally, and SQLAlchemy releases a session's
    # physical connection back to the pool on commit — with NullPool (used in tests) that means
    # the underlying TCP connection actually closes, which makes Postgres drop any session-scoped
    # advisory lock held on it automatically. A lock acquired on `db`'s connection would silently
    # evaporate the moment ensure_system_categories commits, long before the real coverage/session
    # work happens — caught by a concurrency regression test that still failed with the lock
    # wired that way. Held instead on its own independent connection via `import timeos.db as
    # db_module` (not a top-level `from timeos.db import engine`, which would capture a stale
    # engine reference from before tests rebind it — see conftest.py's
    # _use_nullpool_engine_for_tests) for this function's entire duration, so it's immune to
    # whatever `db` does with its own transactions.
    import timeos.db as db_module

    lock_key = f"timeos.recompute_day:{user.id}:{local_date.isoformat()}"
    async with db_module.engine.connect() as lock_conn:
        await lock_conn.execute(
            text("SELECT pg_advisory_lock(hashtext(:key)::bigint)"), {"key": lock_key}
        )
        try:
            return await _recompute_day_locked(db, user, local_date)
        finally:
            await lock_conn.execute(
                text("SELECT pg_advisory_unlock(hashtext(:key)::bigint)"), {"key": lock_key}
            )


async def ensure_day_computed(db: AsyncSession, user: User, local_date: date) -> DailyMetric:
    """The lazy-compute-on-read pattern timeos/api/days.py's read endpoints all share (see that
    module's docstring for why there's no scheduled pipeline yet): reuse an up-to-date
    `daily_metrics` row if one exists, recompute only when it's missing or `dirty_days` says
    `local_date` changed since it was last computed. Factored out here (rather than staying
    private to days.py) so §18's goal-alignment endpoint can ensure the same freshness guarantee
    over a whole window without duplicating the dirty-check."""
    existing = await db.get(DailyMetric, (user.id, local_date))
    dirty = await db.get(DirtyDay, (user.id, local_date))
    if existing is not None and dirty is None:
        return existing
    return await recompute_day(db, user, local_date)


async def _recompute_day_locked(db: AsyncSession, user: User, local_date: date) -> DailyMetric:
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

    device_rows = (
        (await db.execute(select(Device).where(Device.id.in_(device_ids))))
        .scalars()
        .all()
        if device_ids
        else []
    )
    devices_by_id = {d.id: d for d in device_rows}

    all_classified: list[ClassifiedSession] = []
    screen_time_s = 0.0
    unlock_count = 0

    # §38 Phase 10: activities are no longer persisted directly inside the per-device loop below.
    # Each device (Android or browser) instead contributes `DeviceActivity` records to this list,
    # which are combined and run through `cluster_cross_device_activities` AFTER both loops finish
    # — same-category activities from different devices that overlap or nearly-abut (e.g. reading
    # docs on the phone while coding on the laptop) collapse into one cross-device Activity row
    # instead of two independent ones. `session_meta` carries the per-source-session
    # classification_source/evidence/duration that `DeviceActivity` itself doesn't (it only knows
    # what clustering needs), keyed by the originating app_session/browser_session id so the final
    # persistence step can recover it once clustering has picked winners.
    device_activities: list[DeviceActivity] = []
    session_meta: dict[uuid.UUID, dict] = {}

    # Real per-device coverage (Android only) for §38 Phase 10's cross-device union — keyed by
    # str(device_id) to match `merge_device_coverage`'s dict-of-device-name shape.
    android_coverage_by_device: dict[str, list[CoverageInterval]] = {}

    # Browser devices are sessionized and persisted separately (BrowserSession, not
    # AppSession) — see browser_session.py's own docstring for why. A browser extension has no
    # concept of "screen on/off" independent of the OS device it runs on, so running
    # build_coverage/screen_on_seconds over its events would produce meaningless intervals, not
    # just incomplete ones — they're skipped for those computations entirely, not summed in. Its
    # only honest coverage signal is "was some domain in focus" — a synthesized, TRACKED-only
    # virtual coverage stream built below once arbitration has resolved cross-browser overlap.
    browser_intervals: list[ArbitrationInterval] = []

    for device_id, device_events in events_by_device.items():
        device = devices_by_id.get(device_id)
        if device is not None and device.platform == "browser":
            for browser_session in build_browser_sessions(device_events):
                browser_intervals.append(
                    ArbitrationInterval(
                        browser_family=device.browser_family or "unknown",
                        domain=browser_session.domain,
                        start_ts=browser_session.start_ts,
                        end_ts=browser_session.end_ts,
                        truncated=browser_session.truncated,
                    )
                )
            continue

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
        android_coverage_by_device[str(device_id)] = coverage
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

            session_meta[app_session_row.id] = {
                "classification_source": result.source,
                "evidence": {"rules": list(result.evidence)},
                "duration_s": session.duration_s,
            }
            device_activities.append(
                DeviceActivity(
                    device_id=device_id,
                    category_key=result.category_key,
                    start_ts=session.start_ts,
                    end_ts=session.end_ts,
                    duration_s=session.duration_s,
                    confidence=result.confidence,
                    source_session_ids=(app_session_row.id,),
                )
            )

    # §38 Phase 10: the browser's own virtual coverage — TRACKED-only, built from POST-arbitration
    # intervals so cross-browser-family overlap is already resolved and never double-counted here.
    # Collapsed under one "browser" key (not per-device) because arbitration already guarantees no
    # overlap *within* this stream, so there is nothing for `merge_device_coverage` to dedupe among
    # a user's several browser devices — only between "browser" as a whole and each Android device.
    browser_virtual_coverage: list[CoverageInterval] = []
    domain_catalogue: dict[str, tuple[str, float]] | None = None

    if browser_intervals:
        # §11.4: arbitration runs ONCE across ALL browser devices for this user/day — it's
        # inherently cross-device, unlike app-session building above which is per-device.
        device_id_by_browser_family = {
            d.browser_family: d.id
            for d in devices_by_id.values()
            if d.platform == "browser" and d.browser_family is not None
        }
        domain_catalogue = load_domain_seed_catalogue()
        for arbitrated in arbitrate_browser_sessions(browser_intervals):
            browser_session_row = BrowserSession(
                user_id=user.id,
                device_id=device_id_by_browser_family[arbitrated.browser_family],
                browser_family=arbitrated.browser_family,
                domain=arbitrated.domain,
                start_ts=arbitrated.start_ts,
                end_ts=arbitrated.end_ts,
                duration_s=(arbitrated.end_ts - arbitrated.start_ts).total_seconds(),
                truncated=arbitrated.truncated,
            )
            db.add(browser_session_row)
            await db.flush()

            browser_virtual_coverage.append(
                CoverageInterval(arbitrated.start_ts, arbitrated.end_ts, TRACKED)
            )

            # §38 Phase 10: classify_session needs zero changes to classify a domain instead of an
            # Android package (proven in tests/analytics/test_classify.py) — the domain is simply
            # wrapped as an AppSession-shaped object and classified against the domain catalogue in
            # place of the app catalogue. No L0/L1/L3 inputs: user rules and learned priors are
            # keyed by Android app_key today, and L3's "followed by work" modifier is specific to
            # entertainment app sessions, not browser domains.
            domain_session = AppSession(
                app_key=arbitrated.domain,
                start_ts=arbitrated.start_ts,
                end_ts=arbitrated.end_ts,
                interaction_count=0,
            )
            result = classify_session(domain_session, seed_catalogue=domain_catalogue)
            all_classified.append(
                ClassifiedSession(
                    app_key=arbitrated.domain,
                    category_key=result.category_key,
                    start_ts=arbitrated.start_ts,
                    end_ts=arbitrated.end_ts,
                )
            )
            session_meta[browser_session_row.id] = {
                "classification_source": result.source,
                "evidence": {"rules": list(result.evidence)},
                "duration_s": browser_session_row.duration_s,
            }
            device_activities.append(
                DeviceActivity(
                    device_id=device_id_by_browser_family[arbitrated.browser_family],
                    category_key=result.category_key,
                    start_ts=arbitrated.start_ts,
                    end_ts=arbitrated.end_ts,
                    duration_s=browser_session_row.duration_s,
                    confidence=result.confidence,
                    source_session_ids=(browser_session_row.id,),
                )
            )

    all_classified.sort(key=lambda s: s.start_ts)

    # §38 Phase 10: cluster same-category activities from different devices (phone + laptop as one
    # work block) before persisting `Activity` rows — this is why activities were only *collected*
    # as `DeviceActivity` above rather than written straight to the DB per device.
    for cluster in cluster_cross_device_activities(device_activities):
        dominant_id = max(
            cluster.source_session_ids, key=lambda sid: session_meta[sid]["duration_s"]
        )
        dominant = session_meta[dominant_id]
        evidence = dict(dominant["evidence"])
        if cluster.is_cross_device:
            # Free-form, additive to the dominant member's own evidence — classification_source
            # itself stays one of classify_session's real values (never a made-up "cross_device"
            # source), so a cross-device Activity's provenance reads the same as a single-device
            # one, with this key as the only marker that other devices contributed.
            evidence["cross_device_members"] = [
                {
                    "source_session_id": str(sid),
                    "classification_source": session_meta[sid]["classification_source"],
                }
                for sid in cluster.source_session_ids
                if sid != dominant_id
            ]
        db.add(
            Activity(
                user_id=user.id,
                start_ts=cluster.start_ts,
                end_ts=cluster.end_ts,
                duration_s=cluster.duration_s,
                category_id=category_key_to_id[cluster.category_key],
                confidence=cluster.confidence,
                classification_source=dominant["classification_source"],
                evidence=evidence,
                devices=[str(d) for d in cluster.device_ids],
                source_session_ids=list(cluster.source_session_ids),
            )
        )

    # §38 Phase 10: the true cross-device union of observed time — Android's own per-device
    # coverage plus the browser's virtual (TRACKED-only) coverage stream. Never replaces the
    # Android-only tracked_s/idle_s/unobserved_s/offline_s breakdown below (a browser has no
    # equivalent of those states), only the day's overall observed_s/coverage_ratio and the new
    # dual_device_s column.
    unified_intervals_by_device = dict(android_coverage_by_device)
    if browser_virtual_coverage:
        unified_intervals_by_device["browser"] = browser_virtual_coverage
    unified_coverage = merge_device_coverage(unified_intervals_by_device)
    day_duration_s = (window_end - window_start).total_seconds()
    unified_coverage_ratio = (
        unified_coverage.observed_s / day_duration_s if day_duration_s > 0 else 0.0
    )

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
        unified_coverage_ratio=unified_coverage_ratio,
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
        # observed_s/coverage_ratio are the §38 Phase 10 UNIFIED (Android + virtual browser)
        # figures, not metrics.observed_s/coverage_ratio (device-only) — see merge.py/this
        # function's own docstring for why the split exists.
        observed_s=unified_coverage.observed_s,
        tracked_s=metrics.tracked_s,
        idle_s=metrics.idle_s,
        unobserved_s=metrics.unobserved_s,
        offline_s=metrics.offline_s,
        coverage_ratio=unified_coverage_ratio,
        dual_device_s=unified_coverage.dual_device_s,
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
            delete(BrowserSession).where(
                BrowserSession.device_id.in_(device_ids),
                BrowserSession.start_ts >= window_start,
                BrowserSession.start_ts < window_end,
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
