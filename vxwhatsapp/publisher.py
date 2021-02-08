import asyncio
import time

from aio_pika import Connection, DeliveryMode, ExchangeType
from aio_pika import Message as AMQPMessage
from aioredis import Redis
from sanic.log import logger

from vxwhatsapp import config
from vxwhatsapp.models import Event, Message


class Publisher:
    def __init__(self, connection: Connection, redis: Redis):
        self.connection = connection
        self.redis = redis

    async def setup(self):
        self.channel = await self.connection.channel()
        self.exchange = await self.channel.declare_exchange(
            "vumi", type=ExchangeType.DIRECT, durable=True, auto_delete=False
        )
        self.periodic_task = asyncio.create_task(self._periodic_loop())

    async def teardown(self):
        self.periodic_task.cancel()

    async def publish_message(self, message: Message):
        logger.debug(f"Publishing inbound message {message}")
        await self.exchange.publish(
            AMQPMessage(
                message.to_json().encode("utf-8"),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
                content_encoding="UTF-8",
            ),
            routing_key=f"{config.TRANSPORT_NAME}.inbound",
            timeout=config.PUBLISH_TIMEOUT,
        )

    async def publish_event(self, event: Event):
        logger.debug(f"Publishing inbound event {event}")
        await self.exchange.publish(
            AMQPMessage(
                event.to_json().encode("utf-8"),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
                content_encoding="UTF-8",
            ),
            routing_key=f"{config.TRANSPORT_NAME}.event",
            timeout=config.PUBLISH_TIMEOUT,
        )

    async def _periodic_loop(self):
        while True:
            await self._check_for_session_timeouts()
            await asyncio.sleep(1)

    async def _check_for_session_timeouts(self):
        if not self.redis:
            return
        timestamp = int(time.time() - 5 * 60)
        # Do the get + delete atomically, since there could be multiple processes
        # for the same transport
        transaction: Redis = self.redis.multi_exec()
        transaction.zrangebyscore("claims", max=timestamp)
        transaction.zremrangebyscore("claims", max=timestamp)
        addresses, _ = await transaction.execute()
        for address in addresses:
            msg = Message(
                to_addr=config.WHATSAPP_NUMBER,
                from_addr=address,
                transport_name=config.TRANSPORT_NAME,
                transport_type=Message.TRANSPORT_TYPE.HTTP_API,
                session_event=Message.SESSION_EVENT.CLOSE,
                to_addr_type=Message.ADDRESS_TYPE.MSISDN,
                from_addr_type=Message.ADDRESS_TYPE.MSISDN,
            )
            await self.publish_message(msg)
