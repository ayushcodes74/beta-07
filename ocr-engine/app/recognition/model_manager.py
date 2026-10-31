"""Model lifecycle manager providing singleton caching, CPU/GPU selection, and model abstraction."""

import logging
from typing import Any, Dict, Optional, Tuple
import cv2
import numpy as np

from app.recognition.config import RecognitionConfig, DEFAULT_RECOGNITION_CONFIG
from app.recognition.exceptions import (
    HandwritingRecognitionError,
    ModelLoadingError,
    PrintedRecognitionError,
)

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

        logger.info("Initializing OCR engines on device '%s'...", self.device)

        try:
            # 1. Attempt TrOCR loading for handwriting
            if self.config.backend in ("auto", "trocr"):
                self._load_trocr_model()

            # 2. Attempt PaddleOCR loading for printed typography
            if self.config.backend in ("auto", "paddleocr"):
                self._load_paddle_model()

            self._initialized = True
            logger.info(
                "OCR engines initialized. Handwriting: %s, Printed: %s",
                self.handwriting_engine_status,
                self.printed_engine_status,
            )
        except Exception as e:
            if isinstance(e, ModelLoadingError):
                raise
            raise ModelLoadingError(f"Failed to initialize recognition models: {e}") from e

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
        """Attempt loading PaddleOCR if installed in the environment."""
        try:
            from paddleocr import PaddleOCR

            use_gpu = self.device == "cuda"
            logger.info("Loading PaddleOCR (lang='en', use_gpu=%s)...", use_gpu)
            ocr = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                use_gpu=use_gpu,
                show_log=False,
            )
            self.printed_engine = ocr
            self.printed_engine_status = "loaded"
            self.printed_model_version = self.config.printed_model_name
            self.printed_error_msg = None
            logger.info("PaddleOCR engine loaded successfully.")

        except Exception as e:
            self.printed_engine = None
            self.printed_engine_status = "unavailable"
            self.printed_error_msg = f"{type(e).__name__}: {e}"
            logger.warning("PaddleOCR engine could not be loaded: %s", self.printed_error_msg)
            if not self.config.allow_degraded_fallback:
                raise ModelLoadingError(f"Failed to load PaddleOCR engine: {e}") from e

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
                bgr_crop = crop
                if len(crop.shape) == 2:
                    bgr_crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)

                ocr_results = self.printed_engine.ocr(bgr_crop, cls=True)

                lines = []
                confs = []
                if ocr_results and ocr_results[0]:
                    for line_info in ocr_results[0]:
                        if len(line_info) >= 2 and len(line_info[1]) >= 2:
                            txt, score = line_info[1][0], float(line_info[1][1])
                            lines.append(txt)
                            confs.append(score)

                text = " ".join(lines).strip()
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
