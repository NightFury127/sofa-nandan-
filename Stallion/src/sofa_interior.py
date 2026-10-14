"""
sofa_interior.py — 3D model of a sofa with its internal construction: the sal
frame, plywood panels, zig-zag springs, back webbing, foam and fabric.

Every part is laid out from the construction spec the quote is priced from
(bom_geometry.CONSTRUCTION) and uses the same runs, seat, spring, webbing and
leg counts (bom_geometry.sofa_runs etc.), so the model shows what the quote
charges for. The web viewer opens the sofa up by hiding the fabric and foam
layers, or by showing the exploded model, where each layer is lifted clear of
the one inside it.

Coordinates (mm): x = length, y = depth (front = -y), z = height (0 = floor),
centred on the footprint — the convention cad_generator_3d.py exports from.
Every part is a named mesh "<layer>:<part>", so the exporter can give each
layer its own material.
"""

import numpy as np
import trimesh

from bom_geometry import (CONSTRUCTION, sofa_runs, run_dims, spring_count,
                          webbing_rows, leg_count)

FABRIC_T = 3.0      # upholstery fabric, mm
PLY_T = 12.0        # plywood panels
LEG_W = 50.0        # square leg section
DECK_GAP = 8.0      # springs sit in this gap between the frame and the cushions

# Layers from the inside out; the exploded view lifts each one by this share of the height.
LAYERS = ("legs", "frame", "plywood", "springs", "webbing",
          "padding", "seat_foam", "back_foam", "fabric")
EXPLODE_LIFT = {"legs": 0.0, "frame": 0.0, "plywood": 0.0, "springs": 0.35, "webbing": 0.35,
                "padding": 0.9, "seat_foam": 0.9, "back_foam": 0.9, "fabric": 1.85}


