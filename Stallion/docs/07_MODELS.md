# Detection models: what they are, how to rebuild them, how accurate they are

Last measured: 2026-10-07.

## The three models

| Model | Job | Weights | Rebuildable from this repo |
|---|---|---|---|
| Sofa detector (YOLOv8n-seg, 11 classes) | Is there a sofa? Which parts? Is it the Stallion product? | `data/models/weights/sofa_detector.pt` | Yes, from `merged_sofa_dataset.zip` |
| Type classifier v2 (YOLOv8n-cls) | 1-seater / 2-seater / 3-seater / 4-seater+ / L-shape | `data/models/weights/sofa_type_classifier.pt` (v1 kept as `sofa_type_classifier_prev.pt`) | Yes |
| COCO fallback (YOLOv8n) | Used only if the sofa detector file is missing | `data/models/weights/yolov8n.pt` | Not needed (stock model) |

`.pt` files are gitignored. A fresh clone has none of them: copy them into
`data/models/weights/`, or rebuild them as below.

### How the pipeline uses them (`src/sofa_validator.py`)

1. The detector decides whether there is a sofa at all (rejects the request if not).
2. The type classifier decides the type (the detector's own guess is kept in
   the response as `detector_type`).
3. The API prices the type **the user selected**. The detected type only
   triggers a "detector disagrees" warning on the results page.

Until 2026-10-07 there was an extra rule: if the detector's top match was a
`stallion-sofa*` class, its type (3-seater) overrode the classifier. It was
removed because those classes fire on generic room photos — the live detector
called **628 of 878** reviewed web room photos "Stallion" (confidence up to
0.96), forcing them to 3-seater. They never fired on the white-background
catalogue photos, which is why earlier checks missed it. Without the rule, the
v2 classifier calls 30 of the 42 held-out Stallion photos a 3-seater, and reads
the Stallion room photo `data/inputs/images/test_sofa.jpg` correctly.

## Rebuilding the type classifier

The live classifier (v2, 2026-10-07) is trained on catalogue photos plus
hand-reviewed room photos. Needs (all gitignored; copy them across):
- `data/datasets/raw/<1-seater|2-seater|3-seater|4-seater|L-shape>/` — catalogue photos
- `data/datasets/collected/web/reviewed/<type>/` — reviewed room photos (see "Collecting more photos")
- internet once, for the `yolov8n-cls.pt` base model

```
cd src
python prepare_type_dataset.py         # catalogue: dedupe + seeded 70/15/15 split -> processed/sofa_types/
python augment_type_dataset.py         # catalogue sofas pasted onto synthetic rooms -> processed/sofa_types_composited/
python prepare_type_dataset_rooms.py   # + room photos (60/10/30, seeded per type) -> processed/sofa_types_v2/
python train_type_classifier.py --dataset ../data/datasets/processed/sofa_types_v2 \
    --model yolov8n-cls.pt --img 224 --epochs 60 --batch 64 --device 0 \
    --extra-train ../data/datasets/processed/sofa_types_composited
                                       # ~3 min on the RTX 4060 laptop GPU; writes sofa_type_classifier_candidate.pt
python eval_sofa_types.py --classifier ../data/models/weights/sofa_type_classifier_candidate.pt \
    --dir ../data/datasets/processed/sofa_types_v2/test_rooms   # and --dir .../sofa_types_v2/test for catalogue
```

Copy the candidate over `sofa_type_classifier.pt` only if it scores at least as
well on both the catalogue `test` and the room `test_rooms` splits.

`prepare_type_dataset.py` drops exact duplicate photos, drops photos that appear
in two type folders (listed in `label_conflicts.txt`), and skips types with
fewer than 20 unique photos (catalogue 4-seater has 3). `prepare_type_dataset_rooms.py`
keeps that catalogue split unchanged and adds 4-seater as a class from room
photos (plus the 3 catalogue 4-seaters, train only).

## Rebuilding the sofa detector

The current `sofa_detector.pt` was trained (2026-08-31, 50 epochs) on
`merged_dataset`: 537 train + 145 valid photos, 11 classes, merged from five
Roboflow exports (one seater, two seater, stallion_sofa, stallion_sofa1,
stallion_sofa2). It is kept outside git as `merged_sofa_dataset.zip`
(team copy: `Downloads/datasets/` on the dev laptop). Unzip its
`merged_dataset/` contents into `data/datasets/detector/`, so that
`data/datasets/detector/data.yaml` exists — that is the scripts' default.

Verified 2026-10-07: the live detector scores box mAP50 0.747 on this
dataset's valid split, identical to the figure stored in the checkpoint, so this
is the original training data.

