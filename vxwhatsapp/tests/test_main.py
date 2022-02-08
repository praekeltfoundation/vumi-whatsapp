import pytest

from vxwhatsapp import config
from vxwhatsapp.main import app
from vxwhatsapp.tests.utils import cleanup_amqp, cleanup_redis


@pytest.fixture(autouse=True)
async def cleanup():
    """
    Ensure that we always cleanup redis and amqp
    """
    await cleanup_amqp()
    await cleanup_redis()


@pytest.fixture
async def test_client(sanic_client):
    return await sanic_client(app)


@pytest.fixture
async def test_client_no_redis(sanic_client):
    redis = config.REDIS_URL
    config.REDIS_URL = None
    yield (await sanic_client(app))
    config.REDIS_URL = redis


async def test_health(test_client):
    response = await test_client.get(app.url_for("health"))
    assert response.status == 200
    data = await response.json()
    assert isinstance(data["amqp"].pop("time_since_last_heartbeat"), float)
    assert isinstance(data["redis"].pop("response_time"), float)
    assert data == {
        "status": "ok",
        "amqp": {"connection": True},
        "redis": {"connection": True},
    }


async def test_health_no_redis(test_client_no_redis):
    response = await test_client_no_redis.get(app.url_for("health"))
    assert response.status == 200
    data = await response.json()
    assert isinstance(data["amqp"].pop("time_since_last_heartbeat"), float)
    assert data == {
        "status": "ok",
        "amqp": {"connection": True},
    }


async def test_metrics(test_client):
    response = await test_client.get(app.url_for("metrics"))
    assert response.status == 200
    body = await response.text()
    assert "sanic_request_latency_sec" in body
