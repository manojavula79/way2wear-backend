import redis.asyncio as redis
from app.config import settings
import json
from typing import Any, Optional

# ── Redis client (singleton) ──────────────────
redis_client: redis.Redis = None


async def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
    return redis_client


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


# ── Redis Helper ──────────────────────────────
class RedisCache:

    @staticmethod
    async def set(key: str, value: Any, ttl: int = 3600) -> bool:
        r = await get_redis()
        try:
            serialized = json.dumps(value, default=str)
            await r.setex(key, ttl, serialized)
            return True
        except Exception:
            return False

    @staticmethod
    async def get(key: str) -> Optional[Any]:
        r = await get_redis()
        try:
            raw = await r.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    @staticmethod
    async def delete(key: str) -> bool:
        r = await get_redis()
        try:
            await r.delete(key)
            return True
        except Exception:
            return False

    @staticmethod
    async def delete_pattern(pattern: str) -> int:
        r = await get_redis()
        try:
            keys = await r.keys(pattern)
            if keys:
                return await r.delete(*keys)
            return 0
        except Exception:
            return 0

    @staticmethod
    async def increment(key: str, ttl: int = 60) -> int:
        r = await get_redis()
        pipe = r.pipeline()
        await pipe.incr(key)
        await pipe.expire(key, ttl)
        results = await pipe.execute()
        return results[0]

    # ── Session cache helpers ─────────────────
    @staticmethod
    def session_key(session_id: str) -> str:
        return f"session:{session_id}:messages"

    @staticmethod
    def user_key(user_id: str) -> str:
        return f"user:{user_id}:profile"

    @staticmethod
    def rate_limit_key(user_id: str) -> str:
        return f"ratelimit:{user_id}"
