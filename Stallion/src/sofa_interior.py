"""
sofa_interior.py — 3D model of a sofa with its internal construction, built
from the parts list in sofa_build.py (which follows the industry reference
model "Sofa Internal Structure.f3z"): the timber frame and arm frames, 12 mm
plywood, sinuous springs and clips, seat and back belts, foam and fabric.

The quote's material quantities are measured off the same parts
(bom_geometry.geometry_bom), so the model shows what the quote charges for.
The web viewer opens the sofa up by hiding the fabric and foam layers, or by
showing the exploded model, where each layer is lifted clear of the one
inside it.

Coordinates (mm): x = length, y = depth (front = -y), z = height (0 = floor),
centred on the footprint — the convention cad_generator_3d.py exports from.
Every part is a named mesh "<layer>:<part>", so the exporter can give each
layer its own material.
"""

import trimesh

from sofa_build import build_parts

# Layers from the inside out; the exploded view lifts each one by this share of the height.
LAYERS = ("legs", "frame", "plywood", "springs", "webbing",
          "padding", "seat_foam", "back_foam", "fabric")
EXPLODE_LIFT = {"legs": 0.0, "frame": 0.0, "plywood": 0.0, "springs": 0.35, "webbing": 0.35,
                "padding": 0.9, "seat_foam": 0.9, "back_foam": 0.9, "fabric": 1.85}


def build_interior_scene(sofa_type: str, length_mm: float, width_mm: float, height_mm: float,
                         exploded: bool = False) -> trimesh.Scene:
    """
    The sofa with all internal parts. sofa_type is a canonical key from
    cost_engine.normalize_sofa_type ('1-seater' … '4-seater', 'l-shape').
    Assembled, the footprint is exactly length x width (x the chaise for an
    L-shape) and the height is height_mm.
    """
    parts = build_parts(sofa_type, length_mm, width_mm, height_mm)
    scene = trimesh.Scene()
    for part in parts:
        mesh = part.mesh()
        if exploded:
            mesh.apply_translation([0.0, 0.0, EXPLODE_LIFT[part.layer] * height_mm])
        scene.add_geometry(mesh, geom_name=f"{part.layer}:{part.name}")
    lo, hi = scene.bounds                 # exploding only lifts parts, so x/y bounds are the footprint
    scene.apply_translation([-(lo[0] + hi[0]) / 2.0, -(lo[1] + hi[1]) / 2.0, 0.0])
    return scene


def layer_of(geom_name: str) -> str:
    return geom_name.split(":", 1)[0]
