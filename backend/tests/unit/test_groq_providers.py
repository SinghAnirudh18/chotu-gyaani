"""Groq adapters tested offline with httpx.MockTransport (no network, no credits)."""
import json

import httpx
import pytest

from app.core.config import get_settings
from app.core.exceptions import ProviderNotConfigured, ProviderUnavailable
from app.providers import groq_http
from app.providers.llm.base import IntentContext
from app.providers.llm.groq_llm import GroqLLM, strict_schema
from app.providers.stt import GroqSTT
from app.providers.tts import GroqTTS
from app.schemas.assistant import AgentConfig, Intent
from tests.conftest import wav_with_transcript

CTX = IntentContext(language="hi-Latn", timezone="Asia/Kolkata", today_iso="2026-10-20",
                    allowed_intents=["get_customer_balance"])


@pytest.fixture
def groq(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(get_settings(), "groq_api_key", "test-key")
    calls: list[httpx.Request] = []
    responses: list[httpx.Response] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return responses.pop(0)

    monkeypatch.setattr(groq_http, "transport_override", httpx.MockTransport(handler))
    return calls, responses


def chat(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def _walk_objects(node):  # type: ignore[no-untyped-def]
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for v in node.values():
            yield from _walk_objects(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_objects(v)


def test_strict_schema_is_closed_and_fully_required() -> None:
    for model in (Intent, AgentConfig):
        schema = strict_schema(model)
        objects = list(_walk_objects(schema))
        assert objects
        for obj in objects:
            assert obj["additionalProperties"] is False
            assert sorted(obj["required"]) == sorted(obj["properties"])
        assert "maxLength" not in json.dumps(schema) and '"default"' not in json.dumps(schema)


async def test_extract_intent_request_and_parsing(groq) -> None:  # type: ignore[no-untyped-def]
    calls, responses = groq
    payload = {"type": "get_customer_balance", "confidence": 0.9, "missing_fields": [],
               "entities": {"customer_name": "Ramesh", "customer_phone": None, "invoice_number": None,
                            "amount_phrase": None, "date": None, "channel": None, "query": None}}
    responses.append(chat(json.dumps(payload)))
    intent = await GroqLLM().extract_intent("Ramesh ka kitna baaki hai? <script>", CTX)
    assert intent.type == "get_customer_balance" and intent.entities.customer_name == "Ramesh"
    body = json.loads(calls[0].content)
    assert calls[0].url.path.endswith("/chat/completions")
    assert calls[0].headers["authorization"] == "Bearer test-key"
    assert body["model"] == "openai/gpt-oss-120b" and body["temperature"] == 0
    assert body["response_format"]["type"] == "json_schema" and body["response_format"]["json_schema"]["strict"]
    user = body["messages"][1]["content"]
    assert "<data>\nRamesh ka kitna baaki hai? <script>\n</data>" in user  # user text is wrapped as data


async def test_extract_intent_retries_once_then_fails_safely(groq) -> None:  # type: ignore[no-untyped-def]
    calls, responses = groq
    responses.extend([chat("not json"), chat('{"type": "drop_tables"}')])
    with pytest.raises(ProviderUnavailable):
        await GroqLLM().extract_intent("x", CTX)
    assert len(calls) == 2


@pytest.mark.parametrize("status,body,exc,code", [
    (401, {"error": {"message": "bad key"}}, ProviderNotConfigured, "provider_not_configured"),
    (400, {"error": {"code": "model_terms_required"}}, ProviderNotConfigured, "provider_not_configured"),
    (429, {"error": {"code": "rate_limit_exceeded"}}, ProviderUnavailable, "provider_unavailable"),
])
async def test_error_mapping(groq, status, body, exc, code) -> None:  # type: ignore[no-untyped-def]
    _, responses = groq
    responses.append(httpx.Response(status, json=body))
    with pytest.raises(exc) as e:
        await GroqLLM().compose_reply("hi", "en", None)
    assert e.value.code == code


async def test_server_error_is_retried_once(groq) -> None:  # type: ignore[no-untyped-def]
    calls, responses = groq
    responses.extend([httpx.Response(503, json={}), chat("Namaste!")])
    assert await GroqLLM().compose_reply("hi", "hi-Latn", None) == "Namaste!"
    assert len(calls) == 2


async def test_short_rate_limit_is_waited_out_once(groq) -> None:  # type: ignore[no-untyped-def]
    calls, responses = groq
    responses.extend([httpx.Response(429, headers={"retry-after": "0"}, json={}), chat("Hello")])
    assert await GroqLLM().compose_reply("hi", "en", None) == "Hello"
    responses.extend([httpx.Response(429, headers={"retry-after": "999"}, json={})])
    with pytest.raises(ProviderUnavailable) as e:
        await GroqLLM().compose_reply("hi", "en", None)
    assert e.value.details["retry_after"] == "999" and len(calls) == 3


def test_missing_key_is_not_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    with pytest.raises(ProviderNotConfigured):
        GroqLLM()


async def test_stt_parses_verbose_json_and_drops_non_speech(groq) -> None:  # type: ignore[no-untyped-def]
    calls, responses = groq
    responses.append(httpx.Response(200, json={
        "task": "transcribe", "language": "Hindi", "duration": 2, "text": "Ramesh ka kitna baaki hai? umm",
        "segments": [{"text": " Ramesh ka kitna baaki hai?", "avg_logprob": -0.1, "no_speech_prob": 0.01},
                     {"text": " umm", "avg_logprob": -1.5, "no_speech_prob": 0.95}]}))
    tr = await GroqSTT().transcribe(wav_with_transcript(""), "hi-Latn")
    assert tr.text == "Ramesh ka kitna baaki hai?" and tr.language == "hi-Latn" and tr.provider == "groq"
    assert 0.85 < tr.confidence <= 1.0
    req = calls[0]
    assert req.url.path.endswith("/audio/transcriptions")
    raw = req.content
    assert b'name="model"' in raw and b"whisper-large-v3" in raw and b"verbose_json" in raw
    assert b'name="language"\r\n\r\nhi' in raw and b'name="prompt"' in raw and b'filename="audio.wav"' in raw


async def test_stt_silence_gives_empty_transcript(groq) -> None:  # type: ignore[no-untyped-def]
    _, responses = groq
    responses.append(httpx.Response(200, json={"text": " प्राप्त", "segments": [
        {"text": " प्राप्त", "avg_logprob": -0.9, "no_speech_prob": 0.9}]}))
    tr = await GroqSTT().transcribe(wav_with_transcript(""), None)
    assert tr.text == "" and tr.confidence == 0.0


async def test_tts_transliterates_devanagari(groq) -> None:  # type: ignore[no-untyped-def]
    calls, responses = groq
    audio = wav_with_transcript("", seconds=1.0)
    responses.append(httpx.Response(200, content=audio, headers={"content-type": "audio/wav"}))
    result = await GroqTTS().synthesize("रमेश का कितना बाकी है", "hi", None)
    body = json.loads(calls[0].content)
    assert body["model"] == "canopylabs/orpheus-v1-english" and body["voice"] == "troy"
    assert body["input"].startswith("ramesh") and body["response_format"] == "wav"
    assert result.audio == audio and result.provider == "groq" and result.duration_seconds == 1.0
