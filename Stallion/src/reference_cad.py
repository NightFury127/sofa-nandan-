"""
reference_cad.py — Read the solid bodies of the industry reference sofa
("Sofa Internal Structure.f3z", a Fusion 360 archive) without Fusion.

The measurements in sofa_build.py come from this file. Run the CLI to
re-measure it, or after the reference changes:

    python reference_cad.py "C:/path/Sofa Internal Structure.f3z"

It writes data/reference/reference_parts.json: every distinct solid body
(duplicate copies removed) with its bounding box, in the reference's own
frame, mm:  x = length (centred on 0), y = height (0 = underside of the
frame, legs not modelled), z = depth (+ = front). The tests compare the
generated 3-seater against this file, so the archive itself does not need
to be in the repository. --glb also writes the bodies as a 3D model for
viewing.

How the archive is laid out
  .f3z   zip of .f3d designs; DesignDescription.json names them
  .f3d   zip whose entries are Zstandard-compressed (zip method 93)
  *.smb  "ASM BinaryFile4": an ACIS binary B-rep, units of 1 cm,
         one `body` record per Fusion body
Fusion keeps body names in its own design stream, so bodies are known by
their record number here; sofa_structure notes cite them as "#NNN".
Needs the `zstandard` package.
"""

import argparse
import io
import json
import struct
import zipfile
from pathlib import Path

import numpy as np

DESIGN = "Sofa Internal Structure"
CM = 10.0                                    # file units -> mm
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "reference_parts.json"


# ── Archive ──────────────────────────────────────────────────────────────────

