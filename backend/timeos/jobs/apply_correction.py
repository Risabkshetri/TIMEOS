"""§15.4's correction loop, applied for real (Phase 6): given a corrected category for one
`activities` row, this

  1. inserts a NEW activities row with the corrected category and points the OLD row's
     `superseded_by` at it — history is never mutated or deleted, matching §15.4 exactly;
  2. records the correction durably in `user_feedback`, `applied_at` set immediately (Phase 5's
     stub left `applied_at` NULL forever — this is what actually sets it);
  3. updates `app_classifications` — either as a standing L0 rule (`apply_as_rule=True`) or as
     one more piece of L1 evidence via `bayesian_update_app_classification`;
  4. optionally (`apply_retroactively=True`) re-runs `recompute_day` for every OTHER day with an
     `app_sessions` row for the same app, so the (possibly still-accumulating) updated
     classification takes effect everywhere it applies.

Deliberately never marks the JUST-corrected day dirty or recomputes it: recompute_day rebuilds
activities from raw events through the deterministic classifier, and if the correction hasn't yet
reached L1's >=5-sample threshold (§15.2), rerunning it would silently overwrite the correction
this function just made with the very seed-catalogue guess the user was correcting. The new
activities row IS that day's fix; recompute_day has no reason to touch it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.analytics.classify import LearnedPrior, bayesian_update_app_classification
from timeos.ingest.service import local_date_for_event
from timeos.jobs.pipeline import recompute_day
from timeos.jobs.seed_categories import ensure_system_categories
from timeos.models.activity import Activity
from timeos.models.app_classification import AppClassification
from timeos.models.app_session import AppSession
from timeos.models.user import User
from timeos.models.user_feedback import UserFeedback

RULE_CONFIDENCE = 1.0
RULE_SAMPLE_COUNT = 9999  # comfortably clears the >=5 L1 threshold; never meant to look "new"


class ActivityNotFoundError(Exception):
    """The activity doesn't exist, or doesn't belong to this user."""


class UnknownCategoryError(Exception):
    """corrected_category_key doesn't match any of this user's activity_categories."""


class CorrectionResult:
    def __init__(
        self,
        new_activity_id: uuid.UUID,
        app_classification_source: str,
        app_classification_confidence: float,
        app_classification_sample_count: int,
        retroactively_recomputed_dates: list[date],
    ) -> None:
        self.new_activity_id = new_activity_id
        self.app_classification_source = app_classification_source
        self.app_classification_confidence = app_classification_confidence
        self.app_classification_sample_count = app_classification_sample_count
        self.retroactively_recomputed_dates = retroactively_recomputed_dates


async def _resolve_app_key(db: AsyncSession, activity: Activity) -> str | None:
    if not activity.source_session_ids:
        return None
    result = await db.execute(
        select(AppSession.app_key).where(AppSession.id == activity.source_session_ids[0])
    )
    return result.scalar_one_or_none()


async def _other_local_dates_for_app(
    db: AsyncSession, user: User, app_key: str, exclude: date
) -> list[date]:
    result = await db.execute(
        select(AppSession.start_ts).where(
            AppSession.user_id == user.id, AppSession.app_key == app_key
        )
    )
    dates = {
        local_date_for_event(int(ts.timestamp() * 1000), user.timezone, user.day_start_hour)
        for (ts,) in result.all()
    }
    dates.discard(exclude)
    return sorted(dates)


async def apply_classification_correction(
    db: AsyncSession,
    user: User,
    activity_id: uuid.UUID,
    corrected_category_key: str,
    apply_as_rule: bool,
    apply_retroactively: bool,
) -> CorrectionResult:
    old_activity = await db.get(Activity, activity_id)
    if old_activity is None or old_activity.user_id != user.id:
        raise ActivityNotFoundError(str(activity_id))

    category_key_to_id = await ensure_system_categories(db, user.id)
    if corrected_category_key not in category_key_to_id:
        raise UnknownCategoryError(corrected_category_key)
    new_category_id = category_key_to_id[corrected_category_key]

    app_key = await _resolve_app_key(db, old_activity)

    new_activity = Activity(
        user_id=user.id,
        start_ts=old_activity.start_ts,
        end_ts=old_activity.end_ts,
        duration_s=old_activity.duration_s,
        category_id=new_category_id,
        confidence=RULE_CONFIDENCE,
        classification_source="user",
        evidence={"correction_of": str(old_activity.id)},
        devices=old_activity.devices,
        source_session_ids=old_activity.source_session_ids,
    )
    db.add(new_activity)
    await db.flush()
    old_activity.superseded_by = new_activity.id

    now = datetime.now(UTC)
    db.add(
        UserFeedback(
            user_id=user.id,
            target_type="activity",
            target_id=old_activity.id,
            correction={
                "corrected_category_key": corrected_category_key,
                "apply_as_rule": apply_as_rule,
            },
            applied_at=now,
        )
    )

    app_source = "user"
    app_confidence = RULE_CONFIDENCE
    app_sample_count = RULE_SAMPLE_COUNT

    if app_key is not None:
        existing_row = await db.get(AppClassification, (user.id, app_key))

        if not apply_as_rule:
            id_to_key = {v: k for k, v in category_key_to_id.items()}
            existing_prior = (
                LearnedPrior(
                    id_to_key.get(existing_row.category_id, "unknown"),
                    float(existing_row.confidence),
                    existing_row.sample_count,
                )
                if existing_row is not None
                else None
            )
            existing_updated_at = existing_row.updated_at if existing_row is not None else None
            update = bayesian_update_app_classification(
                corrected_category_key, existing_prior, existing_updated_at, now=now
            )
            app_source = "learned"
            app_confidence = update.confidence
            app_sample_count = update.sample_count

        if existing_row is None:
            db.add(
                AppClassification(
                    user_id=user.id,
                    app_key=app_key,
                    category_id=new_category_id,
                    confidence=app_confidence,
                    source=app_source,
                    sample_count=app_sample_count,
                    updated_at=now,
                )
            )
        else:
            existing_row.category_id = new_category_id
            existing_row.confidence = app_confidence
            existing_row.source = app_source
            existing_row.sample_count = app_sample_count
            existing_row.updated_at = now

    await db.commit()

    recomputed_dates: list[date] = []
    if apply_retroactively and app_key is not None:
        corrected_local_date = local_date_for_event(
            int(old_activity.start_ts.timestamp() * 1000), user.timezone, user.day_start_hour
        )
        affected_dates = await _other_local_dates_for_app(
            db, user, app_key, exclude=corrected_local_date
        )
        for affected_date in affected_dates:
            await recompute_day(db, user, affected_date)
            recomputed_dates.append(affected_date)

    return CorrectionResult(
        new_activity_id=new_activity.id,
        app_classification_source=app_source,
        app_classification_confidence=app_confidence,
        app_classification_sample_count=app_sample_count,
        retroactively_recomputed_dates=recomputed_dates,
    )
