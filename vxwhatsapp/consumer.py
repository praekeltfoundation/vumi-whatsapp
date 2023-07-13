import os
from asyncio import sleep
from json.decoder import JSONDecodeError
from typing import Any, Dict
from urllib.parse import ParseResult, unquote_plus, urlparse, urlunparse

import aiohttp
import ujson
from aio_pika import Connection, ExchangeType, IncomingMessage
from prometheus_client import Histogram
from redis.asyncio import Redis
from sanic.log import logger

from vxwhatsapp import config
from vxwhatsapp.claims import delete_conversation_claim, store_conversation_claim
from vxwhatsapp.models import Message
from vxwhatsapp.utils import valid_url

WHATSAPP_RQS_LATENCY = Histogram(
    "whatsapp_api_request_latency_sec",
    "WhatsApp API Request Latency Histogram",
    ["endpoint"],
)
whatsapp_message_send = WHATSAPP_RQS_LATENCY.labels("/v1/messages")
whatsapp_media_upload = WHATSAPP_RQS_LATENCY.labels("/v1/media")
whatsapp_contact_check = WHATSAPP_RQS_LATENCY.labels("/v1/contacts")


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
        self.contact_url = self._make_url("/v1/contacts")

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

        logger.debug(f"Processing outbound message {msg}")
        try:
            await self.submit_message(msg)
        except aiohttp.ClientResponseError as e:
            # If it's a retryable upstream error, requeue the message
            if e.status > 499:
                await message.reject(requeue=True)
                # If we've retried this before, wait before retrying again
                if message.redelivered:
                    await sleep(0.5)
            else:
                # Otherwise log the error and reject
                logger.exception(f"Upstream HTTP error processing {msg}")
                await message.reject(requeue=False)
        except Exception:
            # Any other errors aren't recoverable, so log and reject
            logger.exception(f"Error processing {msg}")
            await message.reject(requeue=False)
        else:
            await message.ack()

    async def get_media_id(self, media_url):
        if media_url in self.media_cache:
            return self.media_cache[media_url]

        async with self.media_session.get(media_url) as media_response:
            media_response.raise_for_status()
            with whatsapp_media_upload.time():
                turn_response = await self.session.post(
                    self.media_url,
                    headers={
                        "Content-Type": media_response.headers["Content-Type"],
                    },
                    data=media_response.content,
                )
            response_data: Any = await turn_response.json()
            media_id = response_data["media"][0]["id"]
            self.media_cache[media_url] = (
                media_id,
                media_response.headers["Content-Type"],
            )
            return self.media_cache[media_url]

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
                    message.helper_metadata.get("automation_handle")
                    and message.in_reply_to
                ):
                    url = self.message_automation_url.format(message.in_reply_to)
                    headers["Accept"] = "application/vnd.v1+json"
                await delete_conversation_claim(self.redis, claim, message.to_addr)

        data: Dict[str, Any] = {"to": message.to_addr}

        if "buttons" in message.helper_metadata:
            options = message.helper_metadata["buttons"]
            data["type"] = "interactive"
            data["interactive"] = {
                "type": "button",
                "body": {"text": (message.content or "")[:1024]},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": option[:256], "title": option[:20]},
                        }
                        for option in options[:3]
                    ],
                },
            }
            if "header" in message.helper_metadata:
                header = message.helper_metadata["header"]
                if valid_url(header):
                    media_id, content_type = await self.get_media_id(header)
                    if content_type in ("image/jpeg", "image/png"):
                        data["interactive"]["header"] = {
                            "type": "image",
                            "image": {"id": media_id},
                        }
                    elif content_type in ("video/mp4", "video/3gpp"):
                        data["interactive"]["header"] = {
                            "type": "video",
                            "video": {"id": media_id},
                        }
                    else:
                        data["interactive"]["header"] = {
                            "type": "document",
                            "document": {
                                "id": media_id,
                                "filename": self._extract_filename(header),
                            },
                        }
                else:
                    data["interactive"]["header"] = {
                        "type": "text",
                        "text": header[:60],
                    }
            if "footer" in message.helper_metadata:
                data["interactive"]["footer"] = {
                    "text": message.helper_metadata["footer"][:60]
                }
        elif "sections" in message.helper_metadata:
            data["type"] = "interactive"

            for section in message.helper_metadata["sections"]:
                for row in section["rows"]:
                    row["id"] = row["id"][:200]
                    row["title"] = row["title"][:24]

            data["interactive"] = {
                "type": "list",
                "body": {"text": (message.content or "")[:1024]},
                "action": {
                    "button": message.helper_metadata["button"][:20],
                    "sections": message.helper_metadata["sections"][:10],
                },
            }
            if "header" in message.helper_metadata:
                data["interactive"]["header"] = {
                    "type": "text",
                    "text": message.helper_metadata["header"][:60],
                }
            if "footer" in message.helper_metadata:
                data["interactive"]["footer"] = {
                    "text": message.helper_metadata["footer"][:60]
                }
        elif "document" in message.helper_metadata:
            document_url = message.helper_metadata["document"]
            media_id, _ = await self.get_media_id(document_url)
            data["type"] = "document"
            data["document"] = {
                "id": media_id,
                "filename": self._extract_filename(document_url),
            }
        elif "image" in message.helper_metadata:
            image_url = message.helper_metadata["image"]
            media_id, _ = await self.get_media_id(image_url)
            data["type"] = "image"
            data["image"] = {"id": media_id}
            if message.content:
                data["image"]["caption"] = message.content
        else:
            data["text"] = {"body": message.content or ""}

        try:
            with whatsapp_message_send.time():
                await self.session.post(url, headers=headers, json=data)
        except aiohttp.ClientResponseError as e:
            # If it fails with a 404, it could be that the contact has been forgotten.
            # So do a contact check, and then try sending the message again
            if e.status != 404:  # pragma: no cover
                raise e
            with whatsapp_contact_check.time():
                c = await self.session.post(
                    self.contact_url,
                    json={
                        "blocking": "wait",
                        "contacts": [f"+{message.to_addr.lstrip('+')}"],
                    },
                )
                contact_status = (await c.json())["contacts"][0]["status"]
                if contact_status != "valid":
                    # If the contact isn't on whatsapp, drop the message and log error
                    logger.exception(f"Contact {message.to_addr} not on whatsapp")
                    return
                await self.session.post(url, headers=headers, json=data)
