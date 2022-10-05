import logging
import time
from asyncio import Future
from dataclasses import dataclass, field
from io import StringIO

import pytest
import pytest_asyncio
from aio_pika import Connection, DeliveryMode, ExchangeType
from aio_pika import Message as AMQPMessage
from sanic import Sanic
from sanic.log import logger
from sanic.response import json, text

from vxwhatsapp import config
from vxwhatsapp.main import app
from vxwhatsapp.models import Message
from vxwhatsapp.tests.utils import cleanup_amqp, cleanup_redis, run_sanic


@pytest_asyncio.fixture
async def app_server():
    config.REDIS_URL = config.REDIS_URL or "redis://"
    async with run_sanic(app) as server:
        yield server
    await cleanup_amqp()
    await cleanup_redis()


@dataclass
class TState:
    future: Future = field(default_factory=Future)
    contact_future: Future = field(default_factory=Future)
    message_status_code: int = 200
    message_client_error_code: int = 400
    request_count: int = 0


@pytest_asyncio.fixture
async def whatsapp_mock_server():
    Sanic.test_mode = True
    app = Sanic("mock_whatsapp")
    tstate = TState()

    @app.route("/v1/messages", methods=["POST"])
    async def messages(request):
        tstate.future.set_result(request)
        tstate.request_count += 1

        status_code = tstate.message_status_code
        if request.json["to"] == "27820001003":
            status_code = tstate.message_client_error_code

        return json({}, status=status_code)

    @app.route("/v1/messages/<message_id>/automation", methods=["POST"])
    async def message_automation(request, message_id):
        tstate.future.set_result(request)
        return json({})

    @app.route("/v1/media", methods=["POST"])
    async def media_upload(request):
        return json({"media": [{"id": "test-media-id"}]})

    @app.route("/v1/contacts", methods=["POST"])
    async def contact_check(request):
        tstate.contact_future.set_result(request)
        msisdn = request.json["contacts"][0]
        if msisdn == "+27820001111":
            status = "invalid"
        else:
            status = "valid"
            tstate.message_status_code = 200
        return json(
            {
                "contacts": [
                    {"wa_id": msisdn.lstrip("+"), "input": msisdn, "status": status}
                ]
            }
        )

    async with run_sanic(app) as server:
        server.tstate = tstate
        yield server


@pytest_asyncio.fixture
async def media_mock_server():
    Sanic.test_mode = True
    app = Sanic("mock_media")

    @app.route("test_document.pdf", methods=["GET"])
    async def test_document(request):
        return text("test_document")

    @app.route("test_image.jpeg", methods=["GET"])
    async def test_image(request):
        return text("test_image")

    async with run_sanic(app) as server:
        yield server


async def send_outbound_amqp_message(connection: Connection, message: bytes):
    channel = await connection.channel()
    exchange = await channel.declare_exchange(
        "vumi", type=ExchangeType.DIRECT, durable=True, auto_delete=False
    )
    await exchange.publish(
        AMQPMessage(
            message,
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            content_encoding="UTF-8",
        ),
        routing_key="whatsapp.outbound",
    )


async def send_outbound_message(connection: Connection, message: Message):
    await send_outbound_amqp_message(connection, message.to_json().encode("utf-8"))


@pytest.mark.asyncio
async def test_outbound_text_message(whatsapp_mock_server, app_server):
    """
    Should make a request to the whatsapp API, extending the conversation claim
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/messages"
    )
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            transport_metadata={"claim": "test-claim"},
            content="test message",
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {"text": {"body": "test message"}, "to": "27820001001"}
    assert request.headers["X-Turn-Claim-Extend"] == "test-claim"

    [addr] = await app_server.app.ctx.redis.zrange("claims", 0, -1)
    assert addr == "27820001001"
    await app_server.app.ctx.redis.delete("claims")


@pytest.mark.asyncio
async def test_outbound_text_message_client_error(whatsapp_mock_server, app_server):
    """
    Should make a request to the whatsapp API, but not retry for a client error
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/messages"
    )
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001003",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            transport_metadata={},
            content="test message 2",
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {"text": {"body": "test message 2"}, "to": "27820001003"}

    assert whatsapp_mock_server.tstate.request_count == 1


@pytest.mark.asyncio
async def test_outbound_text_end_session(whatsapp_mock_server, app_server):
    """
    Should make a request to the whatsapp API, releasing the conversation claim, and
    removing it from the set of open conversations
    """
    redis = app_server.app.ctx.redis
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/messages"
    )
    await redis.zadd("claims", {"27820001001": int(time.time())})
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            transport_metadata={"claim": "test-claim"},
            content="test message",
            session_event=Message.SESSION_EVENT.CLOSE,
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {"text": {"body": "test message"}, "to": "27820001001"}
    assert request.headers["X-Turn-Claim-Release"] == "test-claim"

    assert await redis.zcount("claims", "-inf", "+inf") == 0
    await redis.delete("claims")


