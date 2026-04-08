"""API Key authentication middleware for FastAPI services."""
import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Reads from any of these env vars
API_KEY = (
    os.environ.get("COS_API_KEY", "") or
    os.environ.get("CTRE_API_KEY", "") or
    os.environ.get("DMS_API_KEY", "") or
    os.environ.get("DDL_API_KEY", "") or
    os.environ.get("CLOUDOS_API_KEY", "")
)

PUBLIC_PATHS = ("/health", "/docs", "/openapi.json", "/redoc")


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in PUBLIC_PATHS):
            return await call_next(request)
        if path.startswith("/media/"):
            return await call_next(request)
        if not API_KEY:
            return await call_next(request)
        key = request.headers.get("X-API-Key", "")
        if key != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "API key required"})
        return await call_next(request)
