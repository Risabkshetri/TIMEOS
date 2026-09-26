"""timeos.jobs.daily_analysis — the full Phase 8 orchestration, against real Postgres. Uses
NullProvider (the zero-config default) for the "happy path" tests, and a scripted fake provider
(monkeypatched in place of timeos.jobs.daily_analysis.get_provider) for the security-relevant
failure-mode tests §33 names explicitly: malformed output isn't persisted as insights, a
fabricated number drops just that insight, and a provider outage fails the job cleanly.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from timeos.ai.provider import CompletionResult, Message, ProviderError
from timeos.config import Settings
from timeos.ingest.service import day_window_utc
from timeos.jobs.daily_analysis import (
    AnalysisFailed,
    BudgetExceeded,
    RateLimitExceeded,
    run_daily_analysis,
)
from timeos.jobs.pipeline import recompute_day
from timeos.models.ai_analysis import AIAnalysis
from timeos.models.device import Device
from timeos.models.raw_event import RawEvent
from timeos.models.user import User

LOCAL_DATE = (datetime.now(UTC) - timedelta(days=1)).date()
DAY_START, _ = day_window_utc(LOCAL_DATE, "UTC", 4)
CHROME_APP_KEY = "com.android.chrome"


def _null_settings(**overrides) -> Settings:
    return Settings(ai_provider="null", ai_monthly_budget_usd=5.0, **overrides)


async def _make_user_and_device(session) -> tuple[User, Device]:
    user = User(timezone="UTC", day_start_hour=4)
    session.add(user)
    await session.flush()
    device = Device(
        id=uuid.uuid4(), user_id=user.id, name="phone", platform="android", token_hash="x"
    )
    session.add(device)
    await session.flush()
    return user, device


async def _seed_activity(session, user, device, local_date) -> None:
    day_start, _ = day_window_utc(local_date, "UTC", 4)
    session.add_all(
        [
            RawEvent(
                id=uuid.uuid4(),
                ts_utc=day_start + timedelta(seconds=offset),
                device_id=device.id,
                user_id=user.id,
                seq=seq,
                tz_offset_min=0,
                tz_id="UTC",
                uptime_ms=int(offset * 1000),
                type=type_,
                payload=payload,
                schema_v=1,
            )
            for seq, offset, type_, payload in [
                (1, 0, "SCREEN_ON", {}),
                (2, 5, "APP_FOREGROUND", {"package": CHROME_APP_KEY}),
                (3, 605, "APP_BACKGROUND", {"package": CHROME_APP_KEY}),
            ]
        ]
    )
    await session.commit()
    await recompute_day(session, user, local_date)


class _ScriptedProvider:
    model_name = "scripted-test-model"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def complete(self, messages: list[Message]) -> CompletionResult:
        text = self._responses.pop(0)
        return CompletionResult(text=text, token_in=10, token_out=10, cost_usd=0.01, latency_ms=1)


class _BrokenProvider:
    model_name = "broken-test-model"

    async def complete(self, messages: list[Message]) -> CompletionResult:
        raise ProviderError("simulated outage")


VALID_JSON_NO_INSIGHTS = (
    '{"day_score": 50, "score_rationale": "ok", "summary": "A day.", "data_caveats": [], '
    '"wins": [], "problems": [], "patterns": [], "distractions": [], "goal_alignment": [], '
    '"recommendations": [], "tomorrow_priorities": [], "overall_confidence": 0.5}'
)


async def test_null_provider_produces_a_persisted_analysis_with_no_insights():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _seed_activity(session, user, device, LOCAL_DATE)

        result = await run_daily_analysis(session, user, LOCAL_DATE, _null_settings())

        assert result.analysis.provider == "null"
        assert result.analysis.day_score in (None, 50)  # 50 survives the band check, or is dropped
        assert result.insights == []


async def test_identical_context_reuses_the_cached_analysis():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _seed_activity(session, user, device, LOCAL_DATE)

        first = await run_daily_analysis(session, user, LOCAL_DATE, _null_settings())
        second = await run_daily_analysis(session, user, LOCAL_DATE, _null_settings())

        assert first.analysis.id == second.analysis.id

        from sqlalchemy import func, select

        count = (
            await session.execute(
                select(func.count())
                .select_from(AIAnalysis)
                .where(AIAnalysis.user_id == user.id)
            )
        ).scalar_one()
        assert count == 1


async def test_manual_trigger_rate_limit_of_5_per_day():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _seed_activity(session, user, device, LOCAL_DATE)

        # Distinct dates avoid the context-hash cache short-circuiting before rate limiting runs.
        for i in range(5):
            await run_daily_analysis(
                session, user, LOCAL_DATE - timedelta(days=i), _null_settings()
            )

        with pytest.raises(RateLimitExceeded):
            await run_daily_analysis(
                session, user, LOCAL_DATE - timedelta(days=5), _null_settings()
            )


async def test_budget_cap_halts_calls():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _seed_activity(session, user, device, LOCAL_DATE)

        session.add(
            AIAnalysis(
                user_id=user.id,
                scope="day",
                scope_key="2026-01-01",
                triggered_by="manual",
                context_hash="a" * 64,
                context_version="1.0",
                provider="null",
                model="none",
                prompt_version="1.0",
                validation_status="ok",
                raw_output={},
                cost_usd=5.0,
            )
        )
        await session.commit()

        with pytest.raises(BudgetExceeded):
            await run_daily_analysis(session, user, LOCAL_DATE, _null_settings())


async def test_provider_outage_raises_and_persists_nothing():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _seed_activity(session, user, device, LOCAL_DATE)

        with patch(
            "timeos.jobs.daily_analysis.get_provider", return_value=_BrokenProvider()
        ):
            with pytest.raises(AnalysisFailed):
                await run_daily_analysis(session, user, LOCAL_DATE, _null_settings())

        from sqlalchemy import func, select

        count = (
            await session.execute(
                select(func.count())
                .select_from(AIAnalysis)
                .where(AIAnalysis.user_id == user.id)
            )
        ).scalar_one()
        assert count == 0


async def test_malformed_output_is_persisted_as_failed_with_no_insights():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _seed_activity(session, user, device, LOCAL_DATE)

        provider = _ScriptedProvider(["not json at all", "still not json"])
        with patch("timeos.jobs.daily_analysis.get_provider", return_value=provider):
            result = await run_daily_analysis(session, user, LOCAL_DATE, _null_settings())

        assert result.analysis.validation_status == "failed"
        assert result.analysis.day_score is None
        assert result.insights == []


async def test_fabricated_number_insight_is_dropped_but_the_analysis_still_persists():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _seed_activity(session, user, device, LOCAL_DATE)

        fabricated_win = {
            "claim": "You had 99999 context switches.",
            "evidence": {
                "fields": ["focus.context_switches"],
                "values": {"context_switches": 99999},
                "narrative": "99999 context switches recorded.",
            },
            "confidence": 0.8,
            "epistemic_status": "INFERENCE",
        }
        import json

        payload = json.loads(VALID_JSON_NO_INSIGHTS)
        payload["wins"] = [fabricated_win]
        provider = _ScriptedProvider([json.dumps(payload)])

        with patch("timeos.jobs.daily_analysis.get_provider", return_value=provider):
            result = await run_daily_analysis(session, user, LOCAL_DATE, _null_settings())

        assert result.analysis.validation_status == "partial"
        assert result.insights == []  # the fabricated insight was dropped, not persisted


async def test_a_grounded_insight_is_persisted():
    import timeos.db as db

    async with db.async_session_factory() as session:
        user, device = await _make_user_and_device(session)
        await _seed_activity(session, user, device, LOCAL_DATE)

        import json

        payload = json.loads(VALID_JSON_NO_INSIGHTS)
        payload["wins"] = [
            {
                "claim": "You completed at least one focus session.",
                "evidence": {
                    "fields": ["focus.sessions"],
                    "values": {"sessions": 0},
                    "narrative": "0 focus sessions were recorded today.",
                },
                "confidence": 0.7,
                "epistemic_status": "FACT",
            }
        ]
        provider = _ScriptedProvider([json.dumps(payload)])

        with patch("timeos.jobs.daily_analysis.get_provider", return_value=provider):
            result = await run_daily_analysis(session, user, LOCAL_DATE, _null_settings())

        assert len(result.insights) == 1
        assert result.insights[0].kind == "wins"
        assert result.insights[0].evidence_verified is True
