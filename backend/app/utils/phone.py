import phonenumbers

from app.core.exceptions import ValidationFailed


def normalize_phone(raw: str | None, region: str = "IN") -> str | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        num = phonenumbers.parse(str(raw), region)
    except phonenumbers.NumberParseException as e:
        raise ValidationFailed("Invalid phone number", code="invalid_phone") from e
    if not phonenumbers.is_valid_number(num):
        raise ValidationFailed("Invalid phone number", code="invalid_phone")
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def try_normalize_phone(raw: str | None, region: str = "IN") -> str | None:
    try:
        return normalize_phone(raw, region)
    except ValidationFailed:
        return None
