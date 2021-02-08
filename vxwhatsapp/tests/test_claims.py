from aioredis import create_redis_pool

from vxwhatsapp import config
from vxwhatsapp.claims import store_conversation_claim, delete_conversation_claim


async def test_store_missing_parameters():
    """
    If no redis or no claim is passed, should do nothing
    """
    await store_conversation_claim(None, "foo", "bar")

    redis = await create_redis_pool(config.REDIS_URL or "redis://", encoding="utf8")
    await store_conversation_claim(redis, None, "bar")

    assert await redis.zcount("claims") == 0
    await redis.delete("claims")


async def test_store_claims():
    """
    Should store the claim inside the "claims" zset
    """
    redis = await create_redis_pool(config.REDIS_URL or "redis://", encoding="utf8")
    await store_conversation_claim(redis, "claim", "value")

    [val] = await redis.zrange("claims", start=0, stop=-1)
    assert val == "value"
    await redis.delete("claims")


async def test_delete_missing_parameters():
    """
    If no redis or no claim is passed, should do nothing
    """
    await delete_conversation_claim(None, "foo", "bar")

    redis = await create_redis_pool(config.REDIS_URL or "redis://", encoding="utf8")
    await delete_conversation_claim(redis, None, "bar")

    assert await redis.zcount("claims") == 0
    await redis.delete("claims")


async def test_delete_claims():
    """
    Should delete the specified claim
    """
    redis = await create_redis_pool(config.REDIS_URL or "redis://", encoding="utf8")
    await redis.zadd("claims", 1, "27820001001")
    await delete_conversation_claim(redis, "foo", "27820001001")

    assert await redis.zcount("claims") == 0
    await redis.delete("claims")
