"""§23.3's anti-fabrication validator, §22.3's schema gate, §22.6's confidence ceiling, §22.7's
rejection list — all pure-function, no DB."""

import pytest

from timeos.ai.validate import (
    SchemaValidationFailed,
    contains_rejected_term,
    flatten_context_numbers,
    parse_and_validate_schema,
    resolve_path,
    text_numbers_are_grounded,
    validate_and_sanitize,
)
from timeos.schemas.ai_context import (
    AIContext,
    Baselines,
    DataQuality,
    FocusSummary,
    GoalSummary,
    Totals,
)


def _context(**overrides) -> dict:
    context = AIContext(
        scope="day",
        date="2026-09-13",
        weekday="Sunday",
        data_quality=DataQuality(
            coverage_ratio=overrides.get("coverage_ratio", 0.9),
            unknown_ratio=overrides.get("unknown_ratio", 0.05),
            devices_reporting=["android"],
            unobserved_minutes=0,
            offline_minutes=0,
        ),
        totals=Totals(
            day_minutes=1440, observed_minutes=500, screen_minutes=431, active_minutes=388
        ),
        focus=FocusSummary(
            sessions=4,
            deep_sessions=1,
            longest_minutes=52,
            average_minutes=24,
            total_focus_minutes=96,
            avg_quality=0.61,
            fragmentation_index=0.58,
            context_switches=51,
            switches_per_hour=6.1,
            interruptions=13,
        ),
        goals=[
            GoalSummary(
                name="Build",
                priority=1,
                target_weekly_minutes=1200,
                aligned_minutes_today=186,
                uncertainty=28,
                week_attainment=0.41,
            )
        ],
        baselines=Baselines(
            window_days=30,
            valid_days=26,
            screen_minutes_mean=452,
            deep_work_minutes_mean=61,
            fragmentation_mean=0.48,
        ),
    )
    return context.model_dump(mode="json")


def _valid_output_json(**overrides) -> str:
    import json

    payload = {
        "day_score": overrides.get("day_score", 68),
        "score_rationale": overrides.get("score_rationale", "Solid focus, some fragmentation."),
        "summary": overrides.get("summary", "A reasonably focused day with one deep session."),
        "data_caveats": overrides.get("data_caveats", []),
        "wins": overrides.get("wins", []),
        "problems": overrides.get("problems", []),
        "patterns": overrides.get("patterns", []),
        "distractions": overrides.get("distractions", []),
        "goal_alignment": overrides.get("goal_alignment", []),
        "recommendations": overrides.get("recommendations", []),
        "tomorrow_priorities": overrides.get("tomorrow_priorities", []),
        "overall_confidence": overrides.get("overall_confidence", 0.8),
    }
    return json.dumps(payload)


def _insight(claim, fields, values, narrative, confidence=0.8, epistemic_status="INFERENCE"):
    return {
        "claim": claim,
        "evidence": {"fields": fields, "values": values, "narrative": narrative},
        "confidence": confidence,
        "epistemic_status": epistemic_status,
    }


# --- schema gate -------------------------------------------------------------


def test_parse_and_validate_schema_accepts_valid_json():
    output = parse_and_validate_schema(_valid_output_json())
    assert output.day_score == 68


def test_parse_and_validate_schema_rejects_invalid_json():
    with pytest.raises(SchemaValidationFailed):
        parse_and_validate_schema("not json at all {")


def test_parse_and_validate_schema_rejects_out_of_range_day_score():
    with pytest.raises(SchemaValidationFailed):
        parse_and_validate_schema(_valid_output_json(day_score=150))


def test_parse_and_validate_schema_rejects_too_many_wins():
    wins = [
        _insight(f"win {i}", ["focus.sessions"], {"sessions": 4}, "narrative")
        for i in range(5)
    ]
    with pytest.raises(SchemaValidationFailed):
        parse_and_validate_schema(_valid_output_json(wins=wins))


# --- evidence path resolution --------------------------------------------------


def test_resolve_path_dotted():
    context = _context()
    found, value = resolve_path(context, "focus.context_switches")
    assert found
    assert value == 51


def test_resolve_path_bracket_index():
    context = _context()
    found, value = resolve_path(context, "goals[0].week_attainment")
    assert found
    assert value == pytest.approx(0.41)


def test_resolve_path_missing_key_is_not_found():
    context = _context()
    found, _value = resolve_path(context, "focus.nonexistent_field")
    assert not found


def test_resolve_path_out_of_range_index_is_not_found():
    context = _context()
    found, _value = resolve_path(context, "goals[5].name")
    assert not found


# --- numeric grounding ----------------------------------------------------------


def test_flatten_context_numbers_excludes_booleans():
    # True/False are int subclasses in Python (True == 1), so this checks the actual count and
    # values rather than `in`, which would spuriously pass due to that equality.
    numbers = flatten_context_numbers({"a": True, "b": 1, "c": [False, 2.5]})
    assert numbers == [1.0, 2.5]


def test_text_numbers_are_grounded_exact_match():
    context_numbers = flatten_context_numbers(_context())
    assert text_numbers_are_grounded("You had 51 context switches today.", context_numbers)


