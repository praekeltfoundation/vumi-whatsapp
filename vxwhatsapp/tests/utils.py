import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import redis.asyncio as aioredis
from aio_pika import connect_robust
from sanic import Sanic
from sanic.server import AsyncioServer

from vxwhatsapp import config


async def cleanup_redis():
    redis = aioredis.from_url(
        config.REDIS_URL or "redis://", encoding="utf-8", decode_responses=True
    )
    await redis.delete("claims")
    for key in await redis.keys("msglock:*"):
        await redis.delete(key)
    for key in await redis.keys("msgseen:*"):
        await redis.delete(key)
    await redis.close()


async def cleanup_amqp():
    connection = await connect_robust(config.AMQP_URL)
    async with connection:
        channel = await connection.channel()
        for routing_key in [
            f"{config.TRANSPORT_NAME}.inbound",
            f"{config.TRANSPORT_NAME}.outbound",
            f"{config.TRANSPORT_NAME}.event",
            f"{config.TRANSPORT_NAME}.answer",
        ]:
            queue = await channel.declare_queue(
                routing_key, durable=True, auto_delete=False
            )
            while True:
                message = await queue.get(fail=False)
                if message is None:
                    break
                message.ack()
    await connection.close()


def unused_port():
    """
    Find an unused port by temporarily binding a socket to it.

    Unfortunately, Sanic.create_server() replaces port 0 with its default port
    8000. If we want to bind to an arbitrary unused port, we need to find an
    unused one to pass in explicitly. This potentially has a race condition in
    it, so let's hope we don't hit that.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class MockServer:
    app: Sanic
    server: AsyncioServer
    host: str
    port: int

    async def request(self, method, path, **kwargs):
        url = f"http://{self.host}:{self.port}{path}"
        async with httpx.AsyncClient() as client:
            return await client.request(method, url, **kwargs)

    async def get(self, path, **kwargs):
        return await self.request("GET", path, **kwargs)

    async def post(self, path, **kwargs):
        return await self.request("POST", path, **kwargs)


@asynccontextmanager
async def run_sanic(app):
    """
    Run a sanic app as a context manager. Best used in pytest fixtures.
    """
    Sanic.test_mode = True
    port = unused_port()
    server = await app.create_server(return_asyncio_server=True, port=port)
    if hasattr(server, "startup"):
        # This was introduced between 21.6 and 21.12
        await server.startup()
    await server.start_serving()
    [sock] = server.server.sockets
    host, port = sock.getsockname()
    yield MockServer(app, server, host, port)
    for f in server._before_stop:
        await f(server.loop)
    await server.close()
    for f in server._after_stop:
        await f(server.loop)
