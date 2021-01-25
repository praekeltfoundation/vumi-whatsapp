from sanic import Blueprint
from sanic.response import json

from vxwhatsapp import config
from vxwhatsapp.auth import validate_hmac

bp = Blueprint("whatsapp", version=1)


@bp.route("/webhook", methods=["POST"])
@validate_hmac("X-Turn-Hook-Signature", lambda: config.HMAC_SECRET)
def whatsapp_webhook(request):
    return json({})
