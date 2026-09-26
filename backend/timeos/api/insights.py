"""GET /v1/insights/{date}, POST /v1/ai/analyze/{date} — §12.2, Phase 8's Daily AI Analyst.

The manual-trigger endpoint is the ONLY way an analysis gets created today (no scheduled
automatic job exists yet — see timeos.jobs.daily_analysis's own module docstring for why), so it
carries §22.9's "manual triggers capped at 5/day" limit. A day with no analysis yet is a normal,
expected state (§22.10: the system must work with zero AI configuration) — `GET` 404s rather than
erroring, and the dashboard is expected to render its deterministic view either way.
"""

from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import enforce_csrf, get_current_user, get_db
from timeos.config import get_settings
from timeos.jobs.daily_analysis import (
    AnalysisFailed,
    BudgetExceeded,
    DailyAnalysisResult,
    RateLimitExceeded,
    run_daily_analysis,
)
from timeos.models.ai_analysis import AIAnalysis
from timeos.models.ai_insight import AIInsight
from timeos.models.user import User
from timeos.schemas.insights import AnalysisOut, InsightOut

router = APIRouter(tags=["insights"])


def _to_response(result: DailyAnalysisResult) -> AnalysisOut:
    analysis = result.analysis
    return AnalysisOut(
        id=analysis.id,
        scope=analysis.scope,
        scope_key=analysis.scope_key,
        provider=analysis.provider,
        model=analysis.model,
        day_score=analysis.day_score,
        score_rationale=analysis.score_rationale,
        summary=analysis.summary,
        overall_confidence=(
            float(analysis.overall_confidence)
            if analysis.overall_confidence is not None
            else None
        ),
        data_caveats=analysis.data_caveats,
        tomorrow_priorities=analysis.tomorrow_priorities,
        validation_status=analysis.validation_status,
        created_at=analysis.created_at,
        insights=[
            InsightOut(
                id=insight.id,
                kind=insight.kind,
                claim=insight.claim,
                evidence=insight.evidence,
                confidence=float(insight.confidence),
                evidence_verified=insight.evidence_verified,
                epistemic_status=insight.epistemic_status,
            )
            for insight in result.insights
        ],
    )


@router.get("/v1/insights/{local_date}", response_model=AnalysisOut)
async def get_insights(
    local_date: date_type,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisOut:
    analysis = (
        await db.execute(
            select(AIAnalysis)
            .where(
                AIAnalysis.user_id == user.id,
                AIAnalysis.scope == "day",
                AIAnalysis.scope_key == local_date.isoformat(),
            )
            .order_by(AIAnalysis.created_at.desc())
        )
    ).scalars().first()

    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no AI analysis exists for this date yet")

    insights = (
        (await db.execute(select(AIInsight).where(AIInsight.analysis_id == analysis.id)))
        .scalars()
        .all()
    )
    return _to_response(DailyAnalysisResult(analysis=analysis, insights=list(insights)))


@router.post(
    "/v1/ai/analyze/{local_date}",
    response_model=AnalysisOut,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_analysis(
    local_date: date_type,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(enforce_csrf),
) -> AnalysisOut:
    try:
        result = await run_daily_analysis(
            db, user, local_date, get_settings(), triggered_by="manual"
        )
    except RateLimitExceeded as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except BudgetExceeded as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc
    except AnalysisFailed as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return _to_response(result)
