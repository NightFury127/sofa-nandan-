"""
bom_geometry.py — Work out a sofa's material quantities from its dimensions and
a fixed construction spec, the way a factory estimator does: frame members ×
section → timber volume, cushion volume × density → foam kg, upholstered panel
area ÷ roll width → fabric metres, and so on.

The construction below is an ASSUMED mid-range Bengaluru build (hardwood frame,
12 mm ply panels, zig-zag spring seat, elastic-webbing back, 40D seat / 32D back
foam, 54" fabric). It is not Stallion's confirmed spec — change CONSTRUCTION when
the factory's real build is known. Sources and reasoning: docs/08_COSTING.md.

Quantities are NET (what ends up in the sofa). Cutting wastage is added at
pricing time from the rate sheet (pricing.json), so it stays editable.
"""

import math
from dataclasses import dataclass

# All lengths in metres.
CONSTRUCTION = {
    "arm_width":          0.15,   # outer arm width
    "arm_height":         0.62,   # arm top from floor (capped at sofa height - 0.15)
    "leg_height":         0.12,
    "base_frame_height":  0.20,   # seat frame box, above the legs
    "back_frame_depth":   0.10,   # back frame incl. ply and padding
    "seat_foam_thick":    0.15,   # 40D seat cushion (6" — common mid-range spec)
    "back_foam_thick":    0.10,   # 32D back cushion
    "seat_height":        0.43,   # top of seat cushion from floor
    "pad_thick":          0.025,  # 28D padding on arms and outer back
    "member_section":     (0.075, 0.05),   # frame timber 3" x 2" (dressed)
    "seat_module":        0.60,   # cushion width a seat is counted by
    "spring_pitch":       0.125,  # zig-zag springs across the seat
    "webbing_pitch":      0.10,   # elastic webbing rows up the back
    "fabric_usable_width": 1.32,  # 54" roll, ~1.32 m usable after selvedge
    "fabric_seam_allow":  0.20,   # seams, boxing and cutting-layout loss on the roll
    "adhesive_kg_per_m2": 0.15,   # spray/contact adhesive on glued foam faces
    "centre_legs_from":   2.0,    # straight runs this long get 2 centre legs
    "chaise_width":       0.75,   # L-shape chaise module incl. its arm
    "chaise_projection":  1.55,   # L-shape chaise length from the back
}

FOAM_DENSITY = {"seat": 40.0, "back": 32.0, "pad": 28.0}   # kg/m3
M3_TO_CFT = 35.3147


@dataclass
class _Totals:
    timber_m: float = 0.0       # running metres of frame member
    ply_m2: float = 0.0
    seat_foam_m3: float = 0.0
    back_foam_m3: float = 0.0
    pad_foam_m3: float = 0.0
    fabric_m2: float = 0.0
    wrap_m2: float = 0.0        # polyester fibre over cushions
    springs: int = 0
    webbing_m: float = 0.0
    legs: int = 0
    seats: int = 0


def _cushion_fabric(width, depth, thick, count):
    """Two faces plus boxing strips for `count` cushions sharing `width`."""
    cw = width / count
    faces = 2 * width * depth
    boxing = count * 2 * (cw + depth) * thick
    return faces + boxing


def _straight_run(t: _Totals, length, depth, height, arms, c=CONSTRUCTION, seats=None, back=True):
    """Add a straight sofa section (or chaise if back=False) to the totals."""
    arm_w, leg_h = c["arm_width"], c["leg_height"]
    arm_h = min(c["arm_height"], height - 0.15)
    base_top = leg_h + c["base_frame_height"]
    seat_w = max(0.3, length - arms * arm_w)
    seat_d = max(0.3, depth - (c["back_frame_depth"] + c["back_foam_thick"] if back else 0.0))
    n = seats or max(1, round(seat_w / c["seat_module"]))
    t.seats += n

    # Frame: base box + seat cross rails, back frame, arm frames
    cross_rails = n + 1
    t.timber_m += 2 * length + 2 * depth + cross_rails * seat_d
    back_h = height - base_top
    if back:
        t.timber_m += 2 * length + (n + 1) * back_h
    t.timber_m += arms * (2 * (arm_h - leg_h) + 2 * depth)

    # 12 mm ply: both faces of each arm, the back panel, the front base board
    t.ply_m2 += arms * 2 * depth * (arm_h - base_top)
    if back:
        t.ply_m2 += length * back_h
    t.ply_m2 += length * c["base_frame_height"]

    # Foam
    t.seat_foam_m3 += seat_w * seat_d * c["seat_foam_thick"]
    back_cushion_h = max(0.2, height - c["seat_height"] - 0.03)
    if back:
        t.back_foam_m3 += seat_w * back_cushion_h * c["back_foam_thick"]
    arm_pad = arms * (2 * depth * (arm_h - base_top) + depth * arm_w + arm_w * (arm_h - leg_h))
    back_pad = (length * (height - leg_h) + length * c["back_frame_depth"]) if back else 0.0
    t.pad_foam_m3 += (arm_pad + back_pad) * c["pad_thick"]

    # Fabric (upholstered surface area; converted to running metres later)
    area = _cushion_fabric(seat_w, seat_d, c["seat_foam_thick"], n)
    if back:
        area += _cushion_fabric(seat_w, back_cushion_h, c["back_foam_thick"], n)
        area += length * (height - leg_h)                 # outside back
        area += seat_w * (height - base_top)              # inside back, behind cushions
        area += length * c["back_frame_depth"]            # top of back
    area += arm_pad                                       # arms, all faces
    area += length * (base_top - leg_h)                   # front base panel
    area += seat_w * seat_d                               # seat deck under the cushions
    t.fabric_m2 += area
    t.wrap_m2 += seat_w * seat_d + (seat_w * back_cushion_h if back else 0.0)

    # Suspension
    t.springs += math.ceil(seat_w / c["spring_pitch"])
    if back:
        t.webbing_m += math.ceil(back_cushion_h / c["webbing_pitch"]) * seat_w

    # Legs: corners, plus centre support on long runs
    t.legs += 4 + (2 if length >= c["centre_legs_from"] else 0)


