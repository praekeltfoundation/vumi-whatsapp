import time
from typing import Optional

from aioredis import Redis


async def store_conversation_claim(
    redis: Optional[Redis], claim: Optional[str], address: str
) -> None:
    if not redis:
        return

    if not claim:
        return

    now = int(time.time())
    # We actually only need the user address to send the session expiry message, so
    # instead of storing the claim ID, and then storing the message in another key,
    # just store the user address
    await redis.zadd("claims", now, address)
