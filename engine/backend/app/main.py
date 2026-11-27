from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.models.db import Database
from app.services.uploads import sweep_expired
from app.services.fetch import FetchWorker
from app.workers.pipeline import Worker, sweep_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("clipmitra")


async def _retention_loop(app: FastAPI) -> None:
    while True:
        try:
            n = await asyncio.to_thread(sweep_expired, app.state.db)
            n += await asyncio.to_thread(sweep_jobs, app.state.db)
            if n:
                log.info("retention sweep removed %d files", n)
        except Exception:  # never kill the loop
            log.exception("retention sweep failed")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.db = Database(s.db_path)
    app.state.worker = None
    app.state.fetcher = None
    if s.worker_enabled:
        app.state.worker = Worker(app.state.db)
        app.state.worker.start()
        app.state.fetcher = FetchWorker(app.state.db)
        app.state.fetcher.start()
    task = asyncio.create_task(_retention_loop(app))
    yield
    if app.state.worker:
        app.state.worker.stop()
    if app.state.fetcher:
        app.state.fetcher.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Wonder Clips", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=list(s.cors_origins),
        allow_methods=["GET", "POST", "PUT"], allow_headers=["*"],
        # The hosted UI (https://clips.wondermayank.in) calls this engine on 127.0.0.1:
        # Chrome's Private Network Access preflight must be answered explicitly.
        allow_private_network=True,
    )

    @app.middleware("http")
    async def _only_known_sites(request: Request, call_next):
        """Browsers let ANY website send simple POSTs (e.g. multipart uploads) to 127.0.0.1 without a
        CORS preflight. Reject requests from pages that are not the Wonder Clips UI. Requests without an
        Origin (curl, scripts on this machine, same-origin GETs) are allowed."""
        origin = request.headers.get("origin")
        if origin and origin not in s.cors_origins:
            return JSONResponse(status_code=403, content={"code": "forbidden_origin",
                                                          "message": "This website is not allowed to use Wonder Clips."})
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"code": "bad_request",
                                                      "message": "The request was not valid."})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"code": "internal_error",
                                                      "message": "Something went wrong on our side."})

    app.include_router(router)
    return app


app = create_app()
