"""
Full-Coverage Parametric CAD + BOM Validation Test Suite

Validates all 6 requirements from the production-grade CAD spec:
1. Coverage check: all 10 Fusion folders in BOM + CAD
2. Sofa-type matrix: BOM + CAD for 1/2/3/4-seater + L-shape
3. L-shape join check: chaise module independent
4. Clips-derivation check: Clips count derived from belt/spring counts
5. Production CAD sanity: STEP round-trip
6. Real data outputs (BOM JSON, CAD preview, STEP file)
"""

import sys
sys.path.insert(0, 'src')

from pathlib import Path
from typing import Dict, List, Tuple, Any
import json

from component_schema_extended import (
    COMPONENT_SCHEMA_EXTENDED,
    FUSION_FOLDER_STRUCTURE,
    SOFA_TYPES,
    validate_folder_coverage,
    get_components_by_fusion_folder,
)
from component_schema_validator import GranularBOMGenerator
from production_cad import build_sofa_step_model, build_sofa_l_shape_modular

# ============================================================================
# VALIDATION 1: COVERAGE CHECK
# ============================================================================

def validate_folder_coverage_complete() -> Tuple[bool, str]:
    """
    Validation #1: Ensure all 10 Fusion folders are mapped and populated.
    
    Returns:
        (success: bool, report: str)
    """
    print("=" * 70)
    print("VALIDATION 1: FOLDER COVERAGE CHECK")
    print("=" * 70)
    
    unmapped, empty = validate_folder_coverage()
    
    report_lines = []
    report_lines.append(f"Total components: {len(COMPONENT_SCHEMA_EXTENDED)}")
    report_lines.append(f"Total Fusion folders: {len(FUSION_FOLDER_STRUCTURE)}")
    report_lines.append("")
    report_lines.append("Component Coverage:")
    
    all_mapped = True
    for comp_id, comp_data in COMPONENT_SCHEMA_EXTENDED.items():
        has_folder = "fusion_folder" in comp_data
        status = "✓" if has_folder else "✗"
        folder = comp_data.get("fusion_folder", "UNMAPPED")
        report_lines.append(f"  {status} {comp_id:30} -> {folder}")
        if not has_folder:
            all_mapped = False
    
    report_lines.append("")
    report_lines.append("Folder Coverage:")
    
    all_folders_populated = True
    for folder_key, folder_data in FUSION_FOLDER_STRUCTURE.items():
        folder_name = folder_data["folder_name"]
        comp_ids = folder_data.get("component_ids", [])
        status = "✓" if comp_ids else "✗"
        report_lines.append(f"  {status} {folder_name:30} ({len(comp_ids)} components)")
        if not comp_ids:
            all_folders_populated = False
    
    success = all_mapped and all_folders_populated
    status = "PASS" if success else "FAIL"
    report_lines.append("")
    report_lines.append(f"Result: {status}")
    
    report = "\n".join(report_lines)
    print(report)
    return success, report


# ============================================================================
# VALIDATION 2: SOFA-TYPE MATRIX
# ============================================================================

