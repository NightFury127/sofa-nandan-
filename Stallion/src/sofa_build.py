"""
sofa_build.py — The sofa as it is built, part by part, following the industry
reference model "Sofa Internal Structure.f3z" (a Fusion 360 design of a
3-seater, measured with reference_cad.py; catalogue in
data/reference/reference_parts.json).

The 3D model (sofa_interior.py) and the quote's material quantities
(bom_geometry.geometry_bom) both come from the parts built here, so the model
shows exactly what the quote prices.

How the reference is fitted to any size
  * Timber and plywood sections (25x40, 25x65, 25x45, 45x25, 51x48, 12 mm ply)
    are stock sizes and never scale; their lengths and positions do.
  * Heights scale with the frame height (overall height - legs), depths with
    the sofa's depth, the seat span with its length.
  * Repeated parts are re-spaced at the reference pitch: sinuous springs at
    127 mm, vertical back belts at 107 mm, a centre support per 850 mm of span.
  * Arms keep the reference width (230 mm per side) unless the sofa is too
    narrow for it.

Reference frame used in the measurements below ("#NNN" = body record in the
.f3z): x = length (centred), y = height above the frame underside,
z = depth (+ = front, front face 423, back face -414); mm. The reference
3-seater is 2061 long, 837 deep and 693 tall above its legs, with a seat
span of 1576 between the 12 mm side panels.

Not in the reference, so assumed (see docs/08_COSTING.md): legs (none
modelled), a second 50 mm seat foam layer filling the gap under the seat
fabric, the rear seat rail the springs hook onto (its clips are modelled),
mirror-image details the reference draws on one side only, and the L-shape
chaise.

Our frame for the built parts (mm): X = length (0..L), Y = depth from the
front (0..W), Z = height (0 = floor).
"""

import math
from dataclasses import dataclass, field

import numpy as np

# ── Reference measurements ───────────────────────────────────────────────────
REF_FRONT, REF_BACK = 423.0, -414.0       # z of the front / back faces (#1)
REF_FRAME_H = 693.0                        # frame underside -> top of back (#1)
REF_ARM_ZONE = 230.0                       # side panel -> outside of arm (800 -> 1030, #13)
ARM_GAP = 13.0                             # side panel -> arm (800 -> 813)
REF_ARM_W = REF_ARM_ZONE - ARM_GAP         # 217, arm incl. its fabric (#13)
PANEL_T = 12.0                             # side panels, 12 mm ply (#417)
REAR_SEAT_EDGE = -160.0                    # z behind the rear seat rail: a chaise (no back) ends here

SPRING_PITCH, SPRING_MARGIN = 127.0, 153.0   # 11 springs at x = -635 ... 635 (clips #82-#138)
BELT_PITCH, BELT_MARGIN = 107.0, 147.0       # vertical back belts (#150-#159)
SUPPORT_BAY = 850.0                          # one centre support for the 1576 span (#380, #393)
MIN_SEAT_PER_PERSON = 520.0                  # arms narrow below this seat width per seat

WIRE_R = 2.0           # sinuous spring wire, 4 mm (torus minor radius 0.2 cm, #139)
BEND_R = 12.5          # spring bend radius (torus major radius 1.25 cm)
SPRING_BAR = 23.0      # spring zig-zag width between bend centres
SPRING_STEP = 25.0     # bars along the spring
LEG_W = 50.0

