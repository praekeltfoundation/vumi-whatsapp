from aio_pika import Connection, DeliveryMode, ExchangeType
from aio_pika import Message as AMQPMessage

from vxwhatsapp import config
from vxwhatsapp.models import Message


class Publisher:
    def __init__(self, connection: Connection):
        self.connection = connection

    async def setup(self):
        self.channel = await self.connection.channel()
        self.exchange = await self.channel.declare_exchange(
            "vumi", type=ExchangeType.DIRECT, durable=True, auto_delete=False
        )

    async def publish_message(self, message: Message):
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
