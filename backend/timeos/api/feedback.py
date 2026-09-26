"""POST /v1/feedback — §15.4's correction affordance, stubbed for Phase 5 (§38 Phase 5:
"correction affordance wired to Phase 6's feedback endpoint stub"). Durably records the
correction. POST /v1/feedback/classification is Phase 6's real thing: it actually applies a
correction (new activities row, app_classifications Bayesian update, opt-in retroactive
recompute) via timeos.jobs.apply_correction. Both are CSRF-protected since both are mutations
(§28)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import enforce_csrf, get_current_user, get_db
from timeos.jobs.apply_correction import (
    ActivityNotFoundError,
    UnknownCategoryError,
    apply_classification_correction,
)
from timeos.models.user import User
from timeos.models.user_feedback import UserFeedback
from timeos.schemas.feedback import (
    ClassificationCorrectionRequest,
    ClassificationCorrectionResponse,
    FeedbackRequest,
    FeedbackResponse,
)

router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(enforce_csrf),
) -> FeedbackResponse:
    row = UserFeedback(
        user_id=user.id,
        target_type=body.target_type,
        target_id=body.target_id,
        correction=body.correction,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return FeedbackResponse(id=row.id)


@router.post(
    "/classification",
    response_model=ClassificationCorrectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_classification_correction(
    body: ClassificationCorrectionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(enforce_csrf),
) -> ClassificationCorrectionResponse:
    try:
        result = await apply_classification_correction(
            db,
            user,
            activity_id=body.activity_id,
            corrected_category_key=body.corrected_category_key,
            apply_as_rule=body.apply_as_rule,
            apply_retroactively=body.apply_retroactively,
        )
    except ActivityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="activity not found"
        ) from exc
    except UnknownCategoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown category key"
        ) from exc

    return ClassificationCorrectionResponse(
        new_activity_id=result.new_activity_id,
        app_classification_source=result.app_classification_source,
        app_classification_confidence=result.app_classification_confidence,
        app_classification_sample_count=result.app_classification_sample_count,
        retroactively_recomputed_dates=result.retroactively_recomputed_dates,
    )
