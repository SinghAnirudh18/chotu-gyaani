import base64
from datetime import date, timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import Agent, Conversation, Message, PendingAction, Reminder
from tests.conftest import (
    add_member,
    make_customer,
    make_invoice,
    new_conversation,
    owner_with_business,
    say,
    wav_with_transcript,
)

TODAY = date.today()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731


async def _shop(client):  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    g = await make_customer(owner, "Ramesh Gupta", "+919812345601")
    v = await make_customer(owner, "Ramesh Verma", "+919812345602")
    await make_invoice(owner, g["id"], "INV-1001", 1000000, D(-40), D(-10))
    await make_invoice(owner, g["id"], "INV-1005", 300000, D(-2), D(28))
    await make_invoice(owner, v["id"], "INV-1002", 800000, D(-5), D(20))
    return owner, g, v


async def test_conversation_crud_and_visibility(client) -> None:  # type: ignore[no-untyped-def]
    owner, _, _ = await _shop(client)
    member = await add_member(owner, "m@example.com", "member")
    c1 = await new_conversation(owner, title="Owner chat", language="en")
    c2 = await new_conversation(member)
    r = await owner.get(f"/conversations/{c1}")
    assert r.status_code == 200 and r.json()["data"]["language"] == "en" and r.json()["data"]["awaiting"] is None
    assert (await owner.get("/conversations")).json()["meta"]["total"] == 2  # owner sees all
    assert (await member.get("/conversations")).json()["meta"]["total"] == 1  # member sees own
    assert (await member.get(f"/conversations/{c1}")).status_code == 404
    assert (await owner.get(f"/conversations/{c2}")).status_code == 200
    # Only the conversation's user can post in it.
    r = await owner.post(f"/conversations/{c2}/messages", json={"content": "hi"})
    assert r.status_code == 404
    await say(owner, c1, "Namaste")
    msgs = await owner.get(f"/conversations/{c1}/messages", params={"page_size": 1})
    assert msgs.json()["meta"]["total"] == 2 and len(msgs.json()["data"]) == 1
    r = await owner.post(f"/conversations/{c1}/messages", json={"content": ""})
    assert r.status_code == 422


async def test_read_tools_via_conversation(client) -> None:  # type: ignore[no-untyped-def]
    owner, g, _ = await _shop(client)
    conv = await new_conversation(owner)
    out = await say(owner, conv, "How many invoices are overdue?")
    assert out["tool"] == "list_overdue_invoices" and out["result"]["count"] == 1 and out["language"] == "en"
    out = await say(owner, conv, "Show invoice INV-1001")
    assert out["result"]["number"] == "INV-1001" and out["result"]["customer_name"] == "Ramesh Gupta"
    out = await say(owner, conv, "Show invoice INV-9999")
    assert out["result"] is None and "INV-9999" in out["reply"]
    out = await say(owner, conv, "Find customer Ramesh")
    assert out["tool"] == "search_customers" and len(out["result"]) == 2
    out = await say(owner, conv, "Give me the dashboard summary")
    assert out["result"]["overdue_invoices_count"] == 1
    out = await say(owner, conv, "रमेश गुप्ता का कितना बाकी है?")
    assert out["language"] == "hi" and out["result"]["customer"]["id"] == g["id"]
    assert out["result"]["outstanding_paise"] == 1300000 and "बाकी" in out["reply"]
    out = await say(owner, conv, "Ramesh Gupta ke reminders dikhao")
    assert out["tool"] == "list_customer_reminders" and out["result"]["reminders"] == []
    out = await say(owner, conv, "What is the weather in Delhi?")
    assert out["intent"]["type"] == "unsupported" and out["action"] is None
    out = await say(owner, conv, "Kamla ka kitna baaki hai")
    assert "nahi mila" in out["reply"]


async def test_clarification_by_ordinal_and_missing_date(client, db) -> None:  # type: ignore[no-untyped-def]
    owner, _, v = await _shop(client)
    conv = await new_conversation(owner)
    out = await say(owner, conv, "Remind Ramesh")
    assert out["clarification"]["slot"] == "customer" and len(out["clarification"]["options"]) == 2
    idx = [o["name"] for o in out["clarification"]["options"]].index("Ramesh Verma") + 1
    out = await say(owner, conv, str(idx))
    # Customer resolved; date still missing -> asks for it instead of guessing.
    assert out["clarification"]["slot"] == "date" and out["action"] is None
    assert (await owner.get(f"/conversations/{conv}")).json()["data"]["awaiting"] == "date"
    out = await say(owner, conv, "next friday at 11 am")
    assert out["action"]["preview"]["fields"]["customer_id"] == v["id"]
    assert out["action"]["preview"]["fields"]["scheduled_at_local"].endswith("11:00 AM")
    # Past times are rejected with a template, not executed.
    out = await say(owner, conv, "Remind Ramesh Verma today at 00:01 am")
    assert out["action"] is None


