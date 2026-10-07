"""
Phase 3 - Sofa Image Validation (Plugin Architecture)

HOW IT WORKS
============
Detection is split into two layers:

  1. DETECTOR (pluggable backend)
     ─ Responsible for: "is there a sofa in this image, and where?"
     ─ Returns a list of raw detections: [{bbox, confidence, components?, polygon?}, ...]
     ─ Default: StallionSofaDetector (YOLO11 segmentation model with 11 classes)
     ─ Fallback: YOLOv8DetectorBackend (yolov8n.pt, COCO pre-trained)

  2. CLASSIFIER (shared logic)
     ─ Responsible for: "what type of sofa is this?"
     ─ Uses detected class or bbox aspect ratio + detection count:
         2+ non-overlapping detections          →  l_shape
         one-seater                             →  1_seater
         two-seater                             →  2_seater
         stallion-sofa*                         →  3_seater
         aspect ratio rules fallback
"""

import os
import json
import threading
from abc import ABC, abstractmethod
from pathlib import Path

import cv2

from sofa_type_classifier import get_type_classifier

# ---------------------------------------------------------------------------
# Constants (shared by all backends)
# ---------------------------------------------------------------------------

MIN_CONFIDENCE = 0.25   # detections below this are ignored

# Below this classifier confidence the detected type is not used to flag a
# mismatch. Classifier v2 (2026-10-07): catalogue test >=0.6 -> 95.7% correct,
# <0.6 -> 80.0%; 264 held-out room photos >=0.6 -> 83.5%, <0.6 -> 43.8%
# (see docs/07_MODELS.md). A flag is only ever a suggestion to double-check.
TYPE_CONFIDENCE_THRESHOLD = 0.6

# Aspect-ratio thresholds (width ÷ height of bounding box)
# Calibrated against real sofa photography:
_RATIO_RULES = [
    ("1_seater",      0.00,  1.30),
    ("2_seater",      1.30,  1.60),
    ("3_seater",      1.60,  3.20),
    ("4_seater_plus", 3.20,  float("inf")),
]

SUPPORTED_TYPES = ["1_seater", "2_seater", "3_seater", "4_seater_plus", "l_shape"]

_TYPE_LABELS = {
    "1_seater":      "1-seater (armchair)",
    "2_seater":      "2-seater (loveseat)",
    "3_seater":      "3-seater",
    "4_seater_plus": "4-seater / large sofa",
    "l_shape":       "L-shape / sectional",
}

# 11-Class Taxonomy for Stallion YOLO11 Segmentation
SOFA_TYPE_CLASSES = {
    6: ("one-seater", "1_seater"),
    7: ("stallion-sofa1", "3_seater"),
    8: ("stallion-sofa2", "3_seater"),
    9: ("stallion-sofa", "3_seater"),
    10: ("two-seater", "2_seater"),
}

COMPONENT_CLASSES = {
    0: "back_cushion",
    1: "base",
    2: "left_arm",
    3: "legs",
    4: "right_arm",
    5: "seat_cushion",
}

# Detections are mapped by class NAME (read from the model), so retrained
# detectors with a different class order or merged classes keep working.
# The id tables above are only the fallback for models without names.
SOFA_TYPE_BY_NAME = {name: sofa_type for name, sofa_type in SOFA_TYPE_CLASSES.values()}
COMPONENT_NAMES   = set(COMPONENT_CLASSES.values())
_FALLBACK_NAMES   = {**{i: n for i, (n, _) in SOFA_TYPE_CLASSES.items()}, **COMPONENT_CLASSES}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SofaValidationError(ValueError):
    """Raised when an image fails sofa validation (no sofa, or unsupported type)."""


# ---------------------------------------------------------------------------
# PLUGIN BASE CLASS
# ---------------------------------------------------------------------------

class SofaDetectorBase(ABC):
    """
    Abstract interface every sofa detector backend must implement.
    """

    @abstractmethod
    def detect(self, image_path: str) -> list:
        """
        Run inference on *image_path*.

        Returns a list of detections, each a dict:
            {
                "bbox":       [x1, y1, x2, y2],   # pixel coords, ints
                "confidence": float,                # 0.0 – 1.0
            }
        """


# ---------------------------------------------------------------------------
# BUILT-IN BACKEND: YOLOv8-nano COCO Fallback
# ---------------------------------------------------------------------------

