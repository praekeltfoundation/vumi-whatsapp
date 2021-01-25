import asyncio
import time

import psutil
from prometheus_client import Counter, Gauge, Histogram
from sanic import Sanic

RQS_COUNT = Counter(
    "sanic_request_count", "Sanic Request Count", ["method", "endpoint", "http_status"]
)

RQS_LATENCY = Histogram(
    "sanic_request_latency_sec",
    "Sanic Request Latency Histogram",
    ["method", "endpoint", "http_status"],
)

PROC_RSS_MEM_BYTES = Gauge(
    "sanic_mem_rss_bytes", "Resident memory used by process running Sanic"
)
PROC_RSS_MEM_PERC = Gauge(
    "sanic_mem_rss_perc",
    "A per cent of total physical memory used by the process running Sanic",
)


def setup_metrics_middleware(app: Sanic) -> None:
    @app.middleware("request")
    async def before_request(request):
        if request.path != "/metrics" and request.method != "OPTIONS":
            request.ctx.start_time = time.time()

    @app.middleware("response")
    async def before_response(request, response):
        if request.path != "/metrics" and request.method != "OPTIONS":
            RQS_LATENCY.labels(request.method, request.path, response.status).observe(
                time.time() - request.ctx.start_time
            )
            RQS_COUNT.labels(request.method, request.path, response.status).inc()

    async def periodic_memcollect_task(app: Sanic):
        p = psutil.Process()
        while True:
            PROC_RSS_MEM_BYTES.set(p.memory_info().rss)
            PROC_RSS_MEM_PERC.set(p.memory_percent())
            await asyncio.sleep(30)

    @app.listener("before_server_start")
    async def start_memcollect_task(app, loop):
        app.memcollect_task = loop.create_task(periodic_memcollect_task(app))

    @app.listener("after_server_stop")
    async def stop_memcollect_task(app, loop):
        app.memcollect_task.cancel()
