"""ArchIQ API entrypoint. Run with: uvicorn app.main:app --reload --port 8000"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routers import api_router
from app.core import errors
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.mock_ai.generators import documents
from app.repositories.store import get_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_store()  # loads (and, if needed, generates) the seeded Northwind Assurance estate
    documents.load_uploads()  # documents people uploaded in earlier sessions
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="AI backend for the ArchIQ enterprise architecture intelligence platform.",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    errors.install(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
