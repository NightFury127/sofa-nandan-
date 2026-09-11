"""
Granular Component Schema — Single Source of Truth for Cost Engine & CAD Generator

This schema defines all discrete sofa components at the manufacturing level:
~20-25 parts (frame rails, webbing, foam layers, panels, legs) instead of
monolithic aggregates (e.g., "Wood Frame").

Both cost_engine.py and cad_generator_3d.py import this schema to ensure
BOM costing and CAD geometry cannot silently drift apart.

Schema structure:
  component_id: unique identifier (e.g., 'seat_rail_front')
  category: frame | webbing_spring | foam | upholstery | hardware | misc
  dimension_type: 'linear' (scales with L/W/H), 'count' (discrete), 'fixed' (constant)
  formula: explicit parametric rule (references L/W/H or sofa_type)
  unit_of_measurement: meters, kg, pieces, square_meters, etc.
  base_qty_by_sofa_type: {'1-seater': X, '2-seater': Y, ...}
  default_material: material descriptor
  cad_box_scale_mode: how to compute 3D mesh extents (linear_pct, constant_mm, etc.)
"""

COMPONENT_SCHEMA = {
    # =========================================================================
    # SEAT FRAME (structural skeleton holding seat foam & springs)
    # =========================================================================
    "seat_rail_front": {
        "category": "frame",
        "dimension_type": "linear",
        "description": "Front horizontal rail of seat frame",
        "unit_of_measurement": "meters",
        "formula": "base_length * 1.0",
        "base_qty_by_sofa_type": {
            "1-seater": 1.2,
            "2-seater": 1.6,
            "3-seater": 2.1,
            "4-seater": 2.6,
            "l-shape": 3.1,
        },
        "default_material": "hardwood (pine/birch)",
        "cost_per_unit": 850.0,  # per linear meter, adjusted later via cost_sheet
        "scaling_rule": "count by length",
        "cad_box_scale_mode": "linear_length",
    },
    "seat_rail_back": {
        "category": "frame",
        "dimension_type": "linear",
        "description": "Back horizontal rail of seat frame",
        "unit_of_measurement": "meters",
        "formula": "base_length * 1.0",
        "base_qty_by_sofa_type": {
            "1-seater": 1.2,
            "2-seater": 1.6,
            "3-seater": 2.1,
            "4-seater": 2.6,
            "l-shape": 3.1,
        },
        "default_material": "hardwood (pine/birch)",
        "cost_per_unit": 850.0,
        "scaling_rule": "count by length",
        "cad_box_scale_mode": "linear_length",
    },
    "seat_rail_left": {
        "category": "frame",
        "dimension_type": "linear",
        "description": "Left side rail of seat frame",
        "unit_of_measurement": "meters",
        "formula": "base_width * 0.5",
        "base_qty_by_sofa_type": {
            "1-seater": 0.6,
            "2-seater": 0.6,
            "3-seater": 0.6,
            "4-seater": 0.6,
            "l-shape": 0.6,
        },
        "default_material": "hardwood (pine/birch)",
        "cost_per_unit": 850.0,
        "scaling_rule": "count by height",
        "cad_box_scale_mode": "linear_width",
    },
    "seat_rail_right": {
        "category": "frame",
        "dimension_type": "linear",
        "description": "Right side rail of seat frame",
        "unit_of_measurement": "meters",
        "formula": "base_width * 0.5",
        "base_qty_by_sofa_type": {
            "1-seater": 0.6,
            "2-seater": 0.6,
            "3-seater": 0.6,
            "4-seater": 0.6,
            "l-shape": 0.6,
        },
        "default_material": "hardwood (pine/birch)",
        "cost_per_unit": 850.0,
        "scaling_rule": "count by height",
        "cad_box_scale_mode": "linear_width",
    },
    "seat_cross_member": {
        "category": "frame",
        "dimension_type": "count",
        "description": "Cross-bracing members (perpendicular to front-back rails)",
        "unit_of_measurement": "pieces",
        "formula": "ceil(base_width / 300) + 2",  # ~1 per 300mm of width + end blocks
        "base_qty_by_sofa_type": {
            "1-seater": 2.0,
            "2-seater": 3.0,
            "3-seater": 3.0,
            "4-seater": 4.0,
            "l-shape": 5.0,
        },
        "default_material": "hardwood",
        "cost_per_unit": 850.0,
        "scaling_rule": "count by length",
        "cad_box_scale_mode": "constant_mm",
    },
    "seat_deck_board": {
        "category": "frame",
        "dimension_type": "area",
        "description": "Plywood deck/base supporting seat foam",
        "unit_of_measurement": "square_meters",
        "formula": "(base_length * base_width) / 1e6",
        "base_qty_by_sofa_type": {
            "1-seater": 0.8,
            "2-seater": 1.2,
            "3-seater": 1.6,
            "4-seater": 2.0,
            "l-shape": 2.5,
        },
        "default_material": "plywood (15mm)",
        "cost_per_unit": 620.0,  # per square meter
        "scaling_rule": "area",
        "cad_box_scale_mode": "area_based",
    },

    # =========================================================================
    # SEAT WEBBING & SPRINGS (beneath the foam — supports cushioning)
    # =========================================================================
    "webbing_strap": {
        "category": "webbing_spring",
        "dimension_type": "count",
        "description": "Nylon webbing straps (horizontal rows under seat foam)",
        "unit_of_measurement": "pieces",
        "formula": "ceil(base_width / 150)",  # ~1 strap per 150mm of width
        "base_qty_by_sofa_type": {
            "1-seater": 4.0,
            "2-seater": 6.0,
            "3-seater": 6.0,
            "4-seater": 6.0,
            "l-shape": 8.0,
        },
        "default_material": "nylon webbing (50mm wide)",
        "cost_per_unit": 12.0,  # per linear meter
        "scaling_rule": "count by length",
        "cad_box_scale_mode": "count_based",
    },
    "spring_unit": {
        "category": "webbing_spring",
        "dimension_type": "count",
        "description": "Coil spring or sinuous wire spring (seat support)",
        "unit_of_measurement": "pieces",
        "formula": "ceil((base_length * base_width) / 100000)",  # ~1 per 100000 mm^2
        "base_qty_by_sofa_type": {
            "1-seater": 8.0,
            "2-seater": 14.0,
            "3-seater": 20.0,
            "4-seater": 26.0,
            "l-shape": 30.0,
        },
        "default_material": "steel coil spring or sinuous wire",
        "cost_per_unit": 25.0,  # per piece
        "scaling_rule": "count by length",
        "cad_box_scale_mode": "count_based",
    },
    "spring_clip": {
        "category": "webbing_spring",
        "dimension_type": "count",
        "description": "Clips/fasteners securing springs to frame",
        "unit_of_measurement": "pieces",
        "formula": "derived from spring_unit (typically 2-3 clips per spring)",
        "base_qty_by_sofa_type": {
            "1-seater": 16.0,
            "2-seater": 28.0,
            "3-seater": 40.0,
            "4-seater": 52.0,
            "l-shape": 60.0,
        },
        "default_material": "metal clip",
        "cost_per_unit": 2.0,  # per piece
        "scaling_rule": "derived from springs",
        "cad_box_scale_mode": "count_based",
    },

    # =========================================================================
    # BACK FRAME (structural support for backrest)
    # =========================================================================
    "back_rail_top": {
        "category": "frame",
        "dimension_type": "linear",
        "description": "Top horizontal rail of backrest frame",
        "unit_of_measurement": "meters",
        "formula": "base_length * 0.95",
        "base_qty_by_sofa_type": {
            "1-seater": 1.1,
            "2-seater": 1.5,
            "3-seater": 2.0,
            "4-seater": 2.4,
            "l-shape": 2.9,
        },
        "default_material": "hardwood",
        "cost_per_unit": 850.0,
        "scaling_rule": "count by length",
        "cad_box_scale_mode": "linear_length",
    },
    "back_rail_bottom": {
        "category": "frame",
        "dimension_type": "linear",
        "description": "Bottom horizontal rail of backrest frame (at base of back)",
        "unit_of_measurement": "meters",
        "formula": "base_length * 0.95",
        "base_qty_by_sofa_type": {
            "1-seater": 1.1,
            "2-seater": 1.5,
            "3-seater": 2.0,
            "4-seater": 2.4,
            "l-shape": 2.9,
        },
        "default_material": "hardwood",
        "cost_per_unit": 850.0,
        "scaling_rule": "count by length",
        "cad_box_scale_mode": "linear_length",
    },
    "back_cross_member": {
        "category": "frame",
        "dimension_type": "count",
        "description": "Cross-bracing in back frame",
        "unit_of_measurement": "pieces",
        "formula": "ceil(base_length / 400) + 1",
        "base_qty_by_sofa_type": {
            "1-seater": 2.0,
            "2-seater": 2.0,
            "3-seater": 3.0,
            "4-seater": 3.0,
            "l-shape": 4.0,
        },
        "default_material": "hardwood",
        "cost_per_unit": 850.0,
        "scaling_rule": "count by length",
        "cad_box_scale_mode": "constant_mm",
    },

    # =========================================================================
    # FOAM CUSHIONING
    # =========================================================================
    "seat_foam": {
        "category": "foam",
        "dimension_type": "area",
        "description": "Polyurethane foam for seat cushion (typically 100-150mm thick)",
        "unit_of_measurement": "kg",
        "formula": "(base_length * base_width) / 1e6 * 5.0",
        "base_qty_by_sofa_type": {
            "1-seater": 4.0,
            "2-seater": 8.0,
            "3-seater": 12.0,
            "4-seater": 16.0,
            "l-shape": 18.0,
        },
        "default_material": "polyurethane foam, density 30-40 kg/m³",
        "cost_per_unit": 210.0,  # per kg
        "scaling_rule": "area/volume",
        "cad_box_scale_mode": "area_based",
    },
    "back_foam": {
        "category": "foam",
        "dimension_type": "area",
        "description": "Polyurethane foam for backrest cushion",
        "unit_of_measurement": "kg",
        "formula": "(base_length * base_height) / 1e6 * 3.0",
        "base_qty_by_sofa_type": {
            "1-seater": 2.5,
            "2-seater": 5.0,
            "3-seater": 7.5,
            "4-seater": 10.0,
            "l-shape": 11.0,
        },
        "default_material": "polyurethane foam, density 25-35 kg/m³",
        "cost_per_unit": 180.0,  # per kg
        "scaling_rule": "area/volume",
        "cad_box_scale_mode": "area_based",
    },
    "arm_foam": {
        "category": "foam",
        "dimension_type": "area",
        "description": "Polyurethane foam for armrest cushions (left + right)",
        "unit_of_measurement": "kg",
        "formula": "(base_height * base_width * 0.4) / 1e6 * 2.0",  # 2 = both arms
        "base_qty_by_sofa_type": {
            "1-seater": 1.0,
            "2-seater": 1.5,
            "3-seater": 2.0,
            "4-seater": 2.5,
            "l-shape": 3.0,
        },
        "default_material": "polyurethane foam, density 30 kg/m³",
        "cost_per_unit": 200.0,  # per kg
        "scaling_rule": "area/volume",
        "cad_box_scale_mode": "area_based",
    },

    # =========================================================================
    # ARMREST FRAME (left + right, independent structural members)
    # =========================================================================
    "arm_post_front": {
        "category": "frame",
        "dimension_type": "linear",
        "description": "Front vertical post of armrest (left side)",
        "unit_of_measurement": "meters",
        "formula": "base_height * 0.7",
        "base_qty_by_sofa_type": {
            "1-seater": 0.6,
            "2-seater": 0.6,
            "3-seater": 0.6,
            "4-seater": 0.6,
            "l-shape": 0.6,
        },
        "default_material": "hardwood",
        "cost_per_unit": 850.0,
        "scaling_rule": "count by height",
        "cad_box_scale_mode": "linear_height",
    },
    "arm_post_back": {
        "category": "frame",
        "dimension_type": "linear",
        "description": "Back vertical post of armrest (left side)",
        "unit_of_measurement": "meters",
        "formula": "base_height * 0.7",
        "base_qty_by_sofa_type": {
            "1-seater": 0.6,
            "2-seater": 0.6,
            "3-seater": 0.6,
            "4-seater": 0.6,
            "l-shape": 0.6,
        },
        "default_material": "hardwood",
        "cost_per_unit": 850.0,
        "scaling_rule": "count by height",
        "cad_box_scale_mode": "linear_height",
    },
    "arm_top_rail": {
        "category": "frame",
        "dimension_type": "linear",
        "description": "Top horizontal rail of armrest (connects front & back posts)",
        "unit_of_measurement": "meters",
        "formula": "base_width * 0.3",
        "base_qty_by_sofa_type": {
            "1-seater": 0.25,
            "2-seater": 0.25,
            "3-seater": 0.25,
            "4-seater": 0.25,
            "l-shape": 0.25,
        },
        "default_material": "hardwood",
        "cost_per_unit": 850.0,
        "scaling_rule": "count by height",
        "cad_box_scale_mode": "linear_width",
    },

    # =========================================================================
    # UPHOLSTERY (fabric covering & trim)
    # =========================================================================
    "fabric_seat": {
        "category": "upholstery",
        "dimension_type": "area",
        "description": "Fabric covering for seat cushion (includes piping, seams)",
        "unit_of_measurement": "square_meters",
        "formula": "(base_length * base_width) / 1e6 * 1.25",  # +25% for seams
        "base_qty_by_sofa_type": {
            "1-seater": 2.2,
            "2-seater": 3.3,
            "3-seater": 4.4,
            "4-seater": 5.5,
            "l-shape": 6.0,
        },
        "default_material": "upholstery fabric (mixed fibers)",
        "cost_per_unit": 450.0,  # per square meter
        "scaling_rule": "surface area",
        "cad_box_scale_mode": "area_based",
    },
    "fabric_back": {
        "category": "upholstery",
        "dimension_type": "area",
        "description": "Fabric covering for backrest",
        "unit_of_measurement": "square_meters",
        "formula": "(base_length * base_height * 0.4) / 1e6 * 1.2",
        "base_qty_by_sofa_type": {
            "1-seater": 1.5,
            "2-seater": 2.2,
            "3-seater": 2.9,
            "4-seater": 3.6,
            "l-shape": 4.5,
        },
        "default_material": "upholstery fabric",
        "cost_per_unit": 450.0,
        "scaling_rule": "surface area",
        "cad_box_scale_mode": "area_based",
    },
    "fabric_arm": {
        "category": "upholstery",
        "dimension_type": "area",
        "description": "Fabric covering for both armrests",
        "unit_of_measurement": "square_meters",
        "formula": "(base_height * base_width * 0.4) / 1e6 * 1.15",
        "base_qty_by_sofa_type": {
            "1-seater": 0.8,
            "2-seater": 1.2,
            "3-seater": 1.6,
            "4-seater": 2.0,
            "l-shape": 2.5,
        },
        "default_material": "upholstery fabric",
        "cost_per_unit": 450.0,
        "scaling_rule": "surface area",
        "cad_box_scale_mode": "area_based",
    },

    # =========================================================================
    # LEGS & HARDWARE (fixed count, independent of size)
    # =========================================================================
    "leg": {
        "category": "hardware",
        "dimension_type": "fixed",
        "description": "Wooden or plastic leg (fixed count per sofa type)",
        "unit_of_measurement": "pieces",
        "formula": "fixed per sofa_type",
        "base_qty_by_sofa_type": {
            "1-seater": 4.0,
            "2-seater": 4.0,
            "3-seater": 4.0,
            "4-seater": 6.0,
            "l-shape": 6.0,
        },
        "default_material": "wood (hardwood feet)",
        "cost_per_unit": 90.0,  # per piece
        "scaling_rule": "fixed",
        "cad_box_scale_mode": "fixed_height",
    },
    "corner_block": {
        "category": "hardware",
        "dimension_type": "fixed",
        "description": "Corner reinforcement block (frame-to-leg junction)",
        "unit_of_measurement": "pieces",
        "formula": "fixed per sofa_type (typically 1 per leg)",
        "base_qty_by_sofa_type": {
            "1-seater": 4.0,
            "2-seater": 4.0,
            "3-seater": 4.0,
            "4-seater": 6.0,
            "l-shape": 6.0,
        },
        "default_material": "hardwood",
        "cost_per_unit": 30.0,  # per piece
        "scaling_rule": "fixed",
        "cad_box_scale_mode": "constant_mm",
    },
    "hardware_fastener": {
        "category": "hardware",
        "dimension_type": "count",
        "description": "Bolts, screws, nails for frame assembly",
        "unit_of_measurement": "pieces",
        "formula": "ceil((num_frame_members * 3) + 10)",
        "base_qty_by_sofa_type": {
            "1-seater": 20.0,
            "2-seater": 28.0,
            "3-seater": 36.0,
            "4-seater": 44.0,
            "l-shape": 52.0,
        },
        "default_material": "steel fasteners (mixed)",
        "cost_per_unit": 1.5,  # per piece
        "scaling_rule": "count by length",
        "cad_box_scale_mode": "count_based",
    },

    # =========================================================================
    # MISCELLANEOUS (adhesive, thread, etc.)
    # =========================================================================
    "adhesive": {
        "category": "misc",
        "dimension_type": "area",
        "description": "Wood glue, fabric adhesive, etc.",
        "unit_of_measurement": "kg",
        "formula": "(base_length * base_width * base_height) / 1e9 * 0.4",
        "base_qty_by_sofa_type": {
            "1-seater": 0.4,
            "2-seater": 0.6,
            "3-seater": 0.8,
            "4-seater": 1.0,
            "l-shape": 1.1,
        },
        "default_material": "polyurethane glue / fabric adhesive",
        "cost_per_unit": 140.0,  # per kg
        "scaling_rule": "3d volume",
        "cad_box_scale_mode": "area_based",
    },
    "thread": {
        "category": "misc",
        "dimension_type": "area",
        "description": "Sewing thread for upholstery seams",
        "unit_of_measurement": "cones",
        "formula": "ceil((surface_area_ratio * 1.0) / 2)",
        "base_qty_by_sofa_type": {
            "1-seater": 1.0,
            "2-seater": 1.5,
            "3-seater": 2.0,
            "4-seater": 2.5,
            "l-shape": 3.0,
        },
        "default_material": "polyester thread",
        "cost_per_unit": 60.0,  # per cone
        "scaling_rule": "surface area",
        "cad_box_scale_mode": "area_based",
    },
}


def get_schema():
    """Return the complete component schema dict."""
    return COMPONENT_SCHEMA


def get_component_by_id(component_id: str):
    """Retrieve a single component by ID."""
    return COMPONENT_SCHEMA.get(component_id)


def list_components_by_category(category: str):
    """Return all components in a given category."""
    return {
        cid: comp for cid, comp in COMPONENT_SCHEMA.items()
        if comp.get("category") == category.lower()
    }


def list_all_categories():
    """Return all unique categories in the schema."""
    return sorted(set(comp["category"] for comp in COMPONENT_SCHEMA.values()))
