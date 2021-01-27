import os

HMAC_SECRET = os.environ.get("HMAC_SECRET")
SENTRY_DSN = os.environ.get("SENTRY_DSN")
AMQP_URL = os.environ.get("AMQP_URL", "amqp://guest:guest@127.0.0.1/")
TRANSPORT_NAME = os.environ.get("TRANSPORT_NAME", "whatsapp")
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "none")
PUBLISH_TIMEOUT = int(os.environ.get("PUBLISH_TIMEOUT", "10"))
