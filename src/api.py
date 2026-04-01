"""HTTP API for Small Group — deployed to Cloud Run.

Uses Firebase ID token auth for all authenticated endpoints.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Small Group API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v2 router (rooms, series, occurrences, check-ins)
from api_v2 import router as v2_router  # noqa: E402
app.include_router(v2_router)


class StripApiPrefixMiddleware:
    """Allow Firebase Hosting /api/** rewrites without requiring separate routes.

    Firebase Hosting forwards requests to Cloud Run with the original path, e.g.
    `/api/pages/foo`. The backend historically serves `/pages/foo`.

    This middleware strips a leading `/api` prefix so both paths work.
    """

    def __init__(self, inner_app):
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path") or ""
            if path == "/api":
                scope = dict(scope)
                scope["path"] = "/"
            elif path.startswith("/api/"):
                scope = dict(scope)
                scope["path"] = path[len("/api"):]
        await self.inner_app(scope, receive, send)


# Must be installed before routing.
app.add_middleware(StripApiPrefixMiddleware)


@app.middleware("http")
async def logging_middleware(request: Request, call_next) -> Response:
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000, 1)

    extra = {
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    }

    trace_header = request.headers.get("x-cloud-trace-context")
    if trace_header:
        extra["trace"] = trace_header.split("/")[0]

    logger.info("request %s %s %d %.1fms", extra["method"], extra["path"],
                extra["status_code"], duration_ms, extra=extra)
    return response


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Log 422 validation errors with the request body for debugging."""
    body = await request.body()
    logger.error("Validation error on %s %s body=%s errors=%s",
                 request.method, request.url.path, body.decode("utf-8", errors="replace"),
                 exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Convert ValueError from storage layer to 400 Bad Request."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/_healthz")
@app.get("/healthz")
def healthz():
    return {"ok": True}
