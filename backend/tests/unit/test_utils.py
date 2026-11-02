from datetime import UTC, date, datetime

import pytest

from app.core.exceptions import ValidationFailed
from app.core.security import hash_password, validate_password_policy, verify_password
from app.utils.audio import sniff, validate_audio, wav_duration
from app.utils.dates import add_months, resolve_datetime, resolve_future_date, resolve_relative_date
from app.utils.i18n import T, detect_language, t
from app.utils.money import format_inr
from app.utils.numbers import find_amount_phrase, parse_amount_to_paise
from app.utils.phone import normalize_phone
from app.utils.text import normalize_name, transliterate
from tests.conftest import wav_with_transcript


# ---------- passwords ----------
def test_password_hash_roundtrip_argon2id() -> None:
    h = hash_password("Secret123")
    assert h.startswith("$argon2id$")
    assert verify_password("Secret123", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "not-a-hash")


@pytest.mark.parametrize("pw", ["short1", "allletters", "12345678", "a" * 129 + "1"])
def test_password_policy_rejects(pw: str) -> None:
    with pytest.raises(ValidationFailed):
        validate_password_policy(pw)


# ---------- money ----------
@pytest.mark.parametrize("paise,expected", [
    (0, "₹0"), (100, "₹1"), (150, "₹1.50"), (12345678, "₹1,23,456.78"), (1_000_000_000, "₹1,00,00,000"), (100_000_000, "₹10,00,000"),
    (-5000, "-₹50"), (None, None)])
def test_format_inr(paise, expected) -> None:  # type: ignore[no-untyped-def]
    assert format_inr(paise) == expected


# ---------- numbers ----------
@pytest.mark.parametrize("phrase,paise", [
    ("do lakh", 200000_00), ("paanch hazaar", 5000_00), ("dedh sau", 150_00), ("1.5 lakh", 150000_00),
    ("5000", 5000_00), ("₹1,50,000", 150000_00), ("saade teen hazaar", 3500_00), ("paune do lakh", 175000_00),
    ("dhai hazaar", 2500_00), ("two thousand five hundred", 2500_00), ("5k", 5000_00), ("ek crore", 10000000_00),
    ("दो लाख", 200000_00), ("पांच हज़ार", 5000_00), ("750 rupees", 750_00), ("sava sau", 125_00),
    ("twenty five thousand", 25000_00), ("bees hazaar", 20000_00)])
def test_parse_amount(phrase: str, paise: int) -> None:
    assert parse_amount_to_paise(phrase) == paise


@pytest.mark.parametrize("phrase", ["", "kuch nahi", "zero", None])
def test_parse_amount_none(phrase) -> None:  # type: ignore[no-untyped-def]
    assert parse_amount_to_paise(phrase) is None


def test_find_amount_phrase_ignores_times() -> None:
    assert find_amount_phrase("kal 5 baje yaad dila do") is None
    assert find_amount_phrase("Ramesh ne 5000 rupaye diye") == "5000"
    assert find_amount_phrase("Mohan do lakh dega") == "do lakh"


# ---------- dates ----------
def test_relative_dates_weekdays_and_month_ends() -> None:
    mon = date(2026, 10, 19)  # Monday
    assert resolve_relative_date("tomorrow", mon) == date(2026, 10, 20)
    assert resolve_relative_date("day_after_tomorrow", mon) == date(2026, 10, 21)
    assert resolve_relative_date("next_monday", mon) == date(2026, 10, 26)
    assert resolve_relative_date("this_monday", mon) == mon
    assert resolve_relative_date("next_friday", mon) == date(2026, 10, 23)
    assert resolve_relative_date("next_week", mon) == date(2026, 10, 26)
    assert resolve_relative_date("end_of_month", date(2026, 2, 3)) == date(2026, 2, 28)
    assert resolve_relative_date("in_3_days", mon) == date(2026, 10, 22)
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    with pytest.raises(ValidationFailed):
        resolve_relative_date("someday", mon)


def test_resolve_datetime_uses_business_timezone() -> None:
    now = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)  # 11:30 IST
    dt = resolve_datetime({"relative": "tomorrow", "time": "17:00"}, "Asia/Kolkata", now)
    assert dt == datetime(2026, 10, 20, 11, 30, tzinfo=UTC)  # 17:00 IST
    # IST date rollover: 20:00 UTC on the 19th is already the 20th in India
    late = datetime(2026, 10, 19, 20, 0, tzinfo=UTC)
    assert resolve_datetime({"relative": "tomorrow", "time": "10:00"}, "Asia/Kolkata", late).date() == date(2026, 10, 21)


def test_resolve_rejects_past() -> None:
    now = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    with pytest.raises(ValidationFailed) as e:
        resolve_datetime({"relative": "today", "time": "09:00"}, "Asia/Kolkata", now)
    assert e.value.code == "date_in_past"
    with pytest.raises(ValidationFailed):
        resolve_future_date({"date": "2026-01-01"}, "Asia/Kolkata", now)
    with pytest.raises(ValidationFailed):
        resolve_datetime({"relative": "tomorrow", "time": "25:00"}, "Asia/Kolkata", now)


# ---------- text / i18n ----------
def test_transliteration_and_normalization() -> None:
    assert transliterate("रमेश") == "ramesh"
    assert normalize_name("रमेश") == normalize_name("Ramesh") == "ramesh"
    assert normalize_name("Ramesh  Guptaa") == normalize_name("ramesh gupta")
    assert normalize_name("Suneeta") == normalize_name("Sunita")
    assert normalize_name("Wasim") == normalize_name("Vasim")


@pytest.mark.parametrize("text_,lang", [
    ("Kitne invoice overdue hain?", "hi-Latn"), ("How much does Ramesh owe?", "en"),
    ("रमेश का कितना बाकी है?", "hi"), ("Ramesh ka kitna baaki hai", "hi-Latn")])
def test_detect_language(text_: str, lang: str) -> None:
    assert detect_language(text_) == lang


def test_templates_exist_in_all_languages() -> None:
    for key, variants in T.items():
        assert set(variants) == {"en", "hi", "hi-Latn"}, key
    assert "Confirm" in t("preview_schedule_reminder", "hi-Latn", customer="A", when="B", channel="sms", invoice="")


# ---------- phone ----------
def test_phone_normalization() -> None:
    assert normalize_phone("98123 45601") == "+919812345601"
    assert normalize_phone("+91-98123-45601") == "+919812345601"
    assert normalize_phone(None) is None
    with pytest.raises(ValidationFailed):
        normalize_phone("12345")


# ---------- audio ----------
def test_audio_validation() -> None:
    wav = wav_with_transcript("hello", seconds=2)
    assert sniff(wav) == "wav"
    assert round(wav_duration(wav) or 0) == 2
    assert validate_audio(wav, "audio/wav")["format"] == "wav"
    with pytest.raises(ValidationFailed) as e:
        validate_audio(b"not audio at all", "audio/wav")
    assert e.value.code == "audio_unsupported_type"
    with pytest.raises(ValidationFailed) as e:
        validate_audio(wav, "audio/mpeg")
    assert e.value.code == "audio_mime_mismatch"
    with pytest.raises(ValidationFailed) as e:
        validate_audio(wav_with_transcript("x", seconds=200), "audio/wav")
    assert e.value.code in ("audio_too_long", "audio_too_large")
