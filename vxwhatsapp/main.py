import os

import sentry_sdk
from sanic import Sanic
from sanic.request import Request
from sanic.response import HTTPResponse, json
from sanic_prometheus import monitor
from sentry_sdk.integrations.sanic import SanicIntegration

SENTRY_DSN = os.environ.get("SENTRY_DSN", None)
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, integrations=[SanicIntegration()])

app = Sanic("vxwhatsapp")
monitor(app).expose_endpoint()


@app.route("/")
async def health(request: Request) -> HTTPResponse:
    return json({"status": "ok"})
