from aioredis import from_url, Redis

from vxwhatsapp import config
from vxwhatsapp.claims import delete_conversation_claim, store_conversation_claim
import pytest
from typing import AsyncGenerator


@pytest.fixture
async def redis() -> AsyncGenerator[Redis, None]:
    conn = from_url(
        config.REDIS_URL or "redis://", encoding="utf8", decode_responses=True
    )
    yield conn
    await conn.close()


async def test_store_missing_parameters(redis):
    """
    If no redis or no claim is passed, should do nothing
    """
    await store_conversation_claim(None, "foo", "bar")

    await store_conversation_claim(redis, None, "bar")

    assert await redis.zcount("claims", "-inf", "+inf") == 0
    await redis.delete("claims")


async def test_store_claims(redis):
    """
    Should store the claim inside the "claims" zset
    """
    await store_conversation_claim(redis, "claim", "value")

    [val] = await redis.zrange("claims", start=0, end=-1)
    assert val == "value"
    await redis.delete("claims")


async def test_delete_missing_parameters(redis):
    """
    If no redis or no claim is passed, should do nothing
    """
    await delete_conversation_claim(None, "foo", "bar")

    await delete_conversation_claim(redis, None, "bar")

    assert await redis.zcount("claims", "-inf", "+inf") == 0
    await redis.delete("claims")


async def test_delete_claims(redis):
    """
    Should delete the specified claim
    """
    await redis.zadd("claims", {"27820001001": 1})
    await delete_conversation_claim(redis, "foo", "27820001001")

    assert await redis.zcount("claims", "-inf", "+inf") == 0
    await redis.delete("claims")
