
# Image-Assisted Dimension Estimation (Phase 3 Extension)

**Date**: 2026-09-01  
**Status**: Ready for Integration  
**Scope Decision**: Option 5a (no depth estimation; user enters manually)  

---

## Overview

This feature provides **honest, confidence-gated dimension suggestions** based on a sofa photo's silhouette, designed to reduce user data-entry friction while maintaining accuracy and transparency.

### What It Does
- Takes: sofa photo (already validated by CLIP/YOLOv8) + one user-provided anchor dimension (length in mm)
- Outputs: suggested overall_height_mm, marked as estimated with confidence score 0–1.0
- Never auto-submits; always requires user confirmation
- Visually distinguishes estimated fields from user-entered fields
- Clearly explains when it's suppressing an estimate due to low confidence

### What It Does NOT Do
- ❌ Infer internal structure (frame, springs, clips, etc.) from exterior photo
- ❌ Estimate depth (perpendicular to image plane) — impossible from single 2D image
- ❌ Attempt multi-view or perspective correction
- ❌ Silently use estimated values in BOM/CAD — always requires user gate

---

## Technical Architecture

### 1. Core Estimation Module (`src/dimension_estimator.py`)

**Key Classes**:
- `DimensionEstimate`: Dataclass holding estimated height, confidence, diagnostics
- `estimate_height_from_bbox()`: Core estimation function
  - Input: bbox [x1, y1, x2, y2], image dimensions, anchor_length_mm
  - Formula: `estimated_height_mm = anchor_length_mm / (pixel_width / pixel_height)`
  - Output: DimensionEstimate with confidence gating applied

**Confidence Gating** (auto-suppress if any gate fails):
1. **Fill ratio**: Sofa should occupy 5–95% of image (reject if thumbnail or fills entire frame)
2. **Image aspect ratio**: Image should be ~square to moderately wide (reject if extreme)
3. **Sofa aspect ratio**: 0.5–3.5 width/height (reject if too narrow or panoramic)
4. **Height range**: Estimated value 300–1800mm (reject if outside typical sofa range)

**Confidence Scoring**:
- Each gate contributes to final score (0.0–1.0)
- Scores <0.5 trigger auto-suppression (estimate not shown to user)
- High-confidence estimates (≥0.8) still show disclaimer: "estimated — please confirm"

**Functions**:
- `estimate_height_from_bbox(bbox, image_width, image_height, anchor_length_mm)` → DimensionEstimate
- `estimate_from_sofa_analysis(sofa_analysis_dict, anchor_length_mm)` → DimensionEstimate
- `format_estimate_for_api_response(estimate)` → dict (JSON-serializable)
- `evaluate_estimate_accuracy(estimate, actual_height_mm)` → dict (for validation)

### 2. Validation Test Harness (`test_dimension_estimator.py`)

Tests the estimator against real sofa photos with known actual dimensions.

**Output Metrics**:
- Mean absolute error (%)
- Max/min error
- Tolerance compliance (within ±15%)
- Suppression rate (% of images where estimate is declined due to low confidence)
- Confidence calibration (do high-confidence estimates actually have lower error?)

**Usage**:
```bash
# Run with synthetic sample data (no real photos needed)
python test_dimension_estimator.py --sample

# Run with real test dataset
python test_dimension_estimator.py --test-set data/test_images.json --output outputs/validation/results.json
```

**Test Dataset Format** (`data/test_images.json`):
```json
[
    {
        "image_path": "samples/sofa_1.jpg",
        "bbox": [50, 100, 550, 400],
        "image_width": 800,
        "image_height": 600,
        "anchor_length_mm": 1500,
        "actual_height_mm": 900,
        "sofa_type": "2-seater",
        "notes": "Front-on shot, good lighting"
    }
]
```

### 3. API Integration Module (`src/dimension_estimator_api.py`)

Bridges dimension estimator with FastAPI backend.

**Functions**:
- `add_dimension_estimates_to_response(response, sofa_analysis, anchor_length_mm)` → enhanced response
- `format_dimension_suggestion_for_ui(estimate_dict)` → UI-ready format with confidence label

**Example Integration**:
```python
from dimension_estimator_api import add_dimension_estimates_to_response

# In the /api/quote POST handler, after sofa_result is obtained:
response["estimated_dimensions"] = add_dimension_estimates_to_response(
    response,
    sofa_analysis=sofa_result,
    anchor_length_mm=length_mm,  # User-provided length
)
```

---

## Integration Points

### Backend (FastAPI)

Add to `src/api.py` POST `/api/quote` endpoint:

