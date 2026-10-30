"""Image loading and persistence utilities."""

from pathlib import Path
import cv2
import numpy as np

from app.preprocessing.exceptions import ImageLoadError, ImageSaveError


class ImageLoader:
    """Safe image loading and writing service compatible with Windows paths."""

    @staticmethod
    def load_image(image_path: str | Path) -> np.ndarray:
        """Load an image file safely into an OpenCV BGR numpy array.

        Uses np.fromfile + cv2.imdecode to reliably handle Windows unicode paths.

        Args:
            image_path: Path to the image file.

        Returns:
            Decoded BGR image as numpy array.

        Raises:
            ImageLoadError: If the image cannot be read or decoded.
        """
        path = Path(image_path).resolve()
        try:
            data = np.fromfile(str(path), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                raise ImageLoadError(f"Failed to decode image from '{image_path}'.")
            return img
        except Exception as e:
            if isinstance(e, ImageLoadError):
                raise
            raise ImageLoadError(f"Error loading image from '{image_path}': {e}") from e

    @staticmethod
    def save_image(image: np.ndarray, output_path: str | Path, ext: str = ".png") -> Path:
        """Save a BGR or grayscale numpy image to disk safely.

        Args:
            image: Image numpy array.
            output_path: Destination path.
            ext: File extension (e.g. '.png').

        Returns:
            Resolved Path of the saved image.

        Raises:
            ImageSaveError: If saving the image fails.
        """
        path = Path(output_path).resolve()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            success, encoded_img = cv2.imencode(ext, image)
            if not success or encoded_img is None:
                raise ImageSaveError(f"Failed to encode image for '{output_path}'.")
            with open(path, "wb") as f:
                f.write(encoded_img.tobytes())
            return path
        except Exception as e:
            if isinstance(e, ImageSaveError):
                raise
            raise ImageSaveError(f"Error saving image to '{output_path}': {e}") from e

