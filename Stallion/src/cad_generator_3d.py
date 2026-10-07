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


SEATS_BY_TYPE = {"1_seater": 1, "2_seater": 2, "3_seater": 3, "4_seater_plus": 4, "l_shape": 3}


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def build_sofa_mesh(scaled_bom: dict, dimensions: dict, sofa_type: str = "3_seater") -> trimesh.Scene:
    """
    Build a primitive-based 3D sofa from the same scaled BOM and dimensions
    used in the cost engine. The overall footprint is exactly length x width
    x height (mm; z up, front of the sofa towards -y). Parts appear only when
    the BOM contains them; seat/back cushions are split per seat, and an
    L-shape gets a chaise extending forward on the right.
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
    arm_qty       = _lookup_qty(scaled_bom, "handle frame", "handle_frame",
                                "armrest", "arm rest")

    def add_span(name, x0, x1, y0, y1, z0, z1):
        """Add an axis-aligned box spanning [x0,x1] x [y0,y1] x [z0,z1]."""
        mesh = trimesh.creation.box(extents=[x1 - x0, y1 - y0, z1 - z0])
        mesh.apply_translation([(x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0])
        scene.add_geometry(mesh, geom_name=name)
        return mesh

    L, W, H = length, width, height
    has_arms = wood_qty > 0 or arm_qty > 0
    n_seats  = SEATS_BY_TYPE.get(str(sofa_type).lower().replace("-", "_"), 3)

    leg_h    = _clamp(H * 0.11, 60.0, 140.0)
    base_h   = _clamp(H * 0.20, 110.0, 220.0)            # frame/base above the legs
    cush_h   = _clamp(H * 0.13, 80.0, 160.0)             # seat cushion thickness
    arm_w    = _clamp(L * 0.09, 90.0, 220.0) if has_arms else 0.0
    back_d   = _clamp(W * 0.20, 110.0, 260.0)            # back frame depth
    bcush_d  = _clamp(W * 0.15, 90.0, 190.0)             # back cushion depth
    gap      = 12.0                                      # between cushions
    seat_z0  = leg_h + base_h
    seat_top = seat_z0 + cush_h
    arm_top  = _clamp(H * 0.72, seat_top + 120.0, H - 40.0)
    x_in0, x_in1 = -L / 2.0 + arm_w, L / 2.0 - arm_w      # between the arms
    front, back = -W / 2.0, W / 2.0

    # Structure
    add_span("seat_base", x_in0, x_in1, front, back, leg_h, seat_z0)
    add_span("backrest", -L / 2.0, L / 2.0, back - back_d, back, leg_h, H)
    if has_arms:
        add_span("left_armrest", -L / 2.0, x_in0, front, back, leg_h, arm_top)
        add_span("right_armrest", x_in1, L / 2.0, front, back, leg_h, arm_top)
    if plywood_qty > 0:   # seat deck, inside the base
        add_span("plywood_core", x_in0 + 30, x_in1 - 30, front + 30, back - back_d - 10,
                 seat_z0 - 45, seat_z0 - 15)

    # Cushions, one per seat
    seat_w = (x_in1 - x_in0 - gap * (n_seats - 1)) / n_seats
    for i in range(n_seats):
        x0 = x_in0 + i * (seat_w + gap)
        suffix = "" if n_seats == 1 else f"_{i + 1}"
        if seat_foam_qty > 0:
            add_span(f"seat_foam{suffix}", x0, x0 + seat_w, front + 15, back - back_d - bcush_d * 0.35,
                     seat_z0, seat_top)
        if back_foam_qty > 0:
            add_span(f"back_foam{suffix}", x0, x0 + seat_w, back - back_d - bcush_d, back - back_d,
                     seat_top, H - 50)

    # L-shape: a chaise extending forward on the right-hand side
    chaise = None
    if str(sofa_type).lower().replace("-", "_") == "l_shape":
        chaise_w = _clamp(L * 0.36, 650.0, 1000.0)
        reach = _clamp(W * 0.80, 600.0, 900.0)
        cx0, cx1 = x_in1 - chaise_w, x_in1
        add_span("chaise_base", cx0, cx1, front - reach, front, leg_h, seat_z0)
        if seat_foam_qty > 0:
            add_span("chaise_foam", cx0, cx1, front - reach + 15, front - gap, seat_z0, seat_top)
        if has_arms:
            add_span("chaise_armrest", x_in1, L / 2.0, front - reach, front, leg_h, arm_top)
        chaise = (cx0, cx1, front - reach)

    # Legs at the corners of the footprint, extras spread along front and back
    leg_w = _clamp(min(L, W) * 0.045, 35.0, 60.0)
    inset = 40.0 + leg_w / 2.0
    positions = [(-L / 2 + inset, front + inset), (L / 2 - inset, front + inset),
                 (-L / 2 + inset, back - inset), (L / 2 - inset, back - inset)]
    for k in range(max(4, leg_qty) - 4):
        x = -L / 2 + L * (k // 2 + 1) / (max(4, leg_qty) // 2)
        positions.append((min(x, L / 2 - inset), front + inset if k % 2 == 0 else back - inset))
    if chaise:
        cx0, cx1, cfront = chaise
        positions += [(cx0 + inset, cfront + inset), (L / 2 - inset, cfront + inset)]
    for idx, (x, y) in enumerate(positions):
        add_span(f"leg_{idx + 1}", x - leg_w / 2, x + leg_w / 2, y - leg_w / 2, y + leg_w / 2, 0.0, leg_h)

    return scene


# Colours for the exported model (RGBA). Upholstered parts share the fabric
# colour; the base/arms/back frame are a shade darker so cushions read clearly.
_FABRIC  = [176, 168, 152, 255]
_FRAME   = [146, 139, 126, 255]
_WOOD    = [74, 52, 36, 255]
_DECK    = [196, 170, 128, 255]


def _part_colour(name: str):
    if name.startswith("leg"):
        return _WOOD
    if name.startswith("plywood"):
        return _DECK
    if "foam" in name:
        return _FABRIC
    return _FRAME


def _srgb_to_linear(rgba):
    """glTF baseColorFactor is linear; the palette above is sRGB (as displayed)."""
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return [lin(float(c)) for c in rgba[:3]] + [rgba[3] / 255.0]


def _part_material(name: str) -> trimesh.visual.material.PBRMaterial:
    """
    Explicit non-metallic material. A glTF mesh without a material (e.g. plain
    vertex colours) defaults to metallicFactor 1.0, which renders almost black
    in viewers without environment lighting — so every part gets one.
    """
    wood = name.startswith("leg")
    return trimesh.visual.material.PBRMaterial(
        name=name,
        baseColorFactor=_srgb_to_linear(_part_colour(name)),
        metallicFactor=0.0,
        roughnessFactor=0.6 if wood else 0.9,   # fabric is matte; wood a little glossier
    )


def _gltf_ready_copy(scene: trimesh.Scene) -> trimesh.Scene:
    """Coloured copy in glTF conventions: Y up, metres, front facing +Z."""
    out = scene.copy()
    for name, geom in out.geometry.items():
        geom.visual = trimesh.visual.TextureVisuals(material=_part_material(name))
    # z-up -> y-up: (x, y, z) -> (x, z, -y); mm -> m
    rot = trimesh.transformations.rotation_matrix(-math.pi / 2.0, [1, 0, 0])
    out.apply_transform(rot)
    out.apply_scale(0.001)
    return out


def export_3d_model(scene: trimesh.Scene, output_dir: str, request_id: str) -> dict:
    """
    Export the scene to GLB and OBJ next to the 2D CAD files, coloured and in
    glTF conventions (Y up, metres) so viewers and 3D apps show it upright and
    at the right size.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    glb_path = out_dir / f"{request_id}.glb"
    obj_path = out_dir / f"{request_id}.obj"

    export_scene = _gltf_ready_copy(scene)
    export_scene.export(file_obj=str(glb_path), file_type="glb")
    export_scene.export(file_obj=str(obj_path), file_type="obj")

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
