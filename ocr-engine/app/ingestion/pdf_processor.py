"""Main PDF-to-image processing pipeline."""

import logging
from pathlib import Path
from typing import List, Optional

import pymupdf

from app.ingestion.config import IngestionConfig, DEFAULT_CONFIG
from app.ingestion.exceptions import (
    PDFRenderingError,
    PathTraversalError,
)
from app.ingestion.metadata_extractor import MetadataExtractor
from app.ingestion.pdf_validator import PDFValidator
from app.ingestion.schemas import PageRecord, PDFProcessingResult

logger = logging.getLogger(__name__)


def process_pdf(
    pdf_path: str,
    submission_id: str,
    output_dir: str,
    config: Optional[IngestionConfig] = None,
) -> PDFProcessingResult:
    """Validate, inspect, and convert a student assignment PDF into high-quality page images.

    This service function:
    1. Validates the submission_id for path safety.
    2. Validates the input file (existence, size, magic bytes).
    3. Safely opens the PDF with PyMuPDF and validates document structure.
    4. Extracts document-level metadata.
    5. Sequentially renders each page into a high-quality PNG image at configured DPI.
    6. Saves rendered images in `{output_dir}/{submission_id}/pages/page_XXX.png`.
    7. Cleans up incomplete files if processing fails, without deleting the input PDF.
    8. Returns a structured `PDFProcessingResult` Pydantic model.

    Args:
        pdf_path: Path to the input PDF file.
        submission_id: Unique identifier for the submission.
        output_dir: Root directory where processed output should be saved.
        config: Optional configuration override (defaults to DEFAULT_CONFIG).

    Returns:
        PDFProcessingResult containing submission_id, total_pages, page records, and metadata.

    Raises:
        InvalidPDFError: If input is not a valid PDF.
        EmptyPDFError: If PDF file is 0 bytes.
        FileTooLargeError: If file exceeds maximum size limit.
        CorruptedPDFError: If PDF cannot be parsed.
        PasswordProtectedPDFError: If PDF is encrypted/password protected.
        ZeroPagesPDFError: If PDF contains no pages.
        PageLimitExceededError: If page count exceeds maximum configured limit.
        PDFRenderingError: If page rendering or image saving fails.
        PathTraversalError: If submission_id or output_dir contains traversal attacks.
    """
    cfg = config or DEFAULT_CONFIG
    validator = PDFValidator(config=cfg)

    # 1. Validate submission_id to prevent directory traversal
    clean_submission_id = validator.validate_submission_id(submission_id)

    # 2. Setup and validate output paths
    output_base = Path(output_dir)
    target_submission_dir = (output_base / clean_submission_id).resolve()
    base_resolved = output_base.resolve()

    # Prevent escaping base directory
    try:
        target_submission_dir.relative_to(base_resolved)
    except ValueError:
        raise PathTraversalError(f"Target directory escapes base output directory: '{submission_id}'")

    submission_pages_dir = target_submission_dir / "pages"
    submission_pages_dir.mkdir(parents=True, exist_ok=True)

    # 3. Validate file and document structure
    doc: Optional[pymupdf.Document] = None
    rendered_file_paths: List[Path] = []

    try:
        doc = validator.validate_document_structure(pdf_path)
        total_pages = doc.page_count

        # 4. Extract document metadata
        doc_metadata = MetadataExtractor.extract_document_metadata(doc)

        # 5. Render pages sequentially
        page_records: List[PageRecord] = []

        for page_idx in range(total_pages):
            page_num = page_idx + 1

            try:
                page = doc.load_page(page_idx)
            except Exception as load_err:
                raise PDFRenderingError(
                    f"Failed to load page {page_num} from PDF: {load_err}",
                    page_number=page_num,
                    original_error=str(load_err),
                ) from load_err

            # Render page to pixmap
            try:
                pix = page.get_pixmap(dpi=cfg.rendering_dpi)
            except Exception as render_err:
                raise PDFRenderingError(
                    f"Failed to render page {page_num} at {cfg.rendering_dpi} DPI: {render_err}",
                    page_number=page_num,
                    original_error=str(render_err),
                ) from render_err

            # Format image output path
            image_filename = cfg.image_name_pattern.format(page_number=page_num)
            page_image_path = submission_pages_dir / image_filename

            try:
                pix.save(str(page_image_path))
            except Exception as save_err:
                raise PDFRenderingError(
                    f"Failed to save rendered image for page {page_num}: {save_err}",
                    page_number=page_num,
                    original_error=str(save_err),
                ) from save_err

            rendered_file_paths.append(page_image_path)

            # Build relative image path for contract
            # Standard contract: e.g. "processed/{submission_id}/pages/page_001.png"
            if output_base.is_absolute():
                try:
                    rel_image_path = page_image_path.relative_to(Path.cwd()).as_posix()
                except ValueError:
                    rel_image_path = f"{output_base.name}/{clean_submission_id}/pages/{image_filename}"
            else:
                rel_image_path = (output_base / clean_submission_id / "pages" / image_filename).as_posix()

            orig_w, orig_h, rot = MetadataExtractor.extract_page_dimensions(page)

            page_records.append(
                PageRecord(
                    page_number=page_num,
                    image_path=rel_image_path,
                    width=pix.width,
                    height=pix.height,
                    original_width=orig_w,
                    original_height=orig_h,
                    rotation=rot,
                )
            )

        return PDFProcessingResult(
            submission_id=clean_submission_id,
            status="processed",
            total_pages=total_pages,
            pages=page_records,
            metadata=doc_metadata,
        )

    except Exception:
        # Failure cleanup: clean up incomplete rendered images from disk
        logger.error(
            "Processing failed for submission '%s'. Cleaning up %d partially rendered files.",
            clean_submission_id,
            len(rendered_file_paths),
        )
        for rendered_path in rendered_file_paths:
            try:
                if rendered_path.exists():
                    rendered_path.unlink()
            except OSError as cleanup_err:
                logger.warning("Failed to remove temporary file '%s': %s", rendered_path, cleanup_err)

        # Remove empty directories if no files remain
        try:
            if submission_pages_dir.exists() and not any(submission_pages_dir.iterdir()):
                submission_pages_dir.rmdir()
            if target_submission_dir.exists() and not any(target_submission_dir.iterdir()):
                target_submission_dir.rmdir()
        except OSError:
            pass

        raise

    finally:
        # Guarantee PDF document handle is closed
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass

