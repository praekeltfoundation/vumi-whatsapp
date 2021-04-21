import os
from json.decoder import JSONDecodeError
from typing import Any, Dict
from urllib.parse import ParseResult, unquote_plus, urlparse, urlunparse

import aiohttp
import ujson
from aio_pika import Connection, ExchangeType, IncomingMessage
from aioredis import Redis
from prometheus_client import Histogram
from sanic.log import logger

from vxwhatsapp import config
from vxwhatsapp.claims import delete_conversation_claim, store_conversation_claim
from vxwhatsapp.models import Message

WHATSAPP_RQS_LATENCY = Histogram(
    "whatsapp_api_request_latency_sec",
    "WhatsApp API Request Latency Histogram",
    ["endpoint"],
)
whatsapp_message_send = WHATSAPP_RQS_LATENCY.labels("/v1/messages")


class Consumer:
    def __init__(self, connection: Connection, redis: Redis):
        self.redis = redis
        self.connection = connection
        self.session = aiohttp.ClientSession(
            json_serialize=ujson.dumps,
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(total=config.CONSUME_TIMEOUT),
            connector=aiohttp.TCPConnector(limit=config.CONCURRENCY),
            headers={"Authorization": f"Bearer {config.API_TOKEN}"},
        )
        self.media_session = aiohttp.ClientSession(
            json_serialize=ujson.dumps,
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(total=config.CONSUME_TIMEOUT),
            connector=aiohttp.TCPConnector(limit=config.CONCURRENCY),
        )
        self.api_host = config.API_HOST
        self.message_url = self._make_url("/v1/messages")
        self.message_automation_url = self._make_url("/v1/messages/{}/automation")
        self.media_url = self._make_url("/v1/media")
        self.media_cache: Dict[str, str] = {}

    def _make_url(self, path):
        return urlunparse(
            ParseResult(
                scheme="https",
                netloc=self.api_host,
                path=path,
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
        await self.media_session.close()

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
            with whatsapp_message_send.time():
                await self.submit_message(msg)

    async def get_media_id(self, media_url):
        if media_url in self.media_cache:
            return self.media_cache[media_url]

        async with self.media_session.get(media_url) as media_response:
            media_response.raise_for_status()
            turn_response = await self.session.post(
                self.media_url,
                headers={
                    "Content-Type": media_response.headers["Content-Type"],
                },
                data=media_response.content,
            )
            turn_response.raise_for_status()
            response_data: Any = await turn_response.json()
            media_id = response_data["media"][0]["id"]
            self.media_cache[media_url] = media_id
            return media_id

    @staticmethod
    def _extract_filename(url: str):
        path = urlparse(url).path
        return os.path.basename(unquote_plus(path))

    async def submit_message(self, message: Message):
        # TODO: support more message types

        headers: Dict[str, str] = {}
        url = self.message_url
        if claim := message.transport_metadata.get("claim"):
            if (
                message.session_event == Message.SESSION_EVENT.RESUME
                or message.session_event == Message.SESSION_EVENT.NONE
            ):
                headers["X-Turn-Claim-Extend"] = claim
                await store_conversation_claim(self.redis, claim, message.to_addr)
            elif message.session_event == Message.SESSION_EVENT.CLOSE:
                headers["X-Turn-Claim-Release"] = claim
                if (
                    message.transport_metadata.get("automation_handle")
                    and message.in_reply_to
                ):
                    url = self.message_automation_url.format(message.in_reply_to)
                await delete_conversation_claim(self.redis, claim, message.to_addr)

        data: dict[str, Any] = {"to": message.to_addr}

        if "document" in message.helper_metadata:
            document_url = message.helper_metadata["document"]
            media_id = await self.get_media_id(document_url)
            data["type"] = "document"
            data["document"] = {
                "id": media_id,
                "filename": self._extract_filename(document_url),
            }
        else:
            data["text"] = {"body": message.content or ""}

        await self.session.post(
            url,
            headers=headers,
            json=data,
        )
