"""
collect_web_photos.py — Collect sofa photos from web image search (DuckDuckGo /
Bing results, via the `ddgs` package) as candidates for training and testing.

Unlike collect_openverse_photos.py these photos are NOT openly licensed: most
are retailer or manufacturer images. The source URL of every file is recorded
in the manifest so any photo can be traced and removed later.

Output:  data/datasets/collected/web/candidates/<type>/<md5>.jpg   (max 800px)
         data/datasets/collected/web/manifest.csv                 (one row per photo)

- Exact and near-duplicate photos are dropped, including copies of photos
  already in data/datasets/raw/ and the Openverse collection, so a web photo
  can't leak a test photo into training.
- The <type> folder comes from the search query, so it is only a GUESS.
  --suggest runs the live detector + type classifier over the candidates and
  writes their opinion into review.csv to speed up review.
- Every photo must be reviewed before use: fill in the verdict column of
  data/datasets/collected/web/review.csv (a type such as 2_seater, or
  "reject"), then run --apply-review to copy accepted photos to
  data/datasets/collected/web/reviewed/<type>/.

Run:
    python collect_web_photos.py                 # ~80 results per query
    python collect_web_photos.py --per-query 150
    python collect_web_photos.py --suggest
    python collect_web_photos.py --apply-review
"""

import argparse
import csv
import hashlib
import io
import shutil
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SRC_DIR      = Path(__file__).parent.resolve()
PROJECT_ROOT = SRC_DIR.parent.resolve()
DATASETS     = PROJECT_ROOT / "data" / "datasets"
OUT_DIR      = DATASETS / "collected" / "web"
MANIFEST     = OUT_DIR / "manifest.csv"
REVIEW       = OUT_DIR / "review.csv"
# Existing photos to de-duplicate against
EXISTING     = [DATASETS / "raw", DATASETS / "collected" / "candidates"]

HEADERS   = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StallionSofaResearch/1.0"}
MAX_BYTES = 10_000_000
MAX_SIDE  = 800
MIN_SIDE  = 200
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Room-photo queries per pipeline type: customers send room photos, and the
# training set is short of them. Results are only candidates for review.
QUERIES = {
    "1_seater":      ["single seater sofa in living room", "armchair living room photo",
                      "one seater sofa home interior", "accent chair in room",
                      "1 seater sofa", "single seater sofa", "one seater sofa chair", "1 seater sofa living room",
                      "single seater leather sofa", "1 seater wooden sofa", "single seater recliner",
                      "club chair living room", "upholstered armchair living room", "velvet armchair room",
                      "grey armchair living room", "single sofa chair bedroom", "1 seater sofa india"],
    "2_seater":      ["two seater sofa in living room", "loveseat living room photo",
                      "2 seater sofa home interior", "small couch apartment living room",
                      "2 seater sofa", "two seater couch", "loveseat sofa", "2 seater fabric sofa living room",
                      "2 seater leather sofa living room", "2 seater wooden sofa living room",
                      "grey 2 seater sofa", "blue 2 seater sofa", "green loveseat living room",
                      "beige 2 seater sofa", "2 seater chesterfield sofa", "2 seater recliner sofa",
                      "velvet loveseat living room", "small 2 seater sofa bedroom", "2 seater sofa india"],
    "3_seater":      ["three seater sofa in living room", "3 seater sofa home interior",
                      "3 seater couch living room photo", "three seat fabric sofa room",
                      "3 seater sofa", "three seater couch", "3 seater fabric sofa living room",
                      "3 seater leather sofa living room", "3 seater wooden sofa living room",
                      "3 seat sofa apartment", "grey 3 seater sofa", "blue 3 seater sofa",
                      "beige 3 seater sofa living room", "green 3 seater sofa", "3 seater chesterfield sofa",
                      "3 seater recliner sofa living room", "3 seater sofa india living room",
                      "three seater sofa with cushions"],
    "4_seater_plus": ["four seater sofa living room", "4 seater sofa home interior",
                      "extra long sofa living room", "large 4 seat couch room",
                      "4 seater sofa", "four seater couch", "4 seater fabric sofa", "4 seater leather sofa",
                      "4 seater wooden sofa", "4 seater recliner sofa", "4 seater modular sofa",
                      "grey 4 seater sofa", "4 seater chesterfield sofa", "four seat sofa living room",
                      "4 seater sofa india", "extra large sofa 4 seats", "long four seat couch"],
    "l_shape":       ["l shaped sofa living room", "sectional sofa living room photo",
                      "corner sofa home interior", "l shape couch apartment"],
}
MANIFEST_FIELDS = ["file", "guessed_type", "query", "title", "image_url", "page_url", "md5", "ahash"]
REVIEW_FIELDS   = ["file", "guessed_type", "sofa_found", "suggested_type", "suggested_conf",
                   "verdict", "reviewer_note"]


def _ahash(img) -> str:
    """64-bit average hash, to spot near-identical copies (resized/re-encoded)."""
    small = img.convert("L").resize((8, 8))
    px = list(small.getdata())
    avg = sum(px) / len(px)
    return "".join("1" if p > avg else "0" for p in px)


def _hamming(a: str, b: str) -> int:
    return sum(x != y for x, y in zip(a, b))


def _existing_hashes():
    """md5s and ahashes of photos we already have."""
    from PIL import Image

    md5s, ahashes = set(), []
    for root in EXISTING:
        for p in root.rglob("*"):
            if p.suffix.lower() not in IMAGE_EXTS:
                continue
            try:
                md5s.add(hashlib.md5(p.read_bytes()).hexdigest())
                ahashes.append(_ahash(Image.open(p)))
            except Exception:
                pass
    return md5s, ahashes


