"""Central OCR orchestrator coordinating Modules 1, 2, 3, and 4 into a unified workflow."""

import logging
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.api.schemas import OCRDocumentResult
from app.ingestion.config import IngestionConfig
from app.ingestion.pdf_processor import process_pdf
from app.ingestion.schemas import PDFProcessingResult
from app.math_recognition.config import MathRecognitionConfig
from app.math_recognition.recognition_pipeline import process_math_page
from app.math_recognition.schemas import PageMathRecognitionResult
from app.orchestration.result_aggregator import ResultAggregator
from app.preprocessing.config import PreprocessingConfig
from app.preprocessing.pipeline import preprocess_page
from app.preprocessing.schemas import ImageQualityMetrics, PreprocessingResult
from app.recognition.config import RecognitionConfig
from app.recognition.recognition_pipeline import recognize_page
from app.recognition.schemas import PageRecognitionResult

logger = logging.getLogger(__name__)


class OCROrchestrator:
    """Orchestrates end-to-end PDF processing across Modules 1 through 4."""

    def __init__(
        self,
        ingestion_config: Optional[IngestionConfig] = None,
        preprocessing_config: Optional[PreprocessingConfig] = None,
        recognition_config: Optional[RecognitionConfig] = None,
        math_config: Optional[MathRecognitionConfig] = None,
    ) -> None:
        self.ingestion_config = ingestion_config
        self.preprocessing_config = preprocessing_config
        self.recognition_config = recognition_config
        self.math_config = math_config

    def process_submission(
        self,
        pdf_path: str,
        submission_id: str,
        output_dir: str,
        job_id: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> OCRDocumentResult:
        """Execute full OCR pipeline on an assignment submission with per-stage timing and error isolation.

        Args:
            pdf_path: Path to the validated input PDF file.
            submission_id: Unique submission identifier.
            output_dir: Dedicated directory for rendered images and enhanced artifacts.
            job_id: Unique background job identifier.
            progress_callback: Optional callable(stage_name, percent_complete).

        Returns:
            OCRDocumentResult representing unified document text and mathematical structure.
        """
        t_total_start = time.time()
        stage_durations: Dict[str, float] = {}
        job_warnings: List[str] = []
        job_errors: List[str] = []

        # ======================================================================
        # STAGE 1: PDF Ingestion & Page Rendering (Module 1)
        # ======================================================================
        if progress_callback:
            progress_callback("ingestion", 10)

        t_stage_start = time.time()
        logger.info("[Job %s] Stage 1: Ingesting PDF '%s' for submission '%s'...", job_id, pdf_path, submission_id)

        pdf_result: PDFProcessingResult = process_pdf(
            pdf_path=pdf_path,
            submission_id=submission_id,
            output_dir=output_dir,
            config=self.ingestion_config,
        )
        stage_durations["ingestion"] = (time.time() - t_stage_start) * 1000.0

        total_pages = pdf_result.total_pages
        logger.info(
            "[Job %s] Stage 1 completed: %d pages rendered in %.1f ms",
            job_id,
            total_pages,
            stage_durations["ingestion"],
        )

        if total_pages == 0:
            job_warnings.append("Document contains zero extractable pages.")
            return ResultAggregator.aggregate_results(
                job_id=job_id,
                submission_id=submission_id,
                pdf_result=pdf_result,
                preprocessing_results=[],
                recognition_results=[],
                math_results=[],
                stage_durations=stage_durations,
                total_time_ms=(time.time() - t_total_start) * 1000.0,
                job_warnings=job_warnings,
            )

        # ======================================================================
        # STAGE 2: Image Preprocessing & Enhancement (Module 2)
        # ======================================================================
        if progress_callback:
            progress_callback("preprocessing", 25)

        t_stage_start = time.time()
        logger.info("[Job %s] Stage 2: Preprocessing %d page images...", job_id, total_pages)

        preprocessing_results: List[PreprocessingResult] = []
        for p in pdf_result.pages:
            try:
                prep_res = preprocess_page(
                    image_path=p.image_path,
                    submission_id=submission_id,
                    page_number=p.page_number,
                    output_dir=output_dir,
                    config=self.preprocessing_config,
                    known_rotation=p.rotation,
                )
                preprocessing_results.append(prep_res)
            except Exception as e:
                logger.error("[Job %s] Preprocessing failed on page %d: %s", job_id, p.page_number, e)
                job_warnings.append(f"Page {p.page_number} preprocessing encountered error: {e}")
                # Fallback record pointing to original image
                preprocessing_results.append(
                    PreprocessingResult(
                        submission_id=submission_id,
                        page_number=p.page_number,
                        status="failed",
                        original_image_path=p.image_path,
                        enhanced_image_path=p.image_path,
                        image_quality=ImageQualityMetrics(
                            width=p.width,
                            height=p.height,
                            warnings=[f"Preprocessing failure: {e}"],
                        ),
                    )
                )

        stage_durations["preprocessing"] = (time.time() - t_stage_start) * 1000.0
        logger.info("[Job %s] Stage 2 completed in %.1f ms", job_id, stage_durations["preprocessing"])

        # ======================================================================
        # STAGE 3: Text & Handwriting Recognition (Module 3)
        # ======================================================================
        if progress_callback:
            progress_callback("recognition", 50)

        t_stage_start = time.time()
        logger.info("[Job %s] Stage 3: Recognizing printed & handwritten text...", job_id)

        recognition_results: List[PageRecognitionResult] = []
        for prep_item in preprocessing_results:
            p_num = prep_item.page_number
            target_img = prep_item.enhanced_image_path or prep_item.original_image_path
            try:
                rec_res = recognize_page(
                    image_path=target_img,
                    submission_id=submission_id,
                    page_number=p_num,
                    config=self.recognition_config,
                )
                recognition_results.append(rec_res)
            except Exception as e:
                logger.error("[Job %s] Text recognition failed on page %d: %s", job_id, p_num, e)
                job_warnings.append(f"Page {p_num} text recognition failed: {e}")
                recognition_results.append(
                    PageRecognitionResult(
                        submission_id=submission_id,
                        page_number=p_num,
                        status="failed",
                        text_blocks=[],
                        full_text="",
                        warnings=[f"Recognition failed on page {p_num}: {e}"],
                        metadata={"error": str(e), "is_fallback": True, "engine_used": "none"},
                    )
                )

        stage_durations["recognition"] = (time.time() - t_stage_start) * 1000.0
        logger.info("[Job %s] Stage 3 completed in %.1f ms", job_id, stage_durations["recognition"])

        # ======================================================================
        # STAGE 4: Mathematical Recognition & Quality Analysis (Module 4)
        # ======================================================================
        if progress_callback:
            progress_callback("math_recognition", 75)

        t_stage_start = time.time()
        logger.info("[Job %s] Stage 4: Extracting mathematical notation & formulas...", job_id)

        math_results: List[PageMathRecognitionResult] = []
        rec_by_page = {r.page_number: r for r in recognition_results}

        for prep_item in preprocessing_results:
            p_num = prep_item.page_number
            target_img = prep_item.enhanced_image_path or prep_item.original_image_path
            rec_context = rec_by_page.get(p_num)

            try:
                math_res = process_math_page(
                    image_input=target_img,
                    submission_id=submission_id,
                    page_number=p_num,
                    page_recognition_result=rec_context,
                    config=self.math_config,
                )
                math_results.append(math_res)
            except Exception as e:
                logger.error("[Job %s] Mathematical recognition failed on page %d: %s", job_id, p_num, e)
                job_warnings.append(f"Page {p_num} mathematical recognition failed: {e}")
                math_results.append(
                    PageMathRecognitionResult(
                        submission_id=submission_id,
                        page_number=p_num,
                        status="failed",
                        math_regions=[],
                        combined_latex="",
                        warnings=[f"Math recognition failed: {e}"],
                        metadata={"error": str(e)},
                    )
                )

        stage_durations["math_recognition"] = (time.time() - t_stage_start) * 1000.0
        logger.info("[Job %s] Stage 4 completed in %.1f ms", job_id, stage_durations["math_recognition"])

        # ======================================================================
        # STAGE 5: Result Aggregation & Harmonization
        # ======================================================================
        if progress_callback:
            progress_callback("aggregation", 90)

        t_stage_start = time.time()
        logger.info("[Job %s] Stage 5: Aggregating structured document result...", job_id)

        total_time_ms = (time.time() - t_total_start) * 1000.0
        stage_durations["aggregation"] = (time.time() - t_stage_start) * 1000.0

        final_result = ResultAggregator.aggregate_results(
            job_id=job_id,
            submission_id=submission_id,
            pdf_result=pdf_result,
            preprocessing_results=preprocessing_results,
            recognition_results=recognition_results,
            math_results=math_results,
            stage_durations=stage_durations,
            total_time_ms=total_time_ms,
            job_errors=job_errors,
            job_warnings=job_warnings,
        )

        if progress_callback:
            progress_callback("done", 100)

        logger.info(
            "[Job %s] OCR orchestration finished in %.1f ms with status '%s'.",
            job_id,
            total_time_ms,
            final_result.status,
        )
        return final_result
