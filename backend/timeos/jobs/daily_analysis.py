"""Phase 8's Daily AI Analyst orchestrator — the only place that actually calls an LLM. Owns
everything `timeos.ai` is barred from touching: the DB, rate limiting, the budget cap, and
resolving which provider to use from `timeos.config.Settings`. The sequence is exactly §20.1's
boundary diagram: build the real `AIContext` (`timeos.jobs.build_ai_context`) → the privacy gate
(`timeos.privacy.gate`) → only THEN hand the sanitized payload to `timeos.ai`.

No scheduled automatic job is registered here (mirrors `timeos.jobs.pipeline`'s own documented
gap: this project has no running APScheduler process to register one against) — `run_daily_analysis`
is called directly by `POST /v1/ai/analyze/{date}`, which is what §22.9's "manual triggers capped
at 5/day" actually rate-limits. The "1 automatic daily/weekly/monthly call" limit has nothing to
enforce yet without a scheduler, so it isn't implemented as dead code here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.ai.client import request_analysis
from timeos.ai.provider import ProviderError, get_provider
from timeos.ai.validate import ValidatedAnalysis, validate_and_sanitize
from timeos.analytics.day_score import compute_reference_day_score
from timeos.config import Settings
from timeos.ingest.service import day_window_utc, local_date_for_event
from timeos.jobs.build_ai_context import build_ai_context_for_day
from timeos.models.ai_analysis import AIAnalysis
from timeos.models.ai_insight import AIInsight
from timeos.models.user import User
from timeos.privacy.gate import PrivacyViolation, enforce_privacy_gate
from timeos.schemas.ai_context import context_hash as compute_context_hash
from timeos.schemas.ai_output import INSIGHT_SECTIONS, AIAnalysisOutput

PROMPT_VERSION = "1.0"
MANUAL_DAILY_TRIGGER_LIMIT = 5  # §22.9: "manual triggers capped at 5/day"


class RateLimitExceeded(Exception):
    pass


class BudgetExceeded(Exception):
    pass


class AnalysisFailed(Exception):
    """The provider call or the privacy gate itself failed outright — §22's "provider outage →
    job fails cleanly": nothing is persisted, the caller shows the deterministic dashboard."""


@dataclass(frozen=True, slots=True)
class DailyAnalysisResult:
    analysis: AIAnalysis
    insights: list[AIInsight]


async def _count_manual_triggers_today(db: AsyncSession, user: User) -> int:
    today = local_date_for_event(
        int(datetime.now(UTC).timestamp() * 1000), user.timezone, user.day_start_hour
    )
    start_of_today, end_of_today = day_window_utc(today, user.timezone, user.day_start_hour)
    result = await db.execute(
        select(func.count())
        .select_from(AIAnalysis)
        .where(
            AIAnalysis.user_id == user.id,
            AIAnalysis.triggered_by == "manual",
            AIAnalysis.created_at >= start_of_today,
            AIAnalysis.created_at < end_of_today,
        )
    )
    return result.scalar_one()


async def _cost_this_month(db: AsyncSession, user_id: uuid.UUID) -> float:
    now = datetime.now(UTC)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(AIAnalysis.cost_usd), 0)).where(
            AIAnalysis.user_id == user_id, AIAnalysis.created_at >= start_of_month
        )
    )
    return float(result.scalar_one())


async def _find_cached_analysis(
    db: AsyncSession, user_id: uuid.UUID, scope_key: str, hash_value: str
) -> AIAnalysis | None:
    return (
        await db.execute(
            select(AIAnalysis).where(
                AIAnalysis.user_id == user_id,
                AIAnalysis.scope == "day",
                AIAnalysis.scope_key == scope_key,
                AIAnalysis.context_hash == hash_value,
            )
        )
    ).scalar_one_or_none()


def _persist_insight(
    db: AsyncSession,
    analysis_id: uuid.UUID,
    kind: str,
    claim: str,
    evidence: dict,
    confidence: float,
    epistemic_status: str | None,
) -> AIInsight:
    row = AIInsight(
        analysis_id=analysis_id,
        kind=kind,
        claim=claim,
        evidence=evidence,
        confidence=confidence,
        evidence_verified=True,  # only survivors of timeos.ai.validate ever reach this function
        epistemic_status=epistemic_status,
    )
    db.add(row)
    return row


