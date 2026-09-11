"""
Phase 2 - Image intake and validation.

Reworked from the request_package.py prototype in the Sofa-Cost-Estimation
repo: same core logic (load, validate size/format, resize, save + metadata),
but as importable functions instead of a top-level script, so it can be
called from an intake CLI or wired directly into the run_quote.py pipeline.
"""

import os
import json
from pathlib import Path

import cv2
from PIL import Image

ALLOWED_FORMATS = [".jpg", ".jpeg", ".png", ".webp"]
MIN_DIMENSION_PX = 100
PROCESSED_SIZE = (640, 640)


class ImageValidationError(ValueError):
    """Raised when an input image fails validation."""


def remove_image_background(image_path: str, output_path: str = None) -> str:
    """
    Removes background using rembg and composites onto a pure white background.
    Falls back to copying original image if rembg fails or is unavailable.
    """
    if output_path is None:
        p = Path(image_path)
        output_path = str(p.parent / f"{p.stem}_nobg{p.suffix}")

    try:
        from rembg import remove

        original_image = Image.open(image_path).convert("RGBA")
        removed = remove(original_image)
        white_background = Image.new("RGBA", removed.size, (255, 255, 255, 255))
        final_image = Image.alpha_composite(white_background, removed).convert("RGB")
        final_image.save(output_path, quality=95)
        return output_path
    except Exception as e:
        print(f"[image_processor] Background removal skipped ({e}), using original image.")
        return image_path


def validate_image_file(image_path):
    """
    Checks the image exists, is a supported format, and loads correctly.
    Returns the loaded image (BGR, as read by OpenCV).
    Raises FileNotFoundError / ImageValidationError instead of exiting.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    extension = os.path.splitext(image_path)[1].lower()
    if extension not in ALLOWED_FORMATS:
        raise ImageValidationError(
            f"Unsupported image format '{extension}'. Allowed: {ALLOWED_FORMATS}"
        )

    image = cv2.imread(image_path)
    if image is None:
        raise ImageValidationError(
            f"Image could not be loaded (corrupt or unreadable): {image_path}"
        )

    height, width = image.shape[:2]
    if width < MIN_DIMENSION_PX or height < MIN_DIMENSION_PX:
        raise ImageValidationError(
            f"Image too small ({width}x{height}px). "
            f"Minimum is {MIN_DIMENSION_PX}x{MIN_DIMENSION_PX}px."
        )

    return image


def process_image(image_path, request_folder, apply_bg_removal=False):
    """
    Validates the input image, then:
      - copies the original into request_folder/original_image<ext>
      - optionally creates background-removed image
      - saves a resized 640x640 copy as request_folder/processed_image<ext>
      - writes image_metadata.json

    Returns a dict with paths + metadata, so callers can wire it into a
    request summary without re-reading files from disk.
    """
    image = validate_image_file(image_path)
    height, width, channels = image.shape

    extension = os.path.splitext(image_path)[1].lower()
    os.makedirs(request_folder, exist_ok=True)

    original_dst = os.path.join(request_folder, f"original_image{extension}")
    cv2.imwrite(original_dst, image)

    target_for_yolo = original_dst
    nobg_dst = None
    if apply_bg_removal:
        nobg_dst = os.path.join(request_folder, f"background_removed{extension}")
        target_for_yolo = remove_image_background(original_dst, nobg_dst)

    proc_src = cv2.imread(target_for_yolo) if os.path.exists(target_for_yolo) else image
    processed_image = cv2.resize(proc_src, PROCESSED_SIZE)
    processed_dst = os.path.join(request_folder, f"processed_image{extension}")
    cv2.imwrite(processed_dst, processed_image)

    metadata = {
        "file_name": os.path.basename(image_path),
        "format": extension.replace(".", "").upper(),
        "original_width": width,
        "original_height": height,
        "channels": channels,
        "processed_size": list(PROCESSED_SIZE),
        "background_removed": apply_bg_removal and nobg_dst is not None and os.path.exists(nobg_dst),
    }

    metadata_path = os.path.join(request_folder, "image_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)

    return {
        "original_image_path": original_dst,
        "processed_image_path": processed_dst,
        "background_removed_path": nobg_dst if nobg_dst and os.path.exists(nobg_dst) else None,
        "metadata_path": metadata_path,
        "metadata": metadata,
    }
