import asyncio
from datetime import timedelta

from sqlalchemy import func, select, update

from app.db.models import ActionLog, PendingAction, Reminder
from app.db.session import get_sessionmaker
from app.utils.dates import utcnow
from app.workers import reminders as worker
from tests.conftest import make_customer, new_conversation, owner_with_business, say


async def test_fifty_parallel_confirms_one_effect(client, db) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    await make_customer(owner, "Ramesh Gupta")
    conv = await new_conversation(owner)
    action_id = (await say(owner, conv, "Remind Ramesh Gupta tomorrow at 5 pm"))["action"]["id"]

    results = await asyncio.gather(*[owner.post(f"/actions/{action_id}/confirm") for _ in range(50)])
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1, codes
    assert codes.count(409) == 49, codes
    assert (await db.execute(select(func.count()).select_from(Reminder))).scalar_one() == 1
    completed = (await db.execute(select(func.count()).select_from(ActionLog).where(
        ActionLog.action_type == "action.confirmed"))).scalar_one()
    assert completed == 1
    status = (await db.execute(select(PendingAction.status).where(PendingAction.id == action_id))).scalar_one()
    assert status == "completed"


async def test_poller_one_attempt_per_due_reminder_with_two_workers(client, db) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    cust = await make_customer(owner, "Ramesh Gupta")
    ids = []
    for _ in range(10):
        r = await owner.post("/reminders", json={"customer_id": cust["id"],
                                                 "scheduled_at": (utcnow() + timedelta(hours=1)).isoformat()})
        ids.append(r.json()["data"]["id"])
    # Make them due now.
    await db.execute(update(Reminder).values(scheduled_at=utcnow() - timedelta(minutes=1)))
    await db.commit()

    sm = get_sessionmaker()
    await asyncio.gather(worker.run_once(sm), worker.run_once(sm))

    db.expire_all()
    rows = (await db.execute(select(Reminder))).scalars().all()
    assert len(rows) == 10
    for r in rows:
        assert r.delivery_attempts == 1, r.delivery_attempts
        assert r.status == "due"  # stub never claims delivery
        assert r.last_error == "delivery_provider_not_configured"
        assert r.next_attempt_at is not None and r.next_attempt_at > utcnow()
    attempts = (await db.execute(select(func.count()).select_from(ActionLog).where(
        ActionLog.action_type == "reminder.delivery_attempted"))).scalar_one()
    assert attempts == 10


async def test_poller_backoff_and_cap(client, db) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    cust = await make_customer(owner, "Ramesh Gupta")
    r = await owner.post("/reminders", json={"customer_id": cust["id"],
                                             "scheduled_at": (utcnow() + timedelta(hours=1)).isoformat()})
    rid = r.json()["data"]["id"]
    assert worker.backoff_seconds(1) == 60 and worker.backoff_seconds(2) == 120
    assert worker.backoff_seconds(20) == 3600
    sm = get_sessionmaker()
    for _ in range(5):
        await db.execute(update(Reminder).where(Reminder.id == rid).values(
            scheduled_at=utcnow() - timedelta(minutes=1), next_attempt_at=utcnow() - timedelta(seconds=1)))
        await db.commit()
        await worker.run_once(sm)
    db.expire_all()
    rem = (await db.execute(select(Reminder).where(Reminder.id == rid))).scalar_one()
    assert rem.delivery_attempts == 5 and rem.status == "failed"
    assert (await owner.get(f"/reminders/{rid}")).json()["data"]["status"] == "failed"
