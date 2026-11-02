"""Audio upload validation: magic bytes, MIME, size and (for WAV) duration.
Raw audio is never persisted."""
import struct

from app.core.config import get_settings
from app.core.exceptions import ValidationFailed

ALLOWED = {
    "wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
    "mp3": {"audio/mpeg", "audio/mp3"},
    "ogg": {"audio/ogg", "audio/opus"},
    "webm": {"audio/webm", "video/webm"},
    "flac": {"audio/flac", "audio/x-flac"},
    "m4a": {"audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac"},
}


def sniff(data: bytes) -> str | None:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:3] == b"ID3" or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if data[:4] == b"fLaC":
        return "flac"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "m4a"
    return None


def wav_duration(data: bytes) -> float | None:
    pos = 12
    byte_rate = None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        if cid == b"fmt " and size >= 16:
            byte_rate = struct.unpack("<I", data[pos + 16:pos + 20])[0]
        elif cid == b"data" and byte_rate:
            return min(size, len(data) - pos - 8) / byte_rate
        pos += 8 + size + (size % 2)
    return None


def validate_audio(data: bytes, content_type: str | None) -> dict:
    s = get_settings()
    if not data:
        raise ValidationFailed("Audio file is empty", code="audio_empty")
    if len(data) > s.max_audio_bytes:
        raise ValidationFailed("Audio file is too large", code="audio_too_large",
                               details={"max_bytes": s.max_audio_bytes})
    kind = sniff(data)
    if kind is None:
        raise ValidationFailed("Unsupported audio format", code="audio_unsupported_type")
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED[kind]:
        raise ValidationFailed("Audio content type does not match file contents", code="audio_mime_mismatch",
                               details={"detected": kind, "content_type": mime})
    duration = wav_duration(data) if kind == "wav" else None
    if duration is not None and duration > s.max_audio_seconds:
        raise ValidationFailed("Audio is too long", code="audio_too_long",
                               details={"max_seconds": s.max_audio_seconds})
    return {"format": kind, "bytes": len(data), "duration_seconds": round(duration, 2) if duration else None}
