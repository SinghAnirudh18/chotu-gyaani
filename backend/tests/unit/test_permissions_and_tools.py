"""Every cell of the role x permission matrix, and every role x tool (propose/confirm)."""
import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationFailed
from app.core.permissions import MATRIX, Perm, Role, has_perm
from app.schemas.assistant import Intent
from app.tools.registry import ALLOWLIST, REGISTRY, WRITE_TOOLS, effective_tools, get_tool

MEMBER_ONLY_DENIED = {
    Perm.BUSINESS_UPDATE, Perm.BUSINESS_DELETE, Perm.MEMBERS_MANAGE, Perm.CUSTOMERS_DELETE, Perm.CUSTOMERS_IMPORT,
    Perm.PAYMENTS_CONFIRM, Perm.REMINDERS_CONFIRM, Perm.CONVERSATIONS_READ_ALL, Perm.AGENTS_WRITE, Perm.AUDIT_READ,
    Perm.USAGE_READ, Perm.INTEGRATIONS_MANAGE, Perm.DATA_EXPORT,
}
ADMIN_DENIED = {Perm.BUSINESS_DELETE, Perm.INTEGRATIONS_MANAGE}

EXPECTED = {
    Role.OWNER: set(Perm),
    Role.ADMIN: set(Perm) - ADMIN_DENIED,
    Role.MEMBER: set(Perm) - MEMBER_ONLY_DENIED,
}


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("perm", list(Perm))
def test_matrix_cell(role: Role, perm: Perm) -> None:
    assert has_perm(role, perm) is (perm in EXPECTED[role])
    assert (perm in MATRIX[role]) is (perm in EXPECTED[role])


def test_business_setting_relaxes_reminder_confirmation_only() -> None:
    relaxed = {"members_can_confirm_reminders": True}
    assert has_perm("member", Perm.REMINDERS_CONFIRM, relaxed)
    assert not has_perm("member", Perm.PAYMENTS_CONFIRM, relaxed)


TOOL_EXPECT = {
    # tool: (member can propose, member can confirm, admin confirm, owner confirm)
    "search_customers": (True, None), "get_customer_balance": (True, None), "get_invoice_details": (True, None),
    "list_overdue_invoices": (True, None), "list_customer_reminders": (True, None),
    "get_dashboard_summary": (True, None),
    "schedule_reminder": (True, {"member": False, "admin": True, "owner": True}),
    "record_payment_commitment": (True, {"member": True, "admin": True, "owner": True}),
    "record_payment": (True, {"member": False, "admin": True, "owner": True}),
}


@pytest.mark.parametrize("role", ["owner", "admin", "member"])
@pytest.mark.parametrize("tool_name", sorted(TOOL_EXPECT))
def test_tool_role_cells(role: str, tool_name: str) -> None:
    tool = REGISTRY[tool_name]
    can_propose, confirm = TOOL_EXPECT[tool_name]
    assert has_perm(role, tool.propose_perm) is can_propose
    if confirm is None:
        assert tool.kind == "read" and tool.confirm_perm is None and not tool.requires_confirmation
    else:
        assert tool.kind == "write" and tool.requires_confirmation
        assert tool.confirm_perm is not None
        assert has_perm(role, tool.confirm_perm) is confirm[role]


def test_registry_matches_plan() -> None:
    assert ALLOWLIST == set(TOOL_EXPECT)
    assert WRITE_TOOLS == {"schedule_reminder", "record_payment_commitment", "record_payment"}
    for tool in REGISTRY.values():
        assert tool.name and tool.description and tool.input_schema and tool.audit_event


def test_unknown_tool_rejected() -> None:
    with pytest.raises(ValidationFailed) as e:
        get_tool("drop_all_tables")
    assert getattr(e.value, "code", "") == "unknown_tool"


def test_effective_tools_is_intersection() -> None:
    assert effective_tools("member", ["get_customer_balance", "record_payment", "evil_tool"]) == {
        "get_customer_balance", "record_payment"}
    assert effective_tools("owner", None) == set(ALLOWLIST)
    assert effective_tools("owner", []) == set()


def test_intent_schema_rejects_unknown_types() -> None:
    with pytest.raises(ValidationError):
        Intent.model_validate({"type": "execute_sql", "entities": {}})
    ok = Intent.model_validate({"type": "schedule_reminder",
                                "entities": {"customer_name": "Ramesh", "date": {"relative": "tomorrow"}}})
    assert ok.entities.date and ok.entities.date.relative == "tomorrow"
