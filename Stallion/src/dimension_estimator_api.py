"""
API Integration for Image-Assisted Dimension Estimation

Bridges the dimension_estimator module with the FastAPI quote endpoint.
Provides a helper function to add estimated dimensions to the API response.
"""

import sys
from pathlib import Path

# Add src to path if needed
src_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(src_dir))

from dimension_estimator import (
    estimate_from_sofa_analysis,
    format_estimate_for_api_response,
)


def add_dimension_estimates_to_response(
    response: dict,
    sofa_analysis: dict,
    anchor_length_mm: float,
) -> dict:
    """
    Enhance an API response with estimated dimensions.
    
    Takes the existing API response dict and adds an "estimated_dimensions"
    section with suggested height (marked as estimated, with confidence score).
    
    Parameters
    ----------
    response : dict
        Existing API response dict (from the quote endpoint)
    sofa_analysis : dict
        Output from validate_sofa() with bbox and image dims
    anchor_length_mm : float
        User-provided overall_length_mm (the "known" anchor dimension)
    
    Returns
    -------
    dict
        Enhanced response with "estimated_dimensions" section added
    """
    
    if not sofa_analysis or not sofa_analysis.get("validation_passed"):
        # If sofa analysis failed, can't estimate — skip silently
        return response
    
    # Run estimation
    estimate = estimate_from_sofa_analysis(sofa_analysis, anchor_length_mm)
    estimate_dict = format_estimate_for_api_response(estimate)
    
    # Add to response
    response["estimated_dimensions"] = {
        "overall_height_mm": estimate_dict["overall_height_mm"],
        "suppressed": estimate_dict["suppressed"],
    }
    
    if estimate_dict.get("reason_not_estimated"):
        response["estimated_dimensions"]["reason"] = estimate_dict["reason_not_estimated"]
    
    # Diagnostics (optional, for logging/debugging)
    if estimate_dict.get("_diagnostics"):
        response["estimated_dimensions"]["_diagnostics"] = estimate_dict["_diagnostics"]
    
    return response


def format_dimension_suggestion_for_ui(estimate_dict: dict) -> dict:
    """
    Format dimension estimate for UI display.
    
    Creates a dict suitable for passing to the frontend form pre-fill,
    with clear visual distinction between estimated and user-entered fields.
    
    Parameters
    ----------
    estimate_dict : dict
        Output from format_estimate_for_api_response()
    
    Returns
    -------
    dict
        UI-formatted response with:
        - value: estimated height in mm
        - confidence: score 0.0–1.0
        - is_estimate: always true
        - placeholder_text: description for input field
        - confidence_label: human-readable confidence level
    """
    
    height_data = estimate_dict.get("overall_height_mm", {})
    confidence = height_data.get("confidence", 0.0)
    suppressed = estimate_dict.get("suppressed", False)
    
    # Map confidence to human-readable label
    if suppressed or confidence < 0.3:
        confidence_label = "⚠️  Low confidence (please enter manually)"
    elif confidence < 0.6:
        confidence_label = "⚠️  Estimated (please confirm)"
    elif confidence < 0.8:
        confidence_label = "✓ Reasonably confident"
    else:
        confidence_label = "✓ High confidence"
    
    reason = estimate_dict.get("reason_not_estimated", "")
    
    return {
        "value": height_data.get("value"),
        "is_estimate": True,
        "confidence_score": confidence,
        "confidence_label": confidence_label,
        "is_suppressed": suppressed,
        "suppression_reason": reason,
        "help_text": (
            "This is an estimate based on the sofa's silhouette in your image. "
            "Please verify against the actual sofa dimensions (e.g. product spec, tape measure) "
            "before confirming. Depth cannot be estimated from a photo — please enter manually."
        ),
    }
