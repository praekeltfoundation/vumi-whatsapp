from asyncio import gather
from datetime import datetime, timezone

from sanic import Blueprint
from sanic.request import Request
from sanic.response import HTTPResponse, json

from vxwhatsapp import config
from vxwhatsapp.auth import validate_hmac
from vxwhatsapp.models import Event, Message
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
            transport_type=Message.TRANSPORT_TYPE.HTTP_API,
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

    for ev in request.json.get("statuses", []):
        message_id = ev.pop("id")
        status = ev["status"]
        event_type, delivery_status = {
            "read": (
                Event.EVENT_TYPE.DELIVERY_REPORT,
                Event.DELIVERY_STATUS.DELIVERED,
            ),
            "delivered": (
                Event.EVENT_TYPE.DELIVERY_REPORT,
                Event.DELIVERY_STATUS.DELIVERED,
            ),
            "ack": (Event.EVENT_TYPE.ACK, None),
            "failed": (
                Event.EVENT_TYPE.DELIVERY_REPORT,
                Event.DELIVERY_STATUS.FAILED,
            ),
            "deleted": (
                Event.EVENT_TYPE.DELIVERY_REPORT,
                Event.DELIVERY_STATUS.DELIVERED,
            ),
        }[status]
        timestamp = datetime.fromtimestamp(float(ev.pop("timestamp")), tz=timezone.utc)
        event = Event(
            user_message_id=message_id,
            event_type=event_type,
            timestamp=timestamp,
            sent_message_id=message_id,
            delivery_status=delivery_status,
            helper_metadata=ev,
        )
        tasks.append(request.app.publisher.publish_event(event))

    await gather(*tasks)
    return json({})