```
cd src
python train_model.py --epochs 50                    # writes sofa_detector_candidate.pt
python eval_model.py --weights ../data/models/weights/sofa_detector_candidate.pt
python eval_sofa_types.py                            # make sure type results didn't regress
```

Training never overwrites the live `sofa_detector.pt`. Copy the candidate over
it only after it scores at least as well.

**The `stallion-sofa*` classes do not recognise the Stallion product reliably.**
The valid split has no generic sofas, so mAP can't show this. The live detector
calls 628 of 878 generic room photos "Stallion". On 2026-10-07 a GPU fine-tune
of the live detector (100 epochs, run `stallion_ft_20261007_181033`, kept as
`sofa_detector_candidate.pt`) raised box mAP50 from 0.746 to 0.823
(stallion-sofa 0.31 → 0.97) but called **708 of the 1,582** catalogue photos in
`raw/` "Stallion" (live detector: 0), with confidences up to 0.999. Neither
model's Stallion classes affect the sofa type any more (the override was
removed), so the candidate was held back only because it hadn't been
re-checked after that change. To make the Stallion classes trustworthy,
retrain with generic sofas labelled one-seater / two-seater as counter-examples
and count top-match `stallion-sofa*` classes over `raw/` and the web room photos.

## Current accuracy

### Sofa type — classifier v2 (live) vs v1 (`eval_sofa_types.py`)

Room photos are what customers send, so the room column matters most. v1 is
the previous classifier (catalogue photos only), kept as `sofa_type_classifier_prev.pt`.

| Type | Catalogue test v2 | Catalogue test v1 | Room test v2 | Room test v1 |
|---|---:|---:|---:|---:|
| 1-seater | 80.0% (n=30) | 70.0% | **86.9%** (n=84) | 25.0% |
| 2-seater | 97.9% (n=97) | 96.9% | 78.9% (n=71) | 85.9% |
| 3-seater | 88.9% (n=9) | 88.9% | **71.1%** (n=38) | 2.6% |
| 4-seater | no test photos | cannot predict | 45.5% (n=22) | cannot predict |
| L-shape | 98.8% (n=80) | 98.8% | **98.0%** (n=49) | 71.4% |
| **Overall** | **95.4%** (216) | 93.5% | **81.1%** (264) | 44.7% |
| **Balanced** (mean per type) | **91.4%** | 88.6% | **76.0%** | 37.0% |

v1's 2-seater room score is high only because it called almost every room
photo a 2-seater. v2's main remaining confusions on room photos: 2-seater →
3-seater (11 of 71) and 4-seater → 3-seater (8 of 22). On the 15 Openverse room
photos v2 scores 60% (v1: 40%). The old detector rules score 47.2% on the
catalogue test split.

Confidence is now a useful signal on room photos: >=0.6 is 83.5% right,
<0.6 is 43.8% (catalogue: 95.7% vs 80.0%), which supports
`TYPE_CONFIDENCE_THRESHOLD = 0.6`.

### Detector, all 11 classes — merged_dataset valid split (145 photos)

Parts are found well; whole-sofa classes are not, which is why the separate
type classifier decides the type.

| Class | Box AP50 | | Class | Box AP50 |
|---|---:|---|---|---:|
| back_cushion | 0.938 | | one-seater | 0.451 |
| base | 0.888 | | two-seater | 0.737 |
| left_arm | 0.899 | | stallion-sofa1 | 0.647 |
| legs | 0.817 | | stallion-sofa2 | 0.665 |
| right_arm | 0.889 | | stallion-sofa | 0.307 (recall 12%) |
| seat_cushion | 0.972 | | **All 11** | **0.746** |

### Sofa present

The detector found a sofa in all 1,582 dataset photos. Its rate of false
alarms on photos *without* a sofa has not been measured.

### Sofa parts — detector, 144 labelled photos (`eval_model.py`, conf 0.25)

| Part | Box mAP50 |
|---|---:|
| back_cushion | 0.941 |
| base | 0.888 |
| left_arm | 0.898 |
| legs | 0.823 |
| right_arm | 0.890 |
| seat_cushion | 0.972 |
| **All parts** | **0.902** |

These photos come from the part-labelled set in
github.com/Rashmiyr14/Sofa_Project_Model_Training; the detector may have seen
some of them in training, so treat this as an upper bound.

### Caveats

- Catalogue 3-seater has only 9 test photos — one mistake moves its score by 11 points.
- 4-seater has 22 room test photos and no catalogue ones; treat its score as rough.
- Room photos come from web image search (see below) and were reviewed by
  Claude in a first pass from contact sheets; a human spot-check is still
  pending. Many are retailer staging shots, cleaner than a customer's phone photo.
