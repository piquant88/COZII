"""Cozii backend entry point.

Slim by design — all heavy lifting lives in `core.py`, `models.py`
and the per-domain modules under `routes/`. Importing `routes`
registers every @api_router endpoint. We then mount the router on
the FastAPI app and wrap with Socket.IO’s ASGIApp.

Supervisor still runs `uvicorn server:app`.
"""
from __future__ import annotations

import socketio
from core import app, api_router, sio, client, logger
import routes  # noqa: F401 — side effects: registers all routes
from core import _daily_digest_loop  # background task
import asyncio

# Final wiring — exactly once, at the end.
app.include_router(api_router)
fastapi_app = app


@fastapi_app.on_event("startup")
async def _on_startup():
    try:
        asyncio.create_task(_daily_digest_loop())
        logger.info("daily digest background task scheduled")
    except Exception as e:
        logger.warning(f"failed to schedule daily digest task: {e}")


@fastapi_app.on_event("shutdown")
async def _on_shutdown():
    try:
        client.close()
    except Exception:
        pass


app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path='/api/socket.io')
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )