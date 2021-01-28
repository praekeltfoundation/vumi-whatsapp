from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

import ujson

VUMI_DATE_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
_VUMI_DATE_FORMAT_NO_MICROSECONDS = "%Y-%m-%d %H:%M:%S"


def generate_id():
    return uuid4().hex


def generate_timestamp():
    return datetime.now(tz=timezone.utc)


def format_timestamp(timestamp):
    return timestamp.strftime(VUMI_DATE_FORMAT)


def date_time_decoder(json_object):
    for key, value in json_object.items():
        try:
            date_format = VUMI_DATE_FORMAT
            if "." not in value[-10:]:
                date_format = _VUMI_DATE_FORMAT_NO_MICROSECONDS
            timestamp = datetime.strptime(value, date_format)
            timestamp = timestamp.replace(tzinfo=timezone.utc)
            json_object[key] = timestamp
        except (ValueError, TypeError):
            continue
    return json_object


@dataclass
class Message:
    class SESSION_EVENT(Enum):
        NONE = None
        NEW = "new"
        RESUME = "resume"
        CLOSE = "close"

    class TRANSPORT_TYPE(Enum):
        HTTP_API = "http_api"

    class ADDRESS_TYPE(Enum):
        MSISDN = "msisdn"

    to_addr: str
    from_addr: str
    transport_name: str
    transport_type: TRANSPORT_TYPE
    message_version: str = "20110921"
    message_type: str = "user_message"
    timestamp: datetime = field(default_factory=generate_timestamp)
    routing_metadata: dict = field(default_factory=dict)
    helper_metadata: dict = field(default_factory=dict)
    message_id: str = field(default_factory=generate_id)
    in_reply_to: Optional[str] = None
    provider: Optional[str] = None
    session_event: SESSION_EVENT = SESSION_EVENT.NONE
    content: Optional[str] = None
    transport_metadata: dict = field(default_factory=dict)
    group: Optional[str] = None
    to_addr_type: Optional[ADDRESS_TYPE] = None
    from_addr_type: Optional[ADDRESS_TYPE] = None

    def to_json(self):
        """
        Converts the message to JSON representation for serialisation over the message
        broker
        """
        data = asdict(self)
        data["timestamp"] = format_timestamp(data["timestamp"])
        data["transport_type"] = data["transport_type"].value
        data["session_event"] = data["session_event"].value
        if data.get("to_addr_type"):
            data["to_addr_type"] = data["to_addr_type"].value
        if data.get("from_addr_type"):
            data["from_addr_type"] = data["from_addr_type"].value
        return ujson.dumps(data)

    @classmethod
    def from_json(cls, json_string):
        """
        Takes a serialised message from the message broker, and converts into a message
        object
        """
        data = ujson.loads(json_string)
        data = date_time_decoder(data)
        data["transport_type"] = cls.TRANSPORT_TYPE(data["transport_type"])
        data["session_event"] = cls.SESSION_EVENT(data["session_event"])
        if data.get("to_addr_type"):
            data["to_addr_type"] = cls.ADDRESS_TYPE(data["to_addr_type"])
        if data.get("from_addr_type"):
            data["from_addr_type"] = cls.ADDRESS_TYPE(data["from_addr_type"])
        return cls(**data)


@dataclass
class Event:
    class DELIVERY_STATUS(Enum):
        PENDING = "pending"
        FAILED = "failed"
        DELIVERED = "delivered"

    class EVENT_TYPE(Enum):
        ACK = "ack"
        NACK = "nack"
        DELIVERY_REPORT = "delivery_report"

    user_message_id: str
    event_type: EVENT_TYPE
    event_id: str = field(default_factory=generate_id)
    message_type: str = "event"
    message_version: str = "20110921"
    timestamp: datetime = field(default_factory=generate_timestamp)
    routing_metadata: dict = field(default_factory=dict)
    helper_metadata: dict = field(default_factory=dict)
    sent_message_id: Optional[str] = None
    nack_reason: Optional[str] = None
    delivery_status: Optional[DELIVERY_STATUS] = None

    def __post_init__(self):
        if self.event_type == self.EVENT_TYPE.ACK:
            assert self.sent_message_id is not None
        elif self.event_type == self.EVENT_TYPE.NACK:
            assert self.nack_reason is not None
        elif self.event_type == self.EVENT_TYPE.DELIVERY_REPORT:
            assert self.delivery_status is not None

    def to_json(self):
        """
        Converts the event to JSON representation for serialisation over the message
        broker
        """
        data = asdict(self)
        data["timestamp"] = format_timestamp(data["timestamp"])
        data["event_type"] = data["event_type"].value
        if data.get("delivery_status"):
            data["delivery_status"] = data["delivery_status"].value
        return ujson.dumps(data)

    @classmethod
    def from_json(cls, json_string):
        """
        Takes a serialised event from the message broker, and converts into an event
        object
        """
        data = ujson.loads(json_string)
        data = date_time_decoder(data)
        data["event_type"] = cls.EVENT_TYPE(data["event_type"])
        if data.get("delivery_status"):
            data["delivery_status"] = cls.DELIVERY_STATUS(data["delivery_status"])
        return cls(**data)
