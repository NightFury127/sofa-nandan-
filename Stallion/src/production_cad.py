"""
Production CAD Module — BREP-Based Parametric Sofa Generation (build123d backend)

The CAD deliverable for Stallion is a STEP file (ISO-10303), not a GLB mesh.
DXF 2-view drawings stay in cad_generator.py; this module owns the 3D solid.

Usage:
  from production_cad import build_sofa_step_model
  step_file = build_sofa_step_model('3-seater', Path('out.step'), dimensions={...})
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json

try:
    from build123d import *
    HAS_BUILD123D = True
except ImportError:
    HAS_BUILD123D = False
    print("WARNING: build123d not installed. Production CAD features unavailable.")

# ============================================================================
# TYPE / DIMENSION HELPERS
# ============================================================================

_TYPE_ALIASES = {
    "1-seater": "1-seater",
    "1_seater": "1-seater",
    "one-seater": "1-seater",
    "2-seater": "2-seater",
    "2_seater": "2-seater",
    "two-seater": "2-seater",
    "3-seater": "3-seater",
    "3_seater": "3-seater",
    "three-seater": "3-seater",
    "4-seater": "4-seater",
    "4_seater": "4-seater",
    "4-seater-plus": "4-seater",
    "4_seater_plus": "4-seater",
    "l-shape": "l-shape",
    "l_shape": "l-shape",
    "lshape": "l-shape",
    "chaise": "chaise",
}


def normalize_sofa_type(sofa_type: str) -> str:
    if not sofa_type:
        return "3-seater"
    key = str(sofa_type).strip().lower().replace(" ", "-").replace("_", "-")
    return _TYPE_ALIASES.get(key, key)


def map_user_dimensions(dimensions: Optional[Dict], sofa_type: str = "3-seater") -> Dict:
    """Accept API/request dims (length/width/height) or template keys (base_length)."""
    if not dimensions:
        return {}
    d = dict(dimensions)
    length = d.pop("length_mm", None)
    if length is None:
        length = d.pop("length", None)
    width = d.pop("width_mm", None)
    if width is None:
        width = d.pop("width", None)
    height = d.pop("height_mm", None)
    if height is None:
        height = d.pop("height", None)

    if length is not None:
        d.setdefault("base_length", float(length))
        d.setdefault("chaise_length", float(length) * 0.75)
    if width is not None:
        d.setdefault("base_width", float(width))
        d.setdefault("chaise_depth", float(width) * 1.25)
    if height is not None:
        h = float(height)
        d.setdefault("base_height", h)
        d.setdefault("chaise_height", h)
        d.setdefault("seat_height", round(h * 0.50))
        d.setdefault("back_height", round(h * 0.50))
    return d


def _write_step(assembly: Any, output_path: Path) -> str:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if assembly is None:
        raise RuntimeError("No CAD assembly to export")
    ok = export_step(assembly, str(output_path))
    if not ok or not output_path.exists() or output_path.stat().st_size < 200:
        raise RuntimeError(f"STEP export failed for {output_path}")
    return str(output_path)


# ============================================================================
# CONSTANTS
# ============================================================================

# Material-specific tolerances (per PRODUCTION_CAD_DEFAULTS in extended schema)
TOLERANCES = {
    "hardwood": {"linear": 0.5, "thickness": 0.3},  # mm
    "plywood": {"linear": 0.5, "thickness": 0.2},
    "hardware": {"linear": 0.1},
    "foam": {"linear": 2.0},  # foam is less precision-critical
    "fabric": {"linear": 5.0},  # fabric is approximate
}

# ============================================================================
# SOFA DIMENSION MODELS
# ============================================================================

class SofaDimensions:
    """Parametric dimensions for sofa modules."""
    
    def __init__(self, sofa_type: str, custom_dims: Optional[Dict] = None):
        """
        Initialize dimensions for a sofa type.
        
        Args:
            sofa_type: '1-seater', '2-seater', '3-seater', '4-seater', or 'chaise' (for L-shape)
            custom_dims: Override default dimensions (dict with keys like 'base_length', etc.)
        """
        self.sofa_type = normalize_sofa_type(sofa_type)
        
        # Default dimensions (mm)
        defaults = {
            '1-seater': {
                'base_length': 800,
                'base_width': 900,
                'base_height': 900,
                'seat_height': 450,
                'back_height': 450,
                'rail_thickness': 50,
                'foam_thickness': 150,
            },
            '2-seater': {
                'base_length': 1500,
                'base_width': 900,
                'base_height': 900,
                'seat_height': 450,
                'back_height': 450,
                'rail_thickness': 50,
                'foam_thickness': 150,
            },
            '3-seater': {
                'base_length': 2000,
                'base_width': 900,
                'base_height': 900,
                'seat_height': 450,
                'back_height': 450,
                'rail_thickness': 50,
                'foam_thickness': 150,
            },
            '4-seater': {
                'base_length': 2400,
                'base_width': 900,
                'base_height': 900,
                'seat_height': 450,
                'back_height': 450,
                'rail_thickness': 50,
                'foam_thickness': 150,
            },
            'chaise': {
                'chaise_length': 1500,  # extension length
                'chaise_depth': 1200,   # how far it sticks out
                'chaise_height': 900,
                'base_width': 900,
                'seat_height': 450,
                'back_height': 450,
                'rail_thickness': 50,
                'foam_thickness': 150,
            }
        }
        
        # Use defaults or custom overrides
        mapped = map_user_dimensions(custom_dims, self.sofa_type)
        self.dims = defaults.get(self.sofa_type, defaults["3-seater"]).copy()
        if mapped:
            self.dims.update(mapped)
        if self.sofa_type == "chaise":
            self.dims.setdefault("base_length", self.dims.get("chaise_length", 1500))
            self.dims.setdefault("base_width", self.dims.get("chaise_depth", 1200))
            self.dims.setdefault("base_height", self.dims.get("chaise_height", 900))
    
    def get(self, key: str, default: Optional[float] = None) -> float:
        """Get a dimension value."""
        return self.dims.get(key, default)
    
    def __repr__(self):
        return f"SofaDimensions({self.sofa_type}, {self.dims})"


# ============================================================================
# BREP COMPONENT BUILDERS
# ============================================================================

class SofaComponentBuilder:
    """Factory for building individual sofa components as BREP solids."""
    
    @staticmethod
    def build_rail(
        length_mm: float,
        width_mm: float = 50,
        height_mm: float = 50,
        name: str = "rail"
    ) -> Any:
        """
        Build a structural rail (e.g., seat_rail_front).
        
        Args:
            length_mm: Rail length along primary axis
            width_mm: Rail width (perpendicular to length)
            height_mm: Rail height (vertical thickness)
            name: Component name for labeling
        
        Returns:
            build123d Box object (BREP solid)
        """
        if not HAS_BUILD123D:
            return None
        
        # Create rail as a rectangular box
        # Position at origin; caller will transform to final location
        rail = Box(
            length=length_mm,
            width=width_mm,
            height=height_mm,
            align=(Align.CENTER, Align.CENTER, Align.MIN)
        )
        return rail
    
    @staticmethod
    def build_foam_block(
        length_mm: float,
        width_mm: float,
        thickness_mm: float = 150,
        name: str = "foam"
    ) -> Any:
        """
        Build a foam cushion block.
        
        Args:
            length_mm, width_mm: Foam dimensions
            thickness_mm: Foam thickness
            name: Component name
        
        Returns:
            build123d Box object
        """
        if not HAS_BUILD123D:
            return None
        
        foam = Box(
            length=length_mm,
            width=width_mm,
            height=thickness_mm,
            align=(Align.CENTER, Align.CENTER, Align.MIN)
        )
        return foam
    
    @staticmethod
    def build_leg(height_mm: float = 100, base_mm: float = 50) -> Any:
        """
        Build a sofa leg.
        
        Args:
            height_mm: Leg height from floor to frame
            base_mm: Leg base width/depth
        
        Returns:
            build123d Box object
        """
        if not HAS_BUILD123D:
            return None
        
        leg = Box(
            length=base_mm,
            width=base_mm,
            height=height_mm,
            align=(Align.CENTER, Align.CENTER, Align.MIN)
        )
        return leg
    
    @staticmethod
    def add_tolerance_feature(
        solid: Any,
        feature_name: str,
        tolerance_mm: float = 0.1,
        material: str = "hardwood"
    ) -> Any:
        """
        Add a tolerance annotation feature to a solid (for STEP export).
        
        In build123d, this is typically metadata attached to the solid.
        For now, we store tolerance info as a comment in the solid's name.
        
        Args:
            solid: build123d solid object
            feature_name: Name of the feature/dimension being toleranced
            tolerance_mm: Tolerance value in mm
            material: Material type (determines tolerance basis)
        
        Returns:
            Same solid with metadata attached
        """
        if solid is None:
            return None
        
        # Store tolerance info (build123d doesn't have formal GD&T,
        # so we annotate via comments/metadata)
        if not hasattr(solid, '_metadata'):
            solid._metadata = {}
        
        solid._metadata['tolerance_mm'] = tolerance_mm
        solid._metadata['feature_name'] = feature_name
        solid._metadata['material'] = material
        
        return solid


# ============================================================================
# SOFA ASSEMBLY BUILDER
# ============================================================================

class SofaAssemblyBuilder:
    """Builds a complete sofa assembly from parametric dimensions."""
    
    def __init__(self, sofa_type: str, dims: Optional[SofaDimensions] = None):
        """
        Initialize builder for a sofa type.
        
        Args:
            sofa_type: '1-seater', '2-seater', '3-seater', '4-seater', or 'l-shape'
            dims: SofaDimensions object (uses defaults if None)
        """
        self.sofa_type = normalize_sofa_type(sofa_type)
        self.dims = dims or SofaDimensions(self.sofa_type)
        self.components = {}  # Dict of built components
        self.assembly = None   # Final assembled model
    
    def build_seat_frame(self) -> Dict[str, Any]:
        """Build the seat frame structure."""
        if not HAS_BUILD123D:
            return {}
        
        components = {}
        dims = self.dims
        
        # Front rail
        front_rail = SofaComponentBuilder.build_rail(
            length_mm=dims.get('base_length', 800),
            width_mm=50,
            height_mm=50,
            name="seat_rail_front"
        )
        components['seat_rail_front'] = front_rail
        
        # Back rail (parallel to front)
        back_rail = SofaComponentBuilder.build_rail(
            length_mm=dims.get('base_length', 800),
            width_mm=50,
            height_mm=50,
            name="seat_rail_back"
        )
        # Translate back rail to rear position
        back_rail = back_rail.translate((0, dims.get('base_width', 900) - 50, 0))
        components['seat_rail_back'] = back_rail
        
        # Plywood deck
        deck = SofaComponentBuilder.build_foam_block(
            length_mm=dims.get('base_length', 800),
            width_mm=dims.get('base_width', 900),
            thickness_mm=15,  # 15mm plywood
            name="seat_deck_board"
        )
        deck = deck.translate((0, 0, dims.get('seat_height', 450) - 7.5))
        components['seat_deck_board'] = deck
        
        return components
    
    def build_back_frame(self) -> Dict[str, Any]:
        """Build the backrest frame."""
        if not HAS_BUILD123D:
            return {}
        
        components = {}
        dims = self.dims
        
        # Back rails (top and bottom)
        back_top = SofaComponentBuilder.build_rail(
            length_mm=dims.get('base_length', 800),
            name="back_rail_top"
        )
        back_top = back_top.translate((
            0, 0,
            dims.get('seat_height', 450) + dims.get('back_height', 450) - 25
        ))
        components['back_rail_top'] = back_top
        
        back_bottom = SofaComponentBuilder.build_rail(
            length_mm=dims.get('base_length', 800),
            name="back_rail_bottom"
        )
        back_bottom = back_bottom.translate((0, 0, dims.get('seat_height', 450)))
        components['back_rail_bottom'] = back_bottom
        
        return components
    
    def build_legs(self) -> Dict[str, Any]:
        """Build sofa legs."""
        if not HAS_BUILD123D:
            return {}
        
        components = {}
        dims = self.dims
        
        # Determine leg count based on sofa type
        leg_count = {
            '1-seater': 4,
            '2-seater': 4,
            '3-seater': 4,
            '4-seater': 6,
        }.get(self.sofa_type, 4)
        
        # Leg spacing
        length = dims.get('base_length', 800)
        spacing = length / (leg_count - 1) if leg_count > 1 else 0
        
        for i in range(leg_count):
            leg = SofaComponentBuilder.build_leg(
                height_mm=dims.get('seat_height', 450),
                base_mm=50
            )
            x_pos = (i * spacing) - (length / 2)
            leg = leg.translate((x_pos, 25, 0))
            components[f'leg_{i}'] = leg
        
        return components
    
    def build_foam_cushions(self) -> Dict[str, Any]:
        """Build foam cushion blocks."""
        if not HAS_BUILD123D:
            return {}
        
        components = {}
        dims = self.dims
        
        # Seat foam
        seat_foam = SofaComponentBuilder.build_foam_block(
            length_mm=dims.get('base_length', 800),
            width_mm=dims.get('base_width', 900),
            thickness_mm=dims.get('foam_thickness', 150),
            name="seat_foam"
        )
        seat_foam = seat_foam.translate((0, 0, dims.get('seat_height', 450)))
        components['seat_foam'] = seat_foam
        
        # Back foam
        back_foam = SofaComponentBuilder.build_foam_block(
            length_mm=dims.get('base_length', 800),
            width_mm=100,  # thin back cushion
            thickness_mm=dims.get('foam_thickness', 150),
            name="back_foam"
        )
        back_foam = back_foam.translate((
            0,
            dims.get('base_width', 900) - 50,
            dims.get('seat_height', 450)
        ))
        components['back_foam'] = back_foam
        
        return components
    
    def assemble(self) -> Any:
        """Assemble all components into a single model."""
        if not HAS_BUILD123D:
            return None
        
        # Build all component groups
        seat_components = self.build_seat_frame()
        back_components = self.build_back_frame()
        leg_components = self.build_legs()
        foam_components = self.build_foam_cushions()
        
        # Combine all components
        self.components = {
            **seat_components,
            **back_components,
            **leg_components,
            **foam_components,
        }
        
        solids = [v for v in self.components.values() if v is not None]
        if solids:
            self.assembly = Compound(solids, label=f"{self.sofa_type} sofa")
        return self.assembly


# ============================================================================
# PUBLIC API FUNCTIONS
# ============================================================================

def _build_l_shape_assembly(dimensions: Optional[Dict] = None) -> Any:
    mapped = map_user_dimensions(dimensions, "l-shape")
    straight_dims = SofaDimensions("3-seater", mapped)
    chaise_dims = SofaDimensions("chaise", mapped)

    straight_builder = SofaAssemblyBuilder("3-seater", straight_dims)
    straight_builder.assemble()
    chaise_builder = SofaAssemblyBuilder("chaise", chaise_dims)
    chaise_builder.assemble()

    offset_x = (straight_dims.get("base_length", 2000) / 2.0) + (
        chaise_dims.get("base_length", 1500) / 2.0
    )
    solids = [s for s in straight_builder.components.values() if s is not None]
    for solid in chaise_builder.components.values():
        if solid is None:
            continue
        solids.append(solid.translate((offset_x, 0, 0)))
    if not solids:
        return None
    return Compound(solids, label="l-shape sofa")


def build_sofa_step_model(
    sofa_type: str,
    output_path: Optional[Path] = None,
    dimensions: Optional[Dict] = None,
) -> Optional[str]:
    """
    Build a complete sofa model and export to STEP format.

    Args:
        sofa_type: '1-seater', '2-seater', '3-seater', '4-seater', or 'l-shape'
        output_path: Path to save STEP file
        dimensions: User L/W/H or template keys

    Returns:
        Path to saved STEP file, or None if build123d unavailable
    """
    if not HAS_BUILD123D:
        print("ERROR: build123d not available. Cannot build production CAD.")
        return None

    sofa_type = normalize_sofa_type(sofa_type)
    if sofa_type == "l-shape":
        assembly = _build_l_shape_assembly(dimensions)
    else:
        dims = SofaDimensions(sofa_type, dimensions)
        builder = SofaAssemblyBuilder(sofa_type, dims)
        assembly = builder.assemble()

    if assembly is None:
        return None
    if output_path is None:
        return None
    try:
        return _write_step(assembly, Path(output_path))
    except Exception as e:
        print(f"ERROR: Failed to export STEP: {e}")
        return None


def build_sofa_l_shape_modular(
    straight_config: Dict,
    chaise_config: Dict,
    output_path: Optional[Path] = None,
) -> Optional[str]:
    """Build an L-shape sofa as two modules joined and exported as one STEP file."""
    if not HAS_BUILD123D:
        return None

    merged: Dict[str, Any] = {}
    merged.update(straight_config.get("dimensions") or {})
    merged.update(chaise_config or {})
    merged.update(chaise_config.get("dimensions") or {})
    if "chaise_length" in (chaise_config or {}):
        merged["chaise_length"] = chaise_config["chaise_length"]
    if "chaise_depth" in (chaise_config or {}):
        merged["chaise_depth"] = chaise_config["chaise_depth"]

    assembly = _build_l_shape_assembly(merged)
    if assembly is None or output_path is None:
        return None
    try:
        return _write_step(assembly, Path(output_path))
    except Exception as e:
        print(f"ERROR: Failed to export L-shape STEP: {e}")
        return None


# ============================================================================
# TESTING / DEMO
# ============================================================================

if __name__ == "__main__":
    print("Production CAD Module (build123d backend)")
    print("=" * 60)
    
    if not HAS_BUILD123D:
        print("build123d not installed. Install with: pip install build123d")
        sys.exit(1)
    
    # Demo: Build a 3-seater STEP model
    output = Path("outputs/production_cad/demo_3seater.step")
    print(f"Building 3-seater model...")
    result = build_sofa_step_model('3-seater', output)
    if result:
        print(f"✅ STEP file saved to: {result}")
    else:
        print("❌ Failed to build STEP model")
    
    # Demo: Build L-shape modular
    output_lshape = Path("outputs/production_cad/demo_lshape.step")
    print(f"Building L-shape model...")
    result = build_sofa_l_shape_modular(
        {'sofa_type': '3-seater'},
        {'chaise_length': 1500, 'chaise_depth': 1200},
        output_lshape
    )
    if result:
        print(f"✅ L-shape STEP file saved to: {result}")
    else:
        print("❌ Failed to build L-shape model")
