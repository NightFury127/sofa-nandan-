# Granular Component Schema — Task Completion Report

**Date**: 2026-09-01  
**Status**: ✅ COMPLETE - Schema created, validated, and ready for cost engine integration  
**Validation**: All 14 structural tests passing

---

## Executive Summary

This task implemented a **granular component schema** that breaks down the monolithic sofa BOM model (10 components) into **26 discrete manufacturing parts** organized by category (frame, webbing/spring, foam, upholstery, hardware, misc).

The schema serves as a **single source of truth** shared by both the cost engine and CAD generator, preventing silent drift between BOM costing and 3D geometry.

---

## Deliverables

### 1. **Component Schema** (`src/component_schema.py`)

A comprehensive Python module defining 26 granular components with:

- **component_id**: Unique identifier (e.g., `seat_rail_front`)
- **category**: One of 6 manufacturing categories
- **dimension_type**: `linear`, `count`, `area`, or `fixed`
- **formula**: Explicit parametric rule (references base dimensions)
- **unit_of_measurement**: meters, kg, pieces, square_meters, etc.
- **base_qty_by_sofa_type**: Quantities for all 5 sofa types (1-seater through L-shape)
- **scaling_rule**: Cost scaling rule (matches existing cost_engine conventions)
- **cost_per_unit**: Material cost per unit

#### Component List by Category (26 total)

**Frame (12 components)**:
- Seat frame: front rail, back rail, left rail, right rail, cross-members, deck board
- Back frame: top rail, bottom rail, cross-members
- Arm frame: front post, back post, top rail

**Webbing/Springs (3 components)**:
- Webbing straps (horizontal support)
- Spring units (coil/sinuous wire)
- Spring clips (fasteners)

**Foam (3 components)**:
- Seat foam
- Back foam
- Arm foam (both arms)

**Upholstery (3 components)**:
- Fabric for seat
- Fabric for back
- Fabric for arms

**Hardware (3 components)**:
- Legs (fixed count per sofa type)
- Corner blocks (reinforcement)
- Hardware fasteners (bolts/screws)

**Miscellaneous (2 components)**:
- Adhesive (glue/binder)
- Thread (sewing)

### 2. **Validation Framework** (`src/component_schema_validator.py`)

A comprehensive validator that generates:

- **Schema structure validation**: Checks all required fields, categories, dimensions, sofa types
- **BOM generation**: Creates detailed BOMs for all 5 sofa sizes
- **Cost breakdown by category**: Material costs aggregated by manufacturing category
- **Count-formula validation**: Verifies discrete scaling of count-based components
- **Full JSON output**: Structured BOM data ready for downstream processing

#### Validation Results

**Schema Validation**: ✅ PASS
- No structural errors
- No warnings
- All 26 components valid
- All sofa types defined

**BOM Cost Summary** (Materials Only):

| Sofa Type | Total Cost | Frame | Foam | Upholstery | Hardware | Misc |
|-----------|-----------|-------|------|-----------|----------|------|
| 1-seater  | INR 14,480 | INR 10,059 | INR 1,490 | INR 2,025 | INR 510 | INR 116 |
| 2-seater  | INR 19,586 | INR 12,517 | INR 2,880 | INR 3,015 | INR 522 | INR 174 |
| 3-seater  | INR 25,008 | INR 15,315 | INR 4,270 | INR 4,005 | INR 534 | INR 232 |
| 4-seater  | INR 30,500 | INR 17,943 | INR 5,660 | INR 4,995 | INR 786 | INR 290 |
| L-shape   | INR 35,961 | INR 21,653 | INR 6,360 | INR 5,850 | INR 798 | INR 334 |

**Count-Formula Validation** (verifies discrete scaling):

Spring/Webbing counts scale realistically:
```
webbing_strap:   1-seater=4,  2-seater=6,  3-seater=6,  4-seater=6,  l-shape=8
spring_unit:     1-seater=8,  2-seater=14, 3-seater=20, 4-seater=26, l-shape=30
spring_clip:     1-seater=16, 2-seater=28, 3-seater=40, 4-seater=52, l-shape=60
```

