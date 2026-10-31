"""Model lifecycle manager providing singleton caching, CPU/GPU selection, and model abstraction."""

import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

from app.recognition.config import RecognitionConfig, DEFAULT_RECOGNITION_CONFIG
from app.recognition.exceptions import (
    HandwritingRecognitionError,
    ModelLoadingError,
    PrintedRecognitionError,
)
from app.recognition.ocr_space import OCRSpaceClient

logger = logging.getLogger(__name__)


class ModelManager:
    """Singleton model lifecycle manager for printed text and handwriting OCR engines."""

    _instance: Optional["ModelManager"] = None

    def __init__(self, config: Optional[RecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_RECOGNITION_CONFIG
        self.device = self._resolve_device(self.config.device)
        self.printed_engine = None
        self.handwriting_engine = None

        # Tracking statuses and versions for honest metadata reporting
        self.handwriting_engine_status: str = "uninitialized"  # "loaded", "unavailable", "failed"
        self.printed_engine_status: str = "uninitialized"
        self.handwriting_error_msg: Optional[str] = None
        self.printed_error_msg: Optional[str] = None
        self.handwriting_model_version: Optional[str] = None
        self.printed_model_version: Optional[str] = None

        # OCR.space cloud OCR (backend "ocrspace")
        self.ocr_space_client: Optional[OCRSpaceClient] = None
        self.ocr_space_status: str = "uninitialized"
        self.ocr_space_error_msg: Optional[str] = None

        # "v3" -> PaddleOCR 3.x `predict()` API, "v2" -> legacy 2.x `ocr()` API
        self._paddle_api: str = "v3"
        # Paddle predictors are not thread-safe; the job manager runs pages on a thread pool.
        self._paddle_lock = threading.Lock()
        self._init_lock = threading.Lock()

        self._initialized = False

    @classmethod
    def get_instance(cls, config: Optional[RecognitionConfig] = None) -> "ModelManager":
        """Get or create the singleton ModelManager instance."""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for unit testing)."""
        cls._instance = None

    def _resolve_device(self, requested_device: str) -> str:
        """Select CUDA if available and requested, otherwise fall back to CPU."""
        if requested_device.lower() in ("auto", "cuda"):
            try:
                import torch

                if torch.cuda.is_available():
                    return "cuda"
            except ImportError:
                pass
        return "cpu"

    def initialize_models(self) -> None:
        """Load and cache recognition models into memory once."""
        if self._initialized:
            return

        with self._init_lock:
            if self._initialized:
                return

            logger.info("Initializing OCR engines (backend='%s', device='%s')...", self.config.backend, self.device)

            try:
                # 1. TrOCR handwriting model (legacy hybrid / trocr backends only)
                if self.config.backend in ("auto", "trocr"):
                    self._load_trocr_model()
                else:
                    self.handwriting_engine_status = "disabled"

                # 2. PaddleOCR (primary local engine; fallback for OCR.space)
                if self.config.backend in ("auto", "paddleocr", "ocrspace"):
                    self._load_paddle_model()
                else:
                    self.printed_engine_status = "disabled"

                # 3. OCR.space cloud OCR
                if self.config.backend == "ocrspace":
                    self._init_ocr_space()
                else:
                    self.ocr_space_status = "disabled"

                self._initialized = True
                logger.info(
                    "OCR engines initialized. Handwriting: %s, PaddleOCR: %s",
                    self.handwriting_engine_status,
                    self.printed_engine_status,
                )
            except Exception as e:
                if isinstance(e, ModelLoadingError):
                    raise
                raise ModelLoadingError(f"Failed to initialize recognition models: {e}") from e

    def _init_ocr_space(self) -> None:
        """Create the OCR.space client if an API key is configured (no network call here)."""
        if not self.config.ocr_space_api_key:
            self.ocr_space_client = None
            self.ocr_space_status = "unavailable"
            self.ocr_space_error_msg = "OCR_SPACE_API_KEY is not set; using local PaddleOCR"
            logger.warning("OCR.space backend selected but OCR_SPACE_API_KEY is not set; using local PaddleOCR.")
            return
        self.ocr_space_client = OCRSpaceClient(
            api_key=self.config.ocr_space_api_key,
            endpoint=self.config.ocr_space_endpoint,
            engine=self.config.ocr_space_engine,
            timeout_seconds=self.config.ocr_space_timeout_seconds,
            max_upload_bytes=self.config.ocr_space_max_upload_bytes,
        )
        self.ocr_space_status = "loaded"
        self.ocr_space_error_msg = None
        logger.info("OCR.space client configured (engine %d).", self.config.ocr_space_engine)

    @property
    def uses_paddle_page_mode(self) -> bool:
        """True when whole pages should be detected and recognized by PaddleOCR."""
        return self.config.backend in ("paddleocr", "ocrspace") and self.printed_engine is not None

    @property
    def uses_ocr_space(self) -> bool:
        return self.config.backend == "ocrspace" and self.ocr_space_client is not None

    def _load_trocr_model(self) -> None:
        """Attempt loading TrOCR via HuggingFace transformers and PyTorch."""
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            import torch

            logger.info("Loading TrOCR model '%s' on device '%s'...", self.config.handwriting_model_name, self.device)
            processor = TrOCRProcessor.from_pretrained(self.config.handwriting_model_name)
            model = VisionEncoderDecoderModel.from_pretrained(self.config.handwriting_model_name)
            model.to(self.device)
            model.eval()

            self.handwriting_engine = (processor, model)
            self.handwriting_engine_status = "loaded"
            self.handwriting_model_version = self.config.handwriting_model_name
            self.handwriting_error_msg = None
            logger.info("TrOCR model loaded successfully.")

        except Exception as e:
            self.handwriting_engine = None
            self.handwriting_engine_status = "unavailable"
            self.handwriting_error_msg = f"{type(e).__name__}: {e}"
            logger.warning("TrOCR model could not be loaded: %s", self.handwriting_error_msg)
            if not self.config.allow_degraded_fallback:
                raise ModelLoadingError(
                    f"Failed to load TrOCR model '{self.config.handwriting_model_name}': {e}"
                ) from e

    def _load_paddle_model(self) -> None:
        """Load PaddleOCR, supporting both the 3.x and legacy 2.x constructor APIs."""
        try:
            # Skip PaddleX's slow model-hoster connectivity probe on every start-up.
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            import paddleocr
            from paddleocr import PaddleOCR

            version = str(getattr(paddleocr, "__version__", "3"))
            major_str = version.split(".")[0]
            major = int(major_str) if major_str.isdigit() else 3

            if major >= 3:
                device = "gpu:0" if self.device == "cuda" else "cpu"
                logger.info(
                    "Loading PaddleOCR %s (det=%s, rec=%s, device=%s, mkldnn=%s)...",
                    version,
                    self.config.paddle_det_model_name,
                    self.config.paddle_rec_model_name,
                    device,
                    self.config.paddle_enable_mkldnn,
                )
                ocr = PaddleOCR(
                    text_detection_model_name=self.config.paddle_det_model_name,
                    text_recognition_model_name=self.config.paddle_rec_model_name,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=self.config.paddle_use_textline_orientation,
                    device=device,
                    enable_mkldnn=self.config.paddle_enable_mkldnn,
                )
                self._paddle_api = "v3"
                self.printed_model_version = (
                    f"{self.config.paddle_det_model_name}+{self.config.paddle_rec_model_name}"
                )
            else:
                use_gpu = self.device == "cuda"
                logger.info("Loading legacy PaddleOCR %s (lang='en', use_gpu=%s)...", version, use_gpu)
                ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=use_gpu, show_log=False)
                self._paddle_api = "v2"
                self.printed_model_version = self.config.printed_model_name

            self.printed_engine = ocr
            self.printed_engine_status = "loaded"
            self.printed_error_msg = None
            logger.info("PaddleOCR engine loaded successfully.")

        except Exception as e:
            self.printed_engine = None
            self.printed_engine_status = "unavailable"
            self.printed_error_msg = f"{type(e).__name__}: {e}"
            logger.warning("PaddleOCR engine could not be loaded: %s", self.printed_error_msg)
            if not self.config.allow_degraded_fallback:
                raise ModelLoadingError(f"Failed to load PaddleOCR engine: {e}") from e

    def _paddle_predict(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """Run PaddleOCR on a BGR image and return normalized line results.

        Returns a list of ``{"text", "score", "box": (x1, y1, x2, y2)}`` dicts in Paddle's output order,
        with boxes clamped to the image bounds.
        """
        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        image = np.ascontiguousarray(image)

        lines: List[Dict[str, Any]] = []
        with self._paddle_lock:
            if self._paddle_api == "v2":
                raw = self.printed_engine.ocr(image, cls=True)
                for item in (raw[0] if raw and raw[0] else []):
                    if len(item) < 2 or len(item[1]) < 2:
                        continue
                    pts = np.asarray(item[0], dtype=float).reshape(-1, 2)
                    lines.append(
                        {
                            "text": str(item[1][0]),
                            "score": float(item[1][1]),
                            "box": (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()),
                        }
                    )
            else:
                for res in self.printed_engine.predict(image) or []:
                    texts = list(res["rec_texts"])
                    scores = list(res["rec_scores"])
                    boxes = res.get("rec_boxes")
                    if boxes is None or len(boxes) != len(texts):
                        polys = [np.asarray(p, dtype=float).reshape(-1, 2) for p in res["rec_polys"]]
                        boxes = [(p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()) for p in polys]
                    for txt, sc, bx in zip(texts, scores, boxes):
                        lines.append({"text": str(txt), "score": float(sc), "box": tuple(bx)})

        h, w = image.shape[:2]
        for ln in lines:
            x1, y1, x2, y2 = (int(round(float(v))) for v in ln["box"])
            ln["box"] = (max(0, min(x1, w)), max(0, min(y1, h)), max(0, min(x2, w)), max(0, min(y2, h)))
        return lines

    def recognize_page_lines(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """Detect and recognize every text line on a full page image with PaddleOCR.

        Lines with empty text, degenerate boxes, or a score below ``config.paddle_min_score`` are discarded.

        Raises:
            PrintedRecognitionError: If PaddleOCR is not loaded or inference fails.
        """
        if self.printed_engine is None:
            raise PrintedRecognitionError(
                f"PaddleOCR is not loaded: {self.printed_error_msg or 'engine unavailable'}"
            )
        if image is None or image.size == 0:
            return []
        try:
            lines = self._paddle_predict(image)
        except Exception as e:
            logger.error("PaddleOCR page inference failed: %s", e)
            raise PrintedRecognitionError(f"PaddleOCR inference failed: {e}") from e

        return [
            ln
            for ln in lines
            if ln["text"].strip()
            and ln["score"] >= self.config.paddle_min_score
            and ln["box"][2] > ln["box"][0]
            and ln["box"][3] > ln["box"][1]
        ]

    def recognize_handwriting_crop(
        self, crop: np.ndarray
    ) -> Tuple[str, Optional[float], Optional[float], Dict[str, Any]]:
        """Recognize handwritten text from a cropped image array.

        Returns:
            Tuple of (text, model_confidence, quality_score, metadata).
            - text: Transcribed text if genuine model ran, or empty string if degraded.
            - model_confidence: Model token probability, or None if uncalibrated/unavailable.
            - quality_score: Objective image contrast/stroke quality estimate (0.0 to 1.0).
            - metadata: Machine-readable diagnostic dictionary.
        """
        if crop is None or crop.size == 0:
            return "", None, 0.0, {
                "engine_used": "none",
                "is_fallback": True,
                "recognition_mode": "empty_crop",
                "recognition_available": False,
                "model_version": None,
            }

        quality_score = self._compute_image_quality_score(crop)

        # 1. Genuine TrOCR Inference Path
        if self.handwriting_engine is not None:
            try:
                processor, model = self.handwriting_engine
                from PIL import Image
                import torch

                # Convert crop to RGB PIL image
                if len(crop.shape) == 2:
                    rgb_crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2RGB)
                elif crop.shape[2] == 4:
                    rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGRA2RGB)
                else:
                    rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

                pil_img = Image.fromarray(rgb_crop)
                pixel_values = processor(images=pil_img, return_tensors="pt").pixel_values.to(self.device)

                with torch.no_grad():
                    outputs = model.generate(
                        pixel_values,
                        return_dict_in_generate=True,
                        output_scores=True,
                        max_new_tokens=getattr(self.config, "max_target_tokens", 64),
                    )

                generated_ids = outputs.sequences
                text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

                # Calculate genuine model confidence from output logits
                confidence = self._compute_trocr_confidence(model, outputs)

                meta = {
                    "engine_used": "trocr",
                    "model_version": self.handwriting_model_version,
                    "is_fallback": False,
                    "recognition_mode": "deep_learning_inference",
                    "recognition_available": True,
                    "device": self.device,
                }
                return text, confidence, quality_score, meta

            except Exception as e:
                logger.error("TrOCR inference failed on image crop: %s", e)
                raise HandwritingRecognitionError(f"TrOCR inference failed: {e}") from e

        # 2. Honest Degraded Fallback Path (No model available)
        # NEVER return hardcoded placeholder words!
        meta = {
            "engine_used": "none",
            "model_version": None,
            "is_fallback": True,
            "recognition_mode": "degraded_layout_only",
            "recognition_available": False,
            "device": self.device,
            "reason": self.handwriting_error_msg or "TrOCR not loaded in environment",
        }
        return "", None, quality_score, meta

    def recognize_printed_crop(
        self, crop: np.ndarray
    ) -> Tuple[str, Optional[float], Optional[float], Dict[str, Any]]:
        """Recognize printed text from a cropped image array.

        Returns:
            Tuple of (text, model_confidence, quality_score, metadata).
            - text: Transcribed text if genuine model ran, or empty string if degraded.
            - model_confidence: Model score, or None if uncalibrated/unavailable.
            - quality_score: Objective image contrast/stroke quality estimate (0.0 to 1.0).
            - metadata: Machine-readable diagnostic dictionary.
        """
        if crop is None or crop.size == 0:
            return "", None, 0.0, {
                "engine_used": "none",
                "is_fallback": True,
                "recognition_mode": "empty_crop",
                "recognition_available": False,
                "model_version": None,
            }

        quality_score = self._compute_image_quality_score(crop)

        # 1. Genuine PaddleOCR Inference Path
        if self.printed_engine is not None:
            try:
                results = self._paddle_predict(crop)
                text = " ".join(r["text"] for r in results).strip()
                confs = [r["score"] for r in results]
                confidence = round(float(np.mean(confs)), 4) if confs else None

                meta = {
                    "engine_used": "paddleocr",
                    "model_version": self.printed_model_version,
                    "is_fallback": False,
                    "recognition_mode": "deep_learning_inference",
                    "recognition_available": True,
                    "device": self.device,
                }
                return text, confidence, quality_score, meta

            except Exception as e:
                logger.error("PaddleOCR inference failed on image crop: %s", e)
                raise PrintedRecognitionError(f"PaddleOCR inference failed: {e}") from e

        # 2. Honest Degraded Fallback Path (No model available)
        # NEVER return hardcoded placeholder words!
        meta = {
            "engine_used": "none",
            "model_version": None,
            "is_fallback": True,
            "recognition_mode": "degraded_layout_only",
            "recognition_available": False,
            "device": self.device,
            "reason": self.printed_error_msg or "PaddleOCR not loaded in environment",
        }
        return "", None, quality_score, meta

    def _compute_trocr_confidence(self, model: Any, outputs: Any) -> Optional[float]:
        """Compute mean sequence probability from TrOCR output logits."""
        try:
            import torch

            # 1. Preferred method: compute_transition_scores
            if hasattr(model, "compute_transition_scores") and hasattr(outputs, "scores") and outputs.scores:
                transition_scores = model.compute_transition_scores(
                    outputs.sequences, outputs.scores, normalize_logits=True
                )
                probs = torch.exp(transition_scores[0]).detach().cpu().numpy()
                if len(probs) > 0:
                    return round(float(np.mean(probs)), 4)

            # 2. Fallback: mean of top softmax probabilities across output tokens
            if hasattr(outputs, "scores") and outputs.scores:
                token_probs = []
                for step_logits in outputs.scores:
                    probs = torch.softmax(step_logits, dim=-1)
                    max_prob = torch.max(probs, dim=-1).values.item()
                    token_probs.append(max_prob)
                if token_probs:
                    return round(float(np.mean(token_probs)), 4)

        except Exception as e:
            logger.debug("Could not compute TrOCR token confidence: %s", e)

        return None

    def _compute_image_quality_score(self, crop: np.ndarray) -> float:
        """Estimate visual contrast and ink quality of a text region crop.

        This is an objective image heuristic (0.0 to 1.0), NOT an OCR recognition confidence score.
        """
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        h, w = gray.shape
        total_pixels = h * w
        if total_pixels == 0:
            return 0.0

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink_pixels = np.count_nonzero(binary)

        # Nearly empty or blank crop
        if ink_pixels < 10:
            return 0.10

        density = float(ink_pixels) / float(total_pixels)
        if density < 0.01:
            return 0.20

        std_val = float(np.std(gray))
        # Standard contrast mapping
        quality = min(0.95, max(0.20, std_val / 45.0))
        return round(quality, 2)
