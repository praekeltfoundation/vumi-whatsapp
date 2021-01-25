import sentry_sdk
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client.exposition import generate_latest
from sanic import Sanic
from sanic.request import Request
from sanic.response import HTTPResponse, json, raw
from sentry_sdk.integrations.sanic import SanicIntegration

from vxwhatsapp import config
from vxwhatsapp.metrics import setup_metrics_middleware
from vxwhatsapp.whatsapp import bp as whatsapp_blueprint

if config.SENTRY_DSN:
    sentry_sdk.init(dsn=config.SENTRY_DSN, integrations=[SanicIntegration()])

app = Sanic("vxwhatsapp")
app.update_config(config)
setup_metrics_middleware(app)


@app.route("/")
async def health(request: Request) -> HTTPResponse:
    return json({"status": "ok"})


@app.route("/metrics")
async def metrics(request: Request) -> HTTPResponse:
    return raw(generate_latest(), content_type=CONTENT_TYPE_LATEST)


app.blueprint(whatsapp_blueprint)
