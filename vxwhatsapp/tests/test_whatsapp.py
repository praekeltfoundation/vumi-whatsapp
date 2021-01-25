import pytest
import hmac
import json
from base64 import b64encode
from hashlib import sha256

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
    data = json.dumps({"test": "data"})
    response = await test_client.post(
        app.url_for("whatsapp.whatsapp_webhook"),
        headers={"X-Turn-Hook-Signature": generate_hmac_signature(data, "testsecret")},
        data=data,
    )
    assert response.status == 200