All patterns show realistic manufacturing stepping (not fractional, not identical across all sizes).

### 3. **Test Suite** (`tests/test_component_schema.py`)

14 automated tests validating:

- ✅ All components have valid categories
- ✅ All sofa types defined for all components
- ✅ All quantities positive
- ✅ Dimension types are valid
- ✅ Scaling rules recognized by cost_engine
- ✅ Cost per unit non-negative
- ✅ BOM costs increase with sofa size
- ✅ Cost breakdown is reasonable
- ✅ All components contribute to BOMs
- ✅ No duplicate component IDs
- ✅ Categories well-distributed

**Test Results**: 14/14 PASSED ✅

### 4. **Validation Report** (`docs/component_schema_validation_report.txt`)

Full structured report including:
- Component inventory by category
- Validation results (structure, categories, orphan checks)
- Full BOM generation for all sizes
- Cost breakdown by category
- Count-formula validation
- Complete JSON dump of 3-seater BOM (reference data)

---

## Key Design Decisions

### 1. **26-Component Granularity**
The schema breaks down the original monolithic categories (e.g., "Wood Frame") into discrete manufacturing parts (e.g., `seat_rail_front`, `seat_cross_member`, etc.).

**Why**: Accurate BOM costing requires each real cost line item to be separately tracked. A single "Wood Frame" component doesn't differentiate between frame rails (expensive, structural) and cross-members (cheaper, supportive).

### 2. **Six Manufacturing Categories**
Components organized by function:
- **Frame**: Structural skeleton (12 parts)
- **Webbing/Spring**: Seat support system (3 parts)
- **Foam**: Cushioning material (3 parts)
- **Upholstery**: Covering & trim (3 parts)
- **Hardware**: Assembly & fastening (3 parts)
- **Misc**: Adhesives, thread, etc. (2 parts)

**Why**: Enables category-level cost analysis and helps identify cost drivers (e.g., frame = 61% of cost, upholstery = 16%).

### 3. **Explicit Scaling Rules**
Each component defines its scaling rule (`count by length`, `area`, `3d volume`, etc.), which maps to cost_engine conventions and ensures cost calculations remain consistent.

**Why**: Prevents ad-hoc scaling logic from creeping in. Every calculation is traceable to the schema.

### 4. **CAD Mapping (Optional)**
Each component includes a `cad_box_scale_mode` hint (e.g., `linear_length`, `area_based`, `fixed_height`) for CAD generator to create appropriate mesh extents without hardcoding.

**Why**: When CAD is updated to use the schema, this removes dimensionality guessing.

---

## Integration Roadmap

The schema is now ready for integration into existing modules:

### Phase 1: Cost Engine Integration (NEXT)
- Update `src/cost_engine.py` to consume `component_schema.py` instead of hardcoded component lists
- Adapt BOM loading to read schema base quantities
- Keep all scaling rules identical to current behavior
- **Validation**: Run existing cost quote pipeline, verify outputs unchanged

### Phase 2: CAD Generator Integration
- Update `src/cad_generator_3d.py` to read component quantities and box scales from schema
- Generate mesh geometry dynamically based on schema definitions
- Remove hardcoded component list and dimension assumptions
- **Validation**: Verify 3D preview and GLB/OBJ output unchanged

### Phase 3: Cross-Check Against Legacy BOM
- Generate BOMs for reference sofa sizes using both old (10-component) and new (26-component) models
- Compare total costs; flag large unexplained deltas
- Document any discrepancies and their root causes

---

## Files Created

1. **`src/component_schema.py`** (450 lines)
   - Core schema definition: `COMPONENT_SCHEMA` dict with 26 components
   - Utility functions: `get_schema()`, `get_component_by_id()`, `list_components_by_category()`

