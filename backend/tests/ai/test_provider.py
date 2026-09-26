"""§22.10's provider implementations — request shape and response parsing, mocked at the HTTP
layer (no real network calls, no real API key needed). `NullProvider`/`get_provider`'s fallback
behaviour is exercised for real end-to-end (it never touches the network)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from timeos.ai.provider import (
    AnthropicProvider,
    GoogleAIProvider,
    GroqProvider,
    Message,
    NullProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderError,
    get_provider,
)


class _FakeResponse:
    def __init__(self, json_data: dict) -> None:
        self._json = json_data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._json


# --- NullProvider / get_provider selection --------------------------------------


async def test_null_provider_returns_a_schema_valid_fixed_output():
    result = await NullProvider().complete([Message(role="user", content="hi")])
    assert '"day_score"' in result.text
    assert result.cost_usd == 0.0
    assert result.token_in == 0


def test_get_provider_returns_null_when_provider_name_is_null():
    assert isinstance(get_provider("null", None, None), NullProvider)


def test_get_provider_falls_back_to_null_when_api_key_missing():
    assert isinstance(get_provider("anthropic", None, None), NullProvider)
    assert isinstance(get_provider("openai", None, None), NullProvider)
    assert isinstance(get_provider("groq", None, None), NullProvider)
    assert isinstance(get_provider("google", None, None), NullProvider)


def test_get_provider_falls_back_to_null_for_an_unknown_name():
    assert isinstance(get_provider("some-made-up-provider", "key", None), NullProvider)


def test_get_provider_selects_groq_with_a_key():
    provider = get_provider("groq", "test-key", None)
    assert isinstance(provider, GroqProvider)
    assert provider.model_name  # a default model was resolved


def test_get_provider_selects_google_ai_with_a_key():
    provider = get_provider("google", "test-key", None)
    assert isinstance(provider, GoogleAIProvider)


def test_get_provider_selects_ollama_without_a_key():
    # Ollama is local — no API key required.
    provider = get_provider("ollama", None, None)
    assert isinstance(provider, OllamaProvider)


def test_get_provider_honours_an_explicit_model_override():
    provider = get_provider("groq", "test-key", "llama-3.3-70b-versatile")
    assert provider.model_name == "llama-3.3-70b-versatile"


# --- Groq (OpenAI-compatible) ----------------------------------------------------


async def test_groq_provider_parses_response_and_sends_the_right_shape():
    fake_response = _FakeResponse(
        {
            "choices": [{"message": {"content": '{"day_score": 50}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
    )
    with patch(
        "httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)
    ) as mock_post:
        provider = GroqProvider(api_key="test-key", model="llama-3.1-8b-instant")
        result = await provider.complete(
            [Message(role="system", content="sys"), Message(role="user", content="hi")]
        )

    assert result.text == '{"day_score": 50}'
    assert result.token_in == 100
    assert result.token_out == 50
    assert result.cost_usd > 0

    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["model"] == "llama-3.1-8b-instant"
    assert call_kwargs["json"]["response_format"] == {"type": "json_object"}
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert "api.groq.com" in mock_post.call_args.args[0]


async def test_openai_provider_uses_its_own_endpoint():
    fake_response = _FakeResponse(
        {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)) as mock_post:
        provider = OpenAIProvider(api_key="test-key", model="gpt-4o-mini")
        await provider.complete([Message(role="user", content="hi")])

    assert "api.openai.com" in mock_post.call_args.args[0]


async def test_groq_raises_provider_error_on_http_failure():
    with patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(side_effect=httpx.ConnectError("boom")),
    ):
        provider = GroqProvider(api_key="test-key", model="llama-3.1-8b-instant")
        with pytest.raises(ProviderError):
            await provider.complete([Message(role="user", content="hi")])


# --- Google AI (Gemini) ----------------------------------------------------------


async def test_google_ai_provider_parses_response_and_sends_the_right_shape():
    fake_response = _FakeResponse(
        {
            "candidates": [{"content": {"parts": [{"text": '{"day_score": 60}'}]}}],
            "usageMetadata": {"promptTokenCount": 200, "candidatesTokenCount": 80},
        }
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)) as mock_post:
        provider = GoogleAIProvider(api_key="test-key", model="gemini-1.5-flash")
        result = await provider.complete(
            [Message(role="system", content="sys"), Message(role="user", content="hi")]
        )

    assert result.text == '{"day_score": 60}'
    assert result.token_in == 200
    assert result.token_out == 80
    assert result.cost_usd > 0

    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["x-goog-api-key"] == "test-key"
    assert "systemInstruction" in call_kwargs["json"]
    assert call_kwargs["json"]["systemInstruction"]["parts"][0]["text"] == "sys"
    assert "gemini-1.5-flash" in mock_post.call_args.args[0]


async def test_google_ai_raises_provider_error_on_http_failure():
    with patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(side_effect=httpx.ConnectError("boom")),
    ):
        provider = GoogleAIProvider(api_key="test-key", model="gemini-1.5-flash")
        with pytest.raises(ProviderError):
            await provider.complete([Message(role="user", content="hi")])


# --- Anthropic --------------------------------------------------------------------


async def test_anthropic_provider_parses_response_and_sends_the_right_shape():
    fake_response = _FakeResponse(
        {
            "content": [{"type": "text", "text": '{"day_score": 70}'}],
            "usage": {"input_tokens": 150, "output_tokens": 60},
        }
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)) as mock_post:
        provider = AnthropicProvider(api_key="test-key", model="claude-3-5-haiku-20241022")
        result = await provider.complete(
            [Message(role="system", content="sys"), Message(role="user", content="hi")]
        )

    assert result.text == '{"day_score": 70}'
    assert result.token_in == 150
    assert result.token_out == 60

    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["x-api-key"] == "test-key"
    assert call_kwargs["json"]["system"] == "sys"
    assert call_kwargs["json"]["messages"] == [{"role": "user", "content": "hi"}]
