from sanic import Blueprint
from sanic.response import json

from vxwhatsapp import config
from vxwhatsapp.auth import validate_hmac
from vxwhatsapp.schema import validate_schema, whatsapp_webhook_schema

bp = Blueprint("whatsapp", version=1)


@bp.route("/webhook", methods=["POST"])
@validate_hmac("X-Turn-Hook-Signature", lambda: config.HMAC_SECRET)
@validate_schema(whatsapp_webhook_schema)
def whatsapp_webhook(request):
    # TODO: publish messages to message broker
    return json({})
