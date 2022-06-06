import random
from datetime import datetime
from uuid import uuid4

from locust import HttpUser, task

ids = [uuid4().hex for _ in range(100)]
msisdns = [f"2782000100{i}" for i in range(10)]


class WhatsAppWebhookUser(HttpUser):
    @task
    def text_message(self):
        self.client.post(
            "/v1/webhook",
            json={
                "messages": [
                    {
                        "from": random.choice(msisdns),
                        "id": random.choice(ids),
                        "timestamp": str(int(datetime.utcnow().timestamp())),
                        "type": "text",
                        "text": {"body": "test message"},
                    }
                ]
            },
        )
