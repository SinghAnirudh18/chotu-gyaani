"""Speech-to-text providers.

`mock` is deterministic: it reads a transcript embedded in the audio bytes after a
`TRANSCRIPT:` marker (tests and demos build such WAV files), and otherwise
returns an empty transcript. `groq` uses Whisper on Groq (dev/staging).
`gnani` is a production skeleton: no endpoint or field is invented without
official docs and credentials."""
import math
import re
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.core.exceptions import ProviderNotConfigured
from app.providers import groq_http
from app.utils.audio import sniff
from app.utils.i18n import detect_language, normalize_lang


@dataclass
class Transcript:
    text: str
    language: str
    confidence: float
    provider: str


class SpeechToTextProvider(Protocol):
    name: str

    async def transcribe(self, audio: bytes, language_hint: str | None) -> Transcript: ...

    async def health(self) -> dict: ...


class MockSTT:
    name = "mock"

    async def transcribe(self, audio: bytes, language_hint: str | None) -> Transcript:
        m = re.search(rb"TRANSCRIPT:(.*?)(?:\x00|$)", audio, re.S)
        text = m.group(1).decode("utf-8", errors="ignore").strip() if m else ""
        lang = normalize_lang(language_hint) if language_hint else (detect_language(text) if text else "en")
        return Transcript(text=text, language=lang, confidence=1.0 if text else 0.0, provider=self.name)

    async def health(self) -> dict:
        return {"provider": self.name, "status": "ok", "mock": True}


# Whisper hallucinates words on silence/noise; segments this likely to be non-speech are discarded.
NO_SPEECH_THRESHOLD = 0.6
# Biases Whisper toward Roman script when the user writes Hinglish.
HINGLISH_PROMPT = "Ramesh ka kitna baaki hai? Kal 5 baje yaad dila do. Paanch hazaar de diye."
_MIME_EXT = {"wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg", "webm": "audio/webm",
             "flac": "audio/flac", "m4a": "audio/mp4"}


class GroqSTT:
    name = "groq"

    async def transcribe(self, audio: bytes, language_hint: str | None) -> Transcript:
        s = get_settings()
        fmt = sniff(audio) or "wav"
        data: dict[str, str] = {"model": s.groq_stt_model, "response_format": "verbose_json", "temperature": "0"}
        hint = normalize_lang(language_hint) if language_hint else None
        if hint:
            data["language"] = "en" if hint == "en" else "hi"
        if hint == "hi-Latn":
            data["prompt"] = HINGLISH_PROMPT
        resp = await groq_http.post("/audio/transcriptions", files={"file": (f"audio.{fmt}", audio, _MIME_EXT[fmt])},
                                    data=data, timeout=60.0, kind="stt")
        body = resp.json()
        segments = [seg for seg in body.get("segments") or [] if isinstance(seg, dict)]
        speech = [seg for seg in segments if float(seg.get("no_speech_prob", 0.0)) < NO_SPEECH_THRESHOLD]
        if segments:
            text = " ".join(str(seg.get("text", "")).strip() for seg in speech).strip()
            confidence = (sum(math.exp(float(seg.get("avg_logprob", -1.0))) for seg in speech) / len(speech)
                          if speech else 0.0)
        else:
            text = str(body.get("text", "")).strip()
            confidence = 0.5 if text else 0.0
        lang = hint or (detect_language(text) if text else "en")
        if hint == "hi-Latn" and text and detect_language(text) == "hi":
            lang = "hi"  # Whisper answered in Devanagari; reply in the script the user will read
        return Transcript(text=text, language=lang, confidence=round(min(max(confidence, 0.0), 1.0), 3),
                          provider=self.name)

    async def health(self) -> dict:
        configured = bool(get_settings().groq_api_key)
        return {"provider": self.name, "status": "configured" if configured else "not_configured", "mock": False,
                "model": get_settings().groq_stt_model}


class GnaniSTT:
    name = "gnani"

    def __init__(self) -> None:
        s = get_settings()
        self.api_key = s.gnani_api_key
        self.base_url = (s.gnani_base_url or "https://api.vachana.ai").rstrip("/")
        self.configured = bool(self.api_key)

    async def transcribe(self, audio: bytes, language_hint: str | None) -> Transcript:
        if not self.configured:
            raise ProviderNotConfigured("Gnani STT adapter is not configured", details={"provider": "gnani"})

        import httpx
        from app.core.exceptions import ProviderUnavailable

        fmt = sniff(audio) or "wav"
        if fmt not in ("wav", "flac", "mp3", "aac", "m4a", "ogg"):
            import subprocess
            try:
                proc = subprocess.run(
                    ["ffmpeg", "-y", "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
                    input=audio,
                    capture_output=True,
                    check=True,
                )
                if proc.stdout:
                    audio = proc.stdout
                    fmt = "wav"
            except Exception:
                pass

        ext = fmt
        mime = "audio/wav" if fmt == "wav" else f"audio/{ext}"

        lang_code = "hi-IN"
        if language_hint:
            n = normalize_lang(language_hint)
            if n == "en":
                lang_code = "en-IN"
            elif n in ("hi", "hi-Latn"):
                lang_code = "hi-IN"

        headers = {"X-API-Key-ID": self.api_key}
        files = {"audio_file": (f"audio.{ext}", audio, mime)}
        data = {"language_code": lang_code, "model": "prisma-v3.0"}

        url = f"{self.base_url}/stt/v3"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
            if resp.status_code != 200:
                raise ProviderUnavailable(f"Gnani STT error ({resp.status_code}): {resp.text}", details={"provider": "gnani"})
            
            res_json = resp.json()
            transcript_text = res_json.get("transcript", "").strip()
            detected = res_json.get("detected_language_code", "hi-IN")
            lang = "hi" if "hi" in detected.lower() else "en"

            return Transcript(
                text=transcript_text,
                language=lang,
                confidence=0.95 if transcript_text else 0.0,
                provider=self.name,
            )

    async def health(self) -> dict:
        return {
            "provider": self.name,
            "status": "configured" if self.configured else "not_configured",
            "mock": False,
            "model": "prisma-v3.0",
        }


def get_stt() -> SpeechToTextProvider:
    provider = get_settings().stt_provider
    if provider == "groq":
        return GroqSTT()
    if provider == "gnani":
        return GnaniSTT()
    return MockSTT()
