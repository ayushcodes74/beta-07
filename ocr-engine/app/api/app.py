"""FastAPI application factory and middleware configuration for TrustGrade OCR Engine."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.config import APIConfig, DEFAULT_API_CONFIG
from app.api.v1.endpoints.health import get_health
from app.api.v1.router import api_v1_router
from app.ingestion.exceptions import IngestionError
from app.jobs.job_manager import JobManager
from app.math_recognition.exceptions import MathRecognitionError

logger = logging.getLogger("ocr_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for background worker pool and clean shutdown."""
    logger.info("Starting TrustGrade OCR Engine API service...")
    yield
    logger.info("Shutting down TrustGrade OCR Engine API service...")
    JobManager.reset_instance()


def create_app(config: APIConfig = DEFAULT_API_CONFIG) -> FastAPI:
    """Build and configure the TrustGrade OCR Service FastAPI application."""
    app = FastAPI(
        title="TrustGrade OCR Engine API",
        description="Unified OCR and mathematical recognition service for AI-assisted grading",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS configuration for secure internal backend communication
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Root health endpoint
    app.add_api_route("/health", get_health, methods=["GET"], tags=["Health"])

    # Include API v1 router
    app.include_router(api_v1_router)

    # Global Exception Handlers
    @app.exception_handler(IngestionError)
    async def ingestion_exception_handler(request: Request, exc: IngestionError):
        logger.warning("Ingestion validation error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "PDFValidationError", "message": str(exc)},
        )

    @app.exception_handler(MathRecognitionError)
    async def math_exception_handler(request: Request, exc: MathRecognitionError):
        logger.warning("Math recognition error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "MathRecognitionError", "message": str(exc)},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled OCR service error: %s", exc)
        # Never leak raw stack traces to client responses
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "InternalServerError", "message": "An unexpected error occurred during OCR processing."},
        )

    return app


# Default application instance for Uvicorn ASGI servers
app = create_app()

