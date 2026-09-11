import math
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import trimesh

# ---------------------------------------------------------------------------
# Schema alias map — maps legacy BOM component names to schema component IDs
# and vice-versa so _lookup_qty works with both the CSV-based BOM and the
# schema-driven BOM produced by SofaCostEngine.generate_quote_from_schema().
# ---------------------------------------------------------------------------
_LEGACY_TO_SCHEMA: dict = {
    "wood frame":       "seat_rail_front",   # any frame component presence
    "wood_frame":       "seat_rail_front",
    "plywood":          "seat_deck_board",
    "seat foam":        "seat_foam",
    "seat_foam":        "seat_foam",
    "back foam":        "back_foam",
    "back_foam":        "back_foam",
    "handle foam":      "handle_foam",
    "handle_foam":      "handle_foam",
    "fabric":           "fabric_seat",
    "fabric_seat":      "fabric_seat",
    "springs":          "spring_unit",
    "spring_unit":      "spring_unit",
    "clips":            "spring_clip",
    "spring_clip":      "spring_clip",
    "seat belts":       "webbing_strap",
    "webbing_strap":    "webbing_strap",
    "back rest belts":  "back_foam",
    "legs":             "leg",
    "leg":              "leg",
    "handle frame":     "handle_frame",
    "handle_frame":     "handle_frame",
    "armrest":          "handle_frame",
    "arm rest":         "handle_frame",
}


def _coerce_qty(value):
    if isinstance(value, dict):
        for key in ("new_qty", "qty", "quantity"):
            if key in value and value[key] is not None:
                return float(value[key])
        return 0.0
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _lookup_qty(scaled_bom, *names):
    """Look up a component quantity from a scaled BOM dict.

    Accepts both legacy CSV-based BOM keys (e.g. ``"wood frame"``) and
    schema component IDs (e.g. ``"seat_rail_front"``).  When a direct key
    lookup fails, the alias map ``_LEGACY_TO_SCHEMA`` is consulted so that
    either format resolves to the correct value.
    """
    if not isinstance(scaled_bom, dict):
        return 0.0
    norm = {str(k).strip().lower(): v for k, v in scaled_bom.items()}

    def _try(key: str) -> float:
        key = key.strip().lower()
        # 1. Direct match
        if key in norm:
            return _coerce_qty(norm[key])
        # 2. Alias: legacy → schema
        schema_id = _LEGACY_TO_SCHEMA.get(key)
        if schema_id and schema_id in norm:
            return _coerce_qty(norm[schema_id])
        # 3. Reverse alias: schema id → legacy
        for legacy, sid in _LEGACY_TO_SCHEMA.items():
            if sid == key and legacy in norm:
                return _coerce_qty(norm[legacy])
        return 0.0

    for name in names:
        val = _try(str(name))
        if val != 0.0:
            return val
    return 0.0