class YOLOv8DetectorBackend(SofaDetectorBase):
    """
    Fallback backend using YOLOv8-nano (pre-trained on COCO).
    COCO class 57 = "couch".
    """

    COUCH_CLASS_ID = 57          # COCO index for "couch"
    MODEL_NAME = str(
    Path(__file__).resolve().parent.parent
    / "data" / "models" / "weights" / "yolov8n.pt"
)

    def __init__(self):
        from ultralytics import YOLO
        self._model = YOLO(self.MODEL_NAME, verbose=False)

    def detect(self, image_path: str) -> list:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        results = self._model(image_path, verbose=False)[0]

        detections = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])
            if cls_id == self.COUCH_CLASS_ID and conf >= MIN_CONFIDENCE:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append({
                    "bbox":       [round(x1), round(y1), round(x2), round(y2)],
                    "confidence": round(conf, 4),
                })

        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections


# ---------------------------------------------------------------------------
# PRODUCTION DETECTOR: Stallion YOLO11 Segmentation Model (11 Classes)
# ---------------------------------------------------------------------------

class StallionSofaDetector(SofaDetectorBase):
    """
    Production detector using the Stallion-trained YOLO11 segmentation model.

    Trained on 11 classes:
        Components:
            0: back_cushion, 1: base, 2: left_arm, 3: legs, 4: right_arm, 5: seat_cushion
        Sofa Types:
            6: one-seater, 7: stallion-sofa1, 8: stallion-sofa2, 9: stallion-sofa, 10: two-seater
    """

    MODEL_WEIGHTS = "sofa_detector.pt"

    def __init__(self, weights_path: str = None):
        from pathlib import Path
        from ultralytics import YOLO

        src_dir   = Path(__file__).parent.resolve()
        proj_root = src_dir.parent.resolve()

        if weights_path:
            wp = Path(weights_path)
        else:
            wp = proj_root / "data" / "models" / "weights" / self.MODEL_WEIGHTS

        if not wp.exists():
            raise FileNotFoundError(
                f"Stallion model weights not found at: {wp}"
            )

        self._model       = YOLO(str(wp), verbose=False)
        self.weights_path = str(wp)

    def detect(self, image_path: str) -> list:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        results = self._model(image_path, verbose=False, conf=MIN_CONFIDENCE)[0]

        sofa_detections = []
        component_detections = []

        boxes = results.boxes
        masks = getattr(results, "masks", None)
        has_masks = masks is not None and hasattr(masks, "xy") and len(masks.xy) > 0

        names = getattr(self._model, "names", None) or _FALLBACK_NAMES

        for idx, box in enumerate(boxes):
            cls_id = int(box.cls[0])
            cls_name = names.get(cls_id, str(cls_id))
            conf   = float(box.conf[0])
            if conf < MIN_CONFIDENCE:
                continue

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            bbox = [round(x1), round(y1), round(x2), round(y2)]

            mask_polygon = None
            if has_masks and idx < len(masks.xy):
                poly = masks.xy[idx]
                if len(poly) > 0:
                    mask_polygon = [[round(float(pt[0]), 1), round(float(pt[1]), 1)] for pt in poly]

            if cls_name in SOFA_TYPE_BY_NAME:
                det = {
                    "bbox":       bbox,
                    "confidence": round(conf, 4),
                    "class_id":   cls_id,
                    "class_name": cls_name,
                    "sofa_type":  SOFA_TYPE_BY_NAME[cls_name],
                }
                if mask_polygon:
                    det["polygon"] = mask_polygon
                sofa_detections.append(det)

            elif cls_name in COMPONENT_NAMES:
                comp = {
                    "class_id":   cls_id,
                    "class_name": cls_name,
                    "confidence": round(conf, 4),
                    "bbox":       bbox,
                }
                if mask_polygon:
                    comp["polygon"] = mask_polygon
                component_detections.append(comp)

        # Attach sub-components to detections
        if sofa_detections:
            sofa_detections.sort(key=lambda d: d["confidence"], reverse=True)
            sofa_detections[0]["components"] = component_detections
            return sofa_detections

        # If only components were detected, construct unified sofa bbox
        if component_detections:
            all_x1 = min(c["bbox"][0] for c in component_detections)
            all_y1 = min(c["bbox"][1] for c in component_detections)
            all_x2 = max(c["bbox"][2] for c in component_detections)
            all_y2 = max(c["bbox"][3] for c in component_detections)
            avg_conf = sum(c["confidence"] for c in component_detections) / len(component_detections)

            return [{
                "bbox":       [all_x1, all_y1, all_x2, all_y2],
                "confidence": round(avg_conf, 4),
                "components": component_detections,
            }]

        return []


