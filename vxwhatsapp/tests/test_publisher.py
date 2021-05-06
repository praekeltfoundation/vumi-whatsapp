import time
from typing import AsyncGenerator

import pytest
from aio_pika import Connection
from aio_pika import Message as AMQPMessage
from aio_pika import Queue, connect_robust
from aioredis import Redis, from_url

from vxwhatsapp import config
from vxwhatsapp.models import Message
from vxwhatsapp.publisher import Publisher


@pytest.fixture
async def amqp() -> AsyncGenerator[Connection, None]:
    conn: Connection = await connect_robust(config.AMQP_URL)
    yield conn
    await conn.close()


@pytest.fixture
async def redis() -> AsyncGenerator[Redis, None]:
    conn = from_url(
        config.REDIS_URL or "redis://", encoding="utf8", decode_responses=True
    )
    yield conn
    await conn.close()


async def setup_amqp_queue(amqp: Connection, queuename="whatsapp.inbound") -> Queue:
    channel = await amqp.channel()
    queue = await channel.declare_queue(queuename, durable=True)
    await queue.bind("vumi", queuename)
    return queue


async def get_amqp_message(queue: Queue) -> AMQPMessage:
    message = await queue.get(timeout=1)
    assert message is not None
    await message.ack()
    return message


async def test_session_timeout_check(amqp: Connection, redis: Redis):
    queue = await setup_amqp_queue(amqp)
    publisher = Publisher(amqp, redis)
    await publisher.setup()
    publisher.periodic_task.cancel()
    await redis.zadd("claims", {"27820001001": int(time.time() - 6 * 60)})
    await publisher._check_for_session_timeouts()
    msg = await get_amqp_message(queue)
    message = Message.from_json(msg.body.decode("utf-8"))
    assert message.session_event == Message.SESSION_EVENT.CLOSE
    assert message.from_addr == "27820001001"

    await redis.delete("claims")
    await publisher.teardown()
