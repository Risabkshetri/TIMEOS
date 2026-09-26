"""§22.10: the `LLMProvider` protocol, its four spec-named implementations (Anthropic, OpenAI,
Ollama, Null), and two more added for practical testing: `GroqProvider` and `GoogleAIProvider`,
whose genuinely free tiers (no payment method required) make it possible to exercise a REAL
provider call while building/verifying this system — Anthropic and OpenAI are paid-only, and
Ollama needs a local model install.

Every real provider here makes a plain `httpx` POST against the provider's own REST API rather
than an official SDK — no SDK version churn, and everything that leaves this process for a
third-party LLM is visible in one small, auditable module. No provider is ever given tool/
function-calling capability (§22.1: "no tools, no functions") — every request is a single-turn
text completion; a JSON-only instruction lives in the prompt (`timeos.ai.prompts`), and
`timeos.ai.validate` is what actually enforces the output shape post-hoc, exactly as §22.3
requires regardless of provider. OpenAI/Groq's `response_format: json_object` and Ollama's
`format: json` are used where available — a decoding-mode hint, not a tool or a function, so this
doesn't contradict rule 1.

This module has no DB import and never will (§20.2's structural isolation contract) — provider
selection reads plain config values (`ai_provider`, `ai_api_key`, `ai_model`) that the caller
(`timeos.jobs.daily_analysis`) resolves from `timeos.config.Settings` and passes in.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

REQUEST_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class Message:
    role: str  # "system" | "user"
    content: str


@dataclass(frozen=True, slots=True)
class CompletionResult:
    text: str
    token_in: int
    token_out: int
    cost_usd: float
    latency_ms: int


class ProviderError(Exception):
    """A provider call failed outright (network error, timeout, non-2xx response). §22's
    "provider outage → job fails cleanly" — the caller catches this and leaves the day without an
    AI narrative rather than raising through to a broken dashboard."""


class LLMProvider(Protocol):
    model_name: str

    async def complete(self, messages: list[Message]) -> CompletionResult: ...


class NullProvider:
    """§22.10: "used in all tests and whenever no key is configured — the system must run with
    zero AI configuration." Returns a fixed, always-valid, epistemically-empty analysis: zero
    insights, zero recommendations, a neutral day_score. Whether that neutral score survives
    `timeos.analytics.day_score`'s ±15 band check depends on the real day it's checked against —
    deliberately not special-cased, so this provider exercises the exact same validation path
    every other provider's output does."""

    NEUTRAL_DAY_SCORE = 50
    model_name = "none"

    async def complete(self, messages: list[Message]) -> CompletionResult:
        text = json.dumps(
            {
                "day_score": self.NEUTRAL_DAY_SCORE,
                "score_rationale": (
                    "No AI provider is configured; this is a neutral placeholder, not an "
                    "assessment."
                ),
                "summary": "No AI analysis was performed for this day.",
                "data_caveats": [],
                "wins": [],
                "problems": [],
                "patterns": [],
                "distractions": [],
                "goal_alignment": [],
                "recommendations": [],
                "tomorrow_priorities": [],
                "overall_confidence": 0.0,
            }
        )
        return CompletionResult(text=text, token_in=0, token_out=0, cost_usd=0.0, latency_ms=0)


def _elapsed_ms(start: float) -> int:
    return round((time.monotonic() - start) * 1000)


def _split_system_and_user(messages: list[Message]) -> tuple[str | None, list[Message]]:
    system = next((m.content for m in messages if m.role == "system"), None)
    rest = [m for m in messages if m.role != "system"]
    return system, rest