def get_detector(custom_weights: str = None) -> SofaDetectorBase:
    """
    Returns the best available detector:
      1. StallionSofaDetector  — if models/sofa_detector.pt exists (trained model)
      2. YOLOv8DetectorBackend — fallback to COCO pretrained model
    """
    from pathlib import Path
    src_dir   = Path(__file__).parent.resolve()
    proj_root = src_dir.parent.resolve()
    default_wp = proj_root / "data" / "models" / "weights" / "sofa_detector.pt"

    target = Path(custom_weights) if custom_weights else default_wp

    if target.exists():
        try:
            detector = StallionSofaDetector(str(target))
            print(f"[detector] Using Stallion trained model: {target}")
            return detector
        except Exception as e:
            print(f"[detector] Failed to load Stallion model ({e}), falling back to COCO.")

    print("[detector] Using COCO YOLOv8n fallback.")
    return YOLOv8DetectorBackend()


_detector_cache = None
# Ultralytics models aren't thread-safe, and the API serves requests from a
# thread pool, so inference on the shared models is serialised.
_model_lock = threading.Lock()


def _shared_detector() -> SofaDetectorBase:
    """Load the default detector once per process instead of on every request."""
    global _detector_cache
    with _model_lock:
        if _detector_cache is None:
            _detector_cache = get_detector()
    return _detector_cache


# ---------------------------------------------------------------------------
# Shared helpers (used by all backends)
# ---------------------------------------------------------------------------