@pytest.mark.asyncio
async def test_outbound_text_automation_handle(whatsapp_mock_server, app_server):
    """
    Should make a request to the turn automation API to reevaluate
    """
    app_server.app.ctx.consumer.message_automation_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/{}/automation"
    )
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            transport_metadata={"claim": "test-claim"},
            helper_metadata={"automation_handle": True},
            content="test message",
            session_event=Message.SESSION_EVENT.CLOSE,
            in_reply_to="message-id",
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {"text": {"body": "test message"}, "to": "27820001001"}
    assert request.headers["X-Turn-Claim-Release"] == "test-claim"
    assert request.headers["Accept"] == "application/vnd.v1+json"
    assert "/v1/messages/message-id/automation" in request.url


@pytest.mark.asyncio
async def test_invalid_outbound_text_message(app_server):
    """
    If the AMQP message is invalid, then drop it
    """
    log_stream = StringIO()
    logger.addHandler(logging.StreamHandler(log_stream))
    await send_outbound_amqp_message(app_server.app.ctx.amqp_connection, b"invalid")
    assert "Invalid message body b'invalid'" in log_stream.getvalue()
    assert "JSONDecodeError" in log_stream.getvalue()


@pytest.mark.asyncio
async def test_outbound_document(whatsapp_mock_server, media_mock_server, app_server):
    """
    Should upload the document, and then send the message with the media ID
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    app_server.app.ctx.consumer.media_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/media"
    )
    document_url = (
        f"http://{media_mock_server.host}:{media_mock_server.port}/test_document.pdf"
    )
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            helper_metadata={"document": document_url},
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {
        "type": "document",
        "document": {"id": "test-media-id", "filename": "test_document.pdf"},
        "to": "27820001001",
    }


@pytest.mark.asyncio
async def test_outbound_document_cached(whatsapp_mock_server, app_server):
    """
    Should get the media URL from cache
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    doc_url = "http://example/org/cached+%26.pdf"
    app_server.app.ctx.consumer.media_cache[doc_url] = (
        "test-media-id",
        "application/pdf",
    )
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            helper_metadata={"document": doc_url},
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {
        "type": "document",
        "document": {"id": "test-media-id", "filename": "cached &.pdf"},
        "to": "27820001001",
    }


@pytest.mark.asyncio
async def test_outbound_image(whatsapp_mock_server, media_mock_server, app_server):
    """
    Should upload the image, and then send the message with the media ID
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    app_server.app.ctx.consumer.media_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/media"
    )
    image_url = (
        f"http://{media_mock_server.host}:{media_mock_server.port}/test_image.jpeg"
    )
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            content="test caption",
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            helper_metadata={"image": image_url},
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {
        "type": "image",
        "image": {"id": "test-media-id", "caption": "test caption"},
        "to": "27820001001",
    }


@pytest.mark.asyncio
async def test_outbound_missing_contact(whatsapp_mock_server, app_server):
    """
    Makes a contact check, and then tries again
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/messages"
    )
    app_server.app.ctx.consumer.contact_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/contacts"
    )
    whatsapp_mock_server.tstate.message_status_code = 404
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            content="test message",
        ),
    )
    msg1 = await whatsapp_mock_server.tstate.future
    whatsapp_mock_server.tstate.future = Future()
    contact = await whatsapp_mock_server.tstate.contact_future
    msg2 = await whatsapp_mock_server.tstate.future

    assert msg1.url == app_server.app.ctx.consumer.message_url
    assert msg1.json == {"text": {"body": "test message"}, "to": "27820001001"}

    assert contact.url == app_server.app.ctx.consumer.contact_url
    assert contact.json == {"blocking": "wait", "contacts": ["+27820001001"]}

    assert msg2.url == app_server.app.ctx.consumer.message_url
    assert msg2.json == {"text": {"body": "test message"}, "to": "27820001001"}


@pytest.mark.asyncio
async def test_outbound_missing_contact_permanent(whatsapp_mock_server, app_server):
    """
    Makes a contact check, and if the contact isn't valid, drop the message
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/messages"
    )
    app_server.app.ctx.consumer.contact_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/contacts"
    )
    whatsapp_mock_server.tstate.message_status_code = 404
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001111",
            from_addr="27820001000",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            content="test message",
        ),
    )
    msg1 = await whatsapp_mock_server.tstate.future
    contact = await whatsapp_mock_server.tstate.contact_future

    assert msg1.json == {"text": {"body": "test message"}, "to": "27820001111"}

    assert contact.json == {"blocking": "wait", "contacts": ["+27820001111"]}


@pytest.mark.asyncio
async def test_buttons_text(whatsapp_mock_server, app_server):
    """
    Should submit a message with the requested buttons, header, and footer
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            content="test body",
            helper_metadata={
                "buttons": ["button1", "button2", "button3"],
                "header": "test header",
                "footer": "test footer",
            },
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {
        "to": "27820001001",
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "test body"},
            "action": {
                "buttons": [
                    {"reply": {"id": "button1", "title": "button1"}, "type": "reply"},
                    {"reply": {"id": "button2", "title": "button2"}, "type": "reply"},
                    {"reply": {"id": "button3", "title": "button3"}, "type": "reply"},
                ]
            },
            "header": {"type": "text", "text": "test header"},
            "footer": {"text": "test footer"},
        },
    }


