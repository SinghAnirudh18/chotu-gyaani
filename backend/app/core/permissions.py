"""Code-level role -> permission matrix. Every cell is covered by tests/unit/test_permissions.py."""
from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


ROLE_RANK = {Role.MEMBER: 1, Role.ADMIN: 2, Role.OWNER: 3}


class Perm(StrEnum):
    BUSINESS_READ = "business:read"
    BUSINESS_UPDATE = "business:update"
    BUSINESS_DELETE = "business:delete"
    MEMBERS_READ = "members:read"
    MEMBERS_MANAGE = "members:manage"
    CUSTOMERS_READ = "customers:read"
    CUSTOMERS_WRITE = "customers:write"
    CUSTOMERS_DELETE = "customers:delete"
    CUSTOMERS_IMPORT = "customers:import"
    INVOICES_READ = "invoices:read"
    INVOICES_WRITE = "invoices:write"
    PAYMENTS_READ = "payments:read"
    PAYMENTS_PROPOSE = "payments:propose"
    PAYMENTS_CONFIRM = "payments:confirm"
    REMINDERS_READ = "reminders:read"
    REMINDERS_WRITE = "reminders:write"
    REMINDERS_CONFIRM = "reminders:confirm"
    COMMITMENTS_READ = "commitments:read"
    COMMITMENTS_WRITE = "commitments:write"
    COMMITMENTS_CONFIRM = "commitments:confirm"
    CONVERSATIONS_USE = "conversations:use"
    CONVERSATIONS_READ_ALL = "conversations:read_all"
    ACTIONS_READ = "actions:read"
    ACTIONS_CANCEL = "actions:cancel"
    AGENTS_READ = "agents:read"
    AGENTS_WRITE = "agents:write"
    DASHBOARD_READ = "dashboard:read"
    AUDIT_READ = "audit:read"
    USAGE_READ = "usage:read"
    AUDIO_USE = "audio:use"
    INTEGRATIONS_MANAGE = "integrations:manage"
    DATA_EXPORT = "data:export"


_MEMBER = {
    Perm.BUSINESS_READ, Perm.MEMBERS_READ,
    Perm.CUSTOMERS_READ, Perm.CUSTOMERS_WRITE,
    Perm.INVOICES_READ, Perm.INVOICES_WRITE,
    Perm.PAYMENTS_READ, Perm.PAYMENTS_PROPOSE,
    Perm.REMINDERS_READ, Perm.REMINDERS_WRITE,
    Perm.COMMITMENTS_READ, Perm.COMMITMENTS_WRITE, Perm.COMMITMENTS_CONFIRM,
    Perm.CONVERSATIONS_USE, Perm.ACTIONS_READ, Perm.ACTIONS_CANCEL,
    Perm.AGENTS_READ, Perm.DASHBOARD_READ, Perm.AUDIO_USE,
}
_ADMIN = _MEMBER | {
    Perm.BUSINESS_UPDATE, Perm.MEMBERS_MANAGE, Perm.CUSTOMERS_DELETE, Perm.CUSTOMERS_IMPORT,
    Perm.PAYMENTS_CONFIRM, Perm.REMINDERS_CONFIRM, Perm.CONVERSATIONS_READ_ALL,
    Perm.AGENTS_WRITE, Perm.AUDIT_READ, Perm.USAGE_READ, Perm.DATA_EXPORT,
}
_OWNER = _ADMIN | {Perm.BUSINESS_DELETE, Perm.INTEGRATIONS_MANAGE}

MATRIX: dict[Role, frozenset[Perm]] = {
    Role.MEMBER: frozenset(_MEMBER),
    Role.ADMIN: frozenset(_ADMIN),
    Role.OWNER: frozenset(_OWNER),
}


def has_perm(role: str, perm: Perm, business_settings: dict | None = None) -> bool:
    r = Role(role)
    if perm in MATRIX[r]:
        return True
    # Business setting can relax reminder confirmation to members.
    if perm == Perm.REMINDERS_CONFIRM and (business_settings or {}).get("members_can_confirm_reminders"):
        return True
    return False