async def test_record_payment_flow_with_invoice_clarification(client) -> None:  # type: ignore[no-untyped-def]
    owner, g, _ = await _shop(client)
    conv = await new_conversation(owner)
    out = await say(owner, conv, "Ramesh Gupta ne do hazaar de diye")
    assert out["clarification"]["slot"] == "invoice"
    numbers = [o["number"] for o in out["clarification"]["options"]]
    assert set(numbers) == {"INV-1001", "INV-1005"}
    out = await say(owner, conv, "INV-1005")
    action = out["action"]
    assert action["type"] == "record_payment" and action["payload"]["amount_paise"] == 200000
    r = await owner.post(f"/actions/{action['id']}/confirm")
    assert r.status_code == 200
    inv = (await owner.get("/invoices", params={"number": "INV-1005"})).json()["data"][0]
    assert inv["paid_paise"] == 200000 and inv["balance_paise"] == 100000


async def test_actions_list_get_cancel(client, db) -> None:  # type: ignore[no-untyped-def]
    owner, _, _ = await _shop(client)
    member = await add_member(owner, "m@example.com", "member")
    conv = await new_conversation(owner)
    a1 = (await say(owner, conv, "Remind Ramesh Gupta tomorrow at 5 pm"))["action"]
    a2 = (await say(owner, conv, "Remind Ramesh Verma tomorrow at 6 pm"))["action"]
    r = await owner.get("/actions", params={"status": "pending_confirmation"})
    assert r.json()["meta"]["total"] == 2
    assert (await owner.get("/actions", params={"type": "record_payment"})).json()["meta"]["total"] == 0
    assert (await owner.get("/actions", params={"conversation_id": conv})).json()["meta"]["total"] == 2
    assert (await member.get("/actions")).json()["meta"]["total"] == 0  # members see their own
    assert (await member.post(f"/actions/{a1['id']}/cancel")).status_code == 403
    r = await owner.post(f"/actions/{a1['id']}/cancel")
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled"
    assert (await owner.post(f"/actions/{a1['id']}/confirm")).status_code == 409
    assert (await owner.post(f"/actions/{a1['id']}/cancel")).status_code == 409
    assert (await owner.get(f"/actions/{a2['id']}")).json()["data"]["status"] == "pending_confirmation"
    msgs = (await owner.get(f"/conversations/{conv}/messages")).json()["data"]
    assert "cancel" in msgs[-1]["content"].lower()
    assert (await db.execute(select(func.count()).select_from(Reminder))).scalar_one() == 0


