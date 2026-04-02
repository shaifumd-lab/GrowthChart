"""
Image file OCR extraction for GrowthChart v2.

Accepts image files (.jpg, .png, .bmp, .tiff) and extracts patient data
using Tesseract OCR → Hebrew text processing → measurement extraction.

Reuses the full ValidatedPDFExtractor pipeline for text parsing.
"""

import os
from pathlib import Path
from datetime import date
from typing import Dict, Optional, Any

try:
    from PIL import Image, ImageFilter, ExifTags
except ImportError:
    Image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from importers.pdf_extractor import (
    ValidatedPDFExtractor,
    _extract_parental_heights,
    _extract_bone_age,
    _validate_height,
    _validate_weight,
    _validate_date,
)
from config import TESSERACT_CMD


# ── Constants ────────────────────────────────────────────────

SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}

# Minimum width for decent OCR (~300 DPI on an A4 page)
MIN_OCR_WIDTH = 2000


class ImageExtractor:
    """Extract patient data from image files using OCR."""

    def __init__(self):
        if pytesseract is None:
            raise ImportError("pytesseract is required for image OCR")
        if Image is None:
            raise ImportError("Pillow is required for image processing")

        # Configure Tesseract path
        if os.path.isfile(TESSERACT_CMD):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

        # Reuse the PDF extractor's text-parsing pipeline
        self._pdf_extractor = ValidatedPDFExtractor()

    def extract(self, image_path: str, patient_birth_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Extract patient data from an image file.

        Args:
            image_path: Path to image file
            patient_birth_date: Optional DOB for age-appropriate validation

        Returns:
            Same structured dict as ValidatedPDFExtractor.extract()
        """
        path = Path(image_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {image_path}"}

        ext = path.suffix.lower()
        if ext not in SUPPORTED_IMAGE_EXTENSIONS:
            return {"success": False, "error": f"Unsupported image type: {ext}"}

        try:
            # 1. Load and preprocess image
            img = self._load_and_preprocess(image_path)

            # 2. Run OCR (Hebrew + English)
            text = self._run_ocr(img)

            if not text or len(text.strip()) < 10:
                return {
                    "success": False,
                    "error": "OCR could not extract meaningful text from image",
                    "raw_text": text or "",
                }

            # 3. Feed OCR text through the PDF extractor's text-parsing pipeline
            result = self._pdf_extractor.extract_from_text(
                text, patient_birth_date=patient_birth_date
            )

            # Add image-specific metadata
            result["import_type"] = "image_ocr"
            result["source_file"] = str(path.name)
            result["raw_text"] = text[:2000]  # First 2000 chars for debugging

            return result

        except Exception as e:
            return {"success": False, "error": f"Image extraction failed: {str(e)}"}

    def _load_and_preprocess(self, image_path: str) -> Image.Image:
        """Load image, fix orientation, convert to grayscale, enhance for OCR."""
        img = Image.open(image_path)

        # Auto-rotate using EXIF orientation tag
        img = self._fix_exif_rotation(img)

        # Convert to RGB if needed (handles RGBA, palette, etc.)
        if img.mode not in ('L', 'RGB'):
            img = img.convert('RGB')

        # Convert to grayscale for OCR
        if img.mode == 'RGB':
            gray = img.convert('L')
        else:
            gray = img

        # Upscale if too small for reliable OCR
        if gray.width < MIN_OCR_WIDTH:
            scale = MIN_OCR_WIDTH / gray.width
            new_size = (int(gray.width * scale), int(gray.height * scale))
            gray = gray.resize(new_size, Image.LANCZOS)

        # Enhance contrast using adaptive thresholding (if OpenCV available)
        if HAS_CV2:
            gray = self._adaptive_threshold(gray)
        else:
            # Fallback: simple sharpen + contrast
            gray = gray.filter(ImageFilter.SHARPEN)

        return gray

    def _fix_exif_rotation(self, img: Image.Image) -> Image.Image:
        """Auto-rotate image based on EXIF orientation tag."""
        try:
            exif = img._getexif()
            if exif is None:
                return img
            # Find orientation tag
            orientation_key = None
            for key, val in ExifTags.TAGS.items():
                if val == 'Orientation':
                    orientation_key = key
                    break
            if orientation_key is None or orientation_key not in exif:
                return img
            orientation = exif[orientation_key]
            rotations = {
                3: 180,
                6: 270,
                8: 90,
            }
            if orientation in rotations:
                img = img.rotate(rotations[orientation], expand=True)
        except (AttributeError, KeyError, TypeError):
            pass
        return img

    def _adaptive_threshold(self, pil_img: Image.Image) -> Image.Image:
        """Apply adaptive thresholding via OpenCV for better OCR on photos."""
        arr = np.array(pil_img)

        # Denoise
        arr = cv2.fastNlMeansDenoising(arr, h=10)

        # Adaptive threshold — works well on photos of printed text
        arr = cv2.adaptiveThreshold(
            arr, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=31,
            C=10,
        )

        return Image.fromarray(arr)

    def _run_ocr(self, img: Image.Image) -> str:
        """Run Tesseract OCR with Hebrew + English."""
        # Try PSM 6 (uniform block) first — good for data tables
        text_block = pytesseract.image_to_string(
            img, lang="heb+eng", config="--psm 6"
        )

        # If result is very short, try PSM 3 (auto) which handles mixed layouts
        if len(text_block.strip()) < 30:
            text_auto = pytesseract.image_to_string(
                img, lang="heb+eng", config="--psm 3"
            )
            if len(text_auto.strip()) > len(text_block.strip()):
                return text_auto

        return text_block


def is_image_file(filename: str) -> bool:
    """Check if a filename has a supported image extension."""
    return Path(filename).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
