import hmac
from base64 import b64encode
from datetime import datetime, timezone
from hashlib import sha256

import pytest
import pytest_asyncio
import ujson
from aio_pika import Connection, Queue
from aio_pika.exceptions import QueueEmpty

from vxwhatsapp.main import app
from vxwhatsapp.models import Event, Message
from vxwhatsapp.tests.utils import cleanup_amqp, cleanup_redis, run_sanic
from vxwhatsapp.whatsapp import config


@pytest_asyncio.fixture
async def app_server():
    config.REDIS_URL = config.REDIS_URL or "redis://"
    config.HMAC_SECRET = "testsecret"
    async with run_sanic(app) as server:
        yield server
    await cleanup_amqp()
    await cleanup_redis()


def generate_hmac_signature(body: str, secret: str) -> str:
    h = hmac.new(secret.encode(), body.encode(), sha256)
    return b64encode(h.digest()).decode()


@pytest.mark.asyncio
async def test_missing_signature(app_server):
    response = await app_server.post(app.url_for("whatsapp.whatsapp_webhook"))
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_signature(app_server):
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": "incorrect"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_no_secret_config(app_server):
    """
    If no secret is configured, then skip auth check
    """
    config.HMAC_SECRET = None
    response = await app_server.post(app.url_for("whatsapp.whatsapp_webhook"))
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_valid_signature(app_server):
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc121",
                    "timestamp": "123456789",
                    "type": "text",
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status_code == 400
    assert response.json() == {"messages": {"0": ["'text' is a required property"]}}


async def setup_amqp_queue(connection: Connection, queuename="whatsapp.inbound"):
    channel = await connection.channel()
    queue = await channel.declare_queue(queuename, durable=True)
    await queue.bind("vumi", queuename)
    return queue


async def get_amqp_message(queue: Queue):
    message = await queue.get(timeout=1)
    assert message is not None
    await message.ack()
    return message


@pytest.mark.asyncio
async def test_valid_text_message(app_server):
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc122",
                    "timestamp": "123456789",
                    "type": "text",
                    "text": {"body": "test message"},
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={
            "X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret"),
            "X-Turn-Claim": "test-claim",
        },
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.from_addr == "27820001001"
    assert message.content == "test message"
    assert message.message_id == "abc122"
    assert message.timestamp == datetime(1973, 11, 29, 21, 33, 9, tzinfo=timezone.utc)
    assert message.transport_metadata == {
        "contacts": None,
        "message": {"type": "text"},
        "claim": "test-claim",
    }


@pytest.mark.asyncio
async def test_valid_unknown_message(app_server):
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc120",
                    "timestamp": "123456789",
                    "type": "unknown",
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={
            "X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret"),
        },
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.from_addr == "27820001001"
    assert message.content is None
    assert message.message_id == "abc120"
    assert message.timestamp == datetime(1973, 11, 29, 21, 33, 9, tzinfo=timezone.utc)
    assert message.transport_metadata["message"] == {"type": "unknown"}


@pytest.mark.asyncio
async def test_valid_contacts_message(app_server):
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    contact = {
        "addresses": [],
        "emails": [],
        "ims": [],
        "name": {"first_name": "test"},
        "org": {},
        "phones": [{"phone": "+27820001003", "type": "Mobile"}],
        "urls": [],
    }
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc131",
                    "timestamp": "123456789",
                    "type": "contacts",
                    "contacts": [contact],
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={
            "X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret"),
        },
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.from_addr == "27820001001"
    assert message.content is None
    assert message.message_id == "abc131"
    assert message.timestamp == datetime(1973, 11, 29, 21, 33, 9, tzinfo=timezone.utc)
    assert message.transport_metadata["message"] == {
        "type": "contacts",
        "contacts": [contact],
    }


@pytest.mark.asyncio
async def test_text_message_conversation_claim_redis(app_server):
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc124",
                    "timestamp": "123456789",
                    "type": "text",
                    "text": {"body": "test message"},
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={
            "X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret"),
            "X-Turn-Claim": "test-claim",
        },
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    await get_amqp_message(queue)
    [address] = await app_server.app.ctx.redis.zrange("claims", 0, -1)
    assert address == "27820001001"
    await app_server.app.ctx.redis.delete("claims")


