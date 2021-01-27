from asyncio import gather
from datetime import datetime, timezone

from sanic import Blueprint
from sanic.request import Request
from sanic.response import HTTPResponse, json

from vxwhatsapp import config
from vxwhatsapp.auth import validate_hmac
from vxwhatsapp.models import Message
from vxwhatsapp.schema import validate_schema, whatsapp_webhook_schema

bp = Blueprint("whatsapp", version=1)


@bp.route("/webhook", methods=["POST"])
@validate_hmac("X-Turn-Hook-Signature", lambda: config.HMAC_SECRET)
@validate_schema(whatsapp_webhook_schema)
async def whatsapp_webhook(request: Request) -> HTTPResponse:
    tasks = []
    for msg in request.json.get("messages", []):
        if msg["type"] == "system":
            # Ignore system messages
            continue

        timestamp = datetime.fromtimestamp(float(msg.pop("timestamp")), tz=timezone.utc)

        content = None
        if msg["type"] == "text":
            content = msg.pop("text")["body"]
        elif msg["type"] == "location":
            content = msg["location"].pop("name", None)
        elif msg["type"] == "button":
            content = msg["button"].pop("text")
        else:
            content = msg[msg["type"]].pop("caption", None)

        message = Message(
            to_addr=config.WHATSAPP_NUMBER,
            from_addr=msg.pop("from"),
            content=content,
            in_reply_to=msg.get("context", {}).pop("id", None),
            transport_name=config.TRANSPORT_NAME,
            transport_type=Message.TRANSPORT_TYPE.WHATSAPP,
            timestamp=timestamp,
            message_id=msg.pop("id"),
            to_addr_type=Message.ADDRESS_TYPE.MSISDN,
            from_addr_type=Message.ADDRESS_TYPE.MSISDN,
            transport_metadata={
                "contacts": request.json.get("contacts"),
                "message": msg,
            },
        )
        tasks.append(request.app.publisher.publish_message(message))

    # TODO: Handle events

    await gather(*tasks)
    return json({})
