"""Result aggregation service unifying outputs from Modules 1, 2, 3, and 4 into a structured document result."""

import logging
from typing import Any, Dict, List, Optional
from app.api.schemas import (
    BoundingBoxSchema,
    DocumentMetadataSchema,
    MathBlockSchema,
    OCRDocumentResult,
    PageResultSchema,
    ProcessingSummarySchema,
    TextBlockSchema,
)
from app.ingestion.schemas import PDFProcessingResult
from app.math_recognition.schemas import PageMathRecognitionResult
from app.preprocessing.schemas import PreprocessingResult
from app.recognition.schemas import PageRecognitionResult

logger = logging.getLogger(__name__)


def compute_iou(box1: BoundingBoxSchema, box2: BoundingBoxSchema) -> float:
    """Compute Intersection-over-Union (IoU) between two bounding boxes."""
    xA = max(box1.x1, box2.x1)
    yA = max(box1.y1, box2.y1)
    xB = min(box1.x2, box2.x2)
    yB = min(box1.y2, box2.y2)

    inter_width = max(0, xB - xA)
    inter_height = max(0, yB - yA)
    inter_area = inter_width * inter_height

    if inter_area == 0:
        return 0.0

    area1 = (box1.x2 - box1.x1) * (box1.y2 - box1.y1)
    area2 = (box2.x2 - box2.x1) * (box2.y2 - box2.y1)
    union_area = float(area1 + area2 - inter_area)

    return inter_area / union_area if union_area > 0 else 0.0


