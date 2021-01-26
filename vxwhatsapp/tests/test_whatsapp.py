import hmac
import json
from base64 import b64encode
from hashlib import sha256

import pytest

from vxwhatsapp.main import app
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
    data = json.dumps(
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


async def test_valid_body(test_client):
    config.HMAC_SECRET = "testsecret"
    data = json.dumps(
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
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status == 200
    assert (await response.json()) == {}
