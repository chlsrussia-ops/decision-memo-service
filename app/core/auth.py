"""API Key authentication middleware with access logging."""
import os
import logging
from datetime import datetime
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

API_KEY = (
    os.environ.get("COS_API_KEY", "") or
    os.environ.get("CTRE_API_KEY", "") or
    os.environ.get("DMS_API_KEY", "") or
    os.environ.get("DDL_API_KEY", "") or
    os.environ.get("CLOUDOS_API_KEY", "")
)

PUBLIC_PATHS = ("/health", "/docs", "/openapi.json", "/redoc")

_log = logging.getLogger("security.access")
if not _log.handlers:
    _h = logging.FileHandler("/tmp/api_access.log")
    _h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        ip = request.headers.get("X-Real-IP", request.client.host if request.client else "?")

        if any(path == p or path.startswith(p + "/") for p in PUBLIC_PATHS):
            return await call_next(request)
        if path.startswith("/media/"):
            return await call_next(request)
        if not API_KEY:
            return await call_next(request)

        key = request.headers.get("X-API-Key", "")
        if key != API_KEY:
            _log.warning("DENIED ip=%s path=%s method=%s ua=%s",
                         ip, path, request.method,
                         request.headers.get("User-Agent", "?")[:80])
            return JSONResponse(status_code=401, content={"detail": "API key required"})

        _log.info("OK ip=%s path=%s method=%s", ip, path, request.method)
        return await call_next(request)
