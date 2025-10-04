"""Application factory for the SEC data retrieval API."""

from __future__ import annotations

from fastapi import FastAPI

from .data_router import router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="SECDataExtractor Data API",
        version="0.1.0",
        description=(
            "Local-first API for retrieving cached SEC filings with automatic "
            "fallback to the EDGAR data set when cache misses occur."
        ),
    )
    app.include_router(router)
    return app


app = create_app()
