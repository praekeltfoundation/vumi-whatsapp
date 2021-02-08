import pytest
from vxwhatsapp import config
from aio_pika import connect_robust, Connection, Queue, Message as AMQPMessage
from aioredis import create_redis_pool, Redis
from vxwhatsapp.publisher import Publisher
from vxwhatsapp.models import Message
import time


@pytest.fixture
async def amqp() -> Connection:
    conn = await connect_robust(config.AMQP_URL)
    yield conn
    await conn.close()


@pytest.fixture
async def redis() -> Redis:
    conn = await create_redis_pool(config.REDIS_URL or "redis://", encoding="utf8")
    yield conn
    conn.close()
    await conn.wait_closed()


async def setup_amqp_queue(amqp: Connection, queuename="whatsapp.inbound") -> Queue:
    channel = await amqp.channel()
    queue = await channel.declare_queue(queuename, auto_delete=True)
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
    await redis.zadd("claims", int(time.time() - 6 * 60), "27820001001")
    await publisher._check_for_session_timeouts()
    msg = await get_amqp_message(queue)
    message = Message.from_json(msg.body.decode("utf-8"))
    assert message.session_event == Message.SESSION_EVENT.CLOSE
    assert message.from_addr == "27820001001"

    await redis.delete("claims")
    await publisher.teardown()
