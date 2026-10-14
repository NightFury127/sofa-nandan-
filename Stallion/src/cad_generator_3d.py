import math
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import trimesh

from cost_engine import normalize_sofa_type
from sofa_interior import build_interior_scene, layer_of

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


def build_sofa_mesh(scaled_bom: dict, dimensions: dict, sofa_type: str = "3_seater",
                    exploded: bool = False) -> trimesh.Scene:
    """
    Build the 3D sofa with its internal construction (sofa_interior.py, from the
    parts in sofa_build.py that follow the reference "Sofa Internal
    Structure.f3z"): frame, plywood, springs, belts, foam and fabric — the same
    parts the quote's quantities are measured from. The footprint is
    exactly length x width (plus the chaise on an L-shape) and the height is
    height (mm; z up, front of the sofa towards -y). exploded=True lifts each
    layer clear of the one inside it.

    scaled_bom is no longer needed (the quantities come from the same parts);
    it is accepted so existing callers keep working.
    """
    if not isinstance(dimensions, dict):
        raise ValueError("dimensions must be a dictionary with length_mm/width_mm/height_mm")

    length = float(dimensions.get("length_mm", dimensions.get("length", 2100)))
    width = float(dimensions.get("width_mm", dimensions.get("width", 900)))
    height = float(dimensions.get("height_mm", dimensions.get("height", 850)))

    if length <= 0 or width <= 0 or height <= 0:
        raise ValueError("Dimensions must all be positive values")

    return build_interior_scene(normalize_sofa_type(sofa_type), length, width, height, exploded=exploded)


# Colours for the exported model (sRGB, RGBA) per layer. Each layer gets its own
# material named after it, which the web viewer uses to hide fabric and foam.
LAYER_COLOURS = {
    "fabric":    [176, 168, 152, 255],   # upholstery
    "seat_foam": [222, 170, 96, 255],    # 40D seat foam
    "back_foam": [236, 208, 128, 255],   # 32D back foam
    "padding":   [242, 230, 196, 255],   # 28D padding
    "webbing":   [92, 96, 104, 255],     # seat and back belts
    "springs":   [150, 156, 164, 255],   # sinuous spring steel and clips
    "plywood":   [214, 182, 134, 255],   # 12 mm ply
    "frame":     [176, 122, 72, 255],    # timber frame and arm frames
    "legs":      [74, 52, 36, 255],      # dark wood
}


def _part_colour(name: str):
    return LAYER_COLOURS.get(layer_of(name), LAYER_COLOURS["fabric"])


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
    layer = layer_of(name)
    return trimesh.visual.material.PBRMaterial(
        name=layer,
        baseColorFactor=_srgb_to_linear(_part_colour(name)),
        metallicFactor=0.0,
        # fabric and foam are matte; wood and steel a little glossier
        roughnessFactor=0.55 if layer in ("legs", "frame", "plywood", "springs") else 0.9,
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


def glb_bytes(scene: trimesh.Scene) -> bytes:
    """The scene as an in-memory GLB (same conventions as export_3d_model)."""
    return _gltf_ready_copy(scene).export(file_type="glb")


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

    # The still image shows the finished sofa; the interior is for the 3D viewer.
    outside = trimesh.Scene()
    for node in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node]
        if layer_of(geom_name) in ("fabric", "legs"):
            outside.add_geometry(scene.geometry[geom_name], geom_name=geom_name, transform=transform)
    if len(outside.geometry):
        scene = outside

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