def _box(x0, x1, y0, y1, z0, z1) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=[x1 - x0, y1 - y0, z1 - z0])
    mesh.apply_translation([(x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0])
    return mesh


def _zigzag_spring(x, y0, y1, z, amplitude, bend=60.0, wire_r=2.5) -> trimesh.Trimesh:
    """A sinuous (zig-zag) spring running front to back, as one mesh of wire segments."""
    bends = max(2, int((y1 - y0) // bend))
    ys = np.linspace(y0, y1, bends + 1)
    pts = [(x + (amplitude if i % 2 else -amplitude), y, z) for i, y in enumerate(ys)]
    wires = [trimesh.creation.cylinder(radius=wire_r, segment=[a, b], sections=6)
             for a, b in zip(pts[:-1], pts[1:])]
    return trimesh.util.concatenate(wires)


def _build_run(add, run, H, ox, oy, c, drop_back_legs=False):
    """Add the parts of one straight run whose footprint starts at (ox, oy), front at oy."""
    mm = 1000.0
    d = run_dims(run, H / mm, c)
    L, D, n, back = run["length"] * mm, run["depth"] * mm, run["seats"], run["back"]
    aw, leg_h = c["arm_width"] * mm, c["leg_height"] * mm
    arm_h, base_top = d["arm_h"] * mm, d["base_top"] * mm
    seat_w, seat_d = d["seat_w"] * mm, d["seat_d"] * mm
    bfd, bft = c["back_frame_depth"] * mm, c["back_foam_thick"] * mm
    seat_t, pad = c["seat_foam_thick"] * mm, c["pad_thick"] * mm
    sec_h, sec_w = c["member_section"][0] * mm, c["member_section"][1] * mm   # 75 tall x 50 wide
    deck = base_top + DECK_GAP
    left, right = "left" in run["arm_sides"], "right" in run["arm_sides"]
    sx0, sx1 = ox + (aw if left else 0.0), ox + L - (aw if right else 0.0)
    ix0, ix1 = sx0 + FABRIC_T, sx1 - FABRIC_T          # inner parts stay clear of the fabric
    y_front, y_back = oy, oy + D
    tag = run.get("tag", "")

    def part(layer, name, mesh):
        add(layer, f"{tag}{name}", mesh)

    # ── Legs: corners, plus a centre pair on long runs ───────────────────────
    inset = 30.0
    xs = [ox + inset, ox + L - inset - LEG_W]
    if leg_count(run["length"], c) > 4:
        xs.append(ox + L / 2.0 - LEG_W / 2.0)
    rows = [y_front + inset] + ([] if drop_back_legs else [y_back - inset - LEG_W])
    k = 0
    for y in rows:
        for x in xs:
            k += 1
            part("legs", f"leg_{k}", _box(x, x + LEG_W, y, y + LEG_W, 0.0, leg_h))

    # ── Frame: base box, bottom cross rails, back frame, arm frames ──────────
    rail_z = (base_top - sec_h, base_top)
    back_rail_y = (y_back - bfd + 10.0, y_back - bfd + 10.0 + sec_w) if back else (y_back - 15.0 - sec_w, y_back - 15.0)
    part("frame", "base_front_rail", _box(ix0, ix1, y_front + 15.0, y_front + 15.0 + sec_w, *rail_z))
    part("frame", "base_back_rail", _box(ix0, ix1, *back_rail_y, *rail_z))
    part("frame", "base_side_rail_l", _box(ix0, ix0 + sec_w, y_front + 15.0, y_back - 15.0, *rail_z))
    part("frame", "base_side_rail_r", _box(ix1 - sec_w, ix1, y_front + 15.0, y_back - 15.0, *rail_z))
    for i, x in enumerate(np.linspace(ix0 + sec_w / 2, ix1 - sec_w / 2, n + 1)):
        part("frame", f"cross_rail_{i + 1}",
             _box(x - sec_w / 2, x + sec_w / 2, y_front + 15.0, y_front + 15.0 + seat_d, leg_h, leg_h + sec_h))
    if back:
        by = (y_back - bfd + 10.0, y_back - bfd + 10.0 + sec_w)
        top = H - pad - FABRIC_T
        part("frame", "back_bottom_rail", _box(ix0, ix1, *by, base_top, base_top + sec_h))
        part("frame", "back_top_rail", _box(ix0, ix1, *by, top - sec_h, top))
        for i, x in enumerate(np.linspace(ix0 + sec_w / 2, ix1 - sec_w / 2, n + 1)):
            part("frame", f"back_stile_{i + 1}", _box(x - sec_w / 2, x + sec_w / 2, *by, base_top, top))
    for side in run["arm_sides"]:
        ax0 = ox if side == "left" else ox + L - aw                 # arm's outer-left x
        core = (ax0 + aw / 2 - sec_w / 2, ax0 + aw / 2 + sec_w / 2)
        top = arm_h - pad - FABRIC_T
        for name, y in (("front", y_front + 15.0), ("back", y_back - 15.0 - sec_h)):
            part("frame", f"arm_{side}_{name}_post", _box(*core, y, y + sec_h, leg_h, top))
        part("frame", f"arm_{side}_top_rail", _box(*core, y_front + 15.0, y_back - 15.0, top - sec_h, top))
        part("frame", f"arm_{side}_bottom_rail", _box(*core, y_front + 15.0, y_back - 15.0, leg_h, leg_h + sec_h))

        # ── Plywood on both faces of the arm; padding over it ────────────────
        skin = FABRIC_T + pad
        for face, (x0, x1) in (("outer", (ax0 + skin, ax0 + skin + PLY_T) if side == "left" else (ax0 + aw - skin - PLY_T, ax0 + aw - skin)),
                               ("inner", (ax0 + aw - skin - PLY_T, ax0 + aw - skin) if side == "left" else (ax0 + skin, ax0 + skin + PLY_T))):
            part("plywood", f"arm_{side}_{face}_ply", _box(x0, x1, y_front + skin, y_back - skin, base_top, arm_h - skin))
        part("padding", f"arm_{side}_outer_pad", _box(ax0 + FABRIC_T, ax0 + skin, y_front + FABRIC_T, y_back - FABRIC_T, base_top, arm_h - FABRIC_T))
        part("padding", f"arm_{side}_inner_pad", _box(ax0 + aw - skin, ax0 + aw - FABRIC_T, y_front + FABRIC_T, y_back - FABRIC_T, base_top, arm_h - FABRIC_T))
        part("padding", f"arm_{side}_top_pad", _box(ax0 + skin, ax0 + aw - skin, y_front + FABRIC_T, y_back - FABRIC_T, arm_h - skin, arm_h - FABRIC_T))
        part("padding", f"arm_{side}_front_pad", _box(ax0 + skin, ax0 + aw - skin, y_front + FABRIC_T, y_front + skin, leg_h, arm_h - skin))
        part("fabric", f"arm_{side}_cover", _box(ax0, ax0 + aw, y_front, y_back, leg_h, arm_h))

    # ── Plywood: front base board, back panel ────────────────────────────────
    part("plywood", "base_front_board", _box(ix0, ix1, y_front + FABRIC_T, y_front + FABRIC_T + PLY_T, leg_h, base_top))
    if back:
        part("plywood", "back_panel", _box(ix0, ix1, y_back - FABRIC_T - pad - PLY_T, y_back - FABRIC_T - pad, base_top, H - pad - FABRIC_T))

    # ── Zig-zag springs across the seat, running front to back ───────────────
    count = spring_count(d["seat_w"], c)
    pitch = seat_w / count
    for i in range(count):
        x = sx0 + (i + 0.5) * pitch
        part("springs", f"spring_{i + 1}",
             _zigzag_spring(x, y_front + 20.0, y_front + seat_d - 10.0, base_top + DECK_GAP / 2,
                            amplitude=min(25.0, pitch * 0.3)))

    # ── Back: webbing rows, padding, cushions ────────────────────────────────
    if back:
        rows_n = webbing_rows(d["back_cushion_h"], c)
        z0, z1 = c["seat_height"] * mm, H - 30.0
        web_y = y_back - bfd + 10.0 - 2.0
        for i, z in enumerate(np.linspace(z0, z1, rows_n + 2)[1:-1]):
            part("webbing", f"back_webbing_{i + 1}", _box(ix0, ix1, web_y, web_y + 2.0, z - 25.0, z + 25.0))
        part("padding", "back_outer_pad", _box(ix0, ix1, y_back - FABRIC_T - pad, y_back - FABRIC_T, leg_h, H - pad - FABRIC_T))
        part("padding", "back_top_pad", _box(ix0, ix1, y_back - bfd + FABRIC_T, y_back - FABRIC_T, H - pad - FABRIC_T, H - FABRIC_T))
        part("fabric", "back_cover", _box(sx0, sx1, y_back - bfd, y_back, leg_h, H))

    # ── Cushions: foam inside a fabric cover, one per seat ───────────────────
    cw = seat_w / n
    for i in range(n):
        x0, x1 = sx0 + i * cw, sx0 + (i + 1) * cw
        s = "" if n == 1 else f"_{i + 1}"
        t = FABRIC_T
        part("seat_foam", f"seat_cushion{s}", _box(x0 + t, x1 - t, y_front + t, y_front + seat_d - t, deck + t, deck + seat_t - t))
        part("fabric", f"seat_cushion_cover{s}", _box(x0, x1, y_front, y_front + seat_d, deck, deck + seat_t))
        if back:
            by0, by1 = y_back - bfd - bft, y_back - bfd
            bz0, bz1 = c["seat_height"] * mm, c["seat_height"] * mm + d["back_cushion_h"] * mm
            part("back_foam", f"back_cushion{s}", _box(x0 + t, x1 - t, by0 + t, by1 - t, bz0 + t, bz1 - t))
            part("fabric", f"back_cushion_cover{s}", _box(x0, x1, by0, by1, bz0, bz1))

    # ── Base cover: front panel and the deck under the cushions ──────────────
    part("fabric", "base_cover", _box(sx0, sx1, y_front, y_back - (bfd if back else 0.0), leg_h, deck))


def build_interior_scene(sofa_type: str, length_mm: float, width_mm: float, height_mm: float,
                         exploded: bool = False, c: dict = CONSTRUCTION) -> trimesh.Scene:
    """
    The sofa with all internal parts. sofa_type is a canonical key from
    cost_engine.normalize_sofa_type ('1-seater' … '4-seater', 'l-shape').
    Assembled, the footprint is exactly length x width (x the chaise for an
    L-shape) and the height is height_mm.
    """
    runs = sofa_runs(sofa_type, length_mm / 1000.0, width_mm / 1000.0, c)
    H = float(height_mm)
    scene = trimesh.Scene()

    def add(layer, name, mesh):
        if exploded:
            mesh.apply_translation([0.0, 0.0, EXPLODE_LIFT[layer] * H])
        scene.add_geometry(mesh, geom_name=f"{layer}:{name}")

    main = runs[0]
    if len(runs) == 1:
        _build_run(add, main, H, 0.0, 0.0, c)
        total_d = main["depth"] * 1000.0
    else:
        # L-shape: chaise in front of the right-hand end of the main run
        chaise = dict(runs[1], tag="chaise_")
        chaise_d = chaise["depth"] * 1000.0
        _build_run(add, main, H, 0.0, chaise_d, c)
        _build_run(add, chaise, H, length_mm - chaise["length"] * 1000.0, 0.0, c, drop_back_legs=True)
        total_d = chaise_d + main["depth"] * 1000.0

    scene.apply_translation([-length_mm / 2.0, -total_d / 2.0, 0.0])
    return scene


def layer_of(geom_name: str) -> str:
    return geom_name.split(":", 1)[0]
