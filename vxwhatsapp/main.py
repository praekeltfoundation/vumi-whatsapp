import aio_pika
import aioredis
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

if config.SENTRY_DSN:
    sentry_sdk.init(dsn=config.SENTRY_DSN, integrations=[SanicIntegration()])

app = Sanic("vxwhatsapp")
app.update_config(config)
setup_metrics_middleware(app)


@app.listener("before_server_start")
async def setup_amqp(app, loop):
    app.amqp_connection = await aio_pika.connect_robust(config.AMQP_URL, loop=loop)
    app.publisher = Publisher(app.amqp_connection)
    await app.publisher.setup()
    app.consumer = Consumer(app.amqp_connection)
    await app.consumer.setup()


@app.listener("after_server_stop")
async def shutdown_amqp(app, loop):
    await app.amqp_connection.close()
    await app.consumer.teardown()


@app.listener("before_server_start")
async def setup_redis(app, loop):
    if not config.REDIS_URL:
        app.redis = None
        return
    app.redis = await aioredis.create_redis_pool(config.REDIS_URL, encoding="utf8")


@app.listener("after_server_stop")
async def shutdown_redis(app, loop):
    if app.redis:
        app.redis.close()
        await app.redis.wait_closed()


@app.route("/")
async def health(request: Request) -> HTTPResponse:
    return json({"status": "ok"})


@app.route("/metrics")
async def metrics(request: Request) -> HTTPResponse:
    return raw(generate_latest(), content_type=CONTENT_TYPE_LATEST)


app.blueprint(whatsapp_blueprint)
