"""Golden path: request -> intent -> real lookup -> preview -> confirm -> persisted
reminder -> audit record -> dashboard update. Plus the section-14 demo script."""
from datetime import date, timedelta

from sqlalchemy import func, select

from app.db.models import ActionLog, Reminder
from app.utils.dates import today_in
from scripts.seed_demo_data import seed
from tests.conftest import Account, make_customer, make_invoice, new_conversation, owner_with_business, say


async def test_golden_path(client, db) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    cust = await make_customer(owner, "Ramesh Gupta", "+919812345601")
    today = date.today()
    inv = await make_invoice(owner, cust["id"], "INV-1", 500000, (today - timedelta(days=30)).isoformat(),
                             (today - timedelta(days=5)).isoformat())
    assert inv["balance_paise"] == 500000 and inv["is_overdue"]

    before = (await owner.get("/dashboard/summary")).json()["data"]
    conv = await new_conversation(owner)
    out = await say(owner, conv, "Remind Ramesh Gupta tomorrow at 5 pm")
    assert out["intent"]["type"] == "schedule_reminder"
    action = out["action"]
    assert action["status"] == "pending_confirmation"
    assert action["preview"]["fields"]["customer"] == "Ramesh Gupta"
    assert action["preview"]["fields"]["invoice"] == "INV-1"
    assert "17:00" in action["payload"]["scheduled_at"] or "11:30:00" in action["payload"]["scheduled_at"]
    # Nothing is written before confirmation.
    assert (await db.execute(select(func.count()).select_from(Reminder))).scalar_one() == 0

    r = await owner.post(f"/actions/{action['id']}/confirm")
    assert r.status_code == 200, r.text
    confirmed = r.json()["data"]
    assert confirmed["status"] == "completed"
    reminder_id = confirmed["result"]["entity_id"]

    r = await owner.get(f"/reminders/{reminder_id}")
    assert r.status_code == 200
    rem = r.json()["data"]
    assert rem["status"] == "scheduled" and rem["creation_source"] == "assistant"
    assert rem["source_action_id"] == action["id"]

    # Second confirm: 409, still exactly one reminder.
    r = await owner.post(f"/actions/{action['id']}/confirm")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "action_already_handled"
    assert (await db.execute(select(func.count()).select_from(Reminder))).scalar_one() == 1

    # Audit rows exist.
    logs = (await db.execute(select(ActionLog.action_type))).scalars().all()
    assert "reminder.created" in logs and "action.confirmed" in logs and "action.proposed" in logs
    r = await owner.get("/audit-logs", params={"action_type": "reminder.created"})
    assert r.json()["meta"]["total"] == 1

    # Dashboard reflects it.
    after = (await owner.get("/dashboard/summary")).json()["data"]
    assert after["upcoming_reminders_count"] == before["upcoming_reminders_count"] + 1
    up = (await owner.get("/dashboard/upcoming-reminders")).json()["data"]
    assert up[0]["id"] == reminder_id and up[0]["customer_name"] == "Ramesh Gupta"

    # Conversation transcript has user, preview and confirmation messages.
    msgs = (await owner.get(f"/conversations/{conv}/messages")).json()["data"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "assistant"]


async def test_demo_script(client, db) -> None:  # type: ignore[no-untyped-def]
    seeded = await seed(db, email="demo@sharma.example.com", password="Demo12345")
    r = await client.post("/auth/login", json={"email": "demo@sharma.example.com", "password": "Demo12345"})
    owner = Account(client, r.json()["data"]["tokens"]["access_token"], str(seeded["user_id"]),
                    str(seeded["business_id"]))
    conv = await new_conversation(owner)

    # 1. Overdue count from the database, in Hinglish.
    out = await say(owner, conv, "Kitne invoice overdue hain?")
    overdue = (await owner.get("/invoices", params={"overdue": "true"})).json()["meta"]["total"]
    assert out["intent"]["type"] == "list_overdue_invoices"
    assert out["result"]["count"] == overdue >= 1
    assert out["language"] == "hi-Latn" and "overdue hain" in out["reply"]

    # 2. Ambiguous name -> clarification with both Rameshes.
    out = await say(owner, conv, "Ramesh ka kitna baaki hai?")
    names = {o["name"] for o in out["clarification"]["options"]}
    assert names == {"Ramesh Gupta", "Ramesh Verma"}
    assert "1." in out["reply"] and "2." in out["reply"]

    # 3. Resolve the awaiting slot -> balance from records.
    out = await say(owner, conv, "Ramesh Gupta")
    assert out["intent"]["type"] == "get_customer_balance"
    gupta_id = str(seeded["customers"]["Ramesh Gupta"])
    cust = (await owner.get(f"/customers/{gupta_id}")).json()["data"]
    assert out["result"]["customer"]["name"] == "Ramesh Gupta"
    assert out["result"]["outstanding_paise"] == cust["balance"]["outstanding_paise"] > 0

    # 4. Reminder preview for tomorrow 17:00 IST.
    out = await say(owner, conv, "Kal 5 baje yaad dila do")
    action = out["action"]
    assert action and action["status"] == "pending_confirmation"
    assert action["preview"]["fields"]["customer"] == "Ramesh Gupta"
    tomorrow = today_in("Asia/Kolkata") + timedelta(days=1)
    assert action["preview"]["fields"]["scheduled_at_local"].startswith(tomorrow.strftime("%d %b %Y"))
    assert "05:00 PM" in action["preview"]["fields"]["scheduled_at_local"]

    # 5. Confirm -> one reminder, audit entry, dashboard +1; second confirm 409.
    before = (await owner.get("/dashboard/summary")).json()["data"]["upcoming_reminders_count"]
    r = await owner.post(f"/actions/{action['id']}/confirm")
    assert r.status_code == 200 and r.json()["data"]["status"] == "completed"
    after = (await owner.get("/dashboard/summary")).json()["data"]["upcoming_reminders_count"]
    assert after == before + 1
    r = await owner.post(f"/actions/{action['id']}/confirm")
    assert r.status_code == 409
    count = (await db.execute(select(func.count()).select_from(Reminder).where(
        Reminder.source_action_id == action["id"]))).scalar_one()
    assert count == 1
    assert (await owner.get("/audit-logs", params={"action_type": "reminder.created"})).json()["meta"]["total"] == 1


async def test_seed_is_idempotent(db) -> None:  # type: ignore[no-untyped-def]
    a = await seed(db, email="seed@example.com")
    b = await seed(db, email="seed@example.com")
    assert a["business_id"] == b["business_id"]
    assert a["customers"] == b["customers"]
