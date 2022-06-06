import redis.asyncio as aioredis
from aio_pika import connect_robust

from vxwhatsapp import config


async def cleanup_redis():
    redis = aioredis.from_url(
        config.REDIS_URL or "redis://", encoding="utf-8", decode_responses=True
    )
    await redis.delete("claims")
    for key in await redis.keys("msglock:*"):
        await redis.delete(key)
    for key in await redis.keys("msgseen:*"):
        await redis.delete(key)
    await redis.close()


async def cleanup_amqp():
    connection = await connect_robust(config.AMQP_URL)
    async with connection:
        channel = await connection.channel()
        for routing_key in [
            f"{config.TRANSPORT_NAME}.inbound",
            f"{config.TRANSPORT_NAME}.outbound",
            f"{config.TRANSPORT_NAME}.event",
            f"{config.TRANSPORT_NAME}.answer",
        ]:
            queue = await channel.declare_queue(
                routing_key, durable=True, auto_delete=False
            )
            while True:
                message = await queue.get(fail=False)
                if message is None:
                    break
                message.ack()