# Arm cross-sections (u = mm out from the arm's inner face, y up), from the arm
# assembly #200-#226 (u = x - 903) and the arm shell #13 (u = x - 813).
ARM_END_BOARD = [(0, 0), (0, 230), (203, 332), (203, 0)]                 # #204/#205, 12 mm ply
ARM_TOP_BOARD = [(7, 235), (-6, 315), (164, 411), (190, 338)]             # #213/#247, 12 mm ply
ARM_TOP_FOAM = [(-6, 315), (9, 269), (173, 364), (164, 411)]              # #184
ARM_ROLL = [(203, 333), (194, 332), (165, 412), (175, 412)]               # #224
ARM_COVER = [(-8, 0), (-8, 317), (165, 415), (178, 415), (217, 336), (217, 0)]   # #13 + #17 + #184
# (name, u0, u1, y0, y1, z0, z1): arm frame timber, along the arm's depth
ARM_MEMBERS = [
    ("inner_bottom_rail", 0, 25, 0, 45, -388, 383),        # #200  25x45
    ("outer_bottom_rail", 178, 203, 0, 45, -388, 383),     # #201  25x45
    ("outer_top_rail", 178, 203, 283, 328, -388, 383),     # #209  25x45
    ("inner_mid_rail", 0, 25, 92, 157, -388, 383),         # #206  25x65
    ("inner_top_rail", 0, 45, 205, 230, -388, 383),        # #207  45x25
    ("front_spacer", 25, 178, 0, 25, 318, 383),            # #202  25x65
    ("back_spacer", 25, 178, 0, 25, -388, -323),           # #203  25x65
    ("top_slat_2", 46, 71, 289, 334, -388, 357),           # #172  25x45
]
# Arm members set at the slope of the arm top: (name, (u, y) outline, z0, z1)
ARM_SLOPED_MEMBERS = [
    ("top_rail", [(132, 270), (116, 289.2), (81.4, 260.3), (97.5, 241.1)], -388, 383),          # #208 25x45 on edge
    ("top_slat_1", [(34.5, 276), (10.6, 267.3), (9.4, 266.9), (17.5, 244.6), (29.6, 247.6),
                    (49.8, 254.9), (59.6, 260.5), (51.7, 282.2)], -388, 357),                    # #173
    # #175 overlaps the arm-top foam by ~10 mm in the reference; set 10 mm lower so it sits under it
    ("top_slat_3", [(81.6, 326.9), (116.1, 355.8), (100, 375), (65.5, 346)], -388, 357),         # #175 45x25 on edge
    ("top_slat_4", [(165, 336.7), (174.5, 339.6), (170.6, 361.8), (160.5, 361.3), (126, 355.3),
                    (130.4, 330.6)], -388, 357),                                                 # #174
]
SIDE_PANEL = [(395, 0), (-395, 0), (-395, 680), (-330, 680), (-220, 243), (-220, 153), (395, 153)]   # #417 (z, y)
SIDE_PANEL_CHAISE = [(395, 0), (REAR_SEAT_EDGE, 0), (REAR_SEAT_EDGE, 153), (395, 153)]
BACK_STILE = [(-230, 286), (-322, 655), (-346, 649), (-254, 280)]        # #377 (z, y), 40 wide
BACK_FOAM = [(-137, 263), (-242, 680), (-321, 680), (-216, 263)]         # #302
BACK_CUSHION_COVER = [(-134, 262), (-240, 683), (-324, 683), (-219, 262)]   # skin #2 around #302
BACK_BELT = [(-218, 255), (-321, 667), (-323, 667), (-220, 255)]         # #150, 2 mm
CROSS_BELTS = [[(-303, 592), (-291, 543), (-289, 544), (-301, 592)],     # #317
               [(-278, 497), (-268, 448), (-266, 448), (-276, 497)]]     # #318


# ── Parts ────────────────────────────────────────────────────────────────────

@dataclass
class Part:
    """One physical part. kind 'box' (lo, hi), 'prism' (a planar profile swept
    along `sweep`) or 'wire' (a path of round wire)."""
    layer: str
    name: str
    kind: str
    lo: np.ndarray = None
    hi: np.ndarray = None
    profile: np.ndarray = None     # prism: (n, 3) points on the start plane
    sweep: np.ndarray = None       # prism: extrusion vector
    path: np.ndarray = None        # wire: (n, 3) centre line
    radius: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def volume(self) -> float:
        if self.kind == "box":
            return float(np.prod(self.hi - self.lo))
        if self.kind == "prism":
            return _polygon_area(self.profile) * float(np.linalg.norm(self.sweep))
        return math.pi * self.radius ** 2 * self.length

    @property
    def length(self) -> float:
        if self.kind == "wire":
            return float(np.linalg.norm(np.diff(self.path, axis=0), axis=1).sum())
        if self.kind == "prism":
            return float(np.linalg.norm(self.sweep))
        return float((self.hi - self.lo).max())

    def mesh(self):
        """The part as a closed triangle mesh (trimesh), mm."""
        import trimesh
        if self.kind == "box":
            m = trimesh.creation.box(extents=self.hi - self.lo)
            m.apply_translation((self.lo + self.hi) / 2.0)
            return m
        if self.kind == "prism":
            return _extrude(self.profile, self.sweep)
        return _tube(self.path, self.radius)

    def translate(self, d):
        d = np.asarray(d, float)
        for attr in ("lo", "hi", "profile", "path"):
            v = getattr(self, attr)
            if v is not None:
                setattr(self, attr, v + d)