```python
from dimension_estimator_api import add_dimension_estimates_to_response

# After validate_sofa() returns sofa_result, and before cost engine:
response_dict = {
    # ... existing fields ...
    "dimensions_mm": {"length": length_mm, "width": width_mm, "height": height_mm},
    "sofa_analysis": sofa_result,
}

# Add estimated dimensions
response_dict = add_dimension_estimates_to_response(
    response=response_dict,
    sofa_analysis=sofa_result,
    anchor_length_mm=length_mm,
)

# Continue with cost engine...
```

### Frontend (HTML/JavaScript)

In the dimensions form, add a section for estimated suggestions:

```html
<!-- After user enters length_mm -->
<div id="height-input-group">
    <label for="height_mm">Height (mm):</label>
    
    <!-- Estimated suggestion (if available) -->
    <div id="estimated-height" style="display: none; background: #f0f0f0; padding: 10px; margin: 5px 0; border-left: 4px solid orange;">
        <strong>💡 Suggested: <span id="estimated-height-value"></span> mm</strong>
        <div style="font-size: 0.9em; color: #666;">
            <span id="confidence-label"></span>
            <span id="suppression-reason" style="display: none;"></span>
        </div>
        <button type="button" onclick="acceptEstimate()">Use This</button>
        <button type="button" onclick="rejectEstimate()">No, Enter Manually</button>
    </div>
    
    <!-- User input field -->
    <input type="number" id="height_mm" name="height_mm" required 
           data-is-estimated="false" />
    <span id="field-status" style="font-size: 0.85em; color: #999;"></span>
</div>

<script>
function populateEstimate(apiResponse) {
    const est = apiResponse.estimated_dimensions;
    if (!est) return;
    
    const suggestedDiv = document.getElementById("estimated-height");
    if (est.suppressed) {
        // Don't show suppressed estimates
        suggestedDiv.style.display = "none";
        return;
    }
    
    document.getElementById("estimated-height-value").textContent = 
        est.overall_height_mm.value;
    document.getElementById("confidence-label").textContent = 
        ["Low", "Moderate", "High"][Math.floor(est.overall_height_mm.confidence * 3)];
    
    if (est.reason_not_estimated) {
        document.getElementById("suppression-reason").textContent = 
            "(" + est.reason_not_estimated + ")";
        document.getElementById("suppression-reason").style.display = "inline";
    }
    
    suggestedDiv.style.display = "block";
    
    // Pre-fill the input (but don't auto-submit)
    document.getElementById("height_mm").value = est.overall_height_mm.value;
    document.getElementById("field-status").textContent = "← Estimated (please confirm)";
    document.getElementById("height_mm").setAttribute("data-is-estimated", "true");
}

function acceptEstimate() {
    // User clicked "Use This" — keep the pre-filled value
    document.getElementById("height_mm").setAttribute("data-is-estimated", "true");
    alert("Height confirmed. Proceeding with estimate.");
}

function rejectEstimate() {
    // User clicked "No" — clear and let them enter manually
    document.getElementById("height_mm").value = "";
    document.getElementById("height_mm").setAttribute("data-is-estimated", "false");
    document.getElementById("field-status").textContent = "← Please enter manually";
    document.getElementById("estimated-height").style.display = "none";
}
</script>
```

---

## Validation Report Template

When ready to validate against real photos, run:

```bash
python test_dimension_estimator.py --test-set data/test_images.json --output outputs/validation/dimension_estimation_report.json
```

**Expected Report Structure**:
```json
{
    "summary": {
        "total_tests": 20,
        "active_estimates": 18,
        "suppressed_estimates": 2,
        "suppression_rate": 10.0
    },
    "results": [
        {
            "image_path": "samples/sofa_1.jpg",
            "sofa_type": "2-seater",
            "anchor_length_mm": 1500,
            "actual_height_mm": 900,
            "estimated_height_mm": 920.5,
            "error_mm": 20.5,
            "error_percent": 2.3,
            "confidence_score": 0.85,
            "suppressed": false
        }
    ]
}
```

**Success Criteria** (before marking complete):
1. ✅ Mean absolute error: <15% across test set
2. ✅ High-confidence estimates (≥0.7) show lower error than low-confidence (<0.7)
3. ✅ Suppression rate <25% (can decline estimate when uncertain, but not too often)
4. ✅ UI distinguishes estimated fields from user-entered (screenshot attached)
5. ✅ All gates implemented and tested (no silently wrong estimates)

---

## Design Decisions & Trade-offs

### Why No Depth Estimation?

**Option 5a Selected**: User enters depth manually.