class AnthropicProvider:
    """https://docs.anthropic.com/en/api/messages — plain HTTP, no tool use."""

    API_URL = "https://api.anthropic.com/v1/messages"
    ANTHROPIC_VERSION = "2023-06-01"
    MAX_OUTPUT_TOKENS = 2000
    # USD per token — Claude Haiku-class pricing, order of magnitude only (Anthropic's published
    # rates change independently of this code). §22.9/Phase 8's $0.50-for-7-days budget requires
    # a cheap, small model here, not a flagship one — `model` should reflect that at call sites.
    COST_PER_INPUT_TOKEN = 0.0000008
    COST_PER_OUTPUT_TOKEN = 0.000004

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self.model_name = model

    async def complete(self, messages: list[Message]) -> CompletionResult:
        system, rest = _split_system_and_user(messages)
        body = {
            "model": self.model_name,
            "max_tokens": self.MAX_OUTPUT_TOKENS,
            "messages": [{"role": m.role, "content": m.content} for m in rest],
        }
        if system is not None:
            body["system"] = system

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self.API_URL,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": self.ANTHROPIC_VERSION,
                        "content-type": "application/json",
                    },
                    json=body,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Anthropic request failed: {exc}") from exc

        payload = response.json()
        text = "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        )
        usage = payload.get("usage", {})
        token_in = usage.get("input_tokens", 0)
        token_out = usage.get("output_tokens", 0)
        cost_usd = token_in * self.COST_PER_INPUT_TOKEN + token_out * self.COST_PER_OUTPUT_TOKEN

        return CompletionResult(
            text=text,
            token_in=token_in,
            token_out=token_out,
            cost_usd=cost_usd,
            latency_ms=_elapsed_ms(start),
        )


async def _openai_compatible_complete(
    *,
    api_url: str,
    api_key: str,
    model: str,
    messages: list[Message],
    cost_per_input_token: float,
    cost_per_output_token: float,
    provider_label: str,
) -> CompletionResult:
    """Shared request/response handling for any Chat-Completions-compatible endpoint
    (OpenAI itself, and Groq's OpenAI-compatible API). `response_format: json_object` constrains
    decoding to syntactically valid JSON; it is not a tool or a function call, so this doesn't
    violate §22.1's "no tools, no functions"."""
    body = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "response_format": {"type": "json_object"},
    }

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderError(f"{provider_label} request failed: {exc}") from exc

    payload = response.json()
    text = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage", {})
    token_in = usage.get("prompt_tokens", 0)
    token_out = usage.get("completion_tokens", 0)
    cost_usd = token_in * cost_per_input_token + token_out * cost_per_output_token

    return CompletionResult(
        text=text,
        token_in=token_in,
        token_out=token_out,
        cost_usd=cost_usd,
        latency_ms=_elapsed_ms(start),
    )


class OpenAIProvider:
    """https://platform.openai.com/docs/api-reference/chat — Chat Completions, plain HTTP."""

    API_URL = "https://api.openai.com/v1/chat/completions"
    # USD per token — gpt-4o-mini-class pricing, order of magnitude only.
    COST_PER_INPUT_TOKEN = 0.00000015
    COST_PER_OUTPUT_TOKEN = 0.0000006

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self.model_name = model

    async def complete(self, messages: list[Message]) -> CompletionResult:
        return await _openai_compatible_complete(
            api_url=self.API_URL,
            api_key=self._api_key,
            model=self.model_name,
            messages=messages,
            cost_per_input_token=self.COST_PER_INPUT_TOKEN,
            cost_per_output_token=self.COST_PER_OUTPUT_TOKEN,
            provider_label="OpenAI",
        )


class GroqProvider:
    """https://console.groq.com/docs/api-reference#chat-create — Groq's API is Chat-Completions
    compatible (same request/response shape as OpenAI), just a different host and model catalogue.
    Added alongside the spec's four named providers because Groq's free tier (rate-limited, no
    payment method required) makes it practical to actually exercise a REAL provider call while
    building/testing this system, unlike Anthropic/OpenAI (paid-only) or Ollama (needs a local
    install) — see also `GoogleAIProvider` for the same reason."""

    API_URL = "https://api.groq.com/openai/v1/chat/completions"
    # USD per token — llama-3.1-8b-instant-class pricing, order of magnitude only; $0 in practice
    # while a project stays within Groq's free-tier rate limits.
    COST_PER_INPUT_TOKEN = 0.00000005
    COST_PER_OUTPUT_TOKEN = 0.00000008

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self.model_name = model

    async def complete(self, messages: list[Message]) -> CompletionResult:
        return await _openai_compatible_complete(
            api_url=self.API_URL,
            api_key=self._api_key,
            model=self.model_name,
            messages=messages,
            cost_per_input_token=self.COST_PER_INPUT_TOKEN,
            cost_per_output_token=self.COST_PER_OUTPUT_TOKEN,
            provider_label="Groq",
        )


