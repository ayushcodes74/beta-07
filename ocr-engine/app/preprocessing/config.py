"""Configuration settings for Image Preprocessing Module 2."""

from pydantic import BaseModel, Field


class PreprocessingConfig(BaseModel):
    """Configuration options controlling the image enhancement pipeline."""

    # Orientation and Alignment
    enable_orientation_correction: bool = Field(
        default=True,
        description="Whether to detect and correct 90/180/270 degree rotation",
    )
    enable_deskew: bool = Field(
        default=True,
        description="Whether to detect and correct small skew angles",
    )
    max_deskew_angle: float = Field(
        default=15.0,
        description="Maximum rotation angle allowed during deskewing in degrees",
        ge=1.0,
        le=45.0,
    )
    deskew_min_angle: float = Field(
        default=0.5,
        description="Minimum skew angle required to trigger rotation correction",
        ge=0.0,
    )

    # Denoising
    enable_denoising: bool = Field(
        default=True,
        description="Whether to apply gentle edge-preserving denoising",
    )
    bilateral_d: int = Field(
        default=5,
        description="Diameter of pixel neighborhood for bilateral filtering",
    )
    bilateral_sigma_color: float = Field(
        default=30.0,
        description="Filter sigma in color space (small value preserves thin pen strokes)",
    )
    bilateral_sigma_space: float = Field(
        default=30.0,
        description="Filter sigma in coordinate space",
    )

    # Illumination and Contrast
    enable_contrast_enhancement: bool = Field(
        default=True,
        description="Whether to apply adaptive contrast and illumination normalization",
    )
    clahe_clip_limit: float = Field(
        default=2.0,
        description="Threshold for contrast limiting in CLAHE",
    )
    clahe_tile_grid_size: int = Field(
        default=8,
        description="Size of grid for histogram equalization",
    )

    # Variants Generation
    generate_grayscale: bool = Field(
        default=True,
        description="Whether to save a grayscale variant",
    )
    generate_thresholded: bool = Field(
        default=True,
        description="Whether to save an adaptive or Otsu thresholded binary variant",
    )
    thresholding_method: str = Field(
        default="adaptive",
        description="Binarization algorithm ('adaptive' or 'otsu')",
    )

    # Quality and Dimensions
    min_ocr_width: int = Field(
        default=600,
        description="Minimum width in pixels before flagging as low resolution",
    )
    min_ocr_height: int = Field(
        default=800,
        description="Minimum height in pixels before flagging as low resolution",
    )
    min_valid_width: int = Field(
        default=100,
        description="Minimum width for an image to be considered valid",
    )
    min_valid_height: int = Field(
        default=100,
        description="Minimum height for an image to be considered valid",
    )
    blur_threshold: float = Field(
        default=80.0,
        description="Laplacian variance below which an image is flagged as potentially blurry",
    )
    blank_std_threshold: float = Field(
        default=8.0,
        description="Grayscale standard deviation below which a page is considered blank",
    )


DEFAULT_PREPROCESSING_CONFIG = PreprocessingConfig()

