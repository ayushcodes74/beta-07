"""API Version 1 Router aggregating all OCR service endpoints."""

from fastapi import APIRouter

from app.api.v1.endpoints.handwriting import router as handwriting_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.jobs import router as jobs_router
from app.api.v1.endpoints.process import router as process_router
from app.api.v1.endpoints.result import router as result_router
from app.api.v1.endpoints.status import router as status_router

api_v1_router = APIRouter(prefix="/api/v1/ocr")

api_v1_router.include_router(health_router)
api_v1_router.include_router(process_router)
api_v1_router.include_router(status_router)
api_v1_router.include_router(result_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(handwriting_router)

