"""
Typed exceptions and RFC 7807 problem detail responses.

Add FastAPI exception handlers in main.py:
    app.add_exception_handler(HelixError, helix_error_handler)
"""
from fastapi import Request
from fastapi.responses import JSONResponse


class HelixError(Exception):
    """Base for all domain errors. Carries a stable error code."""
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(detail)


class SessionNotFoundError(HelixError):
    status_code = 404
    error_code = "SESSION_NOT_FOUND"


class TraceNotFoundError(HelixError):
    status_code = 404
    error_code = "TRACE_NOT_FOUND"


class UpstreamTimeoutError(HelixError):
    status_code = 504
    error_code = "UPSTREAM_TIMEOUT"


class RateLimitedError(HelixError):
    status_code = 429
    error_code = "RATE_LIMITED"


async def helix_error_handler(request: Request, exc: HelixError) -> JSONResponse:
    """Convert HelixError → RFC 7807 problem detail."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"https://docs.helix.example/errors/{exc.error_code.lower()}",
            "title": exc.error_code,
            "status": exc.status_code,
            "detail": exc.detail,
        },
    )
