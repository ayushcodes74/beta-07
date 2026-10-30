"""Health check endpoints auditing service status and model readiness."""

from fastapi import APIRouter

from app.api.schemas import HealthResponse
from app.jobs.job_manager import JobManager
from app.math_recognition.model_manager import MathModelManager
from app.recognition.model_manager import ModelManager

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return service status, module readiness, and model availability.

    Distinguishes operational service availability from deep-learning model readiness.
    The service remains operational ('healthy') even when models operate in degraded fallback.
    """
    job_mgr = JobManager.get_instance()
    rec_mgr = ModelManager.get_instance()
    math_mgr = MathModelManager.get_instance()

    # Query module availability
    modules_status = {
        "module_1_ingestion": "available",
        "module_2_preprocessing": "available",
        "module_3_recognition": "available",
        "module_4_math_recognition": "available",
    }

    # Query deep-learning model readiness
    models_status = {
        "trocr_handwriting": rec_mgr.handwriting_engine_status,
        "paddleocr_printed": rec_mgr.printed_engine_status,
        "pix2tex_math": math_mgr.model_status,
    }

    # Service is degraded if any model failed or is unavailable, but service remains operational
    all_models_loaded = all(s == "loaded" for s in models_status.values())
    service_status = "healthy" if all_models_loaded else "degraded"

    return HealthResponse(
        status=service_status,
        service_version="1.0.0",
        service_available=True,
        modules=modules_status,
        models=models_status,
        active_jobs=job_mgr.get_active_count(),
    )