def test_text_numbers_are_grounded_percentage_match():
    # share isn't in this fixture's context directly, but week_attainment (0.41) is — "41%"
    # should ground against it.
    context_numbers = flatten_context_numbers(_context())
    assert text_numbers_are_grounded("You're at 41% of your weekly goal.", context_numbers)


def test_text_numbers_are_grounded_rejects_a_fabricated_number():
    context_numbers = flatten_context_numbers(_context())
    assert not text_numbers_are_grounded("You had 999 context switches today.", context_numbers)


# --- rejection list -----------------------------------------------------------


def test_contains_rejected_term_case_insensitive():
    assert contains_rejected_term("This looks like an ADDICTION.")


def test_contains_rejected_term_does_not_match_a_word_it_is_only_a_prefix_of():
    # "clinical" is a rejected term, but "clinically" is a different word — whole-word matching
    # means it must not fire on "clinical" merely appearing as a prefix.
    assert not contains_rejected_term("The room was organized clinically.")


def test_contains_rejected_term_ignores_unrelated_text():
    assert not contains_rejected_term("The synod met on Tuesday.")


def test_clean_text_is_not_flagged():
    assert not contains_rejected_term("You had a focused, productive morning.")


# --- full validate_and_sanitize pipeline ---------------------------------------


def test_drops_insight_with_unresolvable_evidence_path():
    context = _context()
    output = parse_and_validate_schema(
        _valid_output_json(
            wins=[
                _insight(
                    "You had 51 context switches.",
                    ["focus.nonexistent_field"],
                    {"x": 51},
                    "51 context switches occurred.",
                )
            ]
        )
    )
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert result.wins == []
    assert result.validation_status == "partial"


def test_drops_insight_with_a_fabricated_number():
    context = _context()
    output = parse_and_validate_schema(
        _valid_output_json(
            wins=[
                _insight(
                    "You had 999 context switches.",
                    ["focus.context_switches"],
                    {"context_switches": 999},
                    "narrative",
                )
            ]
        )
    )
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert result.wins == []
    assert result.validation_status == "partial"


def test_keeps_insight_with_correctly_grounded_evidence():
    context = _context()
    output = parse_and_validate_schema(
        _valid_output_json(
            wins=[
                _insight(
                    "You had 51 context switches.",
                    ["focus.context_switches"],
                    {"context_switches": 51},
                    "51 context switches were recorded.",
                )
            ]
        )
    )
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert len(result.wins) == 1
    assert result.validation_status == "ok"


def test_downgrades_fact_with_derived_evidence_to_inference():
    context = _context()
    output = parse_and_validate_schema(
        _valid_output_json(
            wins=[
                _insight(
                    "You're at 41% of your weekly goal.",
                    ["goals[0].week_attainment"],
                    {"week_attainment": 0.41},
                    "41% attainment so far.",
                    epistemic_status="FACT",
                )
            ]
        )
    )
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert len(result.wins) == 1
    assert result.wins[0].epistemic_status == "INFERENCE"


def test_keeps_fact_with_directly_measured_evidence():
    context = _context()
    output = parse_and_validate_schema(
        _valid_output_json(
            wins=[
                _insight(
                    "You had 51 context switches.",
                    ["focus.context_switches"],
                    {"context_switches": 51},
                    "51 context switches were recorded.",
                    epistemic_status="FACT",
                )
            ]
        )
    )
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert result.wins[0].epistemic_status == "FACT"


def test_day_score_outside_band_is_dropped_but_narrative_kept():
    context = _context()
    output = parse_and_validate_schema(_valid_output_json(day_score=95))
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert result.day_score is None
    assert result.score_rationale is not None
    assert result.validation_status == "partial"


def test_day_score_within_band_is_kept():
    context = _context()
    output = parse_and_validate_schema(_valid_output_json(day_score=75))
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert result.day_score == 75
    assert result.validation_status == "ok"


def test_confidence_is_capped_under_low_coverage():
    context = _context(coverage_ratio=0.3)
    output = parse_and_validate_schema(
        _valid_output_json(
            overall_confidence=0.95,
            wins=[
                _insight(
                    "You had 51 context switches.",
                    ["focus.context_switches"],
                    {"context_switches": 51},
                    "51 context switches were recorded.",
                    confidence=0.95,
                )
            ],
        )
    )
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert result.overall_confidence <= 0.7
    assert result.wins[0].confidence <= 0.7


def test_confidence_is_capped_under_high_unknown_ratio():
    context = _context(unknown_ratio=0.5)
    output = parse_and_validate_schema(_valid_output_json(overall_confidence=0.95))
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert result.overall_confidence <= 0.7


def test_medical_language_drops_the_summary():
    context = _context()
    output = parse_and_validate_schema(
        _valid_output_json(summary="This pattern resembles an addiction.")
    )
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert result.summary is None
    assert result.validation_status == "partial"


def test_nothing_dropped_is_marked_ok():
    context = _context()
    output = parse_and_validate_schema(_valid_output_json(day_score=68))
    result = validate_and_sanitize(output, context, reference_day_score=68)
    assert result.validation_status == "ok"
