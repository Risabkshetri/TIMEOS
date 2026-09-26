"""§20.2's allowlist layer — the independent, dict-level backstop behind AIContext's own
`extra="forbid"` schema validation."""

from timeos.privacy.allowlist import find_disallowed_keys


def test_a_fully_valid_payload_has_no_disallowed_keys():
    payload = {
        "context_version": "1.0",
        "scope": "day",
        "categories": [{"category": "Development", "minutes": 186, "share": 0.43}],
        "baselines": {"today_vs_mean": {"fragmentation": "+0.10"}},
    }
    assert find_disallowed_keys(payload) == {}


def test_a_stray_top_level_key_is_flagged():
    payload = {"context_version": "1.0", "device_id": "abc-123"}
    violations = find_disallowed_keys(payload)
    assert "device_id" in violations
    assert violations["device_id"] == "device_id"


def test_a_stray_nested_key_is_flagged_with_its_path():
    payload = {"categories": [{"category": "Development", "package_name": "com.example.app"}]}
    violations = find_disallowed_keys(payload)
    assert "categories[0].package_name" in violations


def test_a_disallowed_key_inside_today_vs_mean_is_still_flagged():
    # today_vs_mean's OWN keys are restricted to a known set (schemas/ai_context.py's
    # TODAY_VS_MEAN_KEYS) — this walk catches a key that slipped past that schema validator too.
    payload = {"baselines": {"today_vs_mean": {"raw_note": "something free-text"}}}
    violations = find_disallowed_keys(payload)
    assert "baselines.today_vs_mean.raw_note" in violations


def test_a_raw_event_shaped_object_is_rejected_wholesale():
    # §33's test_raw_event_cannot_reach_llm, exercised at the allowlist layer directly: even if
    # some future bug let a raw_events row's shape reach the gate's input dict (bypassing
    # AIContext's own extra="forbid" schema entirely), this independent walk still catches it.
    raw_event = {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "device_id": "3fa85f64-5717-4562-b3fc-2c963f66afa7",
        "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa8",
        "seq": 42,
        "tz_offset_min": -300,
        "type": "APP_FOREGROUND",
        "payload": {"package": "com.example.app"},
        "clock_suspect": False,
        "schema_v": 1,
    }
    violations = find_disallowed_keys({"leaked_raw_event": raw_event})
    assert "leaked_raw_event" in violations
    for forbidden_key in ["device_id", "user_id", "payload", "clock_suspect", "schema_v"]:
        assert f"leaked_raw_event.{forbidden_key}" in violations
