from vxwhatsapp.claims import store_conversation_claim
from aioredis import create_redis_pool
from vxwhatsapp import config


async def test_store_missing_parameters():
    """
    If no redis or no claim is passed, should do nothing
    """
    await store_conversation_claim(None, "foo", "bar")

    redis = await create_redis_pool(config.REDIS_URL or "redis://", encoding="utf8")
    await store_conversation_claim(redis, None, "bar")

    val = await redis.zrange("claims", start=0, stop=-1)
    assert val == []


async def test_store_claims():
    """
    Should store the claim inside the "claims" zset
    """
    redis = await create_redis_pool(config.REDIS_URL or "redis://", encoding="utf8")
    await store_conversation_claim(redis, "claim", "value")

    [val] = await redis.zrange("claims", start=0, stop=-1)
    assert val == "value"
    await redis.delete("claims")