class GoogleAIProvider:
    """https://ai.google.dev/api/generate-content — Gemini's `generateContent` REST endpoint.
    Added alongside the spec's four named providers for the same reason as `GroqProvider`: a
    genuinely free tier (an API key from Google AI Studio, no payment method required) makes real
    end-to-end testing possible without spending money. No tool/function-calling config is ever
    sent, matching §22.1."""

    API_URL_TEMPLATE = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    # USD per token — Gemini Flash-class pricing, order of magnitude only; $0 in practice while a
    # project stays within Google AI Studio's free tier.
    COST_PER_INPUT_TOKEN = 0.000000075
    COST_PER_OUTPUT_TOKEN = 0.0000003

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self.model_name = model

    async def complete(self, messages: list[Message]) -> CompletionResult:
        system, rest = _split_system_and_user(messages)
        body: dict = {
            "contents": [
                {"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]}
                for m in rest
            ],
        }
        if system is not None:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        url = self.API_URL_TEMPLATE.format(model=self.model_name)
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    url,
                    headers={"x-goog-api-key": self._api_key, "content-type": "application/json"},
                    json=body,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Google AI request failed: {exc}") from exc

        payload = response.json()
        text = "".join(
            part.get("text", "")
            for part in payload["candidates"][0]["content"]["parts"]
        )
        usage = payload.get("usageMetadata", {})
        token_in = usage.get("promptTokenCount", 0)
        token_out = usage.get("candidatesTokenCount", 0)
        cost_usd = token_in * self.COST_PER_INPUT_TOKEN + token_out * self.COST_PER_OUTPUT_TOKEN

        return CompletionResult(
            text=text,
            token_in=token_in,
            token_out=token_out,
            cost_usd=cost_usd,
            latency_ms=_elapsed_ms(start),
        )


class OllamaProvider:
    """https://github.com/ollama/ollama/blob/main/docs/api.md#generate-a-chat-completion — a
    locally-hosted model, no API key, no external billing (`cost_usd` is always 0.0). `base_url`
    defaults to Ollama's own local default; a Docker deployment reaching a host-run Ollama needs
    an explicit URL (e.g. `http://host.docker.internal:11434`), which isn't this personal system's
    default deployment shape today."""

    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, model: str, base_url: str = DEFAULT_BASE_URL) -> None:
        self.model_name = model
        self._base_url = base_url.rstrip("/")

    async def complete(self, messages: list[Message]) -> CompletionResult:
        body = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "format": "json",
        }

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=body)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc

        payload = response.json()
        text = payload.get("message", {}).get("content", "")

        return CompletionResult(
            text=text,
            token_in=payload.get("prompt_eval_count", 0),
            token_out=payload.get("eval_count", 0),
            cost_usd=0.0,
            latency_ms=_elapsed_ms(start),
        )


DEFAULT_MODELS = {
    "anthropic": "claude-3-5-haiku-20241022",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.1",
    # Groq and Google AI both have a genuinely free tier — the two providers actually usable for
    # real end-to-end testing without a paid key. Verify the exact current free-tier model name in
    # each provider's own console before relying on it; provider catalogues change independently
    # of this code.
    "groq": "llama-3.1-8b-instant",
    "google": "gemini-1.5-flash",
}


def get_provider(provider_name: str, api_key: str | None, model: str | None) -> LLMProvider:
    """§22.10's provider selection: plain config values in, a provider out — never raises. An
    unknown provider name, or a real provider missing its required API key, falls back to
    `NullProvider` rather than crash the job; §22.10 is explicit that zero AI configuration must
    always be a working state, not just the `provider_name == "null"` case."""
    name = (provider_name or "").strip().lower()
    resolved_model = model or DEFAULT_MODELS.get(name)

    if name == "anthropic" and api_key:
        return AnthropicProvider(
            api_key=api_key, model=resolved_model or DEFAULT_MODELS["anthropic"]
        )
    if name == "openai" and api_key:
        return OpenAIProvider(api_key=api_key, model=resolved_model or DEFAULT_MODELS["openai"])
    if name == "groq" and api_key:
        return GroqProvider(api_key=api_key, model=resolved_model or DEFAULT_MODELS["groq"])
    if name in ("google", "google_ai", "gemini") and api_key:
        return GoogleAIProvider(api_key=api_key, model=resolved_model or DEFAULT_MODELS["google"])
    if name == "ollama":
        return OllamaProvider(model=resolved_model or DEFAULT_MODELS["ollama"])
    return NullProvider()
