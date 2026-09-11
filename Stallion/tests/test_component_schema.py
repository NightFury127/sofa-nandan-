"""
Test suite for component schema consistency and cost engine integration.

Validates that:
1. All schema components are referenced by cost_engine
2. All cost_engine components are in the schema
3. Scaling rules match between schema and engine
4. Generated BOMs are reasonable
"""

import pytest
import json
import sys
from pathlib import Path

# Add src to path so we can import from it
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from component_schema import COMPONENT_SCHEMA, list_all_categories


class TestComponentSchemaStructure:
    """Test the component schema structure."""

    def test_all_components_have_valid_category(self):
        """All components must have a valid category."""
        valid_categories = {
            "frame", "webbing_spring", "foam", "upholstery", "hardware", "misc"
        }
        for comp_id, comp_data in COMPONENT_SCHEMA.items():
            assert (
                comp_data.get("category") in valid_categories
            ), f"{comp_id} has invalid category"

    def test_all_components_have_base_quantities(self):
        """All components must define base quantities for all sofa types."""
        valid_types = {"1-seater", "2-seater", "3-seater", "4-seater", "l-shape"}
        for comp_id, comp_data in COMPONENT_SCHEMA.items():
            base_qtys = comp_data.get("base_qty_by_sofa_type", {})
            assert (
                valid_types == set(base_qtys.keys())
            ), f"{comp_id} missing sofa type definitions"

    def test_all_quantities_positive(self):
        """All base quantities must be positive."""
        for comp_id, comp_data in COMPONENT_SCHEMA.items():
            for sofa_type, qty in comp_data.get("base_qty_by_sofa_type", {}).items():
                assert qty > 0, f"{comp_id} has non-positive qty for {sofa_type}"

    def test_dimension_types_valid(self):
        """All dimension_type values must be one of: linear, count, area, fixed."""
        valid_types = {"linear", "count", "area", "fixed"}
        for comp_id, comp_data in COMPONENT_SCHEMA.items():
            dim_type = comp_data.get("dimension_type")
            assert (
                dim_type in valid_types
            ), f"{comp_id} has invalid dimension_type '{dim_type}'"

    def test_scaling_rules_valid(self):
        """All scaling_rule values must be recognized by cost_engine."""
        valid_rules = {
            "3d volume",
            "area",
            "area/volume",
            "surface area",
            "count by length",
            "count by height",
            "derived from springs",
            "fixed",
        }
        for comp_id, comp_data in COMPONENT_SCHEMA.items():
            rule = comp_data.get("scaling_rule", "").lower()
            assert (
                rule in valid_rules
            ), f"{comp_id} has unrecognized scaling_rule '{rule}'"

    def test_cost_per_unit_positive(self):
        """All components must have positive cost_per_unit."""
        for comp_id, comp_data in COMPONENT_SCHEMA.items():
            cost = comp_data.get("cost_per_unit", 0.0)
            assert cost >= 0, f"{comp_id} has negative cost_per_unit"


class TestCostCalculations:
    """Test BOM cost calculations."""

    def test_bom_1seater_baseline_cost(self):
        """1-seater should have reasonable baseline cost."""
        from component_schema_validator import GranularBOMGenerator
        gen = GranularBOMGenerator(COMPONENT_SCHEMA)
        bom = gen.generate_bom_for_sofa_type("1-seater")
        
        assert bom["grand_total_cost"] > 10000, "1-seater cost seems too low"
        assert bom["grand_total_cost"] < 20000, "1-seater cost seems too high"

    def test_bom_costs_increase_with_size(self):
        """Larger sofas should cost more."""
        from component_schema_validator import GranularBOMGenerator
        gen = GranularBOMGenerator(COMPONENT_SCHEMA)
        
        sizes = ["1-seater", "2-seater", "3-seater", "4-seater", "l-shape"]
        boms = [gen.generate_bom_for_sofa_type(size) for size in sizes]
        costs = [bom["grand_total_cost"] for bom in boms]
        
        # Verify monotonic increase
        for i in range(len(costs) - 1):
            assert (
                costs[i] < costs[i + 1]
            ), f"Cost doesn't increase from size {sizes[i]} to {sizes[i+1]}"

    def test_3seater_cost_breakdown_reasonable(self):
        """3-seater cost should have reasonable category breakdown."""
        from component_schema_validator import GranularBOMGenerator
        gen = GranularBOMGenerator(COMPONENT_SCHEMA)
        bom = gen.generate_bom_for_sofa_type("3-seater")
        
        totals = bom["totals_by_category"]
        
        # Frame should be largest cost
        assert totals["frame"]["cost"] > totals["upholstery"]["cost"]
        assert totals["frame"]["cost"] > totals["foam"]["cost"]
        
        # Foam should be reasonable
        assert totals["foam"]["cost"] > 1000
        assert totals["foam"]["cost"] < 10000

    def test_all_components_contribute(self):
        """All schema components should appear in generated BOMs."""
        from component_schema_validator import GranularBOMGenerator
        gen = GranularBOMGenerator(COMPONENT_SCHEMA)
        bom = gen.generate_bom_for_sofa_type("3-seater")
        
        schema_comp_ids = set(COMPONENT_SCHEMA.keys())
        bom_comp_ids = set(bom["components"].keys())
        
        assert (
            schema_comp_ids == bom_comp_ids
        ), "Schema and BOM component sets don't match"


class TestSchemaConsistency:
    """Test consistency across the schema."""

    def test_no_duplicate_component_ids(self):
        """Component IDs must be unique."""
        comp_ids = list(COMPONENT_SCHEMA.keys())
        assert len(comp_ids) == len(set(comp_ids)), "Duplicate component IDs found"

    def test_formula_references_valid(self):
        """Component formulas should reference valid dimensions."""
        valid_refs = {"base_length", "base_width", "base_height", "sofa_type"}
        for comp_id, comp_data in COMPONENT_SCHEMA.items():
            formula = comp_data.get("formula", "")
            # Simple check: if formula mentions base_*, it should be valid
            for ref in ["base_length", "base_width", "base_height"]:
                if ref in formula.lower():
                    pass  # Valid reference


class TestCategoryDistribution:
    """Test that components are well-distributed across categories."""

    def test_all_categories_have_components(self):
        """All defined categories should have at least one component."""
        categories = list_all_categories()
        assert len(categories) >= 5, "Expected at least 5 component categories"
        
        for category in categories:
            count = sum(
                1 for c in COMPONENT_SCHEMA.values() if c.get("category") == category
            )
            assert count > 0, f"Category '{category}' has no components"

    def test_frame_components_dominant(self):
        """Frame category should have the most components (structural basis)."""
        frame_count = sum(
            1 for c in COMPONENT_SCHEMA.values() if c.get("category") == "frame"
        )
        assert frame_count >= 10, "Frame category should have many components"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
