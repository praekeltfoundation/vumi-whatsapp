from functools import wraps

from jsonschema.validators import validator_for
from sanic.request import Request
from sanic.response import json

whatsapp_webhook_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "definitions": {
        "media": {
            "type": "object",
            "properties": {
                "caption": {"type": ["string", "null"]},
                "id": {"type": "string"},
                "metadata": {"type": "object"},
                "mime_type": {"type": "string"},
                "sha256": {"type": "string"},
            },
            "required": ["id", "mime_type", "sha256"],
        },
        "message": {
            "type": "object",
            "properties": {
                "context": {"type": "object"},
                "from": {"type": "string"},
                "id": {"type": "string"},
                "identity": {
                    "type": "object",
                    "properties": {
                        "acknowledged": {"type": "boolean"},
                        "created_timestamp": {"type": "integer"},
                        "hash": {"type": "string"},
                    },
                    "required": ["acknowledged", "created_timestamp", "hash"],
                },
                "timestamp": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": [
                        "audio",
                        "button",
                        "contacts",
                        "document",
                        "image",
                        "interactive",
                        "location",
                        "sticker",
                        "system",
                        "text",
                        "unknown",
                        "video",
                        "voice",
                    ],
                },
                "text": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                },
                "location": {
                    "type": "object",
                    "properties": {
                        "latitude": {"type": "number"},
                        "longitude": {"type": "number"},
                        "address": {"type": "string"},
                        "name": {"type": "string"},
                        "url": {"type": "string"},
                    },
                },
                "button": {
                    "type": "object",
                    "properties": {
                        "payload": {"type": ["string", "null"]},
                        "text": {"type": "string"},
                    },
                },
                "image": {
                    "$ref": "#/definitions/media",
                },
                "interactive": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["list_reply", "button_reply"],
                        },
                        "list_reply": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                        "button_reply": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                            },
                        },
                    },
                    "allOf": [
                        {
                            "if": {"properties": {"type": {"const": "list_reply"}}},
                            "then": {"required": ["list_reply"]},
                        },
                        {
                            "if": {"properties": {"type": {"const": "button_reply"}}},
                            "then": {"required": ["button_reply"]},
                        },
                    ],
                },
                "document": {
                    "$ref": "#/definitions/media",
                },
                "audio": {
                    "$ref": "#/definitions/media",
                },
                "video": {
                    "$ref": "#/definitions/media",
                },
                "voice": {
                    "$ref": "#/definitions/media",
                },
                "sticker": {
                    "$ref": "#/definitions/media",
                },
                "system": {"type": "object"},
            },
            "required": ["from", "id", "timestamp", "type"],
            "allOf": [
                {
                    "if": {"properties": {"type": {"const": "audio"}}},
                    "then": {"required": ["audio"]},
                },
                {
                    "if": {"properties": {"type": {"const": "button"}}},
                    "then": {"required": ["button"]},
                },
                {
                    "if": {"properties": {"type": {"const": "contacts"}}},
                    "then": {"required": ["contacts"]},
                },
                {
                    "if": {"properties": {"type": {"const": "document"}}},
                    "then": {"required": ["document"]},
                },
                {
                    "if": {"properties": {"type": {"const": "image"}}},
                    "then": {"required": ["image"]},
                },
                {
                    "if": {"properties": {"type": {"const": "interactive"}}},
                    "then": {"required": ["interactive"]},
                },
                {
                    "if": {"properties": {"type": {"const": "location"}}},
                    "then": {"required": ["location"]},
                },
                {
                    "if": {"properties": {"type": {"const": "sticker"}}},
                    "then": {"required": ["sticker"]},
                },
                {
                    "if": {"properties": {"type": {"const": "system"}}},
                    "then": {"required": ["system"]},
                },
                {
                    "if": {"properties": {"type": {"const": "text"}}},
                    "then": {"required": ["text"]},
                },
                {
                    "if": {"properties": {"type": {"const": "video"}}},
                    "then": {"required": ["video"]},
                },
                {
                    "if": {"properties": {"type": {"const": "voice"}}},
                    "then": {"required": ["voice"]},
                },
            ],
        },
        "status": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "recipient_id": {"type": "string"},
                "message": {
                    "type": "object",
                    "properties": {"recipient_id": {"type": "string"}},
                },
                "status": {
                    "type": "string",
                    "enum": ["read", "delivered", "sent", "failed", "deleted"],
                },
                "timestamp": {"type": "string"},
                "conversation": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                },
                "pricing": {
                    "type": "object",
                    "properties": {
                        "pricing_model": {"type": "string", "enum": ["CBP", "PMP"]},
                        "billable": {"type": "boolean"},
                    },
                },
            },
            "required": ["id", "status", "timestamp"],
        },
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "number"},
                "title": {"type": "string"},
                "details": {"type": "string"},
                "href": {"type": "string"},
            },
            "required": ["code", "title"],
        },
        "contact": {
            "type": "object",
            "parameters": {
                "profile": {
                    "type": "object",
                    "parameters": {"name": {"type": "string"}},
                },
                "wa_id": {"type": "string"},
            },
            "required": ["profile", "wa_id"],
        },
    },
    "type": "object",
    "properties": {
        "contacts": {"type": "array", "items": {"$ref": "#/definitions/contact"}},
        "messages": {"type": "array", "items": {"$ref": "#/definitions/message"}},
        "statuses": {"type": "array", "items": {"$ref": "#/definitions/status"}},
        "errors": {"type": "array", "items": {"$ref": "#/definitions/error"}},
    },
}


def validate_schema(schema: dict):
    """
    Validates the JSON request body according to the given schema, returning a 400 with
    error details for schema failures
    """

    def decorator(f):
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        validator = validator_cls(schema)

        @wraps(f)
        def decorated_function(request: Request, *args, **kwargs):
            errors: dict = {}
            for e in validator.iter_errors(request.json):
                element = errors
                path = list(e.path)
                if not path:
                    path = ["_root"]
                for p in path[:-1]:
                    if p not in element:
                        element[p] = {}
                    element = element[p]
                if path[-1] not in element:
                    element[path[-1]] = []
                element[path[-1]].append(e.message)
            if errors:
                return json(errors, status=400)
            return f(request, *args, **kwargs)

        return decorated_function

    return decorator