def _download(url):
    """Return a normalised RGB image (max MAX_SIDE px) or None."""
    from PIL import Image

    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=15) as r:
            data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return None
        img = Image.open(io.BytesIO(data))
        img.load()
        img = img.convert("RGB")
    except Exception:
        return None
    if min(img.size) < MIN_SIDE:
        return None
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img


def collect(per_query: int, only=None):
    from ddgs import DDGS

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    if MANIFEST.exists():
        with open(MANIFEST, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    seen_urls = {r["image_url"] for r in rows}
    print("Hashing existing photos for de-duplication...")
    seen_md5, seen_ahash = _existing_hashes()
    seen_md5 |= {r["md5"] for r in rows}
    seen_ahash += [r["ahash"] for r in rows]
    print(f"  {len(seen_md5)} existing photos")

    ddgs = DDGS()
    added = 0
    for sofa_type, queries in QUERIES.items():
        if only and sofa_type not in only:
            continue
        type_dir = OUT_DIR / "candidates" / sofa_type
        type_dir.mkdir(parents=True, exist_ok=True)
        for q in queries:
            try:
                results = list(ddgs.images(q, max_results=per_query, type_image="photo"))
            except Exception as e:
                print(f"  [skip] '{q}': {e}")
                time.sleep(10)
                continue
            results = [r for r in results if r.get("image") and r["image"] not in seen_urls]
            seen_urls.update(r["image"] for r in results)

            with ThreadPoolExecutor(max_workers=8) as pool:
                images = list(pool.map(lambda r: _download(r["image"]), results))

            n_new = 0
            for r, img in zip(results, images):
                if img is None:
                    continue
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=90)
                data = buf.getvalue()
                md5, ah = hashlib.md5(data).hexdigest(), _ahash(img)
                if md5 in seen_md5 or any(_hamming(ah, h) <= 4 for h in seen_ahash):
                    continue
                seen_md5.add(md5)
                seen_ahash.append(ah)
                path = type_dir / f"{md5[:16]}.jpg"
                path.write_bytes(data)
                rows.append({
                    "file": path.relative_to(OUT_DIR).as_posix(), "guessed_type": sofa_type,
                    "query": q, "title": (r.get("title") or "")[:200], "image_url": r["image"],
                    "page_url": r.get("url") or "", "md5": md5, "ahash": ah,
                })
                n_new += 1
            added += n_new
            print(f"  {sofa_type:<14} '{q}': {len(results)} results, {n_new} new")
            time.sleep(3)  # space out search requests

    with open(MANIFEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{added} new photos, {len(rows)} total. Manifest: {MANIFEST}")
    print("Every photo is an unreviewed candidate. Next: python collect_web_photos.py --suggest")


def suggest():
    """Run the live detector + classifier over the candidates and write review.csv."""
    sys.path.insert(0, str(SRC_DIR))
    from sofa_type_classifier import get_type_classifier
    from sofa_validator import get_detector

    detector, classifier = get_detector(), get_type_classifier()
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    old = {}
    if REVIEW.exists():
        with open(REVIEW, newline="", encoding="utf-8") as f:
            old = {r["file"]: r for r in csv.DictReader(f)}

    out = []
    for i, m in enumerate(manifest, 1):
        path = OUT_DIR / m["file"]
        dets = detector.detect(str(path))
        sofa_type, conf = (classifier.predict(str(path)) if (dets and classifier) else ("", None))
        prev = old.get(m["file"], {})
        out.append({
            "file": m["file"], "guessed_type": m["guessed_type"], "sofa_found": "yes" if dets else "no",
            "suggested_type": sofa_type, "suggested_conf": f"{conf:.2f}" if conf is not None else "",
            "verdict": prev.get("verdict", ""), "reviewer_note": prev.get("reviewer_note", ""),
        })
        if i % 200 == 0:
            print(f"  {i}/{len(manifest)}")

    with open(REVIEW, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        w.writeheader()
        w.writerows(out)
    agree = sum(r["suggested_type"] == r["guessed_type"] for r in out)
    print(f"{len(out)} candidates, {sum(r['sofa_found'] == 'yes' for r in out)} with a sofa found, "
          f"{agree} where the classifier agrees with the search query. Review sheet: {REVIEW}")


def apply_review():
    """Copy photos accepted in review.csv into reviewed/<type>/."""
    if not REVIEW.exists():
        raise SystemExit(f"[ERROR] {REVIEW} not found — run --suggest and review first.")
    with open(REVIEW, newline="", encoding="utf-8") as f:
        accepted = [r for r in csv.DictReader(f) if r["verdict"] and r["verdict"] != "reject"]

    reviewed = OUT_DIR / "reviewed"
    if reviewed.exists():
        shutil.rmtree(reviewed)
    counts = {}
    for r in accepted:
        src = OUT_DIR / r["file"]
        dst = reviewed / r["verdict"] / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print(f"{len(accepted)} reviewed photos in {reviewed}: {counts}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-query", type=int, default=80, help="Search results to fetch per query")
    ap.add_argument("--only", nargs="+", choices=list(QUERIES), help="Collect only these types")
    ap.add_argument("--suggest", action="store_true", help="Pre-fill review.csv with model suggestions")
    ap.add_argument("--apply-review", action="store_true", help="Copy accepted photos from review.csv")
    args = ap.parse_args()
    if args.suggest:
        suggest()
    elif args.apply_review:
        apply_review()
    else:
        collect(args.per_query, args.only)
