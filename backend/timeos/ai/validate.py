"""§23.3's anti-fabrication validator, plus §22.3's schema gate and §22.7's rejection list.

Pure functions over plain dicts/the `AIAnalysisOutput` schema — no DB, no provider code. This is
the ONE place §22's safety rules actually get enforced; the prompt (`timeos.ai.prompts`) only asks
the model nicely, and a model that ignores every instruction still can't get an insight persisted
here unless its evidence resolves, its numbers are grounded, and its language passes the
rejection list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from timeos.schemas.ai_output import (
    INSIGHT_SECTIONS,
    AIAnalysisOutput,
    Insight,
    Recommendation,
)

NUMERIC_MATCH_TOLERANCE_RATIO = 0.02
NUMERIC_MATCH_TOLERANCE_FLOOR = 0.005
DAY_SCORE_BAND = 15

# §22.6: "When coverage_ratio < 0.6 or unknown_ratio > 0.3 ... a validator rejects output whose
# max confidence exceeds 0.7 under those conditions."
LOW_DATA_QUALITY_COVERAGE_THRESHOLD = 0.6
LOW_DATA_QUALITY_UNKNOWN_RATIO_THRESHOLD = 0.3
LOW_DATA_QUALITY_CONFIDENCE_CEILING = 0.7

# §22.7: "No medical, psychiatric, or diagnostic language. A rejection list is applied to output
# strings." Matched case-insensitively as whole words, so e.g. "syndrome" doesn't also flag on an
# unrelated substring. Not exhaustive — a documented starting set, extendable without touching the
# validator's logic.
REJECTED_TERMS = frozenset(
    {
        "disorder",
        "addiction",
        "addicted",
        "adhd",
        "depression",
        "depressed",
        "anxiety",
        "diagnosis",
        "diagnose",
        "diagnostic",
        "clinical",
        "pathological",
        "pathology",
        "syndrome",
        "psychiatric",
        "mental illness",
        "burnout",
    }
)
_REJECTED_TERMS_RE = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in REJECTED_TERMS) + r")\b", re.IGNORECASE
)

# §23.3 rule 4: a FACT's evidence must be a "directly measured field". These sections are
# themselves already statistical/inferential derivations (§18: goal alignment "is an ESTIMATE,
# always rendered with its uncertainty band"; §17: patterns are detected, not counted; baselines
# are means/deltas over history; a session's quality/fragmentation are computed scores, not raw
# counts) — an insight citing ONLY these as evidence can never be a FACT, only an INFERENCE.
_DERIVED_PATH_PREFIXES = (
    "goals",
    "patterns",
    "baselines",
    "focus.avg_quality",
    "focus.fragmentation_index",
)

_PATH_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\d+)\]")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?%?")


class SchemaValidationFailed(Exception):
    def __init__(self, errors: str) -> None:
        self.errors = errors
        super().__init__(errors)


def parse_and_validate_schema(raw_text: str) -> AIAnalysisOutput:
    """§22.3's first gate: valid JSON, valid against `AIAnalysisOutput`. Raises
    `SchemaValidationFailed` (never a bare exception) so the caller can decide whether to attempt
    the one allowed repair (`timeos.ai.prompts.build_repair_messages`)."""
    try:
        return AIAnalysisOutput.model_validate_json(raw_text)
    except ValidationError as exc:
        raise SchemaValidationFailed(str(exc)) from exc
    except ValueError as exc:  # json.JSONDecodeError is a ValueError subclass
        raise SchemaValidationFailed(f"not valid JSON: {exc}") from exc


def resolve_path(context: dict, path: str) -> tuple[bool, object]:
    """§23.3 rule 1: an evidence path must resolve in the source context. Returns (found, value)
    rather than raising/returning a sentinel, so a genuinely-present `None` or `0` can't be
    confused with "not found"."""
    current: object = context
    consumed_anything = False
    for match in _PATH_TOKEN_RE.finditer(path):
        consumed_anything = True
        key, index = match.group(1), match.group(2)
        if key is not None:
            if not isinstance(current, dict) or key not in current:
                return False, None
            current = current[key]
        else:
            idx = int(index)
            if not isinstance(current, list) or idx >= len(current) or idx < 0:
                return False, None
            current = current[idx]
    if not consumed_anything:
        return False, None
    return True, current


def _flatten_numbers(node: object, acc: list[float]) -> None:
    if isinstance(node, bool):
        return  # bool is an int subclass in Python — never a legitimate numeric evidence value
    if isinstance(node, int | float):
        acc.append(float(node))
    elif isinstance(node, dict):
        for value in node.values():
            _flatten_numbers(value, acc)
    elif isinstance(node, list):
        for value in node:
            _flatten_numbers(value, acc)


def flatten_context_numbers(context: dict) -> list[float]:
    acc: list[float] = []
    _flatten_numbers(context, acc)
    return acc


def _matches_any(value: float, candidates: list[float]) -> bool:
    for candidate in candidates:
        tolerance = max(
            abs(candidate) * NUMERIC_MATCH_TOLERANCE_RATIO, NUMERIC_MATCH_TOLERANCE_FLOOR
        )
        if abs(value - candidate) <= tolerance:
            return True
    return False


def _number_is_grounded(raw_match: str, context_numbers: list[float]) -> bool:
    is_percentage = raw_match.endswith("%")
    value = float(raw_match.rstrip("%"))
    if is_percentage:
        return _matches_any(value / 100, context_numbers) or _matches_any(value, context_numbers)
    return _matches_any(value, context_numbers)


def text_numbers_are_grounded(text: str, context_numbers: list[float]) -> bool:
    """§23.3 rule 2: every numeric literal in the text must match a context value within 2%."""
    return all(_number_is_grounded(m.group(), context_numbers) for m in _NUMBER_RE.finditer(text))


def contains_rejected_term(text: str) -> bool:
    return _REJECTED_TERMS_RE.search(text) is not None


def _is_derived_field(field_path: str) -> bool:
    return any(
        field_path == prefix
        or field_path.startswith(prefix + ".")
        or field_path.startswith(prefix + "[")
        for prefix in _DERIVED_PATH_PREFIXES
    )


def _is_derived_evidence(fields: list[str]) -> bool:
    return all(_is_derived_field(f) for f in fields)


@dataclass(frozen=True, slots=True)
class ValidatedAnalysis:
    day_score: int | None
    score_rationale: str | None
    summary: str | None
    data_caveats: list[str]
    wins: list[Insight] = field(default_factory=list)
    problems: list[Insight] = field(default_factory=list)
    patterns: list[Insight] = field(default_factory=list)
    distractions: list[Insight] = field(default_factory=list)
    goal_alignment: list[Insight] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    tomorrow_priorities: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0
    validation_status: str = "ok"  # ok | partial

    def total_insight_count(self) -> int:
        return (
            len(self.wins)
            + len(self.problems)
            + len(self.patterns)
            + len(self.distractions)
            + len(self.goal_alignment)
        )


def _validate_insight(
    insight: Insight, context: dict, context_numbers: list[float]
) -> Insight | None:
    for evidence_path in insight.evidence.fields:
        found, _value = resolve_path(context, evidence_path)
        if not found:
            return None  # §23.3 rule 1: unresolvable evidence path → drop the whole insight

    evidence_verified = text_numbers_are_grounded(
        insight.claim, context_numbers
    ) and text_numbers_are_grounded(insight.evidence.narrative, context_numbers)
    if not evidence_verified:
        return None  # §23.3 rule 2: an unmatched number drops the insight

    if contains_rejected_term(insight.claim) or contains_rejected_term(insight.evidence.narrative):
        return None  # §22.7

    epistemic_status = insight.epistemic_status
    if epistemic_status == "FACT" and _is_derived_evidence(insight.evidence.fields):
        insight = insight.model_copy(update={"epistemic_status": "INFERENCE"})  # §23.3 rule 4

    return insight


def _validate_recommendation(
    rec: Recommendation, context_numbers: list[float]
) -> Recommendation | None:
    text = f"{rec.action} {rec.rationale} {rec.expected_effect} {rec.measurable_check}"
    if not text_numbers_are_grounded(text, context_numbers):
        return None
    if contains_rejected_term(text):
        return None
    return rec


def validate_and_sanitize(
    output: AIAnalysisOutput, context: dict, reference_day_score: int
) -> ValidatedAnalysis:
    """Runs every §23.3/§22.6/§22.7 check and returns only what survives. Never raises — a bad
    analysis degrades to fewer (or zero) insights, not an exception the caller has to handle."""
    context_numbers = flatten_context_numbers(context)
    started_status = "ok"

    day_score: int | None = output.day_score
    if abs(output.day_score - reference_day_score) > DAY_SCORE_BAND:
        day_score = None
        started_status = "partial"

    score_rationale: str | None = output.score_rationale
    if contains_rejected_term(output.score_rationale):
        score_rationale = None
        started_status = "partial"

    summary: str | None = output.summary
    if contains_rejected_term(output.summary):
        summary = None
        started_status = "partial"

    sections: dict[str, list[Insight]] = {}
    for section_name in INSIGHT_SECTIONS:
        raw_insights: list[Insight] = getattr(output, section_name)
        survivors: list[Insight] = [
            validated_insight
            for insight in raw_insights
            if (validated_insight := _validate_insight(insight, context, context_numbers))
            is not None
        ]
        if len(survivors) != len(raw_insights):
            started_status = "partial"
        sections[section_name] = survivors

    recommendations: list[Recommendation] = [
        validated_rec
        for rec in output.recommendations
        if (validated_rec := _validate_recommendation(rec, context_numbers)) is not None
    ]
    if len(recommendations) != len(output.recommendations):
        started_status = "partial"

    tomorrow_priorities = [p for p in output.tomorrow_priorities if not contains_rejected_term(p)]
    if len(tomorrow_priorities) != len(output.tomorrow_priorities):
        started_status = "partial"

    data_caveats = [c for c in output.data_caveats if not contains_rejected_term(c)]
    if len(data_caveats) != len(output.data_caveats):
        started_status = "partial"

    overall_confidence = output.overall_confidence
    low_data_quality = False
    found, coverage_ratio = resolve_path(context, "data_quality.coverage_ratio")
    if found and isinstance(coverage_ratio, int | float):
        low_data_quality = low_data_quality or coverage_ratio < LOW_DATA_QUALITY_COVERAGE_THRESHOLD
    found, unknown_ratio = resolve_path(context, "data_quality.unknown_ratio")
    if found and isinstance(unknown_ratio, int | float):
        low_data_quality = (
            low_data_quality or unknown_ratio > LOW_DATA_QUALITY_UNKNOWN_RATIO_THRESHOLD
        )

    if low_data_quality:
        overall_confidence = min(overall_confidence, LOW_DATA_QUALITY_CONFIDENCE_CEILING)
        for section_name in INSIGHT_SECTIONS:
            sections[section_name] = [
                insight.model_copy(
                    update={
                        "confidence": min(insight.confidence, LOW_DATA_QUALITY_CONFIDENCE_CEILING)
                    }
                )
                for insight in sections[section_name]
            ]
        recommendations = [
            rec.model_copy(
                update={"confidence": min(rec.confidence, LOW_DATA_QUALITY_CONFIDENCE_CEILING)}
            )
            for rec in recommendations
        ]

    return ValidatedAnalysis(
        day_score=day_score,
        score_rationale=score_rationale,
        summary=summary,
        data_caveats=data_caveats,
        wins=sections["wins"],
        problems=sections["problems"],
        patterns=sections["patterns"],
        distractions=sections["distractions"],
        goal_alignment=sections["goal_alignment"],
        recommendations=recommendations,
        tomorrow_priorities=tomorrow_priorities,
        overall_confidence=overall_confidence,
        validation_status=started_status,
    )
