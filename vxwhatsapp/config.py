import os

HMAC_SECRET = os.environ.get("HMAC_SECRET")
SENTRY_DSN = os.environ.get("SENTRY_DSN")
SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", 0.0))
AMQP_URL = os.environ.get("AMQP_URL", "amqp://guest:guest@127.0.0.1/")
TRANSPORT_NAME = os.environ.get("TRANSPORT_NAME", "whatsapp")
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "none")
PUBLISH_TIMEOUT = int(os.environ.get("PUBLISH_TIMEOUT", "10"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "50"))
CONSUME_TIMEOUT = float(os.environ.get("CONSUME_TIMEOUT", "10"))
API_HOST = os.environ.get("API_HOST", "whatsapp.turn.io")
API_TOKEN = os.environ.get("API_TOKEN")
REDIS_URL = os.environ.get("REDIS_URL")
