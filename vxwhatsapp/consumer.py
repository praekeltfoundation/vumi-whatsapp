from json.decoder import JSONDecodeError
from urllib.parse import ParseResult, urlunparse

import aiohttp
import ujson
from aio_pika import Connection, ExchangeType, IncomingMessage
from prometheus_client import Histogram
from sanic.log import logger

from vxwhatsapp import config
from vxwhatsapp.models import Message

WHATSAPP_RQS_LATENCY = Histogram(
    "whatsapp_api_request_latency_sec",
    "WhatsApp API Request Latency Histogram",
    ["endpoint"],
)
whatsapp_message_send = WHATSAPP_RQS_LATENCY.labels("/v1/messages")


class Consumer:
    def __init__(self, connection: Connection):
        self.connection = connection
        self.session = aiohttp.ClientSession(
            json_serialize=ujson.dumps,
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(total=config.CONSUME_TIMEOUT),
            connector=aiohttp.TCPConnector(limit=config.CONCURRENCY),
            headers={"Authorization": f"Bearer {config.API_TOKEN}"},
        )
        self.message_url = urlunparse(
            ParseResult(
                scheme="https",
                netloc=config.API_HOST,
                path="/v1/messages",
                params="",
                query="",
                fragment="",
            )
        )

    async def setup(self):
        queue_name = f"{config.TRANSPORT_NAME}.outbound"
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=config.CONCURRENCY)
        self.exchange = await self.channel.declare_exchange(
            "vumi", type=ExchangeType.DIRECT, durable=True, auto_delete=False
        )
        self.queue = await self.channel.declare_queue(
            queue_name, durable=True, auto_delete=False
        )
        await self.queue.bind(self.exchange, queue_name)
        await self.queue.consume(self.process_message)

    async def teardown(self):
        await self.session.close()

    async def process_message(self, message: IncomingMessage):
        try:
            msg = Message.from_json(message.body.decode("utf-8"))
        except (
            UnicodeDecodeError,
            JSONDecodeError,
            TypeError,
            KeyError,
            ValueError,
        ):
            # Invalid Vumi message, log and throw away, retrying won't help
            logger.exception(f"Invalid message body {message.body!r}")
            await message.reject(requeue=False)
            return

        async with message.process(requeue=True):
            logger.debug(f"Processing outbound message {msg}")
            await self.submit_message(msg)

    @whatsapp_message_send.time()
    async def submit_message(self, message: Message):
        # TODO: support more message types
        await self.session.post(
            self.message_url,
            json={"to": message.to_addr, "text": {"body": message.content or ""}},
        )