def _member(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.compress_type != 93:             # 93 = Zstandard, which zipfile can't read
        return zf.read(info)
    import zstandard
    zf.fp.seek(info.header_offset)
    head = zf.fp.read(30)
    name_len, extra_len = struct.unpack_from("<HH", head, 26)
    zf.fp.seek(info.header_offset + 30 + name_len + extra_len)
    return zstandard.ZstdDecompressor().decompress(zf.fp.read(info.compress_size),
                                                   max_output_size=info.file_size)


def read_brep(f3z_path, design: str = DESIGN) -> bytes:
    """The B-rep stream (*.smb) of one design inside a .f3z archive."""
    outer = zipfile.ZipFile(f3z_path)
    desc = json.loads(outer.read("DesignDescription.json"))
    names = {o["relativePath"]: o["displayName"]
             for g in desc["designDescription"]["designGraphs"] for o in g["designObjects"]}
    for entry, shown in names.items():
        if shown == design:
            inner = zipfile.ZipFile(io.BytesIO(outer.read(entry)))
            info = next(i for i in inner.infolist() if i.filename.endswith(".smb"))
            return _member(inner, info)
    raise KeyError(f"design {design!r} not found; the archive has {sorted(names.values())}")


# ── ACIS binary records ──────────────────────────────────────────────────────

_FIXED = {0x03: ("short", "<h"), 0x04: ("int", "<i"), 0x05: ("float", "<f"), 0x06: ("dbl", "<d"),
          0x0C: ("ptr", "<i"), 0x13: ("pos", "<3d"), 0x14: ("vec", "<3d"), 0x15: ("enum", "<i"),
          0x16: ("vec2", "<2d"), 0x17: ("i64", "<q")}


def parse_records(data: bytes) -> list:
    """[(entity name, [(kind, value), ...])]; list index = the file's entity number."""
    if not data.startswith(b"ASM BinaryFile4"):
        raise ValueError("not an ASM BinaryFile4 stream")
    p, recs, ident, fields = 31, [], [], []          # 15-byte tag + 16-byte header
    while p < len(data):
        tag = data[p]
        p += 1
        if tag in _FIXED:
            kind, fmt = _FIXED[tag]
            v = struct.unpack_from(fmt, data, p)
            p += struct.calcsize(fmt)
            fields.append((kind, v[0] if len(v) == 1 else v))
        elif tag == 0x02:
            fields.append(("char", data[p]))
            p += 1
        elif tag in (0x07, 0x0D, 0x0E):              # string / entity name / sub-name, 1-byte length
            n = data[p]
            s = data[p + 1:p + 1 + n].decode("latin1")
            p += 1 + n
            (fields.append(("str", s)) if tag == 0x07 else ident.append(s))
        elif tag == 0x08:
            n = struct.unpack_from("<H", data, p)[0]
            fields.append(("str", data[p + 2:p + 2 + n].decode("latin1")))
            p += 2 + n
        elif tag in (0x09, 0x12):
            n = struct.unpack_from("<I", data, p)[0]
            fields.append(("str", data[p + 4:p + 4 + n].decode("latin1")))
            p += 4 + n
        elif tag in (0x0A, 0x0B):
            fields.append(("bool", tag == 0x0A))
        elif tag in (0x0F, 0x10):
            fields.append(("sub", tag == 0x0F))
        elif tag == 0x11:                            # end of record
            recs.append(("-".join(ident), fields))
            ident, fields = [], []
            if recs[-1][0].startswith("End-of"):
                break
        else:
            raise ValueError(f"unknown tag {tag:#x} at byte {p - 1}")
    return recs


_TOPOLOGY = {"lump", "shell", "subshell", "face"}


def _faces(recs, body: int) -> list:
    seen, stack, faces = set(), [recs[body][1][3][1]], []
    while stack:
        i = stack.pop()
        if i < 0 or i in seen:
            continue
        seen.add(i)
        name, fields = recs[i]
        if name.split("-")[0] not in _TOPOLOGY:
            continue
        if name == "face":
            faces.append(i)
        stack.extend(v for k, v in fields if k == "ptr" and v >= 0
                     and recs[v][0].split("-")[0] in _TOPOLOGY)
    return faces


def _point(recs, vertex: int) -> np.ndarray:
    return np.array(recs[recs[vertex][1][5][1]][1][3][1])


def loop_points(recs, loop: int, arc_step: float = 0.25) -> np.ndarray:
    """The ordered outline of a face loop (file units), circular edges sampled."""
    first = coedge = recs[loop][1][4][1]
    pts = []
    for _ in range(10000):
        cf = recs[coedge][1]
        ef = recs[cf[6][1]][1]
        a, b = _point(recs, ef[3][1]), _point(recs, ef[5][1])
        t0, t1, curve = ef[4][1], ef[6][1], ef[8][1]
        seg = [a, b]
        if curve >= 0 and recs[curve][0].startswith("ellipse"):
            q = recs[curve][1]
            centre, normal, major, ratio = np.array(q[3][1]), np.array(q[4][1]), np.array(q[5][1]), q[6][1]
            if t1 < t0:
                t1 += 2 * np.pi
            if abs(t1 - t0) < 1e-9:
                t1 = t0 + 2 * np.pi
            ts = np.linspace(t0, t1, max(3, int(abs(t1 - t0) / arc_step) + 2))
            arc = centre + np.outer(np.cos(ts), major) + np.outer(np.sin(ts), np.cross(normal, major) * ratio)
            if np.linalg.norm(arc[0] - a) < 1e-3 and np.linalg.norm(arc[-1] - b) < 1e-3:
                seg = list(arc)
        if cf[7][1]:                                 # reversed coedge
            seg = seg[::-1]
        pts.extend(seg[:-1])
        coedge = cf[3][1]
        if coedge in (first, -1):
            break
    return np.array(pts)


def bodies(recs) -> list[dict]:
    """Every body: record number, face count, vertices (mm) and face outlines (mm)."""
    out = []
    for idx, (name, fields) in enumerate(recs):
        if name != "body":
            continue
        outlines = []
        for f in _faces(recs, idx):
            loop = recs[f][1][4][1]
            if loop >= 0:
                outlines.append(loop_points(recs, loop) * CM)
        pts = np.vstack(outlines) if outlines else np.zeros((1, 3))
        out.append({"id": idx, "faces": len(outlines), "outlines": outlines,
                    "min": pts.min(0), "max": pts.max(0)})
    return out


def solids(all_bodies: list[dict]) -> list[dict]:
    """Bodies with volume (sheet and construction bodies dropped), one per position:
    the reference holds several pasted copies of the same part in the same place."""
    seen, out = set(), []
    for b in all_bodies:
        size = b["max"] - b["min"]
        if b["faces"] < 4 or size.min() < 0.8:
            continue
        key = (b["faces"], *np.round(b["min"]).astype(int), *np.round(b["max"]).astype(int))
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return out


def catalogue(f3z_path) -> list[dict]:
    rows = []
    for b in solids(bodies(parse_records(read_brep(f3z_path)))):
        rows.append({"id": b["id"], "faces": b["faces"],
                     "min": [round(float(v), 1) for v in b["min"]],
                     "max": [round(float(v), 1) for v in b["max"]]})
    return rows


def _export_glb(f3z_path, path):
    import trimesh
    scene = trimesh.Scene()
    for b in solids(bodies(parse_records(read_brep(f3z_path)))):
        for k, outline in enumerate(b["outlines"]):
            if len(outline) >= 3:
                fan = [[0, i, i + 1] for i in range(1, len(outline) - 1)]
                scene.add_geometry(trimesh.Trimesh(outline / 1000.0, fan, process=False),
                                   geom_name=f"b{b['id']}_{k}")
    scene.export(path)


def main():
    ap = argparse.ArgumentParser(description="Measure the reference sofa (.f3z).")
    ap.add_argument("f3z")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--glb", help="also write the solid bodies as a GLB for viewing")
    a = ap.parse_args()
    rows = catalogue(a.f3z)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({
        "source": Path(a.f3z).name, "design": DESIGN,
        "frame": "x length (centred), y height (0 = frame underside), z depth (+ = front); mm",
        "solids": rows}, indent=1), encoding="utf-8")
    print(f"{len(rows)} distinct solids -> {a.out}")
    if a.glb:
        _export_glb(a.f3z, a.glb)
        print(f"model -> {a.glb}")


if __name__ == "__main__":
    main()
