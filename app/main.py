"""Decision Memo Service — main application.

Human-in-the-loop decision support for e-commerce product evaluation.
This system does NOT make purchase decisions. It provides structured
recommendations with transparent reasoning for human decision-makers.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from app.core.auth import ApiKeyMiddleware
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_decision_memo import router
from app.config import settings

# Logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# App
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, 
    title="Decision Memo Service",
    description=(
        "Human-in-the-loop decision support system. "
        "Generates structured recommendations with transparent reasoning. "
        "Final decisions are ALWAYS made by humans."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(ApiKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mybot123.org"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(router)

from app.api.routes_canonical_memo import router as canonical_memo_router
app.include_router(canonical_memo_router)


@app.get("/health")
async def health():
    """Basic health check."""
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/")
async def root():
    """Root — redirect to docs."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "principle": "Human decides. System recommends.",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