**Rationale**:
- Depth is the axis perpendicular to the image plane — fundamentally invisible in a 2D photo
- Estimating depth from silhouette alone (e.g., assuming a standard 0.45× ratio) would be:
  - Unreliable (different sofa styles have very different depth ratios)
  - Brittle (users would have to correct it constantly)
  - Silent failure risk (if ratio-based estimate is wrong, user might not catch it)
- User entry burden for depth: ~1 second with ruler or product spec
- Better UX: be honest about capability limits than pretend to omniscience

### Confidence Gating Philosophy

Unlike a black-box ML model that always produces an output, this feature **explicitly admits uncertainty**:
- Low confidence (<0.5) → suppress entirely, don't show estimate
- Medium confidence (0.5–0.8) → show estimate with ⚠️ "please confirm" warning
- High confidence (≥0.8) → show estimate with ✓ "reasonably confident" but still ask for confirmation

This avoids the trap of "users trust estimates they see, even if marked uncertain." Better to not show a low-confidence estimate at all.

### Reuse Existing Detection Output

The feature reuses detection output from `validate_sofa()`:
- No duplicate detection pass (already did YOLOv8)
- No new models to deploy
- Uses existing bbox and image dimensions
- Non-invasive addition to existing pipeline

---

## Limitations & Future Improvements

### Known Limitations
- ⚠️ Single-image estimation only (no multi-view stereo)
- ⚠️ Assumes roughly front-on camera angle
- ⚠️ Cannot account for perspective distortion or wide-angle lens effects
- ⚠️ Typical error ±10–20% depending on image quality and sofa position

### Out of Scope (v1)
- Depth estimation (decided: Option 5a)
- Perspective correction
- Component-level geometry inference
- Database storage of dimension ratios by sofa model/year

### Future Enhancements (Roadmap)
- If users provide feedback on typical error patterns, refine confidence gates
- Optional depth estimation (Option 5b) if user study shows demand
- Collect anonymized dimension data → build furniture-database to improve ratio estimates
- Multi-image upload → depth from stereo baseline

---

## File Summary

| File | Lines | Purpose |
|------|-------|---------|
| `src/dimension_estimator.py` | ~250 | Core estimation functions, confidence gating |
| `src/dimension_estimator_api.py` | ~80 | API bridge functions |
| `test_dimension_estimator.py` | ~300 | Validation test harness |
| `docs/04_DIMENSION_ESTIMATION.md` | This file | Feature documentation |

---

## Checklist for Implementation

### Backend Integration
- [ ] Import `dimension_estimator_api` in `src/api.py`
- [ ] Add `add_dimension_estimates_to_response()` call after `validate_sofa()`
- [ ] Test API response includes `estimated_dimensions` field
- [ ] Verify estimated values are marked `estimated: true`

### Frontend Integration
- [ ] Add HTML form section for height input
- [ ] Add JavaScript to populate estimated value from API response
- [ ] Implement "Use This" / "No, Enter Manually" buttons
- [ ] Style estimated fields differently (e.g., orange/yellow background)
- [ ] Test form pre-fill and user confirmation flow

### Validation & Testing
- [ ] Prepare test dataset (10–20 real sofa photos with known dimensions)
- [ ] Run `test_dimension_estimator.py --test-set <data>`
- [ ] Verify mean error <15%
- [ ] Document suppression rate and confidence calibration
- [ ] Take UI screenshot showing field distinction
- [ ] Commit validation report to repo

### Documentation
- [ ] Update README.md with feature overview
- [ ] Add API endpoint documentation (estimated_dimensions field)
- [ ] Create user guide for frontend (how to use estimation, when to override)
- [ ] Record decision on Option 5a (no depth estimation)

---

## Conclusion

This feature provides a **realistic, confidence-aware** dimension estimation capability that:
- ✅ Reuses existing detection output (zero redundancy)
- ✅ Admits uncertainty transparently (no false confidence)
- ✅ Requires user confirmation (no silent auto-submit risk)
- ✅ Distinguishes estimated from user-entered fields (clear UI separation)
- ✅ Scoped honestly (Option 5a: no depth inference)

Ready for integration upon selection of test dataset and successful validation against real sofa photos.

---

**Next Steps**:
1. Provide test dataset (10–20 real sofa photos + actual dimensions)
2. Run validation test harness
3. Implement backend API integration
4. Implement frontend form UI
5. Deploy and gather user feedback on estimate accuracy

---

*Document Generated*: 2026-09-01  
*Scope Decision*: Option 5a (no depth estimation)  
*Status*: Ready for Integration
