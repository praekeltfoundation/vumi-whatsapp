import time

import aio_pika
import redis.asyncio as aioredis
import sentry_sdk
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client.exposition import generate_latest
from sanic import Sanic
from sanic.request import Request
from sanic.response import HTTPResponse, json, raw
from sentry_sdk.integrations.sanic import SanicIntegration

from vxwhatsapp import config
from vxwhatsapp.consumer import Consumer
from vxwhatsapp.metrics import setup_metrics_middleware
from vxwhatsapp.publisher import Publisher
from vxwhatsapp.whatsapp import bp as whatsapp_blueprint

sentry_sdk.init(
    dsn=config.SENTRY_DSN,
    integrations=[SanicIntegration()],
    traces_sample_rate=config.SENTRY_TRACES_SAMPLE_RATE,
)

app = Sanic("vxwhatsapp")
app.update_config(config)
setup_metrics_middleware(app)


@app.before_server_start
async def setup_redis(app, loop):
    if not config.REDIS_URL:
        app.ctx.redis = None
        return
    app.ctx.redis = aioredis.from_url(
        config.REDIS_URL, encoding="utf8", decode_responses=True
    )


@app.after_server_stop
async def shutdown_redis(app, loop):
    if app.ctx.redis:
        await app.ctx.redis.close()


@app.before_server_start
async def setup_amqp(app, loop):
    app.ctx.amqp_connection = await aio_pika.connect_robust(config.AMQP_URL, loop=loop)
    app.ctx.publisher = Publisher(app.ctx.amqp_connection, app.ctx.redis)
    await app.ctx.publisher.setup()
    app.ctx.consumer = Consumer(app.ctx.amqp_connection, app.ctx.redis)
    await app.ctx.consumer.setup()


@app.after_server_stop
async def shutdown_amqp(app, loop):
    await app.ctx.amqp_connection.close()
    await app.ctx.consumer.teardown()
    await app.ctx.publisher.teardown()


@app.route("/")
async def health(request: Request) -> HTTPResponse:
    result: dict = {"status": "ok", "amqp": {}}

    amqp_connection = app.ctx.amqp_connection  # type: ignore
    if amqp_connection.connection is None:  # pragma: no cover
        result["amqp"]["connection"] = False
        result["status"] = "down"
    else:
        result["amqp"]["time_since_last_heartbeat"] = (
            amqp_connection.loop.time() - amqp_connection.heartbeat_last
        )
        result["amqp"]["connection"] = True

    redis = app.ctx.redis  # type: ignore
    if redis:
        result["redis"] = {}
        try:
            start = time.monotonic()
            await redis.ping()
            result["redis"]["response_time"] = time.monotonic() - start
            result["redis"]["connection"] = True
        except ConnectionError:  # pragma: no cover
            result["status"] = "down"
            result["redis"]["connection"] = False

    return json(result, status=200 if result["status"] == "ok" else 500)


@app.route("/metrics")
async def metrics(request: Request) -> HTTPResponse:
    return raw(generate_latest(), content_type=CONTENT_TYPE_LATEST)


app.blueprint(whatsapp_blueprint)
