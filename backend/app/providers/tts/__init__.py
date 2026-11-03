"""Text-to-speech providers. `mock` returns a valid silent WAV whose length scales with the text.
`groq` uses Orpheus on Groq (dev/staging, English voices; Devanagari is transliterated first)."""
import io
import struct
import wave
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.core.exceptions import ProviderNotConfigured
from app.providers import groq_http
from app.utils.audio import wav_duration
from app.utils.text import is_devanagari, transliterate


@dataclass
class AudioResult:
    audio: bytes
    mime_type: str
    duration_seconds: float
    provider: str


class TextToSpeechProvider(Protocol):
    name: str

    async def synthesize(self, text: str, language: str, voice: str | None) -> AudioResult: ...

    async def health(self) -> dict: ...


class MockTTS:
    name = "mock"

    async def synthesize(self, text: str, language: str, voice: str | None) -> AudioResult:
        rate = 8000
        duration = min(max(len(text) / 15.0, 0.5), 10.0)
        frames = int(rate * duration)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(struct.pack("<h", 0) * frames)
        return AudioResult(audio=buf.getvalue(), mime_type="audio/wav", duration_seconds=round(duration, 2),
                           provider=self.name)

    async def health(self) -> dict:
        return {"provider": self.name, "status": "ok", "mock": True}


class GroqTTS:
    name = "groq"

    async def synthesize(self, text: str, language: str, voice: str | None) -> AudioResult:
        s = get_settings()
        # Orpheus voices are English; Roman-script Hindi reads far better than Devanagari.
        spoken = transliterate(text) if is_devanagari(text) else text
        resp = await groq_http.post("/audio/speech", json={
            "model": s.groq_tts_model, "voice": voice or s.groq_tts_voice, "input": spoken[:1000],
            "response_format": "wav"}, timeout=60.0, kind="tts")
        audio = resp.content
        return AudioResult(audio=audio, mime_type="audio/wav",
                           duration_seconds=round(wav_duration(audio) or 0.0, 2), provider=self.name)

    async def health(self) -> dict:
        s = get_settings()
        return {"provider": self.name, "status": "configured" if s.groq_api_key else "not_configured",
                "mock": False, "model": s.groq_tts_model, "voice": s.groq_tts_voice, "languages": ["en"]}


class GnaniTTS:
    name = "gnani"

    def __init__(self) -> None:
        s = get_settings()
        self.api_key = s.gnani_api_key
        self.base_url = (s.gnani_base_url or "https://api.vachana.ai").rstrip("/")
        self.configured = bool(self.api_key)

    async def synthesize(self, text: str, language: str, voice: str | None) -> AudioResult:
        if not self.configured:
            raise ProviderNotConfigured("Gnani TTS adapter is not configured", details={"provider": "gnani"})

        import httpx
        from app.core.exceptions import ProviderUnavailable
        from app.utils.i18n import normalize_lang

        norm = normalize_lang(language)
        lang_code = "en-IN" if norm == "en" else "hi-IN"
        chosen_voice = voice or ("Shivani" if lang_code == "hi-IN" else "Devansh")

        headers = {
            "X-API-Key-ID": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "voice": chosen_voice,
            "model": "timbre-v3.0",
            "language": lang_code,
            "speed": 1.0,
            "audio_config": {
                "sample_rate": 24000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }

        url = f"{self.base_url}/api/v1/tts/inference"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise ProviderUnavailable(f"Gnani TTS error ({resp.status_code}): {resp.text}", details={"provider": "gnani"})

            audio_bytes = resp.content
            duration = wav_duration(audio_bytes)
            return AudioResult(
                audio=audio_bytes,
                mime_type="audio/wav",
                duration_seconds=round(duration, 2),
                provider=self.name,
            )

    async def health(self) -> dict:
        return {
            "provider": self.name,
            "status": "configured" if self.configured else "not_configured",
            "mock": False,
            "model": "timbre-v3.0",
            "voices": ["Shivani", "Devansh", "Kalpana", "Shubham", "Avinash"],
        }


def get_tts() -> TextToSpeechProvider:
    provider = get_settings().tts_provider
    if provider == "groq":
        return GroqTTS()
    if provider == "gnani":
        return GnaniTTS()
    return MockTTS()