class ResultAggregator:
    """Aggregates and deduplicates page-level outputs into the final OCRDocumentResult schema."""

    @classmethod
    def aggregate_results(
        cls,
        job_id: str,
        submission_id: str,
        pdf_result: PDFProcessingResult,
        preprocessing_results: List[PreprocessingResult],
        recognition_results: List[PageRecognitionResult],
        math_results: List[PageMathRecognitionResult],
        stage_durations: Dict[str, float],
        total_time_ms: float,
        job_errors: Optional[List[str]] = None,
        job_warnings: Optional[List[str]] = None,
    ) -> OCRDocumentResult:
        """Combine all module outputs while preserving page order, coordinates, and diagnostic flags.

        Args:
            job_id: Unique job identifier.
            submission_id: Unique submission ID.
            pdf_result: Result from Module 1.
            preprocessing_results: Results from Module 2.
            recognition_results: Results from Module 3.
            math_results: Results from Module 4.
            stage_durations: Execution times per stage in milliseconds.
            total_time_ms: Total pipeline wall-clock execution time.
            job_errors: Optional top-level job errors.
            job_warnings: Optional top-level job warnings.

        Returns:
            Structured OCRDocumentResult.
        """
        all_warnings: List[str] = list(job_warnings or [])
        all_errors: List[str] = list(job_errors or [])

        # Index page-level outputs by 1-based page number
        prep_by_page = {p.page_number: p for p in preprocessing_results}
        rec_by_page = {p.page_number: p for p in recognition_results}
        math_by_page = {p.page_number: p for p in math_results}

        page_schemas: List[PageResultSchema] = []
        processed_count = 0
        failed_count = 0

        # Preserve strict ascending page order from Module 1
        for page_rec in pdf_result.pages:
            p_num = page_rec.page_number
            p_id = f"page-{p_num}"
            p_warnings: List[str] = []

            prep_item = prep_by_page.get(p_num)
            rec_item = rec_by_page.get(p_num)
            math_item = math_by_page.get(p_num)

            # Determine page image references
            orig_img = page_rec.image_path
            enh_img = prep_item.enhanced_image_path if prep_item else None
            p_width = page_rec.width
            p_height = page_rec.height

            # Collect Preprocessing Warnings
            if prep_item and hasattr(prep_item, "image_quality") and prep_item.image_quality:
                if prep_item.image_quality.warnings:
                    p_warnings.extend(prep_item.image_quality.warnings)

            # Convert Text Blocks from Module 3
            text_blocks: List[TextBlockSchema] = []
            if rec_item:
                if rec_item.warnings:
                    p_warnings.extend(rec_item.warnings)
                for b in rec_item.text_blocks:
                    tb_box = BoundingBoxSchema(
                        x1=b.bounding_box.x1,
                        y1=b.bounding_box.y1,
                        x2=b.bounding_box.x2,
                        y2=b.bounding_box.y2,
                    )
                    text_blocks.append(
                        TextBlockSchema(
                            block_id=b.block_id,
                            sequence=b.sequence,
                            type=b.type,
                            text=b.text,
                            confidence=b.confidence,
                            quality_score=b.quality_score,
                            bounding_box=tb_box,
                            warnings=b.warnings,
                            metadata=b.metadata,
                        )
                    )

            # Convert Math Blocks from Module 4
            math_blocks: List[MathBlockSchema] = []
            if math_item:
                if math_item.warnings:
                    p_warnings.extend(math_item.warnings)
                for m in math_item.math_regions:
                    mb_box = BoundingBoxSchema(
                        x1=m.bounding_box.x1,
                        y1=m.bounding_box.y1,
                        x2=m.bounding_box.x2,
                        y2=m.bounding_box.y2,
                    )
                    # Convert symbols and structures to dicts for serialization
                    sym_dicts = [s.model_dump() for s in m.symbols]
                    struct_dicts = [st.model_dump() for st in m.structures]

                    math_blocks.append(
                        MathBlockSchema(
                            region_id=m.region_id,
                            bounding_box=mb_box,
                            recognized_text=m.recognized_text,
                            latex=m.latex,
                            confidence=m.confidence,
                            quality_score=m.quality_score,
                            is_readable=m.is_readable,
                            is_complete=m.is_complete,
                            requires_manual_review=m.requires_manual_review,
                            symbols=sym_dicts,
                            structures=struct_dicts,
                            warnings=m.warnings,
                            recognition_status=m.recognition_status,
                            engine_used=m.engine_used,
                        )
                    )

            # Deduplication & Correlation: link text blocks with math blocks
            for tb in text_blocks:
                for mb in math_blocks:
                    # Check ID linkage (e.g. math-page-1-block-2) or spatial IoU
                    is_linked = mb.region_id == f"math-{tb.block_id}" or compute_iou(tb.bounding_box, mb.bounding_box) >= 0.50
                    if is_linked:
                        tb.metadata["is_mathematical"] = True
                        tb.metadata["math_reference_id"] = mb.region_id

            # Determine Page Status
            is_page_failed = (
                (prep_item and prep_item.status == "failed")
                or (rec_item and rec_item.status == "failed")
                or (math_item and math_item.status == "failed")
            )
            is_page_degraded = (
                (rec_item and rec_item.status == "degraded")
                or (math_item and math_item.status == "degraded")
            )

            if is_page_failed:
                page_status = "failed"
                failed_count += 1
            elif is_page_degraded:
                page_status = "degraded"
                processed_count += 1
            elif p_warnings:
                page_status = "completed_with_warnings"
                processed_count += 1
            else:
                page_status = "completed"
                processed_count += 1

            page_schemas.append(
                PageResultSchema(
                    page_id=p_id,
                    page_number=p_num,
                    status=page_status,
                    width=p_width,
                    height=p_height,
                    image_path=orig_img,
                    enhanced_image_path=enh_img,
                    text_blocks=text_blocks,
                    math_blocks=math_blocks,
                    full_text=rec_item.full_text if rec_item else "",
                    combined_latex=math_item.combined_latex if math_item else "",
                    warnings=p_warnings,
                    metadata={
                        "contrast_score": prep_item.image_quality.contrast_score if prep_item and hasattr(prep_item, "image_quality") else None,
                        "orientation_corrected": prep_item.image_quality.orientation_corrected if prep_item and hasattr(prep_item, "image_quality") else False,
                        "skew_detected": prep_item.image_quality.corrected_skew_angle if prep_item and hasattr(prep_item, "image_quality") else 0.0,
                        "math_regions_count": len(math_blocks),
                        "text_blocks_count": len(text_blocks),
                    },
                )
            )

        # Determine Document-Level Status
        total_p = pdf_result.total_pages
        if failed_count == total_p and total_p > 0:
            doc_status = "failed"
        elif any(p.status == "degraded" for p in page_schemas):
            doc_status = "degraded"
        elif failed_count > 0 or any(p.status == "completed_with_warnings" for p in page_schemas) or all_warnings:
            doc_status = "completed_with_warnings"
        else:
            doc_status = "completed"

        # Document metadata mapping
        doc_meta = DocumentMetadataSchema(
            title=pdf_result.metadata.title,
            author=pdf_result.metadata.author,
            subject=pdf_result.metadata.subject,
            creator=pdf_result.metadata.creator,
            producer=pdf_result.metadata.producer,
            creation_date=pdf_result.metadata.creation_date,
            modification_date=pdf_result.metadata.modification_date,
        )

        # Processing summary mapping
        summary = ProcessingSummarySchema(
            total_pages=total_p,
            processed_pages=processed_count,
            failed_pages=failed_count,
            total_processing_time_ms=round(total_time_ms, 2),
            stage_durations_ms={k: round(v, 2) for k, v in stage_durations.items()},
        )

        return OCRDocumentResult(
            job_id=job_id,
            submission_id=submission_id,
            status=doc_status,
            document_metadata=doc_meta,
            processing_summary=summary,
            pages=page_schemas,
            warnings=all_warnings,
            errors=all_errors,
        )