def _polygon_area(P) -> float:
    P = np.asarray(P, float)
    n = np.zeros(3)
    for a, b in zip(P, np.roll(P, -1, axis=0)):
        n += np.cross(a, b)
    return float(np.linalg.norm(n) / 2.0)


def _ear_clip(P2) -> list:
    """Triangles of a simple polygon given as 2D points."""
    n = len(P2)
    idx = list(range(n))
    if sum(P2[i][0] * P2[(i + 1) % n][1] - P2[(i + 1) % n][0] * P2[i][1] for i in range(n)) < 0:
        idx.reverse()

    def inside(p, a, b, c):
        d = [(p[0] - q[0]) * (r[1] - q[1]) - (r[0] - q[0]) * (p[1] - q[1]) for q, r in ((b, a), (c, b), (a, c))]
        return all(v >= 0 for v in d) or all(v <= 0 for v in d)

    tris = []
    while len(idx) > 3:
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = P2[i0], P2[i1], P2[i2]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-9:
                continue
            if any(inside(P2[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:                                   # degenerate outline: fan the rest
            tris += [(idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1)]
            return tris
    tris.append(tuple(idx))
    return tris


def _extrude(profile, sweep):
    import trimesh
    P = np.asarray(profile, float)
    n = len(P)
    axis = np.asarray(sweep, float) / np.linalg.norm(sweep)
    u = np.cross(axis, [0, 0, 1] if abs(axis[2]) < 0.9 else [1, 0, 0])
    u /= np.linalg.norm(u)
    w = np.cross(axis, u)
    caps = _ear_clip([((p - P[0]) @ u, (p - P[0]) @ w) for p in P])
    faces = [(a, c, b) for a, b, c in caps] + [(a + n, b + n, c + n) for a, b, c in caps]
    for i in range(n):
        j = (i + 1) % n
        faces += [(i, j, j + n), (i, j + n, i + n)]
    mesh = trimesh.Trimesh(np.vstack([P, P + sweep]), faces, process=True)
    mesh.fix_normals()
    return mesh


def _tube(path, radius, sides=6):
    """A round wire along a path, as one mesh."""
    import trimesh
    P = np.asarray(path, float)
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1)[:, None]
    ref = np.where(np.abs(T[:, 2:3]) < 0.9, [[0, 0, 1]], [[1, 0, 0]])
    N = np.cross(T, ref)
    N /= np.linalg.norm(N, axis=1)[:, None]
    B = np.cross(T, N)
    ang = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    rings = P[:, None, :] + radius * (np.cos(ang)[None, :, None] * N[:, None, :] + np.sin(ang)[None, :, None] * B[:, None, :])
    V = rings.reshape(-1, 3)
    F = []
    for i in range(len(P) - 1):
        for k in range(sides):
            a, b = i * sides + k, i * sides + (k + 1) % sides
            F += [(a, b, b + sides), (a, b + sides, a + sides)]
    return trimesh.Trimesh(V, F, process=False)


def box(layer, name, x, y, z, **meta) -> Part:
    lo = np.array([min(x), min(y), min(z)], float)
    hi = np.array([max(x), max(y), max(z)], float)
    return Part(layer, name, "box", lo=lo, hi=hi, meta=meta)


def prism_x(layer, name, yz, x0, x1, **meta) -> Part:
    """Profile in the (Y, Z) plane swept along X from x0 to x1."""
    prof = np.array([(x0, y, z) for y, z in yz], float)
    return Part(layer, name, "prism", profile=prof, sweep=np.array([x1 - x0, 0.0, 0.0]), meta=meta)


def prism_y(layer, name, xz, y0, y1, **meta) -> Part:
    """Profile in the (X, Z) plane swept along Y from y0 to y1."""
    prof = np.array([(x, y0, z) for x, z in xz], float)
    return Part(layer, name, "prism", profile=prof, sweep=np.array([0.0, y1 - y0, 0.0]), meta=meta)


def sinuous_spring(x, y_front, y_back, z) -> np.ndarray:
    """Centre line of a sinuous spring: bars across, joined by half-round bends."""
    n = max(2, int(round((y_back - y_front) / SPRING_STEP)) + 1)
    ys = np.linspace(y_front, y_back, n)
    half = SPRING_BAR / 2.0
    pts = []
    for i, y in enumerate(ys):
        a, b = (x - half, x + half) if i % 2 == 0 else (x + half, x - half)
        pts += [(a, y, z), (b, y, z)]
        if i + 1 < n:                                    # bend round to the next bar
            r = (ys[i + 1] - y) / 2.0
            side = 1.0 if b > x else -1.0
            for t in np.linspace(0, math.pi, 7)[1:-1]:
                pts.append((b + side * r * math.sin(t), y + r - r * math.cos(t), z))
    return np.array(pts, float)


# ── Fitting the reference to a run ───────────────────────────────────────────

class _Fit:
    """Maps reference coordinates onto one straight run of the sofa."""

    def __init__(self, run, H, leg_h, ox, oy):
        self.back = run["back"]
        self.leg_h = leg_h
        self.fy = (H - leg_h) / REF_FRAME_H
        ref_back = REF_BACK if self.back else REAR_SEAT_EDGE
        self.fz = run["depth"] * 1000.0 / (REF_FRONT - ref_back)
        self.oy = oy

    def Y(self, z):                       # reference z -> our depth Y
        return self.oy + (REF_FRONT - z) * self.fz

    def Z(self, y):                       # reference y -> our height Z
        return self.leg_h + y * self.fy

    def Yr(self, z0, z1, keep=False):
        a, b = sorted((self.Y(z0), self.Y(z1)))
        if keep:                          # a timber section: keep its size, move its centre
            c, h = (a + b) / 2.0, abs(z1 - z0) / 2.0
            return c - h, c + h
        return a, b

    def Zr(self, y0, y1, keep=False):
        a, b = self.Z(y0), self.Z(y1)
        if keep:                          # never below the frame's underside
            c, h = (a + b) / 2.0, abs(y1 - y0) / 2.0
            c = max(c, self.leg_h + h)
            return c - h, c + h
        return a, b

    def yz(self, pts):
        """(z, y) reference profile -> (Y, Z)."""
        return [(self.Y(z), self.Z(y)) for z, y in pts]


def arm_zone(length_mm, seats, sides) -> float:
    """Width of each arm incl. the gap to the side panel (230 in the reference)."""
    if not sides:
        return 0.0
    room = (length_mm - 2 * PANEL_T - MIN_SEAT_PER_PERSON * seats) / len(sides)
    return float(np.clip(room, 150.0, REF_ARM_ZONE))


def _build_run(parts, run, H, leg_h, ox, oy, drop_back_legs=False):
    tag = run.get("tag", "")
    f = _Fit(run, H, leg_h, ox, oy)
    L, D = run["length"] * 1000.0, run["depth"] * 1000.0
    sides = run["arm_sides"]
    A = arm_zone(L, run["seats"], sides)
    a_left = A if "left" in sides else 0.0
    a_right = A if "right" in sides else 0.0
    P0, P1 = ox + a_left + PANEL_T, ox + L - a_right - PANEL_T     # seat span between the panels
    S = P1 - P0
    y_front, y_back = oy, oy + D
    back = run["back"]

    def add(p):
        """Keep the part within the run's length (covers reach into the arm gap,
        which a run end without an arm does not have)."""
        p.name = tag + p.name
        if p.kind == "box":
            p.lo[0], p.hi[0] = max(p.lo[0], ox), min(p.hi[0], ox + L)
        elif p.kind == "prism" and p.sweep[0]:
            x0 = max(p.profile[0, 0], ox)
            x1 = min(p.profile[0, 0] + p.sweep[0], ox + L)
            p.profile[:, 0], p.sweep[0] = x0, x1 - x0
        parts.append(p)

    def zr(z0, z1, keep=False):
        """Depth range inside this run: a chaise has no back zone, so parts that
        would fall behind it are clipped, and fixed-size parts moved inside."""
        a, b = f.Yr(z0, z1, keep)
        if keep:
            shift = min(0.0, y_back - b) + max(0.0, y_front - a)
            return a + shift, b + shift
        return max(a, y_front), min(b, y_back)

    # Supports: one per 850 mm bay inside the span
    n_sup = max(0, math.ceil(S / SUPPORT_BAY) - 1)
    supports = [P0 + S * (k + 1) / (n_sup + 1) for k in range(n_sup)]

    # ── Frame: rails across the span ─────────────────────────────────────────
    add(box("frame", "front_seat_rail", (P0, P1), zr(370, 395, True), f.Zr(88, 153, True), section="65x25"))   # #400
    add(box("frame", "rear_seat_rail", (P0, P1), zr(-157, -132, True), f.Zr(88, 153, True), section="65x25"))  # springs' rear clips #127
    add(box("frame", "bottom_middle_rail", (P0, P1), zr(-20, 20, True), f.Zr(0, 25, True), section="25x40"))   # #397
    if back:
        add(box("frame", "bottom_back_rail", (P0, P1), zr(-395, -355, True), f.Zr(0, 25, True), section="25x40"))   # #396
        add(box("frame", "back_top_rail", (P0, P1), zr(-395, -330, True), f.Zr(655, 680, True), section="25x65"))   # #410
    else:
        add(box("frame", "bottom_back_rail", (P0, P1), (y_back - 55, y_back - 15), f.Zr(0, 25, True), section="25x40"))

    # ── Frame: each centre support ───────────────────────────────────────────
    for k, x in enumerate(supports, 1):
        s = f"_{k}"
        rear = -355 if back else REAR_SEAT_EDGE + 40
        add(box("frame", "bottom_stretcher" + s, (x - 32, x + 32), zr(rear, 370), f.Zr(0, 25, True), section="65x25"))   # #393
        add(box("frame", "seat_post" + s, (x - 32, x + 32), zr(-131, -106, True), f.Zr(25, 153), section="65x25"))       # #384
        add(box("frame", "front_post" + s, (x - 32, x + 32), zr(345, 370, True), f.Zr(0, 150), section="65x25"))         # #360
        if back:
            add(box("frame", "back_post" + s, (x - 58, x - 32), zr(-395, -330, True), f.Zr(0, 655), section="25x65"))    # #380
            add(box("frame", "stile_block" + s, (x - 32, x - 8), zr(-395, -253), f.Zr(211, 276, True), section="25x65"))  # #373
            add(prism_x("frame", "back_stile" + s, f.yz(BACK_STILE), x - 65, x - 25, section="40x25"))                   # #377

    # ── Frame and plywood at each end, inside the side panels ────────────────
    for end, (px, sign) in (("l", (P0, 1.0)), ("r", (P1, -1.0))):
        u = lambda a, b: (px + sign * a, px + sign * b)
        add(box("frame", f"side_rail_low_{end}", u(1, 41), zr(-130, 370), f.Zr(0, 25, True), section="40x25"))     # #403
        add(box("frame", f"side_rail_high_{end}", u(1, 41), zr(-130, 370), f.Zr(128, 153, True), section="40x25"))  # #402
        if back:
            add(prism_x("frame", f"end_stile_{end}", f.yz(BACK_STILE), *sorted(u(0, 40)), section="40x25"))         # #388
            add(box("frame", f"corner_post_{end}", u(0, 25), zr(-345, -280, True), f.Zr(65, 290), section="25x65"))  # #365
            add(box("frame", f"corner_block_{end}", u(0, 25), zr(-345, -175), f.Zr(0, 65, True), section="25x65"))   # #366
        pan = (px - PANEL_T, px) if sign > 0 else (px, px + PANEL_T)
        add(prism_x("plywood", f"side_panel_{end}", f.yz(SIDE_PANEL if back else SIDE_PANEL_CHAISE), *pan))        # #417

    if back:
        add(box("plywood", "back_top_cap", (P0 - 17, P1 + 17), zr(-400, -242), f.Zr(680, 692, True)))               # #287 #298 #300

    # ── Suspension: sinuous springs and clips, seat belts, back belts ────────
    n_spr = max(2, int(round((S - 2 * SPRING_MARGIN) / SPRING_PITCH)) + 1)
    for i, x in enumerate(np.linspace(P0 + SPRING_MARGIN, P1 - SPRING_MARGIN, n_spr), 1):
        y0, y1 = sorted((f.Y(387), f.Y(-142)))
        add(Part("springs", f"spring_{i}", "wire", path=sinuous_spring(x, y0, y1, f.Z(159.5)), radius=WIRE_R))   # #139
        add(box("springs", f"clip_front_{i}", (x - 10, x + 10), zr(373, 395, True), f.Zr(154, 164, True)))       # #82 #83
        add(box("springs", f"clip_rear_{i}", (x - 10, x + 10), zr(-154, -132, True), f.Zr(154, 170, True)))      # #127
    for i, (z0, z1) in enumerate(((84, 154), (-58, 12)), 1):                                                    # #149 #148, 70 wide
        add(box("webbing", f"seat_belt_{i}", (P0 + 2, P1 - 2), zr(z0, z1), f.Zr(153, 155, True), run_length=S - 4))
    if back:
        n_belt = max(2, int(round((S - 2 * BELT_MARGIN) / BELT_PITCH)) + 1)
        for i, x in enumerate(np.linspace(P0 + BELT_MARGIN, P1 - BELT_MARGIN, n_belt), 1):
            if any(abs(x - s) < 45 for s in supports):        # the reference leaves out the belt at a stile
                continue
            belt = prism_x("webbing", f"back_belt_{i}", f.yz(BACK_BELT), x - 25, x + 25)
            belt.meta["run_length"] = float(np.hypot(*np.subtract(*f.yz(BACK_BELT)[:2])))
            add(belt)
        for i, prof in enumerate(CROSS_BELTS, 1):
            add(prism_x("webbing", f"back_cross_belt_{i}", f.yz(prof), P0 + 8, P1 - 8, run_length=S - 16))

    # ── Foam ─────────────────────────────────────────────────────────────────
    # Seat foam is stock sheet: 51 mm (#312) plus a 50 mm layer filling the gap under
    # the seat fabric (#2 at 263), the same thickness at any sofa height.
    seat_rear = -220 if back else REAR_SEAT_EDGE
    s0 = f.Z(162)
    s1, seat_top = s0 + 51.0, s0 + 101.0
    add(box("seat_foam", "seat_foam_lower", (P0 - PANEL_T, P1 + PANEL_T), zr(seat_rear, 395), (s0, s1)))           # #312
    add(box("seat_foam", "seat_foam_upper", (P0 - PANEL_T, P1 + PANEL_T), zr(seat_rear, 395), (s1, seat_top)))

    def on_seat(yz, base_y, gap=0.0):
        """Back cushion profile with its foot on the seat top (reference y = base_y)."""
        return [(Y, seat_top + gap if abs(Z - f.Z(base_y)) < 1e-6 else Z) for Y, Z in yz]
    if back:
        add(prism_x("back_foam", "back_cushion", on_seat(f.yz(BACK_FOAM), 263), P0 - PANEL_T, P1 + PANEL_T))      # #302
    add(box("padding", "front_padding", (P0 - PANEL_T, P1 + PANEL_T), zr(396, 421, True), (f.Z(84), seat_top + 1)))    # #309

    # ── Fabric covers ────────────────────────────────────────────────────────
    add(box("fabric", "seat_cover", (P0 - 13, P1 + 13), zr(seat_rear - 2, 398), (f.Z(160), seat_top + 3)))
    add(box("fabric", "front_cover", (P0 - 17, P1 + 17), zr(396, REF_FRONT), (f.Z(0), seat_top + 3)))
    if back:
        add(prism_x("fabric", "back_cushion_cover", on_seat(f.yz(BACK_CUSHION_COVER), 262, -1.0), P0 - 13, P1 + 13))
        add(box("fabric", "back_cover", (P0 - 17, P1 + 17), zr(-401, -241), f.Zr(0, REF_FRAME_H)))                  # #289

    # ── Arms ─────────────────────────────────────────────────────────────────
    for side in sides:
        inner = ox + A - ARM_GAP if side == "left" else ox + L - A + ARM_GAP
        sign = -1.0 if side == "left" else 1.0                  # outward along X
        fu = (A - ARM_GAP) / REF_ARM_W

        def U(u):
            return inner + sign * u * fu

        lo_u, hi_u = sorted((U(0), U(203)))                    # the arm frame's width

        def Ur(u0, u1, keep):
            a, b = sorted((U(u0), U(u1)))
            if keep:                                            # stock section, kept inside the frame
                c, h = (a + b) / 2.0, abs(u1 - u0) / 2.0
                c = min(max(c, lo_u + h), hi_u - h)
                return c - h, c + h
            return a, b

        def xz(profile):
            return [(U(u), f.Z(y)) for u, y in profile]

        a = f"arm_{side}_"
        for name, u0, u1, y0, y1, z0, z1 in ARM_MEMBERS:
            sec = f"{abs(u1 - u0):.0f}x{abs(y1 - y0):.0f}"
            add(box("frame", a + name, Ur(u0, u1, abs(u1 - u0) <= 60), zr(z0, z1, abs(z1 - z0) <= 70),
                    f.Zr(y0, y1, True), section=sec))
        for name, outline, z0, z1 in ARM_SLOPED_MEMBERS:
            add(prism_y("frame", a + name, xz(outline), *zr(z0, z1)))
        for end, (z0, z1) in (("front", (383, 395)), ("back", (-400, -388))):
            ys = zr(z0, z1, True)
            add(prism_y("plywood", a + f"end_board_{end}", xz(ARM_END_BOARD), *ys))                   # #204 #205
            add(prism_y("plywood", a + f"top_board_{end}", xz(ARM_TOP_BOARD), *ys))                   # #213 #247
        add(prism_y("padding", a + "top_foam", xz(ARM_TOP_FOAM), *zr(-388, 395)))                     # #184
        add(prism_y("padding", a + "roll", xz(ARM_ROLL), *zr(-400, 395)))                             # #224
        add(prism_y("fabric", a + "cover", xz(ARM_COVER), *zr(REF_BACK, 409)))                        # #13

    # ── Legs (not in the reference): corners, plus a centre pair on long runs ─
    from bom_geometry import leg_count, CONSTRUCTION
    inset = 30.0
    xs = [ox + inset, ox + L - inset - LEG_W]
    if leg_count(run["length"], CONSTRUCTION) > 4:
        xs.append(ox + L / 2.0 - LEG_W / 2.0)
    rows = [y_front + inset] + ([] if drop_back_legs else [y_back - inset - LEG_W])
    k = 0
    for y in rows:
        for x in xs:
            k += 1
            add(box("legs", f"leg_{k}", (x, x + LEG_W), (y, y + LEG_W), (0.0, leg_h)))


def build_parts(sofa_type: str, length_mm: float, width_mm: float, height_mm: float) -> list[Part]:
    """
    Every part of the sofa, in our frame (X 0..L, Y 0 = front, Z 0 = floor).
    sofa_type is a canonical key from cost_engine.normalize_sofa_type.
    """
    from bom_geometry import CONSTRUCTION, sofa_runs
    c = CONSTRUCTION
    leg_h = c["leg_height"] * 1000.0
    runs = sofa_runs(sofa_type, length_mm / 1000.0, width_mm / 1000.0, c)
    parts: list[Part] = []
    if len(runs) == 1:
        _build_run(parts, runs[0], height_mm, leg_h, 0.0, 0.0)
    else:
        # L-shape: chaise in front of the right-hand end of the main run
        main, chaise = runs[0], dict(runs[1], tag="chaise_")
        chaise_d = chaise["depth"] * 1000.0
        _build_run(parts, main, height_mm, leg_h, 0.0, chaise_d)
        _build_run(parts, chaise, height_mm, leg_h, length_mm - chaise["length"] * 1000.0, 0.0,
                   drop_back_legs=True)
    return parts
