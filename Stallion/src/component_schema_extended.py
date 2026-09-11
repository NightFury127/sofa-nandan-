"""
Extended Component Schema v2 — Full Production-Grade Parametric CAD

This extends the granular component schema (26 components) with:
1. Fusion 360 folder-level metadata (10 folders, 113+ bodies total)
2. Mapping of each component to its parent Fusion folder
3. New handle-related components (Handle Foam, Handle Frame)
4. Support for all sofa types: 1-seater, 2-seater, 3-seater, 4-seater, L-shape
5. L-shape modular architecture (straight module + chaise module, parametrically independent)

This schema is the single source of truth for:
  - cost_engine.py: BOM costing for all sofa types
  - cad_generator_3d.py: 3D mesh preview (trimesh/numpy-stl, unchanged output format)
  - production_cad.py: Production BREP CAD (build123d), tolerances, joinery, STEP export

Schema entry structure (extended from v1):
  component_id: unique identifier
  fusion_folder: parent Fusion 360 folder name
  fusion_body_count: number of bodies in this folder (reference only, not cost-driven)
  category: frame | spring | webbing | foam | upholstery | hardware | handle_frame | handle_foam | misc
  dimension_type: linear | count | area | fixed | instance_multiplier | derived
  formula: explicit parametric rule
  unit_of_measurement: meters, kg, pieces, square_meters, etc.
  base_qty_by_sofa_type: {'1-seater': X, '2-seater': Y, ..., 'l-shape': Z}
  default_material: material descriptor
  cost_per_unit: cost basis per unit
  scaling_rule: how cost scales (matches cost_engine conventions)
  cad_box_scale_mode: for 3D geometry generation
  min_tolerance_mm: minimum global tolerance for BREP (start with 0.1mm global)
  jointery_type: (optional) lap_joint | butt_joint | dowel_joint | bracket | none
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any

# ============================================================================
# IMPORT EXISTING 26-COMPONENT SCHEMA & ADD FUSION FOLDER MAPPINGS
# ============================================================================

from component_schema import COMPONENT_SCHEMA as BASE_COMPONENT_SCHEMA

# ============================================================================
# ADD FUSION FOLDER METADATA TO BASE COMPONENTS
# ============================================================================

def _add_fusion_metadata(component_schema: dict) -> dict:
    """
    Augment base schema components with fusion_folder and related metadata.
    Maps each component to its Fusion 360 folder based on category.
    """
    schema = component_schema.copy()
    
    # Define component -> folder mappings
    folder_mappings = {
        # Seat frame -> Wood Frame
        "seat_rail_front": "Wood Frame",
        "seat_rail_back": "Wood Frame",
        "seat_rail_left": "Wood Frame",
        "seat_rail_right": "Wood Frame",
        "seat_cross_member": "Wood Frame",
        "seat_deck_board": "Plywood",
        
        # Webbing & Springs
        "webbing_strap": "Seat belts",
        "spring_unit": "Springs",
        "spring_clip": "Clips",
        
        # Back frame -> Wood Frame
        "back_rail_top": "Wood Frame",
        "back_rail_bottom": "Wood Frame",
        "back_cross_member": "Wood Frame",
        
        # Foam
        "seat_foam": "Foam",
        "back_foam": "Foam",
        "arm_foam": "Foam",
        
        # Armrest frame -> Wood Frame
        "arm_post_front": "Wood Frame",
        "arm_post_back": "Wood Frame",
        "arm_top_rail": "Wood Frame",
        
        # Upholstery -> Fabric
        "fabric_seat": "Fabric",
        "fabric_back": "Fabric",
        "fabric_arm": "Fabric",
        
        # Hardware
        "leg": "Wood Frame",  # legs attach to frame
        "corner_block": "Wood Frame",
        "hardware_fastener": "Clips",
        
        # Miscellaneous
        "adhesive": "Wood Frame",  # used throughout assembly
        "thread": "Fabric",  # used in upholstery
    }
    
    for comp_id, comp_data in schema.items():
        if comp_id in folder_mappings:
            schema[comp_id]["fusion_folder"] = folder_mappings[comp_id]
            schema[comp_id]["min_tolerance_mm"] = 0.1
            schema[comp_id]["jointery_type"] = "none"
    
    return schema


COMPONENT_SCHEMA_EXTENDED = _add_fusion_metadata(BASE_COMPONENT_SCHEMA)

# Add new handle components (not in base schema)
COMPONENT_SCHEMA_EXTENDED.update({
    "handle_foam": {
        "category": "handle_foam",
        "dimension_type": "count",
        "description": "Foam padding for armrest handles",
        "unit_of_measurement": "kg",
        "formula": "base_height * base_width * 0.05",  # thin padding on top of handle
        "base_qty_by_sofa_type": {
            "1-seater": 0.5,
            "2-seater": 0.8,
            "3-seater": 1.0,
            "4-seater": 1.2,
            "l-shape": 1.5,
        },
        "default_material": "polyurethane foam, density 20-25 kg/m³",
        "cost_per_unit": 150.0,  # per kg
        "scaling_rule": "count by height",
        "cad_box_scale_mode": "area_based",
        "fusion_folder": "Handle Foam",
        "fusion_body_count": 10,
        "min_tolerance_mm": 0.1,
        "jointery_type": "none",
    },
    "handle_frame": {
        "category": "handle_frame",
        "dimension_type": "count",
        "description": "Wooden handle frame structure (graspable top rail for armrests)",
        "unit_of_measurement": "pieces",
        "formula": "2",  # always 2 handles (left + right), independent of sofa size
        "base_qty_by_sofa_type": {
            "1-seater": 2.0,
            "2-seater": 2.0,
            "3-seater": 2.0,
            "4-seater": 2.0,
            "l-shape": 3.0,  # left + right on straight module + 1 on chaise
        },
        "default_material": "hardwood (ash/oak)",
        "cost_per_unit": 200.0,  # per piece
        "scaling_rule": "fixed",
        "cad_box_scale_mode": "fixed_height",
        "fusion_folder": "Handle Frame",
        "fusion_body_count": 22,
        "min_tolerance_mm": 0.1,
        "jointery_type": "lap_joint",
    },
})

# ============================================================================
# FUSION FOLDER METADATA (10 folders from real CAD file)
# ============================================================================

FUSION_FOLDER_STRUCTURE = {
    "back_rest_belts": {
        "folder_name": "Back rest belts",
        "body_count": 15,
        "category": "webbing",
        "description": "Webbing straps supporting the back cushion",
        "component_ids": ["back_foam"],  # Back foam associated with back belts
        "scaling_rule": "area-based (scales with back width × height)",
    },
    "springs": {
        "folder_name": "Springs",
        "body_count": 11,
        "category": "spring",
        "description": "Coil springs and sinuous wire springs for seat support",
        "component_ids": ["spring_unit"],
        "scaling_rule": "count-based (scales with seat area)",
    },
    "clips": {
        "folder_name": "Clips",
        "body_count": 45,  # 45 nested instances (1 body pattern-replicated)
        "category": "hardware",
        "description": "Spring clips and fasteners (DERIVED from spring/belt counts, not independent)",
        "component_ids": ["spring_clip", "hardware_fastener"],
        "scaling_rule": "derived from spring_unit and webbing counts (typically 2-3 clips per spring)",
    },
    "seat_belts": {
        "folder_name": "Seat belts",
        "body_count": 3,
        "category": "webbing",
        "description": "Webbing straps supporting seat cushion",
        "component_ids": ["webbing_strap"],
        "scaling_rule": "count-based (scales with seat width)",
    },
    "foam": {
        "folder_name": "Foam",
        "body_count": 6,  # Mix of named (Foam Pink, Foam Black) + Body IDs
        "category": "foam",
        "description": "Polyurethane foam in different densities for seat, back, and arms",
        "component_ids": ["seat_foam", "arm_foam"],
        "scaling_rule": "area-based (scales with surface area)",
        "material_variants": [
            {"name": "Foam Pink", "density": "35 kg/m³", "cost_index": 1.0},
            {"name": "Foam Black", "density": "40 kg/m³", "cost_index": 1.2},
        ],
    },
    "wood_frame": {
        "folder_name": "Wood Frame",
        "body_count": 23,
        "category": "frame",
        "description": "Structural frame (seat rails, back rails, cross-members, armrest posts, legs, etc.)",
        "component_ids": [
            "seat_rail_front", "seat_rail_back", "seat_rail_left", "seat_rail_right",
            "seat_cross_member", "back_rail_top", "back_rail_bottom", "back_cross_member",
            "arm_post_front", "arm_post_back", "arm_top_rail", "leg", "corner_block",
            "adhesive"
        ],
        "scaling_rule": "mixed (rails linear, cross-members count-based)",
    },
    "plywood": {
        "folder_name": "Plywood",
        "body_count": 2,  # Body1, Body2 (deck sheets)
        "category": "frame",
        "description": "Plywood deck boards supporting seat foam",
        "component_ids": ["seat_deck_board"],
        "scaling_rule": "area-based",
    },
    "handle_foam": {
        "folder_name": "Handle Foam",
        "body_count": 10,
        "category": "handle_foam",
        "description": "Foam padding on top of handles",
        "component_ids": ["handle_foam"],
        "scaling_rule": "count-based (scales with number of handles)",
    },
    "fabric": {
        "folder_name": "Fabric",
        "body_count": 2,  # Body88 + Body226 (57 nested instances)
        "category": "upholstery",
        "description": "Upholstery fabric covering (plain surfaces + nested trim instances)",
        "component_ids": ["fabric_seat", "fabric_back", "fabric_arm", "thread"],
        "scaling_rule": "area-based + instance_multiplier",
        "nested_components": [
            {"name": "Body226", "type": "nested_instances", "count": 57, "per_unit": True}
        ],
    },
    "handle_frame": {
        "folder_name": "Handle Frame",
        "body_count": 22,
        "category": "handle_frame",
        "description": "Wooden handle frame structure (graspable rails on armrests)",
        "component_ids": ["handle_frame"],
        "scaling_rule": "fixed (2 handles standard)",
    },
}

# ============================================================================
# LSHAPE MODULAR CONFIGURATION
# ============================================================================

LSHAPE_MODULE_CONFIG = {
    "description": "L-shape sofa = straight module + chaise corner module, parametrically independent",
    "straight_module": {
        "sofa_type": "3-seater",  # default base straight module
        "description": "Main seating area (scales by base_length, base_width, base_height)",
    },
    "chaise_module": {
        "sofa_type": "chaise",  # special config
        "description": "Corner/lounge extension (scales by chaise_length, chaise_depth)",
        "independent_parameters": {
            "chaise_length": "length of chaise extension (mm)",
            "chaise_depth": "depth of chaise extension (mm)",
            "chaise_height": "height of chaise backrest (mm)",
            "orientation": "left | right (which corner the chaise attaches to)",
        },
        "component_scaling_factor": 0.75,  # chaise components scale to 75% of straight module
    },
    "join_logic": "shared_edge (chaise attaches to one end of straight module)",
    "bom_computation": "straight_module_bom + chaise_module_bom",
}

# ============================================================================
# TOLERANCE & JOINERY DEFAULTS (BREP Production CAD)
# ============================================================================

PRODUCTION_CAD_DEFAULTS = {
    "global_tolerance_mm": 0.1,
    "material_tolerances": {
        "hardwood": {"linear": 0.5, "thickness": 0.3},
        "plywood": {"linear": 0.5, "thickness": 0.2},
        "hardware": {"linear": 0.1},
    },
    "joinery_types": {
        "lap_joint": {"description": "Interlocking half-depth joints", "depth_pct": 50},
        "butt_joint": {"description": "Simple edge-to-edge with fasteners", "depth_pct": 0},
        "dowel_joint": {"description": "Wooden dowel reinforcement", "dowel_mm": 8},
        "bracket_joint": {"description": "Metal L-bracket reinforcement", "type": "L-bracket"},
    },
    "fastener_representation": {
        "style": "simplified_cylinders",  # or "hole_features"
        "diameter_mm": 6,
        "depth_mm": 20,
    },
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_schema_extended() -> Dict[str, Any]:
    """Return the extended 28-component schema."""
    return COMPONENT_SCHEMA_EXTENDED.copy()


def get_component_extended(component_id: str) -> Optional[Dict[str, Any]]:
    """Get a single component from extended schema."""
    return COMPONENT_SCHEMA_EXTENDED.get(component_id)


def get_components_by_fusion_folder(folder_name: str) -> List[str]:
    """Get all component IDs for a given Fusion folder."""
    for folder_key, folder_data in FUSION_FOLDER_STRUCTURE.items():
        if folder_data["folder_name"] == folder_name:
            return folder_data.get("component_ids", [])
    return []


def get_folder_by_component(component_id: str) -> Optional[str]:
    """Get the Fusion folder for a component."""
    comp = get_component_extended(component_id)
    if comp:
        return comp.get("fusion_folder")
    return None


def list_all_fusion_folders() -> List[Dict[str, Any]]:
    """Return all Fusion folder metadata."""
    return list(FUSION_FOLDER_STRUCTURE.values())


def export_schema_to_json(output_path: Optional[Path] = None) -> str:
    """Export extended schema to JSON format."""
    export_data = {
        "schema_version": "2.0",
        "components": COMPONENT_SCHEMA_EXTENDED,
        "fusion_folders": FUSION_FOLDER_STRUCTURE,
        "lshape_config": LSHAPE_MODULE_CONFIG,
        "production_cad_defaults": PRODUCTION_CAD_DEFAULTS,
        "metadata": {
            "total_components": len(COMPONENT_SCHEMA_EXTENDED),
            "total_fusion_folders": len(FUSION_FOLDER_STRUCTURE),
            "sofa_types": ["1-seater", "2-seater", "3-seater", "4-seater", "l-shape"],
        }
    }
    
    json_str = json.dumps(export_data, indent=2)
    
    if output_path:
        output_path.write_text(json_str, encoding="utf-8")
    
    return json_str


def validate_folder_coverage() -> tuple[List[str], List[str]]:
    """
    Validate that all components are mapped to folders and all folders have components.
    Returns: (unmapped_components, empty_folders)
    """
    unmapped = []
    for comp_id in COMPONENT_SCHEMA_EXTENDED.keys():
        if "fusion_folder" not in COMPONENT_SCHEMA_EXTENDED[comp_id]:
            unmapped.append(comp_id)
    
    empty_folders = []
    for folder_key, folder_data in FUSION_FOLDER_STRUCTURE.items():
        if not folder_data.get("component_ids"):
            empty_folders.append(folder_data["folder_name"])
    
    return unmapped, empty_folders


# ============================================================================
# SOFA TYPE CONFIGURATION (used by cost_engine and cad_generator)
# ============================================================================

SOFA_TYPES = {
    "1-seater": {
        "base_length": 800,    # mm
        "base_width": 900,     # mm (arm to arm)
        "base_height": 900,    # mm (seat height)
        "seat_height": 450,    # mm (from floor to seat surface)
        "back_height": 450,    # mm (back cushion height)
        "description": "Single-seat sofa",
    },
    "2-seater": {
        "base_length": 1500,
        "base_width": 900,
        "base_height": 900,
        "seat_height": 450,
        "back_height": 450,
        "description": "Two-seat sofa",
    },
    "3-seater": {
        "base_length": 2000,
        "base_width": 900,
        "base_height": 900,
        "seat_height": 450,
        "back_height": 450,
        "description": "Three-seat sofa (standard)",
    },
    "4-seater": {
        "base_length": 2400,
        "base_width": 900,
        "base_height": 900,
        "seat_height": 450,
        "back_height": 450,
        "description": "Four-seat sofa (sectional)",
    },
    "l-shape": {
        "straight_module": {
            "base_length": 2000,
            "base_width": 900,
            "base_height": 900,
            "seat_height": 450,
            "back_height": 450,
        },
        "chaise_module": {
            "chaise_length": 1500,  # extension from main sofa
            "chaise_depth": 1200,   # how far it sticks out
            "chaise_height": 900,
            "orientation": "right",  # right-side chaise
        },
        "description": "L-shape sectional (straight + chaise corner)",
    },
}


if __name__ == "__main__":
    # Test export
    schema_json = export_schema_to_json()
    print(f"Extended schema JSON length: {len(schema_json)} characters")
    print(f"Total components: {len(COMPONENT_SCHEMA_EXTENDED)}")
    print(f"Total Fusion folders: {len(FUSION_FOLDER_STRUCTURE)}")
    
    # Validate coverage
    unmapped, empty = validate_folder_coverage()
    if unmapped:
        print(f"\n⚠️  WARNING: Unmapped components: {unmapped}")
    if empty:
        print(f"⚠️  WARNING: Empty folders: {empty}")
    else:
        print("\n✅ All components mapped to folders")
        print("✅ All folders have components")
