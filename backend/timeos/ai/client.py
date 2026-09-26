"""§22.3's repair-retry policy: "Invalid → one repair attempt with the validation errors appended
→ second failure → discard." This is the one place that policy is implemented — the caller
(`timeos.jobs.daily_analysis`) just gets back either a validated `AIAnalysisOutput` or `None`,
plus the accumulated cost/latency/token usage across BOTH attempts (a repair attempt still spends
real money and must still count against the budget cap). Still no DB access here.
"""

from __future__ import annotations

from dataclasses import dataclass

from timeos.ai.prompts import build_analysis_messages, build_repair_messages
from timeos.ai.provider import LLMProvider
from timeos.ai.validate import SchemaValidationFailed, parse_and_validate_schema
from timeos.schemas.ai_output import AIAnalysisOutput


@dataclass(frozen=True, slots=True)
class AnalysisAttempt:
    output: AIAnalysisOutput | None  # None means both the original and the repair attempt failed
    raw_text: str  # the LAST raw text received — always stored (ai_analysis.raw_output)
    token_in: int
    token_out: int
    cost_usd: float
    latency_ms: int
    repaired: bool


async def request_analysis(
    provider: LLMProvider, context: dict, output_schema: dict
) -> AnalysisAttempt:
    """Raises `timeos.ai.provider.ProviderError` if the underlying HTTP call itself fails — that's
    the caller's "provider outage" case, distinct from a call that succeeds but returns output
    that never validates (this function's own `output=None` return)."""
    messages = build_analysis_messages(context, output_schema)
    first = await provider.complete(messages)

    try:
        output = parse_and_validate_schema(first.text)
        return AnalysisAttempt(
            output=output,
            raw_text=first.text,
            token_in=first.token_in,
            token_out=first.token_out,
            cost_usd=first.cost_usd,
            latency_ms=first.latency_ms,
            repaired=False,
        )
    except SchemaValidationFailed as first_error:
        repair_messages = build_repair_messages(
            context, output_schema, first.text, first_error.errors
        )
        second = await provider.complete(repair_messages)
        combined_token_in = first.token_in + second.token_in
        combined_token_out = first.token_out + second.token_out
        combined_cost = first.cost_usd + second.cost_usd
        combined_latency = first.latency_ms + second.latency_ms

        try:
            output = parse_and_validate_schema(second.text)
        except SchemaValidationFailed:
            output = None

        return AnalysisAttempt(
            output=output,
            raw_text=second.text,
            token_in=combined_token_in,
            token_out=combined_token_out,
            cost_usd=combined_cost,
            latency_ms=combined_latency,
            repaired=True,
        )