def _iou(box_a, box_b):
    """Intersection-over-union of two [x1,y1,x2,y2] boxes."""
    ix1 = max(box_a[0], box_b[0])
    iy1 = max(box_a[1], box_b[1])
    ix2 = min(box_a[2], box_b[2])
    iy2 = min(box_a[3], box_b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    return inter / (area_a + area_b - inter)


def _classify_type(detections):
    """
    Classify sofa type from detections.
    If a detection already carries "sofa_type", use it directly.
    Otherwise fall back to bbox aspect-ratio heuristic.
    """
    if len(detections) >= 2:
        d0, d1 = detections[0], detections[1]
        if _iou(d0["bbox"], d1["bbox"]) < 0.40:
            return "l_shape"

    best = detections[0]

    if "sofa_type" in best and best["sofa_type"]:
        return best["sofa_type"]

    x1, y1, x2, y2 = best["bbox"]
    width  = x2 - x1
    height = y2 - y1
    ratio  = width / height if height > 0 else 0.0

    for label, lo, hi in _RATIO_RULES:
        if lo <= ratio < hi:
            return label

    return "4_seater_plus"


def _draw_annotated(image_bgr, detections, sofa_type, request_folder, ext=".jpg"):
    """Draw bounding boxes, masks, and components on a copy of the image and save it."""
    annotated = image_bgr.copy()
    colour = (0, 200, 0) if sofa_type in SUPPORTED_TYPES else (0, 60, 220)

    # Draw subcomponents if available
    comp_colors = {
        "seat_cushion": (255, 128, 0),
        "back_cushion": (0, 165, 255),
        "left_arm":     (200, 50, 150),
        "right_arm":    (200, 50, 150),
        "base":         (128, 128, 0),
        "legs":         (0, 128, 255),
    }

    if detections and "components" in detections[0]:
        for comp in detections[0]["components"]:
            cx1, cy1, cx2, cy2 = [int(v) for v in comp["bbox"]]
            cname = comp.get("class_name", "")
            ccol = comp_colors.get(cname, (180, 180, 180))
            cv2.rectangle(annotated, (cx1, cy1), (cx2, cy2), ccol, 1)

    for i, det in enumerate(detections):
        x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
        conf  = det["confidence"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), colour, 3 if i == 0 else 1)
        if i > 0:
            # Only the best detection gets a label; overlapping boxes would
            # print their labels on top of each other (e.g. "33-seater").
            continue
        label = f"{_TYPE_LABELS.get(sofa_type, sofa_type)}  {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(annotated, (x1, y1 - th - 10), (x1 + tw + 6, y1), colour, -1)
        cv2.putText(annotated, label, (x1 + 3, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    save_path = os.path.join(request_folder, f"sofa_annotated{ext}")
    cv2.imwrite(save_path, annotated)
    return save_path


def _save_analysis(analysis, request_folder):
    """Write sofa_analysis.json into request_folder."""
    os.makedirs(request_folder, exist_ok=True)
    path = os.path.join(request_folder, "sofa_analysis.json")
    with open(path, "w") as f:
        json.dump(analysis, f, indent=4)
    analysis["analysis_path"] = path


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def detect_type(image_path) -> dict:
    """
    Quick check for the quote form, run as soon as a photo is chosen: is there
    a sofa, and which type does it look like? Same models as validate_sofa,
    but nothing is written to disk.

    Returns {"sofa_found", "sofa_type", "confidence", "confident"}; confident
    means confidence >= TYPE_CONFIDENCE_THRESHOLD, i.e. worth pre-selecting.
    """
    detector = _shared_detector()
    with _model_lock:
        detections = detector.detect(image_path)
    if not detections:
        return {"sofa_found": False, "sofa_type": None, "confidence": None, "confident": False}

    classifier = get_type_classifier()
    if classifier is None:
        sofa_type, conf = _classify_type(detections), None
    else:
        with _model_lock:
            sofa_type, conf = classifier.predict(image_path)
    return {
        "sofa_found": True,
        "sofa_type":  sofa_type,
        "confidence": conf,
        "confident":  conf is not None and conf >= TYPE_CONFIDENCE_THRESHOLD,
    }


def validate_sofa(image_path, request_folder, detector=None):
    """
    Run Phase 3 sofa validation.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        raise SofaValidationError(f"Could not read image: {image_path}")

    img_h, img_w = image_bgr.shape[:2]
    ext       = os.path.splitext(image_path)[1].lower() or ".jpg"
    write_ext = ext if ext in (".jpg", ".jpeg", ".png") else ".jpg"

    if detector is None:
        detector = _shared_detector()

    with _model_lock:
        detections = detector.detect(image_path)

    # Gate 1: no sofa detected
    if not detections:
        analysis = {
            "validation_passed":    False,
            "error":                "Not a valid image. No sofa detected.",
            "detected_object":      None,
            "predicted_type":       None,
            "confidence":           None,
            "image_width":          img_w,
            "image_height":         img_h,
            "bbox":                 None,
            "aspect_ratio":         None,
            "annotated_image_path": None,
            "detector_backend":     type(detector).__name__,
        }
        _save_analysis(analysis, request_folder)
        raise SofaValidationError(analysis["error"])

    # Classify sofa type
    sofa_type = _classify_type(detections)
    detector_type = sofa_type
    type_source, type_confidence = "detector", None

    # The whole-image type classifier is far more accurate than the detector's
    # type rules on general sofas (95.4% vs 47.2% on the held-out catalogue
    # test split, 81.1% on held-out room photos; see eval_sofa_types.py), so it
    # decides the type when its weights exist. The detector still decides
    # whether there is a sofa at all; its own type stays in detector_type.
    # There is deliberately no "stallion-sofa* match keeps the detector's type"
    # exception: the detector's Stallion classes fire on 628 of 878 generic room
    # photos (conf up to 0.96), while the classifier calls 30 of 42 held-out
    # Stallion photos a 3-seater on its own (docs/07_MODELS.md).
    classifier = get_type_classifier()
    if classifier is not None:
        with _model_lock:
            sofa_type, type_confidence = classifier.predict(image_path)
        type_source = "classifier"

    best      = detections[0]
    x1, y1, x2, y2 = best["bbox"]
    aspect_ratio = round((x2 - x1) / (y2 - y1), 4) if (y2 - y1) > 0 else None

    # Draw annotated image
    annotated_path = _draw_annotated(image_bgr, detections[:2], sofa_type,
                                     request_folder, write_ext)

    # Gate 2: unsupported sofa type
    if sofa_type not in SUPPORTED_TYPES:
        human_label = _TYPE_LABELS.get(sofa_type, sofa_type)
        error_msg   = f"Dimensions for {human_label} not available."
        analysis = {
            "validation_passed":    False,
            "error":                error_msg,
            "detected_object":      "sofa",
            "predicted_type":       sofa_type,
            "confidence":           best["confidence"],
            "image_width":          img_w,
            "image_height":         img_h,
            "bbox":                 best["bbox"],
            "aspect_ratio":         aspect_ratio,
            "annotated_image_path": annotated_path,
            "detector_backend":     type(detector).__name__,
            "components":           best.get("components", []),
        }
        _save_analysis(analysis, request_folder)
        raise SofaValidationError(error_msg)

    # Validation Passed
    analysis = {
        "validation_passed":    True,
        "detected_object":      "sofa",
        "predicted_type":       sofa_type,
        "confidence":           best["confidence"],
        "image_width":          img_w,
        "image_height":         img_h,
        "bbox":                 best["bbox"],
        "aspect_ratio":         aspect_ratio,
        "annotated_image_path": annotated_path,
        "detector_backend":     type(detector).__name__,
        "components":           best.get("components", []),
        "type_source":          type_source,
        "type_confidence":      type_confidence,
        "detector_type":        detector_type,
    }
    if "polygon" in best:
        analysis["polygon"] = best["polygon"]

    _save_analysis(analysis, request_folder)
    return analysis
