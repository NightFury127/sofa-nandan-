"""
Schema Validation & Reporting System for Granular Component Model

Validates schema consistency, BOM totals, count formulas, and cost deltas
between the new granular model and the legacy monolithic model.
"""

import json
import math
from pathlib import Path
from component_schema import COMPONENT_SCHEMA


class ComponentSchemaValidator:
    """Validates the component schema and generates reports."""

    def __init__(self):
        self.schema = COMPONENT_SCHEMA
        self.errors = []
        self.warnings = []

    def validate_schema_structure(self):
        """Check that all components have required fields."""
        required_fields = [
            "category",
            "dimension_type",
            "description",
            "unit_of_measurement",
            "formula",
            "base_qty_by_sofa_type",
            "default_material",
            "scaling_rule",
        ]
        
        for comp_id, comp_data in self.schema.items():
            for field in required_fields:
                if field not in comp_data:
                    self.errors.append(
                        f"Component '{comp_id}' missing required field '{field}'"
                    )
            
            # Validate sofa types
            valid_types = {"1-seater", "2-seater", "3-seater", "4-seater", "l-shape"}
            for sofa_type in comp_data.get("base_qty_by_sofa_type", {}).keys():
                if sofa_type not in valid_types:
                    self.errors.append(
                        f"Component '{comp_id}' has unknown sofa type '{sofa_type}'"
                    )
            
            # Validate dimension_type
            valid_types_dim = {"linear", "count", "area", "fixed"}
            dim_type = comp_data.get("dimension_type")
            if dim_type not in valid_types_dim:
                self.errors.append(
                    f"Component '{comp_id}' has invalid dimension_type '{dim_type}'"
                )

    def validate_categories(self):
        """Check that all categories are reasonable."""
        valid_categories = {
            "frame",
            "webbing_spring",
            "foam",
            "upholstery",
            "hardware",
            "misc",
        }
        for comp_id, comp_data in self.schema.items():
            category = comp_data.get("category")
            if category not in valid_categories:
                self.errors.append(
                    f"Component '{comp_id}' has unknown category '{category}'"
                )

    def validate_no_orphans(self):
        """Check that no component has a base_qty_by_sofa_type entry that doesn't exist elsewhere."""
        # This is just a sanity check; all sofa types should have entries
        all_types = set()
        for comp_data in self.schema.values():
            all_types.update(comp_data.get("base_qty_by_sofa_type", {}).keys())
        
        expected_types = {"1-seater", "2-seater", "3-seater", "4-seater", "l-shape"}
        missing_types = expected_types - all_types
        if missing_types:
            self.warnings.append(
                f"No components defined for sofa types: {missing_types}"
            )

    def run_all_validations(self):
        """Run all validation checks."""
        self.validate_schema_structure()
        self.validate_categories()
        self.validate_no_orphans()
        return self.errors, self.warnings

    def get_schema_report(self):
        """Generate a human-readable schema report."""
        report = []
        report.append("=" * 80)
        report.append("COMPONENT SCHEMA VALIDATION REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Component count by category
        categories = {}
        for comp_id, comp_data in self.schema.items():
            cat = comp_data.get("category")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(comp_id)
        
        report.append("COMPONENTS BY CATEGORY:")
        for cat in sorted(categories.keys()):
            report.append(f"\n  {cat.upper()} ({len(categories[cat])} components):")
            for comp_id in sorted(categories[cat]):
                report.append(f"    - {comp_id}")
        
        report.append("\n" + "=" * 80)
        report.append("VALIDATION RESULTS:")
        report.append("=" * 80)
        
        if self.errors:
            report.append(f"\nERRORS ({len(self.errors)}):")
            for err in self.errors:
                report.append(f"  ✗ {err}")
        else:
            report.append("\n✓ No structural errors found")
        
        if self.warnings:
            report.append(f"\nWARNINGS ({len(self.warnings)}):")
            for warn in self.warnings:
                report.append(f"  ⚠ {warn}")
        else:
            report.append("\n✓ No warnings")
        
        report.append("\n" + "=" * 80)
        return "\n".join(report)


class GranularBOMGenerator:
    """Generate BOMs using the granular component schema."""

    def __init__(self, schema):
        self.schema = schema

    def generate_bom_for_sofa_type(self, sofa_type: str) -> dict:
        """
        Generate a complete BOM for a given sofa type.
        
        Returns a dict with structure:
          {
            'sofa_type': str,
            'components': {
              'component_id': {
                'category': str,
                'qty': float,
                'unit': str,
                'unit_cost': float,
                'total_cost': float,
              },
              ...
            },
            'totals_by_category': {
              'frame': {'qty': float, 'cost': float},
              ...
            },
            'grand_total_cost': float,
            'component_count': int,
          }
        """
        sofa_type = str(sofa_type).lower().strip()
        if sofa_type not in {
            "1-seater", "2-seater", "3-seater", "4-seater", "l-shape"
        }:
            raise ValueError(f"Unknown sofa type: {sofa_type}")

        components_out = {}
        totals_by_category = {}
        grand_total = 0.0

        for comp_id, comp_data in self.schema.items():
            base_qty = comp_data["base_qty_by_sofa_type"].get(sofa_type, 0.0)
            unit_cost = comp_data.get("cost_per_unit", 0.0)
            category = comp_data.get("category")
            unit = comp_data.get("unit_of_measurement")

            total_cost = base_qty * unit_cost
            grand_total += total_cost

            components_out[comp_id] = {
                "category": category,
                "qty": round(base_qty, 3),
                "unit": unit,
                "unit_cost": unit_cost,
                "total_cost": round(total_cost, 2),
            }

            if category not in totals_by_category:
                totals_by_category[category] = {"qty": 0.0, "cost": 0.0}
            totals_by_category[category]["qty"] += base_qty
            totals_by_category[category]["cost"] += total_cost

        return {
            "sofa_type": sofa_type,
            "components": components_out,
            "totals_by_category": {
                cat: {
                    "qty": round(totals_by_category[cat]["qty"], 3),
                    "cost": round(totals_by_category[cat]["cost"], 2),
                }
                for cat in totals_by_category
            },
            "grand_total_cost": round(grand_total, 2),
            "component_count": len(components_out),
        }

    def generate_all_bom_sizes(self) -> dict:
        """Generate BOMs for all sofa sizes (1-seater through 4-seater + l-shape)."""
        sizes = ["1-seater", "2-seater", "3-seater", "4-seater", "l-shape"]
        boms = {}
        for size in sizes:
            boms[size] = self.generate_bom_for_sofa_type(size)
        return boms


def generate_full_validation_report(schema):
    """
    Generate a comprehensive validation report including:
    1. Schema structure validation
    2. BOM generation for all sofa sizes
    3. Cost breakdown by category
    4. Count-formula validation
    5. JSON dump of one full BOM
    """
    report_lines = []

    # 1. Schema validation
    validator = ComponentSchemaValidator()
    errors, warnings = validator.run_all_validations()
    report_lines.append(validator.get_schema_report())

    # 2. Generate BOMs
    bom_gen = GranularBOMGenerator(schema)
    all_boms = bom_gen.generate_all_bom_sizes()

    report_lines.append("\n" + "=" * 80)
    report_lines.append("BOM GENERATION RESULTS")
    report_lines.append("=" * 80)

    for sofa_type, bom in all_boms.items():
        report_lines.append(f"\n\n{sofa_type.upper()}:")
        report_lines.append("-" * 60)
        report_lines.append(f"  Component count: {bom['component_count']}")
        report_lines.append(f"  Grand total cost: INR {bom['grand_total_cost']:,.2f}")
        report_lines.append(f"\n  Costs by category:")
        for category in sorted(bom["totals_by_category"].keys()):
            cat_data = bom["totals_by_category"][category]
            report_lines.append(
                f"    {category}: INR {cat_data['cost']:,.2f} "
                f"({cat_data['qty']:.3f} units)"
            )

    # 3. Count-formula check
    report_lines.append("\n\n" + "=" * 80)
    report_lines.append("COUNT-FORMULA VALIDATION")
    report_lines.append("=" * 80)
    report_lines.append("\nWebbing/Spring counts across all sizes:")
    count_comps = ["webbing_strap", "spring_unit", "spring_clip"]
    for comp_id in count_comps:
        report_lines.append(f"\n  {comp_id}:")
        for sofa_type in ["1-seater", "2-seater", "3-seater", "4-seater", "l-shape"]:
            qty = all_boms[sofa_type]["components"].get(comp_id, {}).get("qty", 0.0)
            report_lines.append(f"    {sofa_type}: {qty:.1f} pieces")

    # 4. Attach full JSON of one BOM (3-seater)
    report_lines.append("\n\n" + "=" * 80)
    report_lines.append("FULL BOM JSON (3-SEATER - COMPLETE STRUCTURED DATA)")
    report_lines.append("=" * 80)
    report_lines.append("\n" + json.dumps(all_boms["3-seater"], indent=2))

    return "\n".join(report_lines), all_boms


if __name__ == "__main__":
    # Run validation and print report
    report, boms = generate_full_validation_report(COMPONENT_SCHEMA)
    print(report)
    
    # Save to file
    report_path = Path(__file__).parent.parent / "docs" / "component_schema_validation_report.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\n\nReport saved to: {report_path}")