@pytest.mark.asyncio
async def test_ignore_system_messages(app_server):
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc125",
                    "timestamp": "123456789",
                    "type": "system",
                    "system": {"body": "test message"},
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    exception = None
    try:
        await get_amqp_message(queue)
    except QueueEmpty as e:
        exception = e
    assert exception is not None


@pytest.mark.asyncio
async def test_valid_location_message(app_server):
    """
    Should put the name of the location as the message content
    """
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc126",
                    "timestamp": "123456789",
                    "type": "location",
                    "location": {"name": "test location"},
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.content == "test location"


@pytest.mark.asyncio
async def test_valid_button_message(app_server):
    """
    Should put the button response as the message content
    """
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc127",
                    "timestamp": "123456789",
                    "type": "button",
                    "button": {"text": "test response"},
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.content == "test response"


@pytest.mark.asyncio
async def test_valid_media_message(app_server):
    """
    Should put the media caption as the message content
    """
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc128",
                    "timestamp": "123456789",
                    "type": "image",
                    "image": {
                        "id": "abc123",
                        "caption": "test caption",
                        "mime_type": "image/png",
                        "sha256": "hash",
                    },
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.content == "test caption"


@pytest.mark.asyncio
async def test_valid_media_message_null_caption(app_server):
    """
    Should have null message content
    """
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc128",
                    "timestamp": "123456789",
                    "type": "image",
                    "image": {
                        "id": "abc123",
                        "caption": None,
                        "mime_type": "image/png",
                        "sha256": "hash",
                    },
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.content is None


@pytest.mark.asyncio
async def test_valid_event(app_server):
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection, "whatsapp.event")
    data = ujson.dumps(
        {
            "statuses": [
                {
                    "id": "abc129",
                    "recipient_id": "27820001001",
                    "status": "read",
                    "timestamp": "123456789",
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    message = await get_amqp_message(queue)
    event = Event.from_json(message.body.decode("utf-8"))
    assert event.user_message_id == "abc129"
    assert event.sent_message_id == "abc129"
    assert event.event_type == Event.EVENT_TYPE.DELIVERY_REPORT
    assert event.delivery_status == Event.DELIVERY_STATUS.DELIVERED
    assert event.timestamp == datetime(1973, 11, 29, 21, 33, 9, tzinfo=timezone.utc)
    assert event.helper_metadata == {"recipient_id": "27820001001", "status": "read"}


@pytest.mark.asyncio
async def test_duplicate_message(app_server):
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc130",
                    "timestamp": "123456789",
                    "type": "text",
                    "text": {"body": "test message"},
                }
            ]
        }
    )
    headers = {
        "X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret"),
        "X-Turn-Claim": "test-claim",
    }
    url = app.url_for("whatsapp.whatsapp_webhook")

    await app_server.post(url, headers=headers, data=data)
    await get_amqp_message(queue)

    await app_server.post(url, headers=headers, data=data)
    err = None
    try:
        await get_amqp_message(queue)
    except QueueEmpty as e:
        err = e
    assert err is not None


@pytest.mark.asyncio
async def test_duplicate_message_no_redis(app_server):
    """
    If there's no redis configured, then we allow duplicate messages
    """
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    app_server.app.ctx.redis = None
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc130",
                    "timestamp": "123456789",
                    "type": "text",
                    "text": {"body": "test message"},
                }
            ]
        }
    )
    headers = {
        "X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret"),
        "X-Turn-Claim": "test-claim",
    }
    url = app.url_for("whatsapp.whatsapp_webhook")
    await app_server.post(url, headers=headers, data=data)
    await get_amqp_message(queue)

    await app_server.post(url, headers=headers, data=data)
    await get_amqp_message(queue)


@pytest.mark.asyncio
async def test_valid_interactive_list_reply_message(app_server):
    """
    Should put the list item as the message content
    """
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc132",
                    "timestamp": "123456789",
                    "type": "interactive",
                    "interactive": {
                        "type": "list_reply",
                        "list_reply": {"title": "test response"},
                    },
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.content == "test response"


@pytest.mark.asyncio
async def test_valid_interactive_button_reply_message(app_server):
    """
    Should put the button text as the message content
    """
    queue = await setup_amqp_queue(app_server.app.ctx.amqp_connection)
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc133",
                    "timestamp": "123456789",
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": {"title": "test response"},
                    },
                }
            ]
        }
    )
    response = await app_server.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status_code == 200
    assert response.json() == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.content == "test response"
