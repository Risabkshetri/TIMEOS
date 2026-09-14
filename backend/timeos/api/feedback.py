"""POST /v1/feedback — §15.4's correction affordance, stubbed for Phase 5 (§38 Phase 5:
"correction affordance wired to Phase 6's feedback endpoint stub"). Durably records the
correction; Phase 6 is what applies it. CSRF-protected since it's a mutation (§28)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import enforce_csrf, get_current_user, get_db
from timeos.models.user import User
from timeos.models.user_feedback import UserFeedback
from timeos.schemas.feedback import FeedbackRequest, FeedbackResponse

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