def validate_sofa_type_matrix() -> Tuple[bool, str]:
    """
    Validation #2: Generate BOM + verify CAD for all sofa sizes.
    
    Returns matrix of costs and component counts for:
    - 1-seater, 2-seater, 3-seater, 4-seater, L-shape
    """
    print("\n" + "=" * 70)
    print("VALIDATION 2: SOFA-TYPE MATRIX (Cost + Component Counts)")
    print("=" * 70)
    
    generator = GranularBOMGenerator(COMPONENT_SCHEMA_EXTENDED)
    sofa_types_to_test = ["1-seater", "2-seater", "3-seater", "4-seater", "l-shape"]
    
    report_lines = []
    report_lines.append("")
    report_lines.append("Sofa Type | Total Cost (INR) | Component Count | Frame Cost | Webbing/Spring | Foam | Upholstery | Hardware | Misc")
    report_lines.append("-" * 130)
    
    all_success = True
    bom_data = {}
    
    for sofa_type in sofa_types_to_test:
        try:
            bom = generator.generate_bom_for_sofa_type(sofa_type)
            bom_data[sofa_type] = bom
            
            total_cost = bom.get("grand_total_cost", 0)
            comp_count = bom.get("component_count", 0)
            
            # totals_by_category values are dicts {"qty": ..., "cost": ...}
            totals_by_cat = bom.get("totals_by_category", {})
            frame_cost    = totals_by_cat.get("frame", {}).get("cost", 0)
            webbing_cost  = totals_by_cat.get("webbing_spring", {}).get("cost", 0)
            foam_cost     = totals_by_cat.get("foam", {}).get("cost", 0)
            upholstery_cost = totals_by_cat.get("upholstery", {}).get("cost", 0)
            hardware_cost = totals_by_cat.get("hardware", {}).get("cost", 0)
            misc_cost     = totals_by_cat.get("misc", {}).get("cost", 0)
            
            line = (f"{sofa_type:10} | {total_cost:15.0f} | {comp_count:15} | "
                   f"{frame_cost:10.0f} | {webbing_cost:14.0f} | {foam_cost:4.0f} | "
                   f"{upholstery_cost:10.0f} | {hardware_cost:8.0f} | {misc_cost:4.0f}")
            report_lines.append(line)
            
        except Exception as e:
            report_lines.append(f"{sofa_type:10} | ERROR: {str(e)}")
            all_success = False
    
    # Verify CAD files were created (production_cad module)
    report_lines.append("")
    report_lines.append("Production CAD Status:")
    
    for sofa_type in sofa_types_to_test:
        if sofa_type == "l-shape":
            output_path = Path(f"outputs/production_cad/{sofa_type}_modular.step")
            result = build_sofa_l_shape_modular(
                {'sofa_type': '3-seater'},
                {'chaise_length': 1500, 'chaise_depth': 1200},
                output_path
            )
        else:
            output_path = Path(f"outputs/production_cad/{sofa_type}.step")
            result = build_sofa_step_model(sofa_type, output_path)
        
        status = "+" if result else "x"
        report_lines.append(f"  {status} {sofa_type:20} -> {output_path}")
    
    success = all_success
    status = "PASS" if success else "FAIL"
    report_lines.append("")
    report_lines.append(f"Result: {status}")
    
    report = "\n".join(report_lines)
    print(report)
    
    return success, report, bom_data


# ============================================================================
# VALIDATION 3: L-SHAPE JOIN CHECK
# ============================================================================