def build_sofa_mesh(scaled_bom: dict, dimensions: dict) -> trimesh.Scene:
    """
    Build a primitive-based 3D sofa mesh from the same scaled BOM and
    dimensional inputs already used in the cost engine.
    """
    if not isinstance(dimensions, dict):
        raise ValueError("dimensions must be a dictionary with length_mm/width_mm/height_mm")

    length = float(dimensions.get("length_mm", dimensions.get("length", 2100)))
    width = float(dimensions.get("width_mm", dimensions.get("width", 900)))
    height = float(dimensions.get("height_mm", dimensions.get("height", 850)))

    if length <= 0 or width <= 0 or height <= 0:
        raise ValueError("Dimensions must all be positive values")

    scene = trimesh.Scene()

    # Use the scaled BOM quantities to control major structural pieces. These are
    # not rederived from a separate template; they are simply read from the already
    # scaled quote output.  Both legacy names and schema component IDs are accepted
    # via the alias-aware _lookup_qty().
    leg_qty       = max(4, int(round(_lookup_qty(scaled_bom, "legs", "leg") or 4)))
    seat_foam_qty = _lookup_qty(scaled_bom, "seat foam", "seat_foam")
    back_foam_qty = _lookup_qty(scaled_bom, "back foam", "back_foam")
    wood_qty      = _lookup_qty(scaled_bom, "wood frame", "wood_frame",
                                "seat_rail_front", "seat_rail_back")
    plywood_qty   = _lookup_qty(scaled_bom, "plywood", "seat_deck_board")
    fabric_qty    = _lookup_qty(scaled_bom, "fabric", "fabric_seat")
    arm_qty       = _lookup_qty(scaled_bom, "handle frame", "handle_frame",
                                "armrest", "arm rest")

    def add_box(name, extents, center):
        mesh = trimesh.creation.box(extents=extents)
        mesh.apply_translation(center)
        scene.add_geometry(mesh, geom_name=name)
        return mesh

    seat_w = max(length * 0.82, 600.0)
    seat_d = max(width * 0.78, 500.0)
    seat_h = max(height * 0.32, 140.0)

    back_w = max(length * 0.82, 600.0)
    back_d = max(width * 0.22, 120.0)
    back_h = max(height * 0.42, 180.0)

    arm_w = max(length * 0.08, 90.0)
    arm_d = max(width * 0.18, 100.0)
    arm_h = max(height * 0.70, 220.0)

    leg_h = max(height * 0.12, 80.0)
    leg_w = max(min(length, width) * 0.04, 35.0)
    leg_d = leg_w

    seat_center = np.array([0.0, 0.0, leg_h + (seat_h / 2.0)])
    add_box("seat_base", [seat_w, seat_d, seat_h], seat_center)

    back_center = np.array([0.0, (seat_d / 2.0) - (back_d / 2.0), leg_h + seat_h + (back_h / 2.0)])
    add_box("backrest", [back_w, back_d, back_h], back_center)

    if wood_qty > 0 or arm_qty > 0:
        arm_offset_y = seat_d / 2.0 + arm_d / 2.0 + 10.0
        arm_base_z = leg_h + seat_h + (arm_h / 2.0)
        add_box("left_armrest", [arm_w, arm_d, arm_h], np.array([-seat_w / 2.0 + arm_w / 2.0, -arm_offset_y, arm_base_z]))
        add_box("right_armrest", [arm_w, arm_d, arm_h], np.array([seat_w / 2.0 - arm_w / 2.0, -arm_offset_y, arm_base_z]))

    if seat_foam_qty > 0:
        foam_offset = 12.0
        add_box("seat_foam", [seat_w - 80.0, seat_d - 70.0, max(seat_h * 0.65, 90.0)], np.array([0.0, 0.0, seat_h * 0.66 + foam_offset]))

    if back_foam_qty > 0:
        add_box("back_foam", [back_w - 80.0, max(back_d * 0.8, 70.0), back_h * 0.8], np.array([0.0, (seat_d / 2.0) - (back_d / 2.0), seat_h + back_h * 0.42]))

    if plywood_qty > 0:
        add_box("plywood_core", [seat_w - 120.0, seat_d - 110.0, max(seat_h * 0.25, 60.0)], np.array([0.0, 0.0, seat_h * 0.38]))

    if fabric_qty > 0:
        add_box("fabric_cover", [seat_w + 12.0, seat_d + 12.0, seat_h + 10.0], np.array([0.0, 0.0, seat_h / 2.0]))

    # Explicitly create legs as standalone geometry at the seat underside corners.
    # This keeps the "legs" BOM component visible in the 3D scene instead of
    # depending on armrest geometry or floor contact to imply its presence.
    leg_positions = []
    corner_offsets = [
        (-seat_w / 2.0 + leg_w, -seat_d / 2.0 + leg_d),
        (seat_w / 2.0 - leg_w, -seat_d / 2.0 + leg_d),
        (-seat_w / 2.0 + leg_w, seat_d / 2.0 - leg_d),
        (seat_w / 2.0 - leg_w, seat_d / 2.0 - leg_d),
    ]
    for idx in range(max(4, leg_qty)):
        if idx < len(corner_offsets):
            x, y = corner_offsets[idx]
        else:
            # Add any extra leg positions in a simple evenly distributed pattern.
            x = ((idx % 2) * seat_w / 2.0) - (seat_w / 4.0)
            y = (((idx // 2) % 2) * seat_d / 2.0) - (seat_d / 4.0)
        leg_positions.append(np.array([x, y, leg_h / 2.0]))

    for idx, leg_pos in enumerate(leg_positions[:max(4, leg_qty)]):
        add_box(f"leg_{idx + 1}", [leg_w, leg_d, leg_h], leg_pos)

    return scene


def export_3d_model(scene: trimesh.Scene, output_dir: str, request_id: str) -> dict:
    """Export the scene to GLB and OBJ at the same output folder used by the 2D CAD files."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    glb_path = out_dir / f"{request_id}.glb"
    obj_path = out_dir / f"{request_id}.obj"

    scene.export(file_obj=str(glb_path), file_type="glb")
    scene.export(file_obj=str(obj_path), file_type="obj")

    return {
        "glb_path": str(glb_path),
        "obj_path": str(obj_path),
    }


def render_preview_image(scene: trimesh.Scene, output_dir: str, request_id: str) -> str:
    """Render a single isometric 3D preview PNG using matplotlib only."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if len(scene.geometry) == 0:
        raise ValueError("Scene contains no geometry to render")

    # trimesh >= 4.x: Scene.dump(concatenate=True) is deprecated; use to_geometry()
    if hasattr(scene, "to_geometry"):
        mesh = scene.to_geometry()
    else:  # pragma: no cover — old trimesh fallback
        mesh = scene.dump(concatenate=True)  # type: ignore[attr-defined]
    vertices = mesh.vertices
    faces = mesh.faces

    fig = plt.figure(figsize=(8, 7), dpi=150)
    ax = fig.add_subplot(111, projection="3d")

    if faces is None or len(faces) == 0:
        raise ValueError("Mesh has no faces to render")

    poly = Poly3DCollection(vertices[faces], edgecolor="k", facecolor="#77aaff", linewidths=0.2, alpha=0.9)
    ax.add_collection3d(poly)

    min_xyz = vertices.min(axis=0)
    max_xyz = vertices.max(axis=0)
    center = (min_xyz + max_xyz) / 2.0
    size = max(max_xyz - min_xyz)

    ax.set_xlim(center[0] - size / 2.0, center[0] + size / 2.0)
    ax.set_ylim(center[1] - size / 2.0, center[1] + size / 2.0)
    ax.set_zlim(center[2] - size / 2.0, center[2] + size / 2.0)

    ax.set_axis_off()
    ax.view_init(elev=22, azim=35)
    ax.grid(False)

    preview_path = out_dir / f"{request_id}_3d_preview.png"
    plt.tight_layout()
    plt.savefig(str(preview_path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    return str(preview_path)