@pytest.mark.asyncio
async def test_buttons_image_header(whatsapp_mock_server, app_server):
    """
    Should upload the image, and then send a message with that image in the header
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    image_url = "http://example.org/image.png"
    app_server.app.ctx.consumer.media_cache[image_url] = ("test-media-id", "image/png")
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            content="test body",
            helper_metadata={
                "buttons": ["button1"],
                "header": image_url,
            },
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {
        "to": "27820001001",
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "test body"},
            "action": {
                "buttons": [
                    {"reply": {"id": "button1", "title": "button1"}, "type": "reply"},
                ]
            },
            "header": {"type": "image", "image": {"id": "test-media-id"}},
        },
    }


@pytest.mark.asyncio
async def test_buttons_video_header(whatsapp_mock_server, app_server):
    """
    Should upload the video, and then send a message with that video in the header
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    video_url = "http://example.org/video.mp4"
    app_server.app.ctx.consumer.media_cache[video_url] = ("test-media-id", "video/mp4")
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            content="test body",
            helper_metadata={
                "buttons": ["button1"],
                "header": video_url,
            },
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {
        "to": "27820001001",
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "test body"},
            "action": {
                "buttons": [
                    {"reply": {"id": "button1", "title": "button1"}, "type": "reply"},
                ]
            },
            "header": {"type": "video", "video": {"id": "test-media-id"}},
        },
    }


@pytest.mark.asyncio
async def test_buttons_document_header(whatsapp_mock_server, app_server):
    """
    Should upload the document, and then send a message with that document in the header
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    document_url = "http://example.org/document.pdf"
    app_server.app.ctx.consumer.media_cache[document_url] = (
        "test-media-id",
        "application/pdf",
    )
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            content="test body",
            helper_metadata={
                "buttons": ["button1"],
                "header": document_url,
            },
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {
        "to": "27820001001",
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "test body"},
            "action": {
                "buttons": [
                    {"reply": {"id": "button1", "title": "button1"}, "type": "reply"},
                ]
            },
            "header": {
                "type": "document",
                "document": {"id": "test-media-id", "filename": "document.pdf"},
            },
        },
    }


@pytest.mark.asyncio
async def test_list(whatsapp_mock_server, app_server):
    """
    Should submit a message with the requested list, header, and footer
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            content="test body",
            helper_metadata={
                "button": "test button",
                "sections": [
                    {
                        "title": "s1",
                        "rows": [{"id": "r1", "title": "row1", "description": "row 1"}],
                    }
                ],
                "header": "test header",
                "footer": "test footer",
            },
        ),
    )
    request = await whatsapp_mock_server.tstate.future
    assert request.json == {
        "to": "27820001001",
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": "test body"},
            "action": {
                "button": "test button",
                "sections": [
                    {
                        "title": "s1",
                        "rows": [{"id": "r1", "title": "row1", "description": "row 1"}],
                    }
                ],
            },
            "header": {"type": "text", "text": "test header"},
            "footer": {"text": "test footer"},
        },
    }


@pytest.mark.asyncio
async def test_list_limits(whatsapp_mock_server, app_server):
    """
    Should submit a message with the requested list, header, and footer
    """
    app_server.app.ctx.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    await send_outbound_message(
        app_server.app.ctx.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            content="test body " * 150,
            helper_metadata={
                "button": "test button " * 10,
                "sections": [
                    {
                        "title": "s1",
                        "rows": [
                            {
                                "id": "id " * 200,
                                "title": "title " * 6,
                                "description": "row 1",
                            },
                        ],
                    }
                ],
                "header": "test header" * 7,
                "footer": "test footer" * 7,
            },
        ),
    )
    request = await whatsapp_mock_server.tstate.future

    action = request.json["interactive"]["action"]
    assert len(action["button"]) == 20
    assert len(action["sections"][0]["rows"][0]["id"]) == 200
    assert len(action["sections"][0]["rows"][0]["title"]) == 24

    assert len(request.json["interactive"]["body"]["text"]) == 1024
    assert len(request.json["interactive"]["header"]["text"]) == 60
    assert len(request.json["interactive"]["footer"]["text"]) == 60
