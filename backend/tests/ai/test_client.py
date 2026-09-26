"""§22.3's one-repair-attempt policy (timeos.ai.client.request_analysis), against a fake
in-test provider double — no real network call, but real prompt-building and real schema
validation."""

from timeos.ai.client import request_analysis
from timeos.ai.provider import CompletionResult, Message

VALID_JSON = (
    '{"day_score": 60, "score_rationale": "ok", "summary": "A day.", "data_caveats": [], '
    '"wins": [], "problems": [], "patterns": [], "distractions": [], "goal_alignment": [], '
    '"recommendations": [], "tomorrow_priorities": [], "overall_confidence": 0.5}'
)


class _ScriptedProvider:
    """Returns each entry in `responses` in order, one per `complete()` call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[Message]] = []

    async def complete(self, messages: list[Message]) -> CompletionResult:
        self.calls.append(messages)
        text = self._responses.pop(0)
        return CompletionResult(text=text, token_in=10, token_out=20, cost_usd=0.001, latency_ms=5)


async def test_valid_first_response_needs_no_repair():
    provider = _ScriptedProvider([VALID_JSON])
    attempt = await request_analysis(provider, context={}, output_schema={})

    assert attempt.output is not None
    assert attempt.output.day_score == 60
    assert attempt.repaired is False
    assert len(provider.calls) == 1
    assert attempt.token_in == 10
    assert attempt.cost_usd == 0.001


async def test_invalid_first_response_triggers_exactly_one_repair_attempt():
    provider = _ScriptedProvider(["not json at all", VALID_JSON])
    attempt = await request_analysis(provider, context={}, output_schema={})

    assert attempt.output is not None
    assert attempt.repaired is True
    assert len(provider.calls) == 2
    # The repair prompt must reference the failed output so the model can actually fix it.
    repair_prompt = provider.calls[1][-1].content
    assert "not json at all" in repair_prompt


async def test_two_invalid_responses_in_a_row_yield_no_output():
    provider = _ScriptedProvider(["not json", "still not json"])
    attempt = await request_analysis(provider, context={}, output_schema={})

    assert attempt.output is None
    assert attempt.repaired is True
    assert attempt.raw_text == "still not json"


async def test_cost_and_tokens_accumulate_across_both_attempts():
    provider = _ScriptedProvider(["not json", VALID_JSON])
    attempt = await request_analysis(provider, context={}, output_schema={})

    assert attempt.token_in == 20  # 10 + 10
    assert attempt.token_out == 40  # 20 + 20
    assert attempt.cost_usd == 0.002  # 0.001 + 0.001
