from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Bad request"

    def __init__(self, message: str | None = None, *, code: str | None = None,
                 details: Any = None, status_code: int | None = None) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details if details is not None else {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class BadRequest(AppError):
    pass


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Authentication required"


class Forbidden(AppError):
    status_code = 403
    code = "permission_denied"
    message = "You do not have permission to perform this action"


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    message = "Conflict"


class Gone(AppError):
    status_code = 410
    code = "gone"
    message = "Resource is no longer available"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_error"
    message = "Validation failed"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests"


class QuotaExceeded(AppError):
    status_code = 429
    code = "quota_exceeded"
    message = "Usage limit reached for this period"


class ProviderNotConfigured(AppError):
    status_code = 503
    code = "provider_not_configured"
    message = "Provider is not configured"


class ProviderUnavailable(AppError):
    status_code = 503
    code = "provider_unavailable"
    message = "Provider is temporarily unavailable"
