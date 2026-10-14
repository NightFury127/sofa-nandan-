"""
bom_geometry.py — A sofa's material quantities, measured off the parts it is
built from (sofa_build.py), the way a factory estimator takes off a drawing:
timber volume of every frame member, plywood area, foam volume x density,
upholstered area / fabric roll width, spring and belt counts.

The construction follows the industry reference model "Sofa Internal
Structure.f3z" (sofa_build.py lists every part and where it was measured).
The layout rules below (seats per type, the L-shape chaise, legs) and the foam
densities are our own assumptions; sources and reasoning in
docs/08_COSTING.md.

Quantities are NET (what ends up in the sofa). Cutting wastage is added at
pricing time from the rate sheet (pricing.json), so it stays editable.
"""

import numpy as np

# All lengths in metres.
CONSTRUCTION = {
    "arm_width":          0.15,   # used only to count seats on long runs (4-seater, L-shape)
    "leg_height":         0.12,   # legs are not in the reference model
    "seat_module":        0.60,   # seat width a seat is counted by
    "fabric_usable_width": 1.32,  # 54" roll, ~1.32 m usable after selvedge
    "fabric_seam_allow":  0.20,   # seams, boxing and cutting-layout loss on the roll
    "adhesive_kg_per_m2": 0.15,   # spray/contact adhesive on glued foam faces
    "centre_legs_from":   2.0,    # straight runs this long get 2 centre legs
    "chaise_width":       0.75,   # L-shape chaise module incl. its arm
    "chaise_projection":  1.55,   # L-shape chaise length from the back
}

FOAM_DENSITY = {"seat": 40.0, "back": 32.0, "pad": 28.0}   # kg/m3
M3_TO_CFT = 35.3147
PAD_GLUE_DEPTH = 0.03          # padding foam is glued over roughly its volume / 30 mm


def sofa_runs(sofa_type: str, L: float, W: float, c: dict = CONSTRUCTION) -> list[dict]:
    """
    The straight sections a sofa is built from (metres), with their seat count.
    A straight sofa is one run with an arm at each end. An L-shape is a main run
    with its arm on the left and a chaise in front of its right-hand end, with
    the chaise arm on the right.
    """
    if sofa_type == "l-shape":
        runs = [dict(length=L, depth=W, arm_sides=("left",), seats=None, back=True),
                dict(length=c["chaise_width"], depth=max(0.3, c["chaise_projection"] - W),
                     arm_sides=("right",), seats=1, back=False)]
    else:
        seats = {"1-seater": 1, "2-seater": 2, "3-seater": 3}.get(sofa_type)
        if sofa_type == "4-seater":
            seats = max(4, round((L - 2 * c["arm_width"]) / c["seat_module"]))
        runs = [dict(length=L, depth=W, arm_sides=("left", "right"), seats=seats, back=True)]
    for r in runs:
        seat_w = max(0.3, r["length"] - len(r["arm_sides"]) * c["arm_width"])
        r["seats"] = r["seats"] or max(1, round(seat_w / c["seat_module"]))
    return runs


def leg_count(length: float, c: dict = CONSTRUCTION) -> int:
    """Corner legs, plus a centre pair on long runs."""
    return 4 + (2 if length >= c["centre_legs_from"] else 0)


def _upholstered_m2(part) -> float:
    """Outside area of a fabric cover, less the underside (not covered in fabric)."""
    mesh = part.mesh()
    up = mesh.face_normals[:, 2] > -0.7
    return float(mesh.area_faces[up].sum()) / 1e6