- v1 misread the Stallion room photo `data/inputs/images/test_sofa.jpg` as a
  2-seater (which is why the Stallion override once existed); v2 reads it as a
  3-seater (0.85). The same photo with its background removed
  (`test_sofa_nobg.jpg`) is read as a 2-seater.
- Near-duplicate photos (same sofa, different angle) are not removed, so some
  may be split across train and test.
- The detector was trained on the same one-seater / two-seater source photos
  that feed the type test split, so its 1-seater and 2-seater scores above are
  partly on photos it has seen. The classifier's test photos are clean.

## Real-world check (room photos)

Catalogue scores overstate real-world accuracy. v1, trained on catalogue shots
only, scored 44.7% on 264 held-out room photos and 40% on 15 openly licensed
room photos (`data/datasets/collected/reviewed/`), calling most sofas 2-seaters.

Responses:
- v2 adds 878 reviewed room photos (60% train / 10% val / 30% held-out test):
  81.1% on the held-out room photos.
- `TYPE_CONFIDENCE_THRESHOLD = 0.6` in `sofa_validator.py`: below it no
  mismatch is flagged.
- The results page words a mismatch as a suggestion to double-check, not a
  correction — the selected type is what is priced.
- `augment_type_dataset.py` pastes the white-background training sofas onto
  synthetic rooms; `train_type_classifier.py --extra-train` uses them.

```
python eval_sofa_types.py --dir ../data/datasets/collected/reviewed
```

## Collecting more photos

`collect_openverse_photos.py` searches Openverse for CC0 / public-domain /
CC BY photos only (retailer sites are not scraped: terms of use and
copyright), downloads ~600px copies, drops near-duplicates and records
licence and source in `data/datasets/collected/manifest.csv`.

Yield is low: of 185 candidates from the first run only 15 were a single,
clearly countable sofa (0 four-seaters, 0 L-shapes). Open photo libraries
are not a substitute for photographing real sofas (showroom, factory floor,
customers' rooms with permission).

Review workflow: record a verdict per file in
`data/datasets/collected/review.csv` (`file, verdict, reviewer_note`;
verdict is a type like `2_seater` or `reject`), then

```
python collect_openverse_photos.py --apply-review   # -> collected/reviewed/<type>/ + CREDITS.csv
```

CC BY photos require attribution if they are ever published.

### Web image search (`collect_web_photos.py`)

Because Openverse yields so few usable photos, the v2 room photos come from web
image search (DuckDuckGo, via the `ddgs` package; `icrawler`'s Google and Bing
parsers no longer work). **These photos are not openly licensed** — most are
retailer or manufacturer images. The decision to use them for training was
made by the project owner (2026-10-07). Every file's image URL and source page
are in `data/datasets/collected/web/manifest.csv`, so any photo can be traced
and removed. Do not publish or redistribute them.

The collector drops exact and near-duplicates, including copies of anything in
`raw/` and the Openverse set, so a web photo can't leak a test photo into training.
The search query only guesses the type: of 1,461 candidates, 878 were accepted
on review (1-seater 279, 2-seater 238, 3-seater 124, 4-seater 75, L-shape 162).
Many listings titled "3 seater" or "4 seater" show fewer seat cushions; those
were relabelled or rejected.

```
python collect_web_photos.py --only 3_seater --per-query 100   # -> collected/web/candidates/<type>/
python collect_web_photos.py --suggest        # pre-fills review.csv with the live models' opinion
# fill in the verdict column of collected/web/review.csv (type or "reject")
python collect_web_photos.py --apply-review   # -> collected/web/reviewed/<type>/
python prepare_type_dataset_rooms.py          # then retrain as above
```

## Known environment constraint

`requirements.txt` pins `numpy==2.3.5`: numpy 2.4+ removed `np.trapz`, which
ultralytics 8.3.47 calls during segmentation validation. Keep it below 2.4
until ultralytics is upgraded.

## GPU training (RTX 4060 laptop, Windows)

- The venv needs a CUDA build of PyTorch: `pip install --force-reinstall --no-deps
  torch==2.13.0+cu130 torchvision==0.28.0+cu130 --index-url https://download.pytorch.org/whl/cu130`
  (the cu128 index stops at 2.11; `pip install -r requirements.txt` can put the
  CPU build back). Pass `--device 0` to the training scripts.
- Any custom script that calls `YOLO(...).train()` needs an
  `if __name__ == "__main__":` guard, or Windows dataloader workers re-run the
  script and training hangs.
- `yolov8s-cls` at 320px crashes with "CUDA error: out of memory" at the first
  optimizer step even at batch 32 (~1.5 GB in use), and the dataloader then
  hangs instead of exiting. Unresolved; `yolov8n-cls` at 224px trains fine.
