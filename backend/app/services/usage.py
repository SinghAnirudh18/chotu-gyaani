import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import QuotaExceeded
from app.db.models import UsageRecord
from app.utils.dates import utcnow

METRICS = ("assistant_messages", "audio_requests", "agent_generations")


def current_period() -> str:
    return utcnow().strftime("%Y-%m")


def limits() -> dict[str, int]:
    s = get_settings()
    return {
        "assistant_messages": s.usage_limit_assistant_messages,
        "audio_requests": s.usage_limit_audio_requests,
        "agent_generations": s.usage_limit_agent_generations,
    }


async def consume(db: AsyncSession, business_id: uuid.UUID, metric: str, amount: int = 1) -> int:
    """Atomically increment a usage counter; raises 429 when over the limit."""
    limit = limits()[metric]
    period = current_period()
    stmt = insert(UsageRecord).values(business_id=business_id, metric=metric, period=period, count=amount)
    upsert = stmt.on_conflict_do_update(
        index_elements=["business_id", "metric", "period"],
        set_={"count": UsageRecord.count + amount},
        where=UsageRecord.count + amount <= limit,
    ).returning(UsageRecord.count)
    if amount > limit:
        raise QuotaExceeded(details={"metric": metric, "limit": limit, "period": period})
    count = (await db.execute(upsert)).scalar_one_or_none()
    await db.commit()
    if count is None:
        raise QuotaExceeded(details={"metric": metric, "limit": limit, "period": period})
    return count


async def summary(db: AsyncSession, business_id: uuid.UUID) -> dict:
    period = current_period()
    rows = (await db.execute(
        select(UsageRecord.metric, UsageRecord.count)
        .where(UsageRecord.business_id == business_id, UsageRecord.period == period)
    )).all()
    counts = {m: c for m, c in rows}
    lim = limits()
    return {
        "period": period,
        "metrics": [{"metric": m, "count": counts.get(m, 0), "limit": lim[m],
                     "remaining": max(lim[m] - counts.get(m, 0), 0)} for m in METRICS],
    }