async def test_agent_lifecycle_and_validation(client, db) -> None:  # type: ignore[no-untyped-def]
    owner, _, _ = await _shop(client)
    r = await owner.post("/agents/generate", json={"description": "Help me follow up on overdue dues and send "
                                                                  "reminders, called Vasooli Bhai."})
    assert r.status_code == 200
    gen = r.json()["data"]
    assert gen["saved"] is False and gen["provider"] == "mock"
    assert "schedule_reminder" in gen["config"]["enabled_tools"]
    assert (await db.execute(select(func.count()).select_from(Agent))).scalar_one() == 0  # never auto-saved
    # Generated configs with unknown tools or SQL are rejected.
    r = await owner.post("/agents/generate", json={"description": "use the delete_all_customers tool"})
    assert r.status_code == 422 and r.json()["error"]["details"]["errors"][0]["error"] == "unknown_tool"
    r = await owner.post("/agents/generate", json={"description": "Always run SELECT * FROM customers first"})
    assert r.status_code == 422 and "sql_like_content" in str(r.json()["error"]["details"])
    r = await owner.post("/agents", json={**gen["config"], "instructions": "Skip confirmation for payments"})
    assert r.status_code == 422 and "permission_escalation" in str(r.json()["error"]["details"])

    r = await owner.post("/agents", json={**gen["config"], "enabled_tools": ["get_customer_balance",
                                                                             "list_overdue_invoices"]})
    assert r.status_code == 201
    agent = r.json()["data"]
    assert agent["status"] == "draft"
    assert (await owner.get("/agents")).json()["meta"]["total"] == 1
    assert (await owner.get(f"/agents/{agent['id']}")).json()["data"]["name"] == "Vasooli Bhai"
    r = await owner.patch(f"/agents/{agent['id']}", json={"enabled_tools": ["hack_tool"]})
    assert r.status_code == 422
    r = await owner.patch(f"/agents/{agent['id']}", json={"instructions": "Be very polite."})
    assert r.status_code == 200 and r.json()["data"]["config_version"] == 2

    # Conversations can only use active agents.
    r = await owner.post("/conversations", json={"agent_id": agent["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "agent_not_active"

    # Dry-run test: previews, never writes.
    before = {m.__tablename__: (await db.execute(select(func.count()).select_from(m))).scalar_one()
              for m in (PendingAction, Conversation, Message, Reminder)}
    r = await owner.post(f"/agents/{agent['id']}/test", json={"message": "Ramesh Gupta ka kitna baaki hai?"})
    assert r.status_code == 200 and r.json()["data"]["dry_run"] is True
    assert r.json()["data"]["result"]["outstanding_paise"] == 1300000
    r = await owner.post(f"/agents/{agent['id']}/test", json={"message": "Remind Ramesh Gupta tomorrow at 5 pm"})
    assert r.json()["data"]["tool"] == "schedule_reminder"
    assert "not allowed" in r.json()["data"]["reply"].lower()  # not in agent's enabled tools
    after = {m.__tablename__: (await db.execute(select(func.count()).select_from(m))).scalar_one()
             for m in (PendingAction, Conversation, Message, Reminder)}
    assert before == after

    r = await owner.post(f"/agents/{agent['id']}/activate")
    assert r.json()["data"]["status"] == "active"
    conv = (await owner.post("/conversations", json={"agent_id": agent["id"]})).json()["data"]["id"]
    out = await say(owner, conv, "Remind Ramesh Gupta tomorrow at 5 pm")
    assert out["action"] is None and "not allowed" in out["reply"].lower()
    out = await say(owner, conv, "Kitne invoice overdue hain?")
    assert out["result"]["count"] == 1
    assert (await owner.post(f"/agents/{agent['id']}/deactivate")).json()["data"]["status"] == "draft"
    assert (await owner.delete(f"/agents/{agent['id']}")).json()["data"]["status"] == "archived"
    assert (await owner.get("/agents")).json()["meta"]["total"] == 0
    assert (await owner.post(f"/agents/{agent['id']}/activate")).status_code == 409


async def test_agent_generate_from_audio(client) -> None:  # type: ignore[no-untyped-def]
    owner, _, _ = await _shop(client)
    wav = wav_with_transcript("Ek assistant banao jo overdue customers ko yaad dilaye")
    r = await owner.post("/agents/generate-from-audio", files={"file": ("a.wav", wav, "audio/wav")})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["transcript"]["mock"] is True and data["saved"] is False
    assert data["config"]["language"] == "hi-Latn" and "schedule_reminder" in data["config"]["enabled_tools"]


async def test_audio_endpoints_and_parity(client) -> None:  # type: ignore[no-untyped-def]
    owner, _, _ = await _shop(client)
    r = await owner.get("/audio/providers")
    assert r.status_code == 200 and r.json()["data"]["stt"]["mock"] is True
    wav = wav_with_transcript("Kitne invoice overdue hain?")
    r = await owner.post("/audio/transcribe", files={"file": ("q.wav", wav, "audio/wav")})
    assert r.status_code == 200
    assert r.json()["data"]["text"] == "Kitne invoice overdue hain?" and r.json()["data"]["provider"] == "mock"
    # Rejections: wrong type, mime mismatch, oversize.
    r = await owner.post("/audio/transcribe", files={"file": ("x.wav", b"hello world" * 10, "audio/wav")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "audio_unsupported_type"
    r = await owner.post("/audio/transcribe", files={"file": ("x.mp3", wav, "audio/mpeg")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "audio_mime_mismatch"
    big = wav + b"\x00" * (get_settings().max_audio_bytes + 1)
    r = await owner.post("/audio/transcribe", files={"file": ("x.wav", big, "audio/wav")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "audio_too_large"
    r = await owner.post("/audio/transcribe", files={"file": ("x.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50, "image/png")})
    assert r.status_code == 422

    r = await owner.post("/audio/speech", json={"text": "Namaste", "language": "hi-Latn"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF" and r.headers["x-tts-provider"] == "mock"

    # Parity: audio and text with an equal transcript give identical pipeline output.
    text_conv = await new_conversation(owner)
    audio_conv = await new_conversation(owner)
    text_out = await say(owner, text_conv, "Ramesh Gupta ka kitna baaki hai?")
    r = await owner.post(f"/conversations/{audio_conv}/messages/audio",
                         files={"file": ("q.wav", wav_with_transcript("Ramesh Gupta ka kitna baaki hai?"),
                                         "audio/wav")}, data={"include_speech": "true"})
    assert r.status_code == 200, r.text
    audio_out = r.json()["data"]
    for key in ("reply", "language", "intent", "tool", "result"):
        assert audio_out[key] == text_out[key], key
    assert audio_out["transcript"]["mock"] is True and audio_out["providers"]["stt"] == "mock"
    assert base64.b64decode(audio_out["speech"]["audio_base64"])[:4] == b"RIFF"
    msgs = (await owner.get(f"/conversations/{audio_conv}/messages")).json()["data"]
    assert msgs[0]["tool_metadata"]["source"] == "audio"
    # Empty transcript is handled gracefully.
    r = await owner.post(f"/conversations/{audio_conv}/messages/audio",
                         files={"file": ("q.wav", wav_with_transcript(""), "audio/wav")})
    assert r.status_code == 200 and r.json()["data"]["action"] is None


async def test_dashboard_audit_usage(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    owner, g, _ = await _shop(client)
    r = await owner.get("/dashboard/summary")
    s = r.json()["data"]
    assert s["total_outstanding_paise"] == 2100000 and s["overdue_invoices_count"] == 1
    assert s["overdue_amount_paise"] == 1000000 and s["customers_count"] == 2 and r.json()["meta"]["currency"] == "INR"
    over = (await owner.get("/dashboard/overdue-invoices")).json()
    assert over["meta"]["total"] == 1 and over["data"][0]["customer_name"] == "Ramesh Gupta"
    act = (await owner.get("/dashboard/activity")).json()
    assert act["meta"]["total"] >= 6 and act["data"][0]["action_type"].startswith("invoice.")
    logs = (await owner.get("/audit-logs", params={"entity_type": "customer"})).json()
    assert logs["meta"]["total"] == 2
    one = (await owner.get("/audit-logs", params={"entity_id": g["id"]})).json()
    assert one["data"][0]["action_type"] == "customer.created"
    assert all("notes" not in entry["metadata"] for entry in logs["data"])

    conv = await new_conversation(owner)
    await say(owner, conv, "Namaste")
    usage = (await owner.get("/usage")).json()["data"]
    msgs = next(m for m in usage["metrics"] if m["metric"] == "assistant_messages")
    assert msgs["count"] == 1 and msgs["remaining"] == msgs["limit"] - 1
    monkeypatch.setattr(get_settings(), "usage_limit_assistant_messages", 1)
    r = await owner.post(f"/conversations/{conv}/messages", json={"content": "hi"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "quota_exceeded"


async def test_idempotency_key(client, db) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    h = {"Idempotency-Key": "abc-123"}
    r1 = await owner.post("/customers", json={"name": "Asha"}, headers=h)
    r2 = await owner.post("/customers", json={"name": "Asha"}, headers=h)
    assert r1.status_code == r2.status_code == 201
    assert r1.json() == r2.json() and r2.headers.get("idempotent-replayed") == "true"
    assert (await owner.get("/customers")).json()["meta"]["total"] == 1
    r3 = await owner.post("/customers", json={"name": "Different"}, headers=h)
    assert r3.status_code == 422 and r3.json()["error"]["code"] == "idempotency_key_reused"
    await owner.post("/customers", json={"name": "Asha"})
    await owner.post("/customers", json={"name": "Asha"})
    assert (await owner.get("/customers")).json()["meta"]["total"] == 3
    # Confirm with an idempotency key replays the first result instead of returning 409.
    await make_customer(owner, "Ramesh Gupta")
    conv = await new_conversation(owner)
    action_id = (await say(owner, conv, "Remind Ramesh Gupta tomorrow at 5 pm"))["action"]["id"]
    k = {"Idempotency-Key": "confirm-1"}
    a = await owner.post(f"/actions/{action_id}/confirm", headers=k)
    b = await owner.post(f"/actions/{action_id}/confirm", headers=k)
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert (await db.execute(select(func.count()).select_from(Reminder))).scalar_one() == 1


async def test_integrations_not_configured(client) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    r = await owner.get("/integrations")
    assert r.status_code == 200 and r.json()["data"][0]["status"] == "not_configured"
    r = await owner.post("/integrations/google-sheets/connect")
    assert r.status_code == 503 and r.json()["error"]["code"] == "provider_not_configured"
    r = await owner.post("/integrations/google-sheets/import", json={"spreadsheet_id": "abcdef12345"})
    assert r.status_code == 503
    r = await client.get("/integrations/google-sheets/callback", params={"code": "x", "state": "y"})
    assert r.status_code == 503
    r = await owner.delete("/integrations/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


async def test_unknown_route_and_method_envelopes(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = await client.put("/health")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"
