"""ASGI application with real HTTP dependency checks, served by Uvicorn."""
import asyncio
import logging
import os
from urllib.request import urlopen

log = logging.getLogger("uvicorn.error")
READY_PATH = os.environ.get("READY_PATH", "/ready")
DEPENDENCY_URL = os.environ.get("DEPENDENCY_URL", "http://dependency:8080/health")


def dependency_ready():
    try:
        with urlopen(DEPENDENCY_URL, timeout=1) as response:
            return response.status == 200
    except (OSError, ValueError) as error:
        log.error("Readiness dependency inventory unavailable: %s", error)
        return False


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                log.info("Readiness route registered: GET %s", READY_PATH)
                await send({"type": "lifespan.startup.complete"})
            elif event["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    elif scope["type"] == "http":
        path = scope["path"]
        status = 200 if path == "/live" else 404
        if path == READY_PATH:
            status = 200 if await asyncio.to_thread(dependency_ready) else 503
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"readiness-lab\n"})
