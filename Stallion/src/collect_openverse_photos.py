"""
collect_openverse_photos.py — Collect openly licensed sofa photos for training/testing.

Searches Openverse (openverse.org) for CC0 / public-domain / CC BY photos only,
downloads a ~600px copy of each, drops duplicates, and records licence and
source for every file. Retailer sites are deliberately not scraped (terms of
use and copyright).

Output:  data/datasets/collected/candidates/<type>/<openverse_id>.jpg
         data/datasets/collected/manifest.csv   (one row per photo)

The <type> folder comes from the search query, so it is only a GUESS.
Every photo must be reviewed before use: record a verdict per file in
data/datasets/collected/review.csv (columns: file, verdict, reviewer_note;
verdict = a type such as 2_seater, or "reject"), then run --apply-review to
copy accepted photos to data/datasets/collected/reviewed/<type>/ with a
CREDITS.csv (CC BY photos require attribution if published).

Run:
    python collect_openverse_photos.py
    python collect_openverse_photos.py --pages 3
    python collect_openverse_photos.py --apply-review
"""

import argparse
import csv
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

SRC_DIR      = Path(__file__).parent.resolve()
PROJECT_ROOT = SRC_DIR.parent.resolve()
OUT_DIR      = PROJECT_ROOT / "data" / "datasets" / "collected"
MANIFEST     = OUT_DIR / "manifest.csv"

API      = "https://api.openverse.org/v1/images/"
HEADERS  = {"User-Agent": "StallionSofaResearch/1.0 (SVCE college project)"}
LICENSES = "cc0,pdm,by"

# Search queries per pipeline type. Results are only candidates for review.
QUERIES = {
    "1_seater":      ["armchair living room", "accent chair upholstered", "club chair"],
    "2_seater":      ["loveseat", "two seater sofa", "small sofa living room"],
    "3_seater":      ["three seater sofa", "3 seater sofa", "couch living room"],
    "4_seater_plus": ["four seater sofa", "long sofa living room", "large couch"],
    "l_shape":       ["sectional sofa", "l shaped sofa", "corner sofa", "sectional couch living room"],
}
MANIFEST_FIELDS = ["file", "guessed_type", "query", "openverse_id", "title", "creator",
                   "license", "license_version", "source", "landing_url", "md5", "ahash"]


def _get(url, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout).read()


def _ahash(img) -> str:
    """64-bit average hash, to spot near-identical copies (resized/re-encoded)."""
    small = img.convert("L").resize((8, 8))
    px = list(small.getdata())
    avg = sum(px) / len(px)
    return "".join("1" if p > avg else "0" for p in px)


def _hamming(a: str, b: str) -> int:
    return sum(x != y for x, y in zip(a, b))


def main(pages: int, page_size: int):
    from PIL import Image

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows, seen_ids, seen_md5, seen_ahash = [], set(), set(), []
    if MANIFEST.exists():
        with open(MANIFEST, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        seen_ids  = {r["openverse_id"] for r in rows}
        seen_md5  = {r["md5"] for r in rows}
        seen_ahash = [r["ahash"] for r in rows]

    added = 0
    for sofa_type, queries in QUERIES.items():
        type_dir = OUT_DIR / "candidates" / sofa_type
        type_dir.mkdir(parents=True, exist_ok=True)
        for q in queries:
            for page in range(1, pages + 1):
                params = {"q": q, "license": LICENSES, "page": page, "page_size": page_size,
                          "mature": "false", "category": "photograph"}
                try:
                    results = json.loads(_get(API + "?" + urllib.parse.urlencode(params)))["results"]
                except Exception as e:
                    print(f"  [skip] '{q}' page {page}: {e}")
                    break
                for r in results:
                    if r["id"] in seen_ids:
                        continue
                    seen_ids.add(r["id"])
                    try:
                        data = _get(f"{API}{r['id']}/thumb/")
                        img = Image.open(io.BytesIO(data)).convert("RGB")
                    except Exception:
                        continue
                    if min(img.size) < 200:
                        continue
                    md5 = hashlib.md5(data).hexdigest()
                    ah = _ahash(img)
                    if md5 in seen_md5 or any(_hamming(ah, h) <= 4 for h in seen_ahash):
                        continue
                    seen_md5.add(md5); seen_ahash.append(ah)
                    path = type_dir / f"{r['id']}.jpg"
                    img.save(path, "JPEG", quality=90)
                    rows.append({
                        "file": path.relative_to(OUT_DIR).as_posix(), "guessed_type": sofa_type,
                        "query": q, "openverse_id": r["id"], "title": (r.get("title") or "")[:200],
                        "creator": r.get("creator") or "", "license": r["license"],
                        "license_version": r.get("license_version") or "", "source": r.get("source") or "",
                        "landing_url": r.get("foreign_landing_url") or "", "md5": md5, "ahash": ah,
                    })
                    added += 1
                print(f"  {sofa_type:<14} '{q}' page {page}: {len(results)} results, {added} new so far")
                time.sleep(1.5)  # stay well inside Openverse's anonymous rate limit
                if len(results) < page_size:
                    break

    with open(MANIFEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{added} new photos, {len(rows)} total. Manifest: {MANIFEST}")
    print("Every photo is an unreviewed candidate — review before use.")


def apply_review():
    """Copy photos accepted in review.csv into reviewed/<type>/ with credits."""
    import shutil

    review_path = OUT_DIR / "review.csv"
    if not review_path.exists():
        raise SystemExit(f"[ERROR] {review_path} not found — review the candidates first.")
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        manifest = {r["file"]: r for r in csv.DictReader(f)}
    with open(review_path, newline="", encoding="utf-8") as f:
        accepted = [r for r in csv.DictReader(f) if r["verdict"] != "reject"]

    reviewed = OUT_DIR / "reviewed"
    if reviewed.exists():
        shutil.rmtree(reviewed)
    credits = []
    for r in accepted:
        src = OUT_DIR / r["file"]
        dst = reviewed / r["verdict"] / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        m = manifest.get(r["file"], {})
        credits.append({"file": dst.relative_to(reviewed).as_posix(), "type": r["verdict"],
                        "creator": m.get("creator", ""), "license": m.get("license", ""),
                        "license_version": m.get("license_version", ""), "landing_url": m.get("landing_url", "")})
    with open(reviewed / "CREDITS.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "type", "creator", "license", "license_version", "landing_url"])
        w.writeheader()
        w.writerows(credits)
    counts = {}
    for c in credits:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    print(f"{len(credits)} reviewed photos in {reviewed}: {counts}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--page-size", type=int, default=20)
    ap.add_argument("--apply-review", action="store_true", help="Copy accepted photos from review.csv")
    args = ap.parse_args()
    if args.apply_review:
        apply_review()
    else:
        main(args.pages, args.page_size)