def geometry_bom(sofa_type: str, length_mm: float, width_mm: float, height_mm: float,
                 c: dict = CONSTRUCTION) -> list[dict]:
    """
    Net material quantities for one sofa. sofa_type is a canonical key from
    cost_engine.normalize_sofa_type ('1-seater' … '4-seater', 'l-shape').
    Returns [{component_group, unit, new_qty, notes}] in a fixed order.
    """
    L, W, H = length_mm / 1000.0, width_mm / 1000.0, height_mm / 1000.0
    t = _Totals()
    fixed_seats = {"1-seater": 1, "2-seater": 2, "3-seater": 3}

    if sofa_type == "l-shape":
        # Main run with one arm; the chaise extends forward at the other end
        _straight_run(t, L, W, H, arms=1, c=c)
        extra = max(0.3, c["chaise_projection"] - W)
        _straight_run(t, c["chaise_width"], extra, H, arms=1, c=c, seats=1, back=False)
        t.legs -= 2            # chaise shares the main run's corner legs
    else:
        seats = fixed_seats.get(sofa_type)
        if sofa_type == "4-seater":
            seats = max(4, round((L - 2 * c["arm_width"]) / c["seat_module"]))
        _straight_run(t, L, W, H, arms=2, c=c, seats=seats)

    sec_w, sec_h = c["member_section"]
    timber_cft = t.timber_m * sec_w * sec_h * M3_TO_CFT
    fabric_m = t.fabric_m2 * (1 + c["fabric_seam_allow"]) / c["fabric_usable_width"]
    glued_m2 = t.wrap_m2 + (t.pad_foam_m3 / c["pad_thick"])

    rows = [
        ("Wood Frame",     "cubic feet",    timber_cft,
         f"{t.timber_m:.1f} m of {sec_w*1000:.0f}x{sec_h*1000:.0f} mm members"),
        ("Plywood",        "square meters", t.ply_m2, "12 mm: arm faces, back panel, base board"),
        ("Seat Foam",      "kg",            t.seat_foam_m3 * FOAM_DENSITY["seat"],
         f"{t.seat_foam_m3:.3f} m3 @ 40 kg/m3, {c['seat_foam_thick']*1000:.0f} mm"),
        ("Back Foam",      "kg",            t.back_foam_m3 * FOAM_DENSITY["back"],
         f"{t.back_foam_m3:.3f} m3 @ 32 kg/m3, {c['back_foam_thick']*1000:.0f} mm"),
        ("Padding Foam",   "kg",            t.pad_foam_m3 * FOAM_DENSITY["pad"],
         f"{t.pad_foam_m3:.3f} m3 @ 28 kg/m3, arms and outer back"),
        ("Fabric",         "metres",        fabric_m,
         f"{t.fabric_m2:.1f} m2 upholstered + {c['fabric_seam_allow']*100:.0f}% seams, 54\" roll"),
        ("Fibre Wrap",     "square meters", t.wrap_m2, "polyester fibre over seat and back cushions"),
        ("Springs",        "pieces",        t.springs, f"zig-zag, {c['spring_pitch']*1000:.0f} mm pitch"),
        ("Elastic Webbing", "metres",       t.webbing_m, "back support rows"),
        ("Adhesive",       "kg",            glued_m2 * c["adhesive_kg_per_m2"], f"{glued_m2:.1f} m2 glued foam"),
        ("Legs",           "pieces",        t.legs, ""),
        ("Sundries",       "sets",          t.seats, "per seat: staples, thread, clips, screws, dust cover"),
    ]
    return [{"component_group": name, "unit": unit, "new_qty": round(qty, 4), "notes": note}
            for name, unit, qty, note in rows]
