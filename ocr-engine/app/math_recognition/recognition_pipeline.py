"""Main mathematical recognition pipeline orchestrating validation, inference, and quality analysis."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import cv2
import numpy as np

from app.math_recognition.config import MathRecognitionConfig, DEFAULT_MATH_CONFIG
from app.math_recognition.exceptions import (
    MathImageError,
    MathPipelineError,
    MathRecognitionError,
    MathRegionValidationError,
)
from app.math_recognition.image_processor import MathImageProcessor
from app.math_recognition.latex_converter import LaTeXConverter
from app.math_recognition.math_ocr import MathOCREngine
from app.math_recognition.model_manager import MathModelManager
from app.math_recognition.quality_analyzer import MathQualityAnalyzer
from app.math_recognition.region_validator import MathRegionValidator
from app.math_recognition.schemas import (
    BoundingBox,
    MathQualityAssessment,
    MathRegionResult,
    PageMathRecognitionResult,
)
from app.math_recognition.structure_analyzer import MathStructureAnalyzer
from app.math_recognition.symbol_analyzer import MathSymbolAnalyzer

logger = logging.getLogger(__name__)


class MathRecognitionPipeline:
    """Orchestrates mathematical region extraction, OCR inference, LaTeX formatting, and quality analysis."""

    def __init__(self, config: Optional[MathRecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_MATH_CONFIG
        self.model_manager = MathModelManager.get_instance(self.config)
        self.region_validator = MathRegionValidator(config=self.config)
        self.quality_analyzer = MathQualityAnalyzer(config=self.config)
        self.ocr_engine = MathOCREngine(config=self.config)

    def process_region(
        self,
        crop: np.ndarray,
        region_id: str,
        page_id: str,
        bounding_box: BoundingBox,
        raw_text_hint: Optional[str] = None,
        page_width: Optional[int] = None,
        page_height: Optional[int] = None,
    ) -> MathRegionResult:
        """Process an individual mathematical crop with full quality and structure analysis.

        Args:
            crop: BGR or grayscale numpy image array.
            region_id: Unique region identifier.
            page_id: Associated page ID.
            bounding_box: BoundingBox coordinates on the page.
            raw_text_hint: Optional prior text hint from Module 3.
            page_width: Optional page width for boundary checking.
            page_height: Optional page height for boundary checking.

        Returns:
            MathRegionResult with recognized LaTeX, quality score, symbols, and diagnostics.
        """
        # Ensure models are initialized
        self.model_manager.initialize_models()

        # 1. Bounding-Box Validation
        self.region_validator.assert_valid_region(
            bounding_box, page_width=page_width, page_height=page_height, crop=crop, region_id=region_id
        )

        # 2. Physical Image Quality Analysis
        quality_assessment: MathQualityAssessment = self.quality_analyzer.analyze_crop(crop, box=bounding_box)

        # 3. Mathematical OCR Inference
        raw_text, raw_latex, model_conf, ocr_meta = self.ocr_engine.recognize_crop(crop, region_id, page_id)

        # If model returned no text but caller provided a raw text hint (e.g. from Module 3)
        if not raw_text and raw_text_hint:
            raw_text = raw_text_hint

        # 4. LaTeX Conversion and Syntax Normalization
        latex_expr, latex_warnings = LaTeXConverter.convert_to_latex(raw_latex or raw_text)

        # 5. Symbol Analysis & Ambiguity Detection
        symbols, symbol_warnings = MathSymbolAnalyzer.analyze_symbols(latex_expr or raw_text)

        # 6. Structural Component Analysis (fractions, roots, powers, integrals)
        structures = MathStructureAnalyzer.analyze_structures(latex_expr or raw_text)

        # 7. Aggregate Warnings
        all_warnings: List[str] = []
        all_warnings.extend(quality_assessment.warnings)
        all_warnings.extend(latex_warnings)
        all_warnings.extend(symbol_warnings)

        if not quality_assessment.is_readable:
            all_warnings.append("Low image quality: teacher verification recommended.")

        # Determine final status
        rec_status = ocr_meta.get("recognition_status", "completed")
        if not quality_assessment.is_readable and rec_status == "completed":
            rec_status = "low_confidence"

        requires_review = (
            quality_assessment.requires_manual_review
            or rec_status in ("low_confidence", "unreadable", "unavailable", "failed")
            or bool(symbol_warnings)
        )

        return MathRegionResult(
            region_id=region_id,
            page_id=str(page_id),
            bounding_box=bounding_box,
            recognized_text=raw_text,
            latex=latex_expr,
            confidence=model_conf,
            quality_score=quality_assessment.quality_score,
            is_readable=quality_assessment.is_readable,
            is_complete=quality_assessment.is_complete,
            requires_manual_review=requires_review,
            symbols=symbols,
            structures=structures,
            warnings=all_warnings,
            recognition_status=rec_status,
            engine_used=ocr_meta.get("engine_used", "none"),
            model_version=ocr_meta.get("model_version"),
            metadata=ocr_meta,
        )

    def process_page(
        self,
        image_input: Union[str, Path, np.ndarray],
        submission_id: str,
        page_number: int,
        page_recognition_result: Optional[Any] = None,
        explicit_regions: Optional[List[Dict[str, Any]]] = None,
    ) -> PageMathRecognitionResult:
        """Process all mathematical regions on an assignment page with complete error isolation.

        Supports seamless integration with Module 3 PageRecognitionResult or explicit crops.

        Args:
            image_input: Path to enhanced page image or numpy array.
            submission_id: Unique submission identifier.
            page_number: 1-based page index.
            page_recognition_result: Optional PageRecognitionResult from Module 3.
            explicit_regions: Optional list of dicts with 'region_id' and 'bounding_box'.

        Returns:
            PageMathRecognitionResult aggregating all extracted mathematical formulas.

        Raises:
            MathPipelineError: If page image cannot be loaded.
        """
        try:
            page_img = MathImageProcessor.load_crop(image_input)
        except Exception as e:
            logger.error("Failed to load page image for math recognition: %s", e)
            raise MathPipelineError(f"Failed to load page image: {e}", page_number=page_number) from e

        h, w = page_img.shape[:2]
        regions_to_process: List[Dict[str, Any]] = []

        # 1. Harvest mathematical regions from Module 3 PageRecognitionResult
        if page_recognition_result is not None:
            blocks = getattr(page_recognition_result, "text_blocks", [])
            for b in blocks:
                warnings = getattr(b, "warnings", [])
                text = getattr(b, "text", "")
                box = getattr(b, "bounding_box", None)
                block_id = getattr(b, "block_id", "unknown-block")

                # Check if block was flagged as containing mathematical notation
                is_math = any("mathematical" in w_msg.lower() for w_msg in warnings) or any(
                    sym in text for sym in ["=", "+", "-", "*", "/", "^", "_", "∫", "∑", "√"]
                )

                if is_math and box is not None:
                    # Convert bounding box if necessary
                    bbox = box if isinstance(box, BoundingBox) else BoundingBox(
                        x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2
                    )
                    regions_to_process.append({
                        "region_id": f"math-{block_id}",
                        "bounding_box": bbox,
                        "raw_text_hint": text,
                    })

        # 2. Add any explicitly provided regions
        if explicit_regions:
            for item in explicit_regions:
                box_item = item["bounding_box"]
                bbox = box_item if isinstance(box_item, BoundingBox) else BoundingBox(**box_item)
                regions_to_process.append({
                    "region_id": item.get("region_id", f"math-page-{page_number}-{len(regions_to_process)+1}"),
                    "bounding_box": bbox,
                    "raw_text_hint": item.get("raw_text_hint"),
                })

        # 3. Process Each Region with Strict Error Isolation
        results: List[MathRegionResult] = []
        page_warnings: List[str] = []

        if not regions_to_process:
            page_warnings.append("No mathematical regions detected on page.")
            return PageMathRecognitionResult(
                submission_id=submission_id,
                page_number=page_number,
                status="completed",
                math_regions=[],
                combined_latex="",
                warnings=page_warnings,
                metadata={"total_math_regions": 0},
            )

        for reg_meta in regions_to_process:
            rid = reg_meta["region_id"]
            bbox = reg_meta["bounding_box"]
            hint = reg_meta.get("raw_text_hint")

            try:
                # Safe crop extraction with bounds clamping
                x1 = max(0, min(bbox.x1, w - 1))
                y1 = max(0, min(bbox.y1, h - 1))
                x2 = max(x1 + 1, min(bbox.x2, w))
                y2 = max(y1 + 1, min(bbox.y2, h))

                crop = page_img[y1:y2, x1:x2].copy()

                reg_result = self.process_region(
                    crop=crop,
                    region_id=rid,
                    page_id=str(page_number),
                    bounding_box=bbox,
                    raw_text_hint=hint,
                    page_width=w,
                    page_height=h,
                )
                results.append(reg_result)

            except Exception as e:
                logger.error("Failed to process mathematical region %s on page %d: %s", rid, page_number, e)
                # Isolate failure: record structured failed region so other regions proceed unharmed
                results.append(
                    MathRegionResult(
                        region_id=rid,
                        page_id=str(page_number),
                        bounding_box=bbox,
                        recognized_text="",
                        latex="",
                        confidence=None,
                        quality_score=0.0,
                        is_readable=False,
                        is_complete=False,
                        requires_manual_review=True,
                        symbols=[],
                        structures=[],
                        warnings=[f"Region processing failure: {e}"],
                        recognition_status="failed",
                        engine_used="none",
                        metadata={"error": str(e)},
                    )
                )

        # 4. Aggregate Combined LaTeX and Overall Status
        valid_latex = [r.latex for r in results if r.latex.strip()]
        combined = "\n".join(valid_latex)

        all_failed = all(r.recognition_status == "failed" for r in results)
        any_degraded = any(r.recognition_status in ("unavailable", "degraded") for r in results)

        if all_failed:
            overall_status = "failed"
        elif any_degraded:
            overall_status = "degraded"
        else:
            overall_status = "completed"

        return PageMathRecognitionResult(
            submission_id=submission_id,
            page_number=page_number,
            status=overall_status,
            math_regions=results,
            combined_latex=combined,
            warnings=page_warnings,
            metadata={
                "total_math_regions": len(results),
                "successful_regions": len(valid_latex),
                "review_required_regions": sum(1 for r in results if r.requires_manual_review),
            },
        )

    def process_batch(
        self,
        pages: List[Dict[str, Any]],
        submission_id: str,
    ) -> List[PageMathRecognitionResult]:
        """Batch process mathematical regions across multiple assignment pages.

        Ensures that a failure on one page does not disrupt other pages.

        Args:
            pages: List of page dictionaries containing 'image_path' and optional 'page_recognition_result'.
            submission_id: Submission identifier.

        Returns:
            List of PageMathRecognitionResult objects.
        """
        results: List[PageMathRecognitionResult] = []

        for idx, page_data in enumerate(pages):
            page_num = page_data.get("page_number", idx + 1)
            img_path = page_data.get("enhanced_image_path") or page_data.get("image_path")
            p_rec = page_data.get("page_recognition_result")

            try:
                page_res = self.process_page(
                    image_input=img_path,
                    submission_id=submission_id,
                    page_number=page_num,
                    page_recognition_result=p_rec,
                )
                results.append(page_res)
            except Exception as e:
                logger.error("Failed to process math on page %d in batch: %s", page_num, e)
                results.append(
                    PageMathRecognitionResult(
                        submission_id=submission_id,
                        page_number=page_num,
                        status="failed",
                        math_regions=[],
                        combined_latex="",
                        warnings=[f"Batch math processing failed on page {page_num}: {e}"],
                        metadata={"total_math_regions": 0},
                    )
                )

        return results


# Module-level convenience functions
def process_math_region(
    crop: np.ndarray,
    region_id: str,
    page_id: str,
    bounding_box: BoundingBox,
    config: Optional[MathRecognitionConfig] = None,
) -> MathRegionResult:
    """Convenience function to process a single mathematical crop."""
    pipeline = MathRecognitionPipeline(config=config)
    return pipeline.process_region(crop, region_id, page_id, bounding_box)


def process_math_page(
    image_input: Union[str, Path, np.ndarray],
    submission_id: str,
    page_number: int,
    page_recognition_result: Optional[Any] = None,
    config: Optional[MathRecognitionConfig] = None,
) -> PageMathRecognitionResult:
    """Convenience function to process all mathematical regions on an assignment page."""
    pipeline = MathRecognitionPipeline(config=config)
    return pipeline.process_page(
        image_input=image_input,
        submission_id=submission_id,
        page_number=page_number,
        page_recognition_result=page_recognition_result,
    )


def process_math_batch(
    pages: List[Dict[str, Any]],
    submission_id: str,
    config: Optional[MathRecognitionConfig] = None,
) -> List[PageMathRecognitionResult]:
    """Convenience function to batch process mathematical pages."""
    pipeline = MathRecognitionPipeline(config=config)
    return pipeline.process_batch(pages=pages, submission_id=submission_id)

