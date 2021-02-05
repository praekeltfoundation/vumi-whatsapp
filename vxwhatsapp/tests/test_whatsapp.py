import hmac
from base64 import b64encode
from datetime import datetime, timezone
from hashlib import sha256

import pytest
import ujson
from aio_pika import Connection, Queue
from aio_pika.exceptions import QueueEmpty

from vxwhatsapp.main import app
from vxwhatsapp.models import Event, Message
from vxwhatsapp.whatsapp import config


@pytest.fixture
def test_client(loop, sanic_client):
    return loop.run_until_complete(sanic_client(app))


def generate_hmac_signature(body: str, secret: str) -> str:
    h = hmac.new(secret.encode(), body.encode(), sha256)
    return b64encode(h.digest()).decode()


async def test_missing_signature(test_client):
    config.HMAC_SECRET = "testsecret"
    response = await test_client.post(app.url_for("whatsapp.whatsapp_webhook"))
    assert response.status == 401


async def test_invalid_signature(test_client):
    config.HMAC_SECRET = "testsecret"
    response = await test_client.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": "incorrect"},
    )
    assert response.status == 403


async def test_valid_signature(test_client):
    config.HMAC_SECRET = "testsecret"
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc123",
                    "timestamp": "123456789",
                    "type": "text",
                }
            ]
        }
    )
    response = await test_client.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status == 400
    assert (await response.json()) == {
        "messages": {"0": ["'text' is a required property"]}
    }


async def setup_amqp_queue(connection: Connection, queuename="whatsapp.inbound"):
    channel = await connection.channel()
    queue = await channel.declare_queue(queuename, auto_delete=True)
    await queue.bind("vumi", queuename)
    return queue


async def get_amqp_message(queue: Queue):
    message = await queue.get(timeout=1)
    assert message is not None
    await message.ack()
    return message


async def test_valid_text_message(test_client):
    queue = await setup_amqp_queue(test_client.app.amqp_connection)
    config.HMAC_SECRET = "testsecret"
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc123",
                    "timestamp": "123456789",
                    "type": "text",
                    "text": {"body": "test message"},
                }
            ]
        }
    )
    response = await test_client.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={
            "X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret"),
            "X-Turn-Claim": "test-claim",
        },
        data=data,
    )
    assert response.status == 200
    assert (await response.json()) == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.from_addr == "27820001001"
    assert message.content == "test message"
    assert message.message_id == "abc123"
    assert message.timestamp == datetime(1973, 11, 29, 21, 33, 9, tzinfo=timezone.utc)
    assert message.transport_metadata == {
        "contacts": None,
        "message": {"type": "text"},
        "claim": "test-claim",
    }


async def test_ignore_system_messages(test_client):
    queue = await setup_amqp_queue(test_client.app.amqp_connection)
    config.HMAC_SECRET = "testsecret"
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc123",
                    "timestamp": "123456789",
                    "type": "system",
                    "system": {"body": "test message"},
                }
            ]
        }
    )
    response = await test_client.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status == 200
    assert (await response.json()) == {}

    exception = None
    try:
        await get_amqp_message(queue)
    except QueueEmpty as e:
        exception = e
    assert exception is not None


async def test_valid_location_message(test_client):
    """
    Should put the name of the location as the message content
    """
    queue = await setup_amqp_queue(test_client.app.amqp_connection)
    config.HMAC_SECRET = "testsecret"
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc123",
                    "timestamp": "123456789",
                    "type": "location",
                    "location": {"name": "test location"},
                }
            ]
        }
    )
    response = await test_client.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status == 200
    assert (await response.json()) == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.content == "test location"


async def test_valid_button_message(test_client):
    """
    Should put the button response as the message content
    """
    queue = await setup_amqp_queue(test_client.app.amqp_connection)
    config.HMAC_SECRET = "testsecret"
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc123",
                    "timestamp": "123456789",
                    "type": "button",
                    "button": {"text": "test response"},
                }
            ]
        }
    )
    response = await test_client.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status == 200
    assert (await response.json()) == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.content == "test response"


async def test_valid_media_message(test_client):
    """
    Should put the media caption as the message content
    """
    queue = await setup_amqp_queue(test_client.app.amqp_connection)
    config.HMAC_SECRET = "testsecret"
    data = ujson.dumps(
        {
            "messages": [
                {
                    "from": "27820001001",
                    "id": "abc123",
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
    response = await test_client.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status == 200
    assert (await response.json()) == {}

    message = await get_amqp_message(queue)
    message = Message.from_json(message.body.decode("utf-8"))
    assert message.content == "test caption"


async def test_valid_event(test_client):
    queue = await setup_amqp_queue(test_client.app.amqp_connection, "whatsapp.event")
    config.HMAC_SECRET = "testsecret"
    data = ujson.dumps(
        {
            "statuses": [
                {
                    "id": "abc123",
                    "recipient_id": "27820001001",
                    "status": "read",
                    "timestamp": "123456789",
                }
            ]
        }
    )
    response = await test_client.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status == 200
    assert (await response.json()) == {}

    message = await get_amqp_message(queue)
    event = Event.from_json(message.body.decode("utf-8"))
    assert event.user_message_id == "abc123"
    assert event.sent_message_id == "abc123"
    assert event.event_type == Event.EVENT_TYPE.DELIVERY_REPORT
    assert event.delivery_status == Event.DELIVERY_STATUS.DELIVERED
    assert event.timestamp == datetime(1973, 11, 29, 21, 33, 9, tzinfo=timezone.utc)
    assert event.helper_metadata == {"recipient_id": "27820001001", "status": "read"}