2. **`src/component_schema_validator.py`** (300 lines)
   - `ComponentSchemaValidator`: Structure & consistency checks
   - `GranularBOMGenerator`: BOM generation for all sofa sizes
   - `generate_full_validation_report()`: Comprehensive report factory

3. **`tests/test_component_schema.py`** (200 lines)
   - 14 pytest test classes covering structure, cost calculations, consistency, distribution
   - All tests passing

4. **`docs/component_schema_validation_report.txt`** (Generated)
   - Full validation output with BOM data, costs per category, JSON dump

---

## Validation Evidence

### Schema Structure: ✅ VALID
```
26 components across 6 categories:
  - frame: 12 components
  - webbing_spring: 3 components
  - foam: 3 components
  - upholstery: 3 components
  - hardware: 3 components
  - misc: 2 components
```

### Cost Calculations: ✅ REASONABLE
```
Costs increase monotonically with sofa size:
  1-seater:  INR 14,480  (baseline)
  2-seater:  INR 19,586  (+35%)
  3-seater:  INR 25,008  (+73%)
  4-seater:  INR 30,500  (+111%)
  l-shape:   INR 35,961  (+149%)
```

### Count Formulas: ✅ REALISTIC
```
Spring units scale with width (discrete increments):
  1-seater → 8, 2-seater → 14, 3-seater → 20, 4-seater → 26, L-shape → 30
  
Pattern: Increases by ~6-8 per size, not fractional or identical.
```

### Test Results: ✅ 14/14 PASS
```
All structural validation tests pass:
  - Categories valid ✓
  - Quantities positive ✓
  - Scaling rules recognized ✓
  - Cost calculations reasonable ✓
  - No duplicates ✓
  - All categories populated ✓
```

---

## Known Limitations & Future Work

### Out of Scope (as specified)
- Curved/rolled arm and back surfaces (visual fidelity only; not needed for costing)
- Manufacturing tolerances and joinery detail
- DXF/STEP output refinement
- Database persistence / versioning of schema

### Optional Enhancements
- Add component photos/diagrams to schema for training materials
- Create cost sensitivity analysis (e.g., what if foam prices +10%?)
- Build web UI for editing component quantities and costs
- Link to supplier catalog entries (SKU cross-reference)

---

## How to Use the Schema

### 1. Read the Schema
```python
from component_schema import COMPONENT_SCHEMA, get_component_by_id

# Get a single component
rail = get_component_by_id("seat_rail_front")
print(rail["base_qty_by_sofa_type"]["3-seater"])  # → 2.1 meters

# Get all frame components
from component_schema import list_components_by_category
frame_parts = list_components_by_category("frame")
```

### 2. Generate BOM
```python
from component_schema_validator import GranularBOMGenerator

gen = GranularBOMGenerator(COMPONENT_SCHEMA)
bom = gen.generate_bom_for_sofa_type("3-seater")

print(bom["grand_total_cost"])  # → INR 25,008
print(bom["totals_by_category"])  # → costs per category
```

### 3. Validate Schema
```python
from component_schema_validator import ComponentSchemaValidator

validator = ComponentSchemaValidator()
errors, warnings = validator.run_all_validations()
print(validator.get_schema_report())
```

---

## Next Steps

1. ✅ Schema created and validated (DONE)
2. ⏭️ **Integrate into cost_engine.py** (NEXT)
   - Replace hardcoded component lists with schema imports
   - Adapt BOM loading logic
   - Run existing test suite to ensure no regression
3. ⏭️ **Integrate into cad_generator_3d.py**
   - Read component quantities and dimensions from schema
   - Generate mesh geometry dynamically
4. ⏭️ **Cross-check against legacy BOM**
   - Compare old (10-component) vs new (26-component) costs
   - Document cost deltas and their sources

---

## Contact & Questions

This schema is designed to be maintainable and extensible. When cost structures change (e.g., new materials, new components), update `component_schema.py` and re-run validation tests.

The schema is the **single source of truth**—keep it updated, and both cost and CAD will remain in sync.
