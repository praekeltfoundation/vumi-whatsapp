import logging
import time
from asyncio import Future
from io import StringIO

import pytest
from aio_pika import Connection, DeliveryMode, ExchangeType
from aio_pika import Message as AMQPMessage
from sanic import Sanic
from sanic.log import logger
from sanic.response import json, text

from vxwhatsapp import config
from vxwhatsapp.main import app
from vxwhatsapp.models import Message


@pytest.fixture
def test_client(loop, sanic_client):
    config.REDIS_URL = config.REDIS_URL or "redis://"
    return loop.run_until_complete(sanic_client(app))


@pytest.fixture
def whatsapp_mock_server(loop, sanic_client):
    Sanic.test_mode = True
    app = Sanic("mock_whatsapp")
    app.future = Future()
    app.contact_future = Future()
    app.message_status_code = 200

    @app.route("/v1/messages", methods=["POST"])
    async def messages(request):
        app.future.set_result(request)
        return json({}, status=app.message_status_code)

    @app.route("/v1/messages/<message_id>/automation", methods=["POST"])
    async def message_automation(request, message_id):
        app.future.set_result(request)
        return json({})

    @app.route("/v1/media", methods=["POST"])
    async def media_upload(request):
        return json({"media": [{"id": "test-media-id"}]})

    @app.route("/v1/contacts", methods=["POST"])
    async def contact_check(request):
        app.contact_future.set_result(request)
        msisdn = request.json["contacts"][0]
        if msisdn == "+27820001111":
            status = "invalid"
        else:
            status = "valid"
            app.message_status_code = 200
        return json(
            {
                "contacts": [
                    {"wa_id": msisdn.lstrip("+"), "input": msisdn, "status": status}
                ]
            }
        )

    return loop.run_until_complete(sanic_client(app))


@pytest.fixture
def media_mock_server(loop, sanic_client):
    Sanic.test_mode = True
    app = Sanic("mock_media")

    @app.route("test_document.pdf", methods=["GET"])
    async def test_document(request):
        return text("test_document")

    return loop.run_until_complete(sanic_client(app))


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


async def test_outbound_text_message(whatsapp_mock_server, test_client):
    """
    Should make a request to the whatsapp API, extending the conversation claim
    """
    test_client.app.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/messages"
    )
    await send_outbound_message(
        test_client.app.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            transport_metadata={"claim": "test-claim"},
            content="test message",
        ),
    )
    request = await whatsapp_mock_server.app.future
    assert request.json == {"text": {"body": "test message"}, "to": "27820001001"}
    assert request.headers["X-Turn-Claim-Extend"] == "test-claim"

    [addr] = await test_client.app.redis.zrange("claims")
    assert addr == "27820001001"
    await test_client.app.redis.delete("claims")


