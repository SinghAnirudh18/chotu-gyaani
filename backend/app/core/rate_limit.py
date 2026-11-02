"""Fixed-window rate limiter: Redis when configured and reachable, in-memory otherwise."""
import logging
import time
from collections import defaultdict

from app.core.config import get_settings
from app.core.exceptions import RateLimited

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self) -> None:
        self._memory: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        self._redis = None
        self._redis_checked = False

    async def _get_redis(self):  # type: ignore[no-untyped-def]
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        url = get_settings().redis_url
        if not url:
            return None
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
            await client.ping()
            self._redis = client
        except Exception:
            logger.warning("redis unavailable; using in-memory rate limiting")
            self._redis = None
        return self._redis

    async def hit(self, key: str, limit: int, window_seconds: int = 60) -> None:
        window = int(time.time() // window_seconds)
        bucket = f"rl:{key}:{window}"
        redis = await self._get_redis()
        if redis is not None:
            try:
                count = await redis.incr(bucket)
                if count == 1:
                    await redis.expire(bucket, window_seconds)
                if count > limit:
                    raise RateLimited(details={"retry_after_seconds": window_seconds})
                return
            except RateLimited:
                raise
            except Exception:
                logger.warning("redis rate-limit error; falling back to memory")
        w, count = self._memory[key]
        count = count + 1 if w == window else 1
        self._memory[key] = (window, count)
        if count > limit:
            raise RateLimited(details={"retry_after_seconds": window_seconds})

    def reset(self) -> None:
        self._memory.clear()


rate_limiter = RateLimiter()
