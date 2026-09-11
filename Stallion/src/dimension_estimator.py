"""
Image-Assisted Dimension Estimation (Phase 3 Extension)

Given a sofa photo already validated by CLIP/YOLOv8 and one user-provided
anchor dimension (overall_length_mm), estimates the sofa's approximate height
using the image silhouette's aspect ratio, as an editable suggestion.

HONEST SCOPE:
  - Input: detection output (bbox, image dims) + user's known length
  - Output: estimated height_mm as a suggestion (marked estimated: true)
  - Never auto-submit; always require user confirmation
  - Confidence gating: suppress estimate if sofa angle extreme or image cropped

DOES NOT ATTEMPT:
  - Multi-view or depth estimation
  - Internal component inference (frame, springs, etc.)
  - Perspective/lens correction
  - Absolute precision (typical error ±10-20% depending on angle)
"""

import math
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class DimensionEstimate:
    """Estimated sofa dimension with confidence and metadata."""
    
    estimated_height_mm: float          # Suggested overall_height_mm
    confidence_score: float             # 0.0–1.0; confidence in the estimate
    pixel_width: int                    # Sofa's pixel width in the image
    pixel_height: int                   # Sofa's pixel height in the image
    image_width: int                    # Original image width
    image_height: int                   # Original image height
    aspect_ratio: float                 # pixel_width / pixel_height
    anchor_length_mm: float             # User-provided length_mm
    
    # Fields with defaults (must come after fields without defaults)
    estimated: bool = True              # Always True for this module
    suppression_reason: Optional[str] = None  # If estimate is unreliable, why?


def estimate_height_from_bbox(
    bbox: list,
    image_width: int,
    image_height: int,
    anchor_length_mm: float,
) -> DimensionEstimate:
    """
    Estimate overall_height_mm from a sofa's bounding box and a known length.
    
    Parameters
    ----------
    bbox : list
        [x1, y1, x2, y2] in pixel coordinates (from YOLOv8)
    image_width : int
        Original image width in pixels
    image_height : int
        Original image height in pixels
    anchor_length_mm : float
        User-provided sofa length in mm (most confident dimension)
    
    Returns
    -------
    DimensionEstimate
        Contains estimated_height_mm, confidence_score, and diagnostics.
        If confidence < 0.5, suppression_reason will explain why.
    """
    
    x1, y1, x2, y2 = bbox
    pixel_width = x2 - x1
    pixel_height = y2 - y1
    
    if pixel_width <= 0 or pixel_height <= 0:
        return DimensionEstimate(
            estimated_height_mm=0.0,
            confidence_score=0.0,
            pixel_width=pixel_width,
            pixel_height=pixel_height,
            image_width=image_width,
            image_height=image_height,
            aspect_ratio=0.0,
            anchor_length_mm=anchor_length_mm,
            suppression_reason="Invalid bounding box (zero or negative dimension)",
        )
    
    aspect_ratio = pixel_width / pixel_height
    
    # Core estimation: height_mm = length_mm × (pixel_height / pixel_width)
    estimated_height_mm = anchor_length_mm / aspect_ratio
    
    # Confidence gating: when to trust the estimate
    confidence_score = 1.0
    suppression_reason = None
    
    # Gate 1: Sofa should occupy a reasonable fraction of the image
    # (not tiny thumbnail, not filling entire frame)
    bbox_fill_ratio = (pixel_width * pixel_height) / (image_width * image_height)
    if bbox_fill_ratio < 0.05:
        # Sofa is <5% of image — too small for reliable silhouette
        confidence_score = 0.3
        suppression_reason = "Sofa is too small in image (thumbnail size)"
    elif bbox_fill_ratio > 0.95:
        # Sofa fills almost entire image — likely cropped or extreme angle
        confidence_score = 0.2
        suppression_reason = "Sofa fills most of the image (possible crop or extreme angle)"
    
    # Gate 2: Image should be roughly front-on for valid aspect ratio
    # If image is extremely narrow or wide, aspect ratio is unreliable
    image_aspect_ratio = image_width / image_height if image_height > 0 else 1.0
    if image_aspect_ratio < 0.5 or image_aspect_ratio > 2.5:
        if confidence_score > 0.5:  # Only downgrade if not already failed Gate 1
            confidence_score = 0.4
            suppression_reason = "Image aspect ratio extreme (unusual camera angle or crop)"
    
    # Gate 3: Sofa aspect ratio should be plausible for standard sofas
    # Standard sofas typically: 0.6 (armchair) to 2.5 (4-seater) width/height
    if aspect_ratio < 0.5 or aspect_ratio > 3.5:
        if confidence_score > 0.5:
            confidence_score = 0.35
            suppression_reason = f"Sofa aspect ratio {aspect_ratio:.2f} is extreme (possible non-standard angle)"
    
    # Gate 4: Estimated height should be in a reasonable range
    # Assuming standard sofas: 700–1100mm height
    if estimated_height_mm < 300 or estimated_height_mm > 1800:
        if confidence_score > 0.5:
            confidence_score = 0.3
            suppression_reason = f"Estimated height {estimated_height_mm:.0f}mm is outside typical range (300–1800mm)"
    
    return DimensionEstimate(
        estimated_height_mm=estimated_height_mm,
        confidence_score=max(0.0, confidence_score),  # Ensure non-negative
        pixel_width=pixel_width,
        pixel_height=pixel_height,
        image_width=image_width,
        image_height=image_height,
        aspect_ratio=aspect_ratio,
        anchor_length_mm=anchor_length_mm,
        suppression_reason=suppression_reason,
    )