def takeoff(parts) -> dict:
    """Net quantities measured off the built parts (SI units)."""
    vol = lambda layer: sum(p.volume for p in parts if p.layer == layer) / 1e9
    seat_top = sum((p.hi[0] - p.lo[0]) * (p.hi[1] - p.lo[1]) for p in parts if p.name.endswith("seat_foam_upper"))
    back_face = sum(p.length * np.linalg.norm(p.profile[1] - p.profile[0])
                    for p in parts if p.name.endswith("back_cushion"))
    return {
        "timber_m3": vol("frame"),
        "ply_m2": vol("plywood") / 0.012,
        "seat_foam_m3": vol("seat_foam"),
        "back_foam_m3": vol("back_foam"),
        "pad_foam_m3": vol("padding"),
        "fabric_m2": sum(_upholstered_m2(p) for p in parts if p.layer == "fabric"),
        "wrap_m2": (seat_top + back_face) / 1e6,
        "springs": sum(1 for p in parts if p.kind == "wire"),
        "clips": sum(1 for p in parts if "clip" in p.name),
        "spring_wire_m": sum(p.length for p in parts if p.kind == "wire") / 1000.0,
        "belts_m": sum(p.meta.get("run_length", 0.0) for p in parts if p.layer == "webbing") / 1000.0,
        "frame_members": sum(1 for p in parts if p.layer == "frame"),
        "legs": sum(1 for p in parts if p.layer == "legs"),
    }


def geometry_bom(sofa_type: str, length_mm: float, width_mm: float, height_mm: float,
                 c: dict = CONSTRUCTION) -> list[dict]:
    """
    Net material quantities for one sofa. sofa_type is a canonical key from
    cost_engine.normalize_sofa_type ('1-seater' … '4-seater', 'l-shape').
    Returns [{component_group, unit, new_qty, notes}] in a fixed order.
    """
    from sofa_build import build_parts

    t = takeoff(build_parts(sofa_type, length_mm, width_mm, height_mm))
    seats = sum(r["seats"] for r in sofa_runs(sofa_type, length_mm / 1000.0, width_mm / 1000.0, c))
    fabric_m = t["fabric_m2"] * (1 + c["fabric_seam_allow"]) / c["fabric_usable_width"]
    glued_m2 = t["wrap_m2"] + t["pad_foam_m3"] / PAD_GLUE_DEPTH

    rows = [
        ("Wood Frame",     "cubic feet",    t["timber_m3"] * M3_TO_CFT,
         f"{t['frame_members']} members, reference sections (25x40, 25x65, 25x45, 51x48)"),
        ("Plywood",        "square meters", t["ply_m2"], "12 mm: side panels, arm end boards, back top cap"),
        ("Seat Foam",      "kg",            t["seat_foam_m3"] * FOAM_DENSITY["seat"],
         f"{t['seat_foam_m3']:.3f} m3 @ 40 kg/m3, tight seat 2 x 50 mm"),
        ("Back Foam",      "kg",            t["back_foam_m3"] * FOAM_DENSITY["back"],
         f"{t['back_foam_m3']:.3f} m3 @ 32 kg/m3, raked back"),
        ("Padding Foam",   "kg",            t["pad_foam_m3"] * FOAM_DENSITY["pad"],
         f"{t['pad_foam_m3']:.3f} m3 @ 28 kg/m3, front panel and arm tops"),
        ("Fabric",         "metres",        fabric_m,
         f"{t['fabric_m2']:.1f} m2 upholstered + {c['fabric_seam_allow']*100:.0f}% seams, 54\" roll"),
        ("Fibre Wrap",     "square meters", t["wrap_m2"], "polyester fibre over the seat and back foam"),
        ("Springs",        "pieces",        t["springs"], f"sinuous, 127 mm pitch, {t['clips']} clips"),
        ("Elastic Webbing", "metres",       t["belts_m"], "seat belts and back belts"),
        ("Adhesive",       "kg",            glued_m2 * c["adhesive_kg_per_m2"], f"{glued_m2:.1f} m2 glued foam"),
        ("Legs",           "pieces",        t["legs"], ""),
        ("Sundries",       "sets",          seats, "per seat: staples, thread, screws, dust cover"),
    ]
    return [{"component_group": name, "unit": unit, "new_qty": round(qty, 4), "notes": note}
            for name, unit, qty, note in rows]
