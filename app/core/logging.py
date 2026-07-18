import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request, Response


logger = logging.getLogger("datapilot.request")


def configure_logging() -> None:
    """Configure the standard logger used by request middleware."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def register_request_logging_middleware(app: FastAPI) -> None:
    """Add trace_id propagation and one structured-ish request log per request."""

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next) -> Response:
        trace_id = request.headers.get("x-trace-id") or str(uuid4())
        request.state.trace_id = trace_id
        started_at = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "request_completed method=%s path=%s status=%s latency_ms=%s trace_id=%s",
                request.method,
                request.url.path,
                status_code,
                latency_ms,
                trace_id,
            )

        response.headers["x-trace-id"] = trace_id
        return response
