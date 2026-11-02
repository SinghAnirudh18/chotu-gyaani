"""In-DB reminder poller (no Celery/Redis needed).

Each due reminder is claimed with FOR UPDATE SKIP LOCKED so concurrent workers
never attempt the same reminder twice. The delivery stub never claims delivery:
attempts are recorded and retried with capped exponential backoff."""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import log_event
from app.db.models import Customer, Reminder
from app.providers.delivery import get_delivery
from app.services.action_service import expire_due
from app.services.audit import audit
from app.utils.dates import utcnow

logger = logging.getLogger(__name__)


def backoff_seconds(attempts: int) -> int:
    s = get_settings()
    return min(s.reminder_backoff_base_seconds * (2 ** max(attempts - 1, 0)), s.reminder_backoff_cap_seconds)


async def mark_due(db: AsyncSession) -> int:
    now = utcnow()
    res = await db.execute(update(Reminder).where(Reminder.status == "scheduled", Reminder.scheduled_at <= now)
                           .values(status="due", next_attempt_at=now).returning(Reminder.id))
    n = len(res.all())
    await db.commit()
    return n


async def process_due(db: AsyncSession, batch: int = 50) -> int:
    s = get_settings()
    now = utcnow()
    rows = (await db.execute(
        select(Reminder).where(Reminder.status == "due",
                               or_(Reminder.next_attempt_at.is_(None), Reminder.next_attempt_at <= now))
        .order_by(Reminder.next_attempt_at).limit(batch).with_for_update(skip_locked=True)
    )).scalars().all()
    delivery = get_delivery()
    for r in rows:
        c = await db.get(Customer, r.customer_id)
        result = await delivery.send(r.channel, c.phone_e164 if c else None, r.message or "")
        r.delivery_attempts += 1
        if result.delivered:
            r.status, r.completed_at, r.last_error = "delivered", utcnow(), None
        else:
            r.last_error = (result.error or "delivery_failed")[:255]
            if r.delivery_attempts >= s.reminder_max_attempts:
                r.status = "failed"
                r.next_attempt_at = None
            else:
                r.next_attempt_at = now + timedelta(seconds=backoff_seconds(r.delivery_attempts))
        audit(db, r.business_id, None, "reminder.delivery_attempted", entity_type="reminder", entity_id=r.id,
              outcome="success" if result.delivered else "failure",
              metadata={"attempt": r.delivery_attempts, "error": r.last_error, "status": r.status})
    await db.commit()
    return len(rows)


async def run_once(sessionmaker: async_sessionmaker[AsyncSession]) -> dict:
    async with sessionmaker() as db:
        due = await mark_due(db)
    async with sessionmaker() as db:
        attempted = await process_due(db)
    async with sessionmaker() as db:
        expired = await expire_due(db)
    return {"marked_due": due, "attempted": attempted, "expired_actions": expired}


async def loop(sessionmaker: async_sessionmaker[AsyncSession], stop: asyncio.Event) -> None:
    interval = get_settings().worker_poll_seconds
    while not stop.is_set():
        try:
            stats = await run_once(sessionmaker)
            if any(stats.values()):
                log_event(logger, "worker_tick", **stats)
        except Exception:
            logger.exception("worker tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