def estimate_from_sofa_analysis(
    sofa_analysis: Dict[str, Any],
    anchor_length_mm: float,
) -> DimensionEstimate:
    """
    Convenience function: extract bbox and image dims from sofa_analysis.json
    (output of validate_sofa) and estimate height.
    
    Parameters
    ----------
    sofa_analysis : dict
        Output dict from validate_sofa() with keys: bbox, image_width, image_height
    anchor_length_mm : float
        User-provided overall_length_mm
    
    Returns
    -------
    DimensionEstimate
    """
    if not sofa_analysis.get("validation_passed"):
        return DimensionEstimate(
            estimated_height_mm=0.0,
            confidence_score=0.0,
            pixel_width=0,
            pixel_height=0,
            image_width=sofa_analysis.get("image_width", 0),
            image_height=sofa_analysis.get("image_height", 0),
            aspect_ratio=0.0,
            anchor_length_mm=anchor_length_mm,
            suppression_reason="Sofa validation failed",
        )
    
    bbox = sofa_analysis.get("bbox")
    if not bbox or len(bbox) != 4:
        return DimensionEstimate(
            estimated_height_mm=0.0,
            confidence_score=0.0,
            pixel_width=0,
            pixel_height=0,
            image_width=sofa_analysis.get("image_width", 0),
            image_height=sofa_analysis.get("image_height", 0),
            aspect_ratio=0.0,
            anchor_length_mm=anchor_length_mm,
            suppression_reason="No valid bounding box in analysis",
        )
    
    return estimate_height_from_bbox(
        bbox=bbox,
        image_width=sofa_analysis.get("image_width", 0),
        image_height=sofa_analysis.get("image_height", 0),
        anchor_length_mm=anchor_length_mm,
    )


def format_estimate_for_api_response(estimate: DimensionEstimate) -> Dict[str, Any]:
    """
    Convert DimensionEstimate to API response format.
    
    Returns a dict suitable for JSON serialization, with fields marked
    for UI distinction (estimated: true/false).
    """
    response = {
        "overall_height_mm": {
            "value": round(estimate.estimated_height_mm, 1),
            "estimated": True,
            "confidence": round(estimate.confidence_score, 2),
        },
        "suppressed": estimate.confidence_score < 0.5,
    }
    
    if estimate.suppression_reason:
        response["reason_not_estimated"] = estimate.suppression_reason
    
    # Diagnostic metadata (for logging/validation)
    response["_diagnostics"] = {
        "pixel_width": estimate.pixel_width,
        "pixel_height": estimate.pixel_height,
        "image_width": estimate.image_width,
        "image_height": estimate.image_height,
        "aspect_ratio": round(estimate.aspect_ratio, 3),
        "anchor_length_mm": estimate.anchor_length_mm,
    }
    
    return response


# ─────────────────────────────────────────────────────────────────────────
# Validation / test harness
# ─────────────────────────────────────────────────────────────────────────

def evaluate_estimate_accuracy(
    estimate: DimensionEstimate,
    actual_height_mm: float,
) -> Dict[str, Any]:
    """
    Compare estimated vs. actual dimension. Used for test harness validation.
    
    Returns
    -------
    dict with error_mm, error_percent, confidence_score, etc.
    """
    if estimate.confidence_score < 0.5:
        return {
            "estimated_height_mm": estimate.estimated_height_mm,
            "actual_height_mm": actual_height_mm,
            "error_mm": None,
            "error_percent": None,
            "confidence_score": estimate.confidence_score,
            "suppressed": True,
            "suppression_reason": estimate.suppression_reason,
        }
    
    error_mm = estimate.estimated_height_mm - actual_height_mm
    error_percent = (error_mm / actual_height_mm * 100) if actual_height_mm > 0 else 0.0
    
    return {
        "estimated_height_mm": round(estimate.estimated_height_mm, 1),
        "actual_height_mm": actual_height_mm,
        "error_mm": round(error_mm, 1),
        "error_percent": round(error_percent, 1),
        "confidence_score": round(estimate.confidence_score, 2),
        "suppressed": False,
        "suppression_reason": None,
    }