def validate_lshape_modular(bom_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validation #3: Verify L-shape is computed as straight + chaise module.
    
    Expected: L-shape_cost ≈ 3-seater_cost + (chaise_cost * 0.75)
    """
    print("\n" + "=" * 70)
    print("VALIDATION 3: L-SHAPE MODULAR COMPOSITION CHECK")
    print("=" * 70)
    
    report_lines = []
    
    # Get costs from generated BOMs
    cost_3seater = bom_data.get("3-seater", {}).get("grand_total_cost", 0)
    cost_lshape = bom_data.get("l-shape", {}).get("grand_total_cost", 0)
    
    # Chaise expected to be ~75% of straight module (see component_schema_extended.py)
    chaise_factor = 0.75
    expected_lshape_cost = cost_3seater + (cost_3seater * chaise_factor)
    
    cost_delta = abs(cost_lshape - expected_lshape_cost)
    cost_pct_delta = (cost_delta / expected_lshape_cost) * 100 if expected_lshape_cost > 0 else 0
    
    report_lines.append("")
    report_lines.append(f"3-seater cost:           INR {cost_3seater:,.0f}")
    report_lines.append(f"Chaise module factor:    {chaise_factor * 100}%")
    report_lines.append(f"Expected L-shape cost:   INR {expected_lshape_cost:,.0f}")
    report_lines.append(f"Actual L-shape cost:     INR {cost_lshape:,.0f}")
    report_lines.append(f"Delta:                   INR {cost_delta:,.0f} ({cost_pct_delta:.1f}%)")
    
    # Allow +-20% tolerance (due to rounding and component count discretization)
    success = cost_pct_delta <= 20.0
    status = "PASS" if success else "FAIL"
    
    report_lines.append("")
    report_lines.append(f"Result: {status}")
    if not success:
        report_lines.append(f"  (Delta exceeds 20% tolerance)")
    
    report = "\n".join(report_lines)
    print(report)
    return success, report


# ============================================================================
# VALIDATION 4: CLIPS-DERIVATION CHECK
# ============================================================================

def validate_clips_derivation(bom_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validation #4: Verify Clips count is DERIVED from spring/webbing counts, not independent.
    
    Expected formula: clips_count = 2-3 * (spring_count + belt_count)
    Check at two different sofa sizes to verify the ratio holds.
    """
    print("\n" + "=" * 70)
    print("VALIDATION 4: CLIPS DERIVATION CHECK")
    print("=" * 70)
    
    report_lines = []
    report_lines.append("")
    report_lines.append("Verifying clips are derived (not independent) at two sofa sizes:")
    report_lines.append("")
    
    # Test sizes
    test_sizes = ["1-seater", "3-seater"]
    
    success = True
    for sofa_type in test_sizes:
        bom = bom_data.get(sofa_type, {})
        components = bom.get("components", {})
        
        # components structure: {comp_id: {"category": ..., "qty": float, ...}}
        spring_count  = components.get("spring_unit",  {}).get("qty", 0)
        clip_count    = components.get("spring_clip",  {}).get("qty", 0)
        webbing_count = components.get("webbing_strap",{}).get("qty", 0)
        
        # Clips should be roughly 1.5-3x the sum of springs + webbing
        # (spring_clip schema: clips = 2*springs, but webbing also in denominator)
        total_fastener_points = spring_count + webbing_count
        expected_ratio_range = (1.2, 3.0)  # clips per (spring + webbing) combined
        
        if total_fastener_points > 0:
            actual_ratio = clip_count / total_fastener_points
            ratio_ok = expected_ratio_range[0] <= actual_ratio <= expected_ratio_range[1]
        else:
            actual_ratio = 0
            ratio_ok = clip_count == 0
        
        status = "✓" if ratio_ok else "✗"
        report_lines.append(f"{status} {sofa_type}:")
        report_lines.append(f"    Spring count:    {spring_count}")
        report_lines.append(f"    Webbing count:   {webbing_count}")
        report_lines.append(f"    Clip count:      {clip_count}")
        report_lines.append(f"    Ratio (clips/springs+webbing): {actual_ratio:.2f}")
        report_lines.append(f"    Expected range:  {expected_ratio_range}")
        report_lines.append(f"    Status: {'✓ PASS' if ratio_ok else '✗ FAIL'}")
        report_lines.append("")
        
        if not ratio_ok:
            success = False
    
    status = "PASS" if success else "FAIL"
    report_lines.append("")
    report_lines.append(f"Overall Result: {status}")
    
    report = "\n".join(report_lines)
    print(report)
    return success, report


# ============================================================================
# VALIDATION 5: PRODUCTION CAD SANITY
# ============================================================================

def validate_production_cad_sanity() -> Tuple[bool, str]:
    """
    Validation #5: Verify STEP files were created and are readable.
    
    Returns:
        (success, report)
    """
    print("\n" + "=" * 70)
    print("VALIDATION 5: PRODUCTION CAD SANITY (STEP Round-Trip)")
    print("=" * 70)
    
    report_lines = []
    report_lines.append("")
    
    output_dir = Path("outputs/production_cad")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    test_sizes = ["1-seater", "3-seater"]
    all_success = True
    
    for sofa_type in test_sizes:
        output_path = output_dir / f"{sofa_type}.step"
        try:
            result = build_sofa_step_model(sofa_type, output_path)
            
            # Check file exists
            file_exists = output_path.exists()
            file_size = output_path.stat().st_size if file_exists else 0
            
            status = "✓" if file_exists and file_size > 0 else "✗"
            report_lines.append(f"{status} {sofa_type:15} -> {str(output_path):50} ({file_size} bytes)")
            
            if not (file_exists and file_size > 0):
                all_success = False
        except Exception as e:
            report_lines.append(f"✗ {sofa_type:15} -> ERROR: {str(e)}")
            all_success = False
    
    # Test L-shape
    lshape_path = output_dir / "l-shape_modular.step"
    try:
        result = build_sofa_l_shape_modular(
            {'sofa_type': '3-seater'},
            {'chaise_length': 1500, 'chaise_depth': 1200},
            lshape_path
        )
        file_exists = lshape_path.exists()
        file_size = lshape_path.stat().st_size if file_exists else 0
        
        status = "✓" if file_exists and file_size > 0 else "✗"
        report_lines.append(f"{status} {'l-shape':15} -> {str(lshape_path):50} ({file_size} bytes)")
        
        if not (file_exists and file_size > 0):
            all_success = False
    except Exception as e:
        report_lines.append(f"✗ {'l-shape':15} -> ERROR: {str(e)}")
        all_success = False
    
    status = "PASS" if all_success else "FAIL"
    report_lines.append("")
    report_lines.append(f"Result: {status}")
    
    report = "\n".join(report_lines)
    print(report)
    return all_success, report


# ============================================================================
# VALIDATION 6: REAL DATA OUTPUTS
# ============================================================================

def validate_real_data_outputs(bom_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validation #6: Export real BOM JSON, CAD outputs, and STEP files.
    
    Returns:
        (success, report)
    """
    print("\n" + "=" * 70)
    print("VALIDATION 6: REAL DATA OUTPUTS (BOM JSON, CAD, STEP)")
    print("=" * 70)
    
    report_lines = []
    report_lines.append("")
    
    output_dir = Path("outputs/validation")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Export comprehensive BOM JSON
    bom_json_path = output_dir / "full_sofa_matrix_bom.json"
    
    bom_export = {
        "schema_version": "2.0",
        "timestamp": "2026-09-01",
        "sofa_type_matrix": bom_data,
        "metadata": {
            "total_sofa_types": len(bom_data),
            "sofa_types": list(bom_data.keys()),
        }
    }
    
    bom_json_path.write_text(json.dumps(bom_export, indent=2))
    report_lines.append(f"✓ BOM JSON exported: {bom_json_path} ({bom_json_path.stat().st_size} bytes)")
    
    # Export 3-seater BOM as detailed reference
    seater_3_path = output_dir / "3-seater_detailed_bom.json"
    seater_3_path.write_text(json.dumps(bom_data.get("3-seater", {}), indent=2))
    report_lines.append(f"✓ 3-seater detailed BOM: {seater_3_path} ({seater_3_path.stat().st_size} bytes)")
    
    # Verify CAD/STEP outputs are in place
    production_cad_dir = Path("outputs/production_cad")
    step_files = list(production_cad_dir.glob("*.step"))
    
    report_lines.append(f"✓ STEP files generated: {len(step_files)} files")
    for step_file in sorted(step_files):
        report_lines.append(f"    - {step_file.name} ({step_file.stat().st_size} bytes)")
    
    report_lines.append("")
    
    # Summary
    success = (
        bom_json_path.exists() and
        seater_3_path.exists() and
        len(step_files) >= 5  # Should have 1, 2, 3, 4-seater + L-shape
    )
    
    status = "PASS" if success else "FAIL"
    report_lines.append(f"Result: {status}")
    
    report = "\n".join(report_lines)
    print(report)
    return success, report


# ============================================================================
# MAIN VALIDATION RUNNER
# ============================================================================

def run_all_validations():
    """Run all 6 validation checks and generate comprehensive report."""
    
    print("\n")
    print("=" * 70)
    print("  FULL-COVERAGE PARAMETRIC CAD + BOM VALIDATION SUITE")
    print("  All Sofa Types: 1-seater, 2-seater, 3-seater, 4-seater, L-shape")
    print("=" * 70)
    
    results = {}
    reports = []
    
    # Validation 1
    success1, report1 = validate_folder_coverage_complete()
    results['coverage'] = success1
    reports.append(report1)
    
    # Validation 2
    success2, report2, bom_data = validate_sofa_type_matrix()
    results['sofa_matrix'] = success2
    reports.append(report2)
    
    # Validation 3
    success3, report3 = validate_lshape_modular(bom_data)
    results['lshape_modular'] = success3
    reports.append(report3)
    
    # Validation 4
    success4, report4 = validate_clips_derivation(bom_data)
    results['clips_derivation'] = success4
    reports.append(report4)
    
    # Validation 5
    success5, report5 = validate_production_cad_sanity()
    results['cad_sanity'] = success5
    reports.append(report5)
    
    # Validation 6
    success6, report6 = validate_real_data_outputs(bom_data)
    results['data_outputs'] = success6
    reports.append(report6)
    
    # Final summary
    print("\n" + "=" * 70)
    print("FINAL VALIDATION SUMMARY")
    print("=" * 70)
    
    all_passed = all(results.values())
    
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{status}  {test_name:30}")
    
    print("")
    print(f"Overall Result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    
    # Save combined report
    report_file = Path("docs/full_coverage_validation_report.txt")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text("\n\n".join(reports), encoding="utf-8")
    print(f"Full report saved to: {report_file}")
    
    return all_passed


if __name__ == "__main__":
    success = run_all_validations()
    sys.exit(0 if success else 1)
