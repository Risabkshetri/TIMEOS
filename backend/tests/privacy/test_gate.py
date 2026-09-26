"""§20.1's boundary itself: timeos.privacy.gate.enforce_privacy_gate, against a real Postgres
(the audit write is real DB I/O, so this is an integration test, not a pure-function one)."""

from sqlalchemy import select

from tests.factories import create_user_with_enrollment_code
from timeos.models.privacy_audit_event import PrivacyAuditEvent
from timeos.privacy.gate import PrivacyViolation, enforce_privacy_gate
from timeos.schemas.ai_context import (
    AIContext,
    Baselines,
    DataQuality,
    FocusSummary,
    GoalSummary,
    Totals,
)


def _minimal_context(**goal_overrides) -> AIContext:
    return AIContext(
        scope="day",
        date="2026-09-13",
        weekday="Sunday",
        data_quality=DataQuality(
            coverage_ratio=0.87,
            unknown_ratio=0.12,
            devices_reporting=["android"],
            unobserved_minutes=0,
            offline_minutes=0,
        ),
        totals=Totals(
            day_minutes=1440, observed_minutes=1000, screen_minutes=400, active_minutes=350
        ),
        focus=FocusSummary(
            sessions=1,
            deep_sessions=0,
            longest_minutes=10,
            average_minutes=10,
            total_focus_minutes=10,
            avg_quality=0.5,
            context_switches=1,
            switches_per_hour=1.0,
            interruptions=0,
        ),
        goals=(
            [
                GoalSummary(
                    name=goal_overrides.get("name", "Build"),
                    priority=1,
                    target_weekly_minutes=600,
                    aligned_minutes_today=100,
                    uncertainty=10,
                    week_attainment=0.3,
                )
            ]
            if goal_overrides.get("include_goal", True)
            else []
        ),
        baselines=Baselines(
            window_days=30, valid_days=20, screen_minutes_mean=400, deep_work_minutes_mean=50,
            fragmentation_mean=0.4,
        ),
    )


async def test_a_clean_context_is_allowed_and_audited():
    import timeos.db as db

    user_id, _code = await create_user_with_enrollment_code()

    async with db.async_session_factory() as session:
        payload = await enforce_privacy_gate(
            session,
            user_id=user_id,
            context=_minimal_context(),
            actor="test",
            ai_share_app_names=False,
        )
        assert payload["scope"] == "day"

        rows = (
            (
                await session.execute(
                    select(PrivacyAuditEvent).where(PrivacyAuditEvent.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].outcome == "allowed"
        assert rows[0].rejected_fields == []
        assert len(rows[0].payload_sha256) == 64


async def test_a_leaking_goal_name_is_rejected_and_audited():
    import timeos.db as db

    user_id, _code = await create_user_with_enrollment_code()
    leaking_context = _minimal_context(name="Build https://leaky.example.com")

    async with db.async_session_factory() as session:
        try:
            await enforce_privacy_gate(
                session,
                user_id=user_id,
                context=leaking_context,
                actor="test",
                ai_share_app_names=False,
            )
            raised = False
        except PrivacyViolation as exc:
            raised = True
            assert any("goals[0].name" in path for path in exc.violations)

        assert raised

        rows = (
            (
                await session.execute(
                    select(PrivacyAuditEvent).where(PrivacyAuditEvent.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].outcome == "rejected"
        assert any("goals[0].name" in field for field in rows[0].rejected_fields)


async def test_ai_share_app_names_setting_is_recorded_on_the_audit_row():
    import timeos.db as db

    user_id, _code = await create_user_with_enrollment_code()

    async with db.async_session_factory() as session:
        await enforce_privacy_gate(
            session,
            user_id=user_id,
            context=_minimal_context(),
            actor="test",
            ai_share_app_names=True,
        )
        row = (
            await session.execute(
                select(PrivacyAuditEvent).where(PrivacyAuditEvent.user_id == user_id)
            )
        ).scalar_one()
        assert row.ai_share_app_names is True


async def test_identical_payloads_produce_identical_digests():
    import timeos.db as db

    user_id, _code = await create_user_with_enrollment_code()

    async with db.async_session_factory() as session:
        await enforce_privacy_gate(
            session,
            user_id=user_id,
            context=_minimal_context(),
            actor="a",
            ai_share_app_names=False,
        )
        await enforce_privacy_gate(
            session,
            user_id=user_id,
            context=_minimal_context(),
            actor="b",
            ai_share_app_names=False,
        )
        rows = (
            (
                await session.execute(
                    select(PrivacyAuditEvent)
                    .where(PrivacyAuditEvent.user_id == user_id)
                    .order_by(PrivacyAuditEvent.occurred_at)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2
        assert rows[0].payload_sha256 == rows[1].payload_sha256


async def test_an_empty_goals_list_is_allowed():
    import timeos.db as db

    user_id, _code = await create_user_with_enrollment_code()

    async with db.async_session_factory() as session:
        payload = await enforce_privacy_gate(
            session,
            user_id=user_id,
            context=_minimal_context(include_goal=False),
            actor="test",
            ai_share_app_names=False,
        )
        assert payload["goals"] == []
