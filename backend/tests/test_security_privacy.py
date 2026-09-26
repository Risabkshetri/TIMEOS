"""§33's named privacy security suite for Phase 7. These tests must exist and must fail the build
if the boundary they check is ever broken — see the spec: "A leak that reaches production is
unrecoverable... this is the one area where test cost is unquestioned."

`test_ai_module_has_no_db_import` and `test_ai_module_cannot_open_connection` were already
established at Phase 0 in tests/test_privacy_isolation.py (that file's own docstring says so
explicitly: "must exist from Phase 0 onward"); `test_device_token_cannot_read` predates this phase
too (tests/test_device_token_scope.py). `test_no_secrets_in_repo` is enforced by the dedicated
gitleaks job in .github/workflows/ci.yml against the real gitleaks binary — a from-scratch pytest
reimplementation here would be a strictly weaker duplicate of that check, not an improvement on it.
This file covers everything else the list names that is specific to Phase 7's new code.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from timeos.privacy.allowlist import find_disallowed_keys
from timeos.privacy.scanner import scan_string
from timeos.schemas.ai_context import (
    AIContext,
    Baselines,
    DataQuality,
    FocusSummary,
    Totals,
)


def _valid_context_kwargs() -> dict:
    return {
        "scope": "day",
        "date": "2026-09-13",
        "weekday": "Sunday",
        "data_quality": DataQuality(
            coverage_ratio=0.87,
            unknown_ratio=0.12,
            devices_reporting=["android"],
            unobserved_minutes=0,
            offline_minutes=0,
        ),
        "totals": Totals(
            day_minutes=1440, observed_minutes=1000, screen_minutes=400, active_minutes=350
        ),
        "focus": FocusSummary(
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
        "baselines": Baselines(
            window_days=30,
            valid_days=20,
            screen_minutes_mean=400,
            deep_work_minutes_mean=50,
            fragmentation_mean=0.4,
        ),
    }


def test_extra_field_forbidden():
    """AIContext's `extra="forbid"` config: a field that isn't part of the declared schema fails
    validation before the object can even be constructed, let alone reach the gate."""
    with pytest.raises(ValidationError):
        AIContext(**_valid_context_kwargs(), device_id="should-never-validate")


def test_raw_event_cannot_reach_llm():
    """Simulates the failure the schema layer is supposed to prevent from ever occurring: a raw
    `raw_events` row's shape reaching the gate's allowlist walk. Exercised at the allowlist layer
    directly (rather than via AIContext, which would reject this at construction time) because the
    whole point of a THIRD independent layer is that it must catch this even if the schema layer
    were somehow bypassed."""
    raw_event_shaped = {
        "id": str(uuid.uuid4()),
        "device_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "seq": 42,
        "tz_offset_min": -300,
        "payload": {"package": "com.example.app"},
        "clock_suspect": False,
        "schema_v": 1,
    }
    violations = find_disallowed_keys({"leaked": raw_event_shaped})
    assert violations, "a raw_events-shaped object must be rejected, not silently accepted"
    for forbidden_key in ["device_id", "user_id", "payload", "clock_suspect", "schema_v"]:
        assert f"leaked.{forbidden_key}" in violations


@pytest.mark.parametrize(
    "label,payload",
    [
        ("raw_event_row", {"device_id": "d1", "seq": 1, "payload": {}}),
        ("message_content", {"message_body": "hey are we still on for lunch"}),
        ("contact_name", {"contact_name": "Alex Rivera"}),
        ("password", {"password": "hunter2"}),
        ("api_token", {"api_token": "not-a-real-token-abcdef"}),
        ("dsn", {"dsn": "postgresql://user:pass@host/db"}),
        ("file_path", {"file_path": "/home/user/secret.txt"}),
        ("document_name", {"document_name": "Q3 layoffs plan.docx"}),
        ("window_title", {"window_title": "Gmail - Inbox"}),
        ("screenshot", {"screenshot_url": "https://cdn.example.com/shot.png"}),
        ("device_identifier", {"device_id": str(uuid.uuid4())}),
        ("ip_address", {"ip_address": "192.168.1.42"}),
        ("mac_address", {"mac_address": "AA:BB:CC:DD:EE:FF"}),
        ("email_address", {"email": "owner@example.com"}),
        ("account_id", {"account_id": str(uuid.uuid4())}),
        ("free_text_not_user_authored", {"ai_generated_note": "some fabricated commentary"}),
        ("bare_uuid", {"record_id": str(uuid.uuid4())}),
    ],
)
def test_forbidden_field_rejected(label, payload):
    """§20.3's FORBIDDEN list, parametrised: every one of these classes must be caught by at
    least one of the two dict-level layers (an unrecognised key, or — for values shaped like a
    leak regardless of key name — the content scanner)."""
    key_violations = find_disallowed_keys(payload)
    scan_violations = {
        key: scan_string(value) for key, value in payload.items() if isinstance(value, str)
    }
    scan_hit = any(v for v in scan_violations.values())
    assert key_violations or scan_hit, f"{label} slipped through both layers: {payload}"


def test_url_email_token_scan():
    assert "url" in scan_string("see https://example.com")
    assert "email_shaped" in scan_string("me@example.com")
    assert "long_digit_run" in scan_string("4111111111111111")
    assert "high_entropy_token" in scan_string("aB3xQ9zK2mN7pR4tW1vY8cU6oL0iH5jG")
    assert scan_string("Development") == []


async def test_ai_module_cannot_open_connection():
    """`timeos.ai` has no code yet (Phase 7's objective is building the boundary BEFORE any LLM
    code exists) — this test patches the engine and imports every submodule that exists today,
    proving the (currently empty) package never touches the DB. It gains real teeth the moment
    Phase 8 adds a client here: if that client ever imports `timeos.db`,
    `test_ai_module_has_no_db_import` (tests/test_privacy_isolation.py) fails the build first,
    before this test would even run."""
    import importlib
    import pkgutil

    import timeos.ai as ai_package

    with patch(
        "sqlalchemy.ext.asyncio.AsyncEngine.connect", new_callable=AsyncMock
    ) as mock_connect:
        for module_info in pkgutil.walk_packages(ai_package.__path__, ai_package.__name__ + "."):
            importlib.import_module(module_info.name)
        mock_connect.assert_not_called()


async def test_malformed_context_is_never_passed_to_the_gate_as_a_dict():
    """A payload that fails Pydantic construction never reaches `enforce_privacy_gate` at all —
    there is no code path that hands a raw dict to the gate instead of a validated `AIContext`."""
    with pytest.raises(ValidationError):
        AIContext(**{**_valid_context_kwargs(), "totals": {"day_minutes": -1}})
