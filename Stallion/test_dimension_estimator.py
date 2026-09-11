"""
Validation Test Harness for Image-Assisted Dimension Estimation

Tests the dimension_estimator module against real sofa photos with known
actual dimensions. Validates:

1. Estimation accuracy (error % against actual values)
2. Confidence gating (suppression rate and correctness)
3. Edge case handling (cropped images, extreme angles, etc.)

USAGE:
    python test_dimension_estimator.py --test-set /path/to/test_images.json

TEST DATASET FORMAT:
    test_images.json:
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
        },
        ...
    ]
"""

import os
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
src_dir = Path(__file__).parent.resolve() / "src"
sys.path.insert(0, str(src_dir))

from dimension_estimator import (
    estimate_height_from_bbox,
    evaluate_estimate_accuracy,
    DimensionEstimate,
)


class DimensionEstimatorValidator:
    """Harness for testing dimension estimation accuracy."""
    
    def __init__(self):
        self.results = []
        self.suppression_count = 0
        self.active_estimate_count = 0
    
    def test_single_image(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test one image and compare estimated vs. actual height.
        
        Parameters
        ----------
        test_case : dict
            Keys: image_path, bbox, image_width, image_height, anchor_length_mm,
                  actual_height_mm, sofa_type, notes (optional)
        
        Returns
        -------
        dict with results (error %, confidence, etc.)
        """
        image_path = test_case.get("image_path", "unknown")
        bbox = test_case.get("bbox")
        image_width = test_case.get("image_width")
        image_height = test_case.get("image_height")
        anchor_length_mm = test_case.get("anchor_length_mm")
        actual_height_mm = test_case.get("actual_height_mm")
        sofa_type = test_case.get("sofa_type", "unknown")
        notes = test_case.get("notes", "")
        
        # Run estimation
        estimate = estimate_height_from_bbox(
            bbox=bbox,
            image_width=image_width,
            image_height=image_height,
            anchor_length_mm=anchor_length_mm,
        )
        
        # Evaluate accuracy
        accuracy = evaluate_estimate_accuracy(estimate, actual_height_mm)
        
        # Log
        if accuracy["suppressed"]:
            self.suppression_count += 1
        else:
            self.active_estimate_count += 1
        
        result = {
            "image_path": image_path,
            "sofa_type": sofa_type,
            "notes": notes,
            "anchor_length_mm": anchor_length_mm,
            "actual_height_mm": actual_height_mm,
            "estimated_height_mm": accuracy.get("estimated_height_mm"),
            "error_mm": accuracy.get("error_mm"),
            "error_percent": accuracy.get("error_percent"),
            "confidence_score": accuracy.get("confidence_score"),
            "suppressed": accuracy.get("suppressed"),
            "suppression_reason": accuracy.get("suppression_reason"),
        }
        
        self.results.append(result)
        return result
    
    def run_test_set(self, test_cases: List[Dict[str, Any]]) -> None:
        """
        Run estimation test on a list of test cases.
        
        Parameters
        ----------
        test_cases : list of dict
            Each dict contains test data (see test_single_image)
        """
        print(f"\n{'='*80}")
        print(f"Image-Assisted Dimension Estimation Validation")
        print(f"{'='*80}\n")
        
        print(f"Running {len(test_cases)} test cases...\n")
        
        for i, test_case in enumerate(test_cases, 1):
            result = self.test_single_image(test_case)
            
            status = "SUPPRESSED" if result["suppressed"] else "ESTIMATE"
            error_display = (
                f"{result['error_percent']:+.1f}%" 
                if result["error_percent"] is not None 
                else "N/A"
            )
            
            print(f"  [{i:2d}] {result['sofa_type']:12s} | "
                  f"Estimated: {result['estimated_height_mm']:7.0f}mm | "
                  f"Actual: {result['actual_height_mm']:4.0f}mm | "
                  f"Error: {error_display:>6s} | "
                  f"{status}")
            
            if result["suppression_reason"]:
                print(f"        → {result['suppression_reason']}\n")
    
    def print_summary(self) -> None:
        """Print summary statistics."""
        print(f"\n{'='*80}")
        print("SUMMARY STATISTICS")
        print(f"{'='*80}\n")
        
        print(f"Total test cases:        {len(self.results)}")
        print(f"Active estimates:        {self.active_estimate_count}")
        print(f"Suppressed (no estimate):{self.suppression_count}")
        print(f"Suppression rate:        {self.suppression_count / len(self.results) * 100:.1f}%\n")
        
        # Error statistics for active estimates only
        active_results = [r for r in self.results if not r["suppressed"]]
        
        if active_results:
            errors = [abs(r["error_percent"]) for r in active_results if r["error_percent"] is not None]
            
            if errors:
                mean_error = sum(errors) / len(errors)
                max_error = max(errors)
                min_error = min(errors)
                
                print("ACTIVE ESTIMATES (non-suppressed):")
                print(f"  Mean absolute error:   {mean_error:.1f}%")
                print(f"  Max error:             {max_error:.1f}%")
                print(f"  Min error:             {min_error:.1f}%")
                
                # Tolerance check: typical acceptable error for image-based estimation
                acceptable_count = sum(1 for e in errors if e <= 15.0)
                print(f"  Within ±15% tolerance: {acceptable_count}/{len(errors)} ({acceptable_count/len(errors)*100:.0f}%)")
                
                # Confidence calibration: do high-confidence estimates actually have lower error?
                high_conf = [r for r in active_results if r["confidence_score"] >= 0.7]
                low_conf = [r for r in active_results if r["confidence_score"] < 0.7]
                
                if high_conf:
                    high_conf_errors = [abs(r["error_percent"]) for r in high_conf if r["error_percent"] is not None]
                    if high_conf_errors:
                        print(f"  High-confidence (≥0.7) mean error: {sum(high_conf_errors)/len(high_conf_errors):.1f}%")
                
                if low_conf:
                    low_conf_errors = [abs(r["error_percent"]) for r in low_conf if r["error_percent"] is not None]
                    if low_conf_errors:
                        print(f"  Low-confidence (<0.7) mean error:  {sum(low_conf_errors)/len(low_conf_errors):.1f}%")
        
        print(f"\n{'='*80}\n")
    
    def export_results(self, output_path: str) -> None:
        """Export test results to JSON."""
        output_dir = os.path.dirname(output_path) or "."
        os.makedirs(output_dir, exist_ok=True)
        
        export_data = {
            "summary": {
                "total_tests": len(self.results),
                "active_estimates": self.active_estimate_count,
                "suppressed_estimates": self.suppression_count,
                "suppression_rate": round(self.suppression_count / len(self.results) * 100, 1) if self.results else 0.0,
            },
            "results": self.results,
        }
        
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)
        
        print(f"Results exported to: {output_path}")


def create_sample_test_dataset() -> List[Dict[str, Any]]:
    """
    Create a small sample test dataset for demonstration.
    These are synthetic/hypothetical data (no real images attached).
    
    To use real images, provide a test_images.json file with actual data.
    """
    return [
        {
            "image_path": "samples/sofa_armchair_front.jpg",
            "bbox": [100, 80, 450, 420],  # pixel coords: x1, y1, x2, y2
            "image_width": 640,
            "image_height": 480,
            "anchor_length_mm": 1000,  # User says length is ~1m
            "actual_height_mm": 850,  # Real height (from spec or tape measure)
            "sofa_type": "1-seater",
            "notes": "Front-on shot, good framing"
        },
        {
            "image_path": "samples/sofa_2seater_angled.jpg",
            "bbox": [50, 120, 550, 360],
            "image_width": 640,
            "image_height": 480,
            "anchor_length_mm": 1500,
            "actual_height_mm": 900,
            "sofa_type": "2-seater",
            "notes": "Slight angle, partially cropped on right"
        },
        {
            "image_path": "samples/sofa_3seater_lowangle.jpg",
            "bbox": [20, 200, 600, 420],  # Very wide, cropped top/bottom
            "image_width": 640,
            "image_height": 480,
            "anchor_length_mm": 2000,
            "actual_height_mm": 900,
            "sofa_type": "3-seater",
            "notes": "Low camera angle, cropped top (should suppress estimate)"
        },
        {
            "image_path": "samples/sofa_thumbnail.jpg",
            "bbox": [300, 250, 340, 310],  # Very small bounding box
            "image_width": 640,
            "image_height": 480,
            "anchor_length_mm": 1500,
            "actual_height_mm": 900,
            "sofa_type": "2-seater",
            "notes": "Thumbnail size (should suppress estimate)"
        },
    ]


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Validate image-assisted dimension estimation"
    )
    parser.add_argument(
        "--test-set",
        type=str,
        default=None,
        help="Path to test_images.json with real test data"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/validation/dimension_estimation_results.json",
        help="Path to save results JSON"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Run with synthetic sample data (no real images required)"
    )
    
    args = parser.parse_args()
    
    validator = DimensionEstimatorValidator()
    
    # Load test data
    if args.test_set:
        if not os.path.exists(args.test_set):
            print(f"Error: Test set file not found: {args.test_set}")
            sys.exit(1)
        with open(args.test_set) as f:
            test_cases = json.load(f)
        print(f"Loaded {len(test_cases)} test cases from {args.test_set}")
    elif args.sample:
        test_cases = create_sample_test_dataset()
        print(f"Using {len(test_cases)} synthetic sample test cases")
    else:
        print("No test data provided. Use --test-set or --sample")
        print("To create a real test dataset, prepare test_images.json with:")
        print("  - image_path, bbox, image_width, image_height")
        print("  - anchor_length_mm, actual_height_mm, sofa_type")
        sys.exit(1)
    
    # Run validation
    validator.run_test_set(test_cases)
    validator.print_summary()
    validator.export_results(args.output)


if __name__ == "__main__":
    main()
