import json
import redis.asyncio as aioredis
from typing import Any, Optional
from app.config import settings

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def cache_get(key: str) -> Optional[Any]:
    r = await get_redis()
    val = await r.get(key)
    if val:
        return json.loads(val)
    return None


async def cache_set(key: str, value: Any, ttl: int = settings.CACHE_TTL) -> None:
    r = await get_redis()
    await r.setex(key, ttl, json.dumps(value, default=str))


async def cache_delete(key: str) -> None:
    r = await get_redis()
    await r.delete(key)


async def cache_delete_pattern(pattern: str) -> None:
    r = await get_redis()
    keys = await r.keys(pattern)
    if keys:
        await r.delete(*keys)


def make_search_key(params: dict) -> str:
    sorted_items = sorted(params.items())
    return "search:" + ":".join(f"{k}={v}" for k, v in sorted_items if v is not None)


def make_doctor_key(doctor_id: int) -> str:
    return f"doctor:{doctor_id}"


def make_slots_key(doctor_id: int, date_str: str) -> str:
    return f"slots:{doctor_id}:{date_str}"