async def _persist_result(
    db: AsyncSession,
    user_id: uuid.UUID,
    scope_key: str,
    hash_value: str,
    context_version: str,
    provider_name: str,
    model_name: str,
    triggered_by: str,
    validation_status: str,
    day_score: int | None,
    score_rationale: str | None,
    summary: str | None,
    overall_confidence: float | None,
    raw_output: dict,
    token_in: int,
    token_out: int,
    cost_usd: float,
    latency_ms: int,
    validated: ValidatedAnalysis | None,
) -> DailyAnalysisResult:
    analysis = AIAnalysis(
        user_id=user_id,
        scope="day",
        scope_key=scope_key,
        triggered_by=triggered_by,
        context_hash=hash_value,
        context_version=context_version,
        provider=provider_name,
        model=model_name,
        prompt_version=PROMPT_VERSION,
        day_score=day_score,
        score_rationale=score_rationale,
        summary=summary,
        overall_confidence=overall_confidence,
        data_caveats=validated.data_caveats if validated is not None else [],
        tomorrow_priorities=validated.tomorrow_priorities if validated is not None else [],
        raw_output=raw_output,
        validation_status=validation_status,
        token_in=token_in,
        token_out=token_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )
    db.add(analysis)
    await db.flush()

    insights: list[AIInsight] = []
    if validated is not None:
        for section_name in INSIGHT_SECTIONS:
            for insight in getattr(validated, section_name):
                insights.append(
                    _persist_insight(
                        db,
                        analysis.id,
                        kind=section_name,
                        claim=insight.claim,
                        evidence=insight.evidence.model_dump(),
                        confidence=insight.confidence,
                        epistemic_status=insight.epistemic_status,
                    )
                )
        for rec in validated.recommendations:
            insights.append(
                _persist_insight(
                    db,
                    analysis.id,
                    kind="recommendation",
                    claim=rec.action,
                    evidence={
                        "rationale": rec.rationale,
                        "expected_effect": rec.expected_effect,
                        "effort": rec.effort,
                        "measurable_check": rec.measurable_check,
                    },
                    confidence=rec.confidence,
                    epistemic_status=None,
                )
            )

    await db.commit()
    for insight in insights:
        await db.refresh(insight)
    await db.refresh(analysis)
    return DailyAnalysisResult(analysis=analysis, insights=insights)


async def run_daily_analysis(
    db: AsyncSession,
    user: User,
    local_date: date,
    settings: Settings,
    triggered_by: str = "manual",
) -> DailyAnalysisResult:
    if triggered_by == "manual":
        triggers_today = await _count_manual_triggers_today(db, user)
        if triggers_today >= MANUAL_DAILY_TRIGGER_LIMIT:
            raise RateLimitExceeded(
                f"manual AI analysis is capped at {MANUAL_DAILY_TRIGGER_LIMIT}/day"
            )

    context = await build_ai_context_for_day(db, user, local_date)
    hash_value = compute_context_hash(context)
    scope_key = local_date.isoformat()

    cached = await _find_cached_analysis(db, user.id, scope_key, hash_value)
    if cached is not None:
        insights = (
            (
                await db.execute(
                    select(AIInsight).where(AIInsight.analysis_id == cached.id)
                )
            )
            .scalars()
            .all()
        )
        return DailyAnalysisResult(analysis=cached, insights=list(insights))

    spent_this_month = await _cost_this_month(db, user.id)
    if spent_this_month >= settings.ai_monthly_budget_usd:
        raise BudgetExceeded(
            f"monthly AI budget of ${settings.ai_monthly_budget_usd:.2f} already reached"
        )

    ai_share_app_names = bool(user.settings.get("ai_share_app_names", False))
    try:
        payload = await enforce_privacy_gate(
            db,
            user_id=user.id,
            context=context,
            actor="ai_analysis",
            ai_share_app_names=ai_share_app_names,
        )
    except PrivacyViolation as exc:
        raise AnalysisFailed(f"privacy gate rejected this day's context: {exc}") from exc

    reference_score = compute_reference_day_score(context)
    provider = get_provider(settings.ai_provider, settings.ai_api_key, settings.ai_model)

    try:
        attempt = await request_analysis(provider, payload, AIAnalysisOutput.model_json_schema())
    except ProviderError as exc:
        raise AnalysisFailed(f"AI provider call failed: {exc}") from exc

    if attempt.output is None:
        return await _persist_result(
            db,
            user_id=user.id,
            scope_key=scope_key,
            hash_value=hash_value,
            context_version=context.context_version,
            provider_name=settings.ai_provider,
            model_name=provider.model_name,
            triggered_by=triggered_by,
            validation_status="failed",
            day_score=None,
            score_rationale=None,
            summary=None,
            overall_confidence=None,
            raw_output={"raw_text": attempt.raw_text},
            token_in=attempt.token_in,
            token_out=attempt.token_out,
            cost_usd=attempt.cost_usd,
            latency_ms=attempt.latency_ms,
            validated=None,
        )

    validated = validate_and_sanitize(attempt.output, payload, reference_score)
    return await _persist_result(
        db,
        user_id=user.id,
        scope_key=scope_key,
        hash_value=hash_value,
        context_version=context.context_version,
        provider_name=settings.ai_provider,
        model_name=provider.model_name,
        triggered_by=triggered_by,
        validation_status=validated.validation_status,
        day_score=validated.day_score,
        score_rationale=validated.score_rationale,
        summary=validated.summary,
        overall_confidence=validated.overall_confidence,
        raw_output={"parsed": attempt.output.model_dump(mode="json")},
        token_in=attempt.token_in,
        token_out=attempt.token_out,
        cost_usd=attempt.cost_usd,
        latency_ms=attempt.latency_ms,
        validated=validated,
    )