async def test_outbound_text_end_session(whatsapp_mock_server, test_client):
    """
    Should make a request to the whatsapp API, releasing the conversation claim, and
    removing it from the set of open conversations
    """
    redis = test_client.app.redis
    test_client.app.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/messages"
    )
    await redis.zadd("claims", int(time.time()), "27820001001")
    await send_outbound_message(
        test_client.app.amqp_connection,
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
    request = await whatsapp_mock_server.app.future
    assert request.json == {"text": {"body": "test message"}, "to": "27820001001"}
    assert request.headers["X-Turn-Claim-Release"] == "test-claim"

    assert await redis.zcount("claims") == 0
    await redis.delete("claims")


async def test_outbound_text_automation_handle(whatsapp_mock_server, test_client):
    """
    Should make a request to the turn automation API to reevaluate
    """
    test_client.app.consumer.message_automation_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/{}/automation"
    )
    await send_outbound_message(
        test_client.app.amqp_connection,
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
    request = await whatsapp_mock_server.app.future
    assert request.json == {"text": {"body": "test message"}, "to": "27820001001"}
    assert request.headers["X-Turn-Claim-Release"] == "test-claim"
    assert request.headers["Accept"] == "application/vnd.v1+json"
    assert "/v1/messages/message-id/automation" in request.url


async def test_invalid_outbound_text_message(test_client):
    """
    If the AMQP message is invalid, then drop it
    """
    log_stream = StringIO()
    logger.addHandler(logging.StreamHandler(log_stream))
    await send_outbound_amqp_message(test_client.app.amqp_connection, b"invalid")
    assert "Invalid message body b'invalid'" in log_stream.getvalue()
    assert "ValueError" in log_stream.getvalue()


async def test_outbound_document(whatsapp_mock_server, media_mock_server, test_client):
    """
    Should upload the document, and then send the message with the media ID
    """
    test_client.app.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    test_client.app.consumer.media_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/media"
    )
    document_url = (
        f"http://{media_mock_server.host}:{media_mock_server.port}/test_document.pdf"
    )
    await send_outbound_message(
        test_client.app.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            helper_metadata={"document": document_url},
        ),
    )
    request = await whatsapp_mock_server.app.future
    assert request.json == {
        "type": "document",
        "document": {"id": "test-media-id", "filename": "test_document.pdf"},
        "to": "27820001001",
    }


async def test_outbound_document_cached(whatsapp_mock_server, test_client):
    """
    Should get the media URL from cache
    """
    test_client.app.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}"
        "/v1/messages/"
    )
    doc_url = "http://example/org/cached+%26.pdf"
    test_client.app.consumer.media_cache[doc_url] = "test-media-id"
    await send_outbound_message(
        test_client.app.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            helper_metadata={"document": doc_url},
        ),
    )
    request = await whatsapp_mock_server.app.future
    assert request.json == {
        "type": "document",
        "document": {"id": "test-media-id", "filename": "cached &.pdf"},
        "to": "27820001001",
    }


async def test_outbound_missing_contact(whatsapp_mock_server, test_client):
    """
    Makes a contact check, and then tries again
    """
    test_client.app.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/messages"
    )
    test_client.app.consumer.contact_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/contacts"
    )
    whatsapp_mock_server.app.message_status_code = 404
    await send_outbound_message(
        test_client.app.amqp_connection,
        Message(
            to_addr="27820001001",
            from_addr="27820001002",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            content="test message",
        ),
    )
    msg1 = await whatsapp_mock_server.app.future
    whatsapp_mock_server.app.future = Future()
    contact = await whatsapp_mock_server.app.contact_future
    msg2 = await whatsapp_mock_server.app.future

    assert msg1.url == test_client.app.consumer.message_url
    assert msg1.json == {"text": {"body": "test message"}, "to": "27820001001"}

    assert contact.url == test_client.app.consumer.contact_url
    assert contact.json == {"blocking": "wait", "contacts": ["+27820001001"]}

    assert msg2.url == test_client.app.consumer.message_url
    assert msg2.json == {"text": {"body": "test message"}, "to": "27820001001"}


async def test_outbound_missing_contact_permanent(whatsapp_mock_server, test_client):
    """
    Makes a contact check, and if the contact isn't valid, drop the message
    """
    test_client.app.consumer.message_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/messages"
    )
    test_client.app.consumer.contact_url = (
        f"http://{whatsapp_mock_server.host}:{whatsapp_mock_server.port}/v1/contacts"
    )
    whatsapp_mock_server.app.message_status_code = 404
    await send_outbound_message(
        test_client.app.amqp_connection,
        Message(
            to_addr="27820001111",
            from_addr="27820001000",
            transport_name="whatsapp",
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
            content="test message",
        ),
    )
    msg1 = await whatsapp_mock_server.app.future
    contact = await whatsapp_mock_server.app.contact_future

    assert msg1.json == {"text": {"body": "test message"}, "to": "27820001111"}

    assert contact.json == {"blocking": "wait", "contacts": ["+27820001111"]}
