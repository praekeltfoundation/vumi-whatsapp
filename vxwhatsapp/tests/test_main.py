import pytest
import pytest_asyncio

from vxwhatsapp import config
from vxwhatsapp.main import app
from vxwhatsapp.tests.utils import cleanup_amqp, cleanup_redis, run_sanic


@pytest_asyncio.fixture
async def app_server():
    config.REDIS_URL = config.REDIS_URL or "redis://"
    async with run_sanic(app) as server:
        yield server
    await cleanup_amqp()
    await cleanup_redis()


@pytest_asyncio.fixture
async def app_server_no_redis():
    redis = config.REDIS_URL
    config.REDIS_URL = None
    async with run_sanic(app) as server:
        yield server
    await cleanup_amqp()
    config.REDIS_URL = redis


@pytest.mark.asyncio
async def test_health(app_server):
    response = await app_server.get(app.url_for("health"))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["amqp"].pop("time_since_last_heartbeat"), float)
    assert isinstance(data["redis"].pop("response_time"), float)
    assert data == {
        "status": "ok",
        "amqp": {"connection": True},
        "redis": {"connection": True},
    }


@pytest.mark.asyncio
async def test_health_no_redis(app_server_no_redis):
    response = await app_server_no_redis.get(app.url_for("health"))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["amqp"].pop("time_since_last_heartbeat"), float)
    assert data == {
        "status": "ok",
        "amqp": {"connection": True},
    }


@pytest.mark.asyncio
async def test_metrics(app_server):
    response = await app_server.get(app.url_for("metrics"))
    assert response.status_code == 200
    assert "sanic_request_latency_sec" in response.text
