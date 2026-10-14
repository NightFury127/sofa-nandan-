# Cost estimation: how quotes are priced, and where every number comes from

Last updated: 2026-10-14. Rates are researched Bengaluru / Indian market rates,
**not supplier quotes**. Replace them with the factory's real figures in the
web app (Staff → Rates) as soon as they are known; the structure stays the same.

## The method

1. **Quantities measured off the built sofa** (`src/sofa_build.py`,
   `src/bom_geometry.py`). The sofa is built part by part at the requested size,
   following the industry reference model (below), and every quantity is taken
   off those parts the way a factory estimator takes off a drawing: volume of
   every frame member → timber cft, plywood area, foam volume × density → kg,
   upholstered area ÷ roll width → fabric metres, springs and belts counted.
   The 3D model on the results page is built from the same parts.
2. **Rates and wastage** (`data/pricing/pricing.json`). Order quantity = net ×
   (1 + wastage %); cost = order quantity × rate × grade multiplier.
3. **Labour and finishing** per sofa type (man-days × daily wage, see below).
4. **Factory price** = (materials + labour + finishing) + overhead 15% + profit 18%.
   Excludes GST.
5. **Retail equivalent** = factory price + dealer markup 40% + GST 18% — an
   estimate of what a showroom would charge for the same sofa.

## Construction: the industry reference model

The build follows **"Sofa Internal Structure.f3z"**, a Fusion 360 model of a
3-seater (2061 × 837 mm, 693 mm above its legs). `src/reference_cad.py` reads
its 437 bodies straight from the archive (133 distinct solids once pasted
duplicates are dropped; catalogue in `data/reference/reference_parts.json`), and
`src/sofa_build.py` rebuilds every part at any size, citing the body each
measurement came from. A test checks that the rebuilt 3-seater at the
reference size puts 34 key parts within 10 mm of the reference.

| Part | Reference construction |
|---|---|
| Seat frame | Rails across the seat span: front seat rail 65 × 25, rear seat rail 65 × 25, bottom rails 25 × 40; side rails 40 × 25 inside each end |
| Centre support | Per 850 mm of span: bottom stretcher, seat post, front post, back post, stile block (65 × 25 / 25 × 65) |
| Back | Raked about 14°: 40 mm stiles at each end and support, back top rail 25 × 65, 12 mm ply top cap |
| Side panels | 12 mm ply, full depth to the seat deck and rising at the back along the rake |
| Arms | 203 mm frame: 12 mm ply end boards, rails 25 × 45 / 25 × 65 / 45 × 25, sloped top slats, spacers; arm top foam rising outward to a roll at 413 mm |
| Seat suspension | Sinuous springs, 4 mm wire, 127 mm pitch (11 on a 3-seater), a clip at each end; two 70 mm seat belts |
| Back suspension | Vertical belts at 107 mm along the rake, plus two cross belts |
| Seat | Tight seat (no loose cushions): 51 mm foam slab + 50 mm layer, front padding 25 mm |
| Back | Raked back foam about 80 mm thick |
| Cover | 54″ fabric (1.32 m usable), +20% for seams and cutting layout |

How it is fitted to other sizes: timber and ply sections and foam sheet
thicknesses never scale; lengths and positions follow the sofa's length,
depth and height; springs, back belts and centre supports are re-spaced at the
reference pitch; arms keep their 230 mm width unless the sofa is too narrow
for 520 mm of seat per person.

**Not in the reference, so still assumed:** the timber species and foam
densities (sal; 40D seat, 32D back, 28D padding), the legs (none in the model;
we use 120 mm, 4 plus 2 centre legs on runs ≥ 2 m), the second 50 mm seat
layer (the reference leaves that gap under its seat fabric empty), the rear
seat rail (the reference has the springs' rear clips but no rail), details the
reference draws on one side only (mirrored), and the L-shape chaise (built
from the same seat construction, without a back).

Standard 2100 × 900 × 850 mm 3-seater: **1.4 cft** of timber net (45 members),
**1.0 m²** of 12 mm ply, **6.4 kg** of foam, **8.5 m** of fabric net (a tight
seat uses less than the 10–12 m of a loose-cushion sofa), 11 springs, 22 clips,
11.8 m of belts.

## Rates (pricing.json) and sources

| Item | Rate | Basis |
|---|---|---|
| Wood frame (sal) | ₹1,850 / cft, 20% wastage | Bengaluru sal ₹1,200–1,851/cft, Sep 2026 ([IndiaMART Bengaluru sal](https://dir.indiamart.com/bengaluru/sal-wood.html)). Sheesham is ~₹6,500/cft; pine ~₹600/cft |
| Plywood 12 mm MR | ₹750 / m² (₹70/sq ft), 12% wastage | National ₹55–70/sq ft mid-range; Bengaluru ₹70–110/sq ft ([Apple Ply 2026](https://www.appleply.in/blog/plywood-price-list-2026-complete-guide), [Apple Ply Bangalore](https://www.appleply.in/blog/plywood-price-bangalore-2026)) |
| Seat foam 40D | ₹265 / kg | 40-density PU ₹230–265/kg ([IndiaMART HD PU foam](https://dir.indiamart.com/impcat/high-density-pu-foam.html)) |
| Back foam 32D | ₹230 / kg | 32-density ₹200–350/kg (same source) |
| Padding foam 28D | ₹200 / kg | 23–50 density ₹190–290/kg ([TradeIndia sofa foam](https://www.tradeindia.com/manufacturers/sofa-foam.html)) |
| Fabric, standard | ₹300 / m, 10% wastage | Chenille/polyester sofa fabric ₹175–300/m wholesale, ~₹350 retail ([TradeIndia upholstery fabric](https://www.tradeindia.com/manufacturers/furniture-upholstery-fabric.html), [IndiaMART sofa fabric](https://dir.indiamart.com/impcat/sofa-fabric.html)) |
| Fabric, premium | × 2.0 (~₹600 / m) | Velvet / designer upholstery |
| Springs | ₹22 / strip | Sinuous (zig-zag) spring ₹85–120/kg ([IndiaMART](https://m.indiamart.com/bnmagencies/zig-zag-spring.html)); a 4 mm strip (~1.4 m of wire on a 3-seater) with its 2 clips is ~0.2 kg |
| Adhesive | ₹260 / kg | Fevicol 998 FW ₹248–251/kg in 5 kg tins |
| Fibre wrap | ₹35 / m² | **Assumption** |
| Elastic webbing | ₹15 / m | **Assumption** (elastic tape ~₹250/roll) |
| Legs | ₹180 / piece | **Assumption** (turned wood / metal) |
| Sundries | ₹300 / seat | **Assumption**: staples, thread, clips, screws, dust cover |
| Foam grade "high-resilience" | × 1.25 | **Assumption** |

### Labour and finishing

Labour = (1 + 1.75 × seats) man-days × ₹1,100/day — carpentry, cutting/stitching
and upholstery. ₹1,100/day is a skilled Bengaluru furniture-worker wage
(national ₹650–1,200/day, metros 20–60% higher; furniture carpenters
₹25,000–35,000/month). The man-days per seat are an **assumption**; time one
real sofa through the workshop to confirm.

| Type | Labour | Finishing (QC, cleaning, packing) |
|---|---:|---:|
| 1-seater | ₹3,000 | ₹500 |
| 2-seater | ₹4,950 | ₹700 |
| 3-seater | ₹6,900 | ₹900 |
| 4-seater | ₹8,800 | ₹1,100 |
| L-shape | ₹10,700 | ₹1,300 |

### Margins and tax

- Overhead 15% (rent, power, supervision, tools, local delivery), profit 18%.
- Dealer markup 40% on the factory price ≈ 28.6% showroom margin; Indian
  furniture showrooms run 25–30% margins, some formats 40–60%
  ([Accountune](https://accountune.com/how-to-start-a-furniture-shop-in-india)).
- GST 18% — upholstered wooden-frame seats, HSN 9401 61 00, unchanged by the
  Sep 2025 GST 2.0 revision ([TaxGamma](https://www.taxgamma.com/gst-rates/gst-on-furniture.html)).

## Results and market check

Standard sizes, standard fabric and foam:

| Type | Size (mm) | Materials | Factory price | Retail equivalent incl. GST |
|---|---|---:|---:|---:|
| 1-seater | 850 × 850 × 850 | ₹5,660 | ₹12,430 | ₹20,534 |
| 2-seater | 1550 × 900 × 850 | ₹8,730 | ₹19,513 | ₹32,236 |
| 3-seater | 2100 × 900 × 850 | ₹11,245 | ₹25,845 | ₹42,695 |
| 4-seater | 2700 × 950 × 850 | ₹14,258 | ₹32,782 | ₹54,156 |
| L-shape | 2700 × 975 × 850 | ₹16,609 | ₹38,823 | ₹64,135 |

(Until 2026-10-14 quotes used an assumed 75 × 50 mm sal frame with loose 6″
cushions and zig-zag springs: the same 3-seater came to ₹34,575 factory /
₹57,118 retail.)

Market, 3-seater fabric sofas (Oct 2026, incl. GST): Urban Ladder sells at
₹30,999–69,999, most ₹38,999–49,999 (MRPs ₹58,499–95,999), e.g. Moreno solid
wood ₹41,999 ([Urban Ladder](https://www.urbanladder.com/collection/fabric-sofas));
Wakefit Lounger (solid wood, 32D foam) ₹27,585; Pepperfry from ~₹20,000.

The 3-seater retail equivalent (₹42,695) sits in the middle of the market
range, within Urban Ladder's most common band. The reference build is lighter
than a loose-cushion sofa (slimmer timber sections, a tight seat), which brings
it below the old estimate. Only the 3-seater was checked against listings; the
other types follow the same method.

## Accuracy and what would improve it

- Material quantities: measured off a part-by-part build of the industry
  reference model, checked against the reference at its own size. Good for
  comparing sizes and types.
- Rates: researched market ranges, typically ±20%. Supplier quotes for the four
  biggest items — **timber, fabric, foam and labour** (≈ 80% of the cost) — are
  the most valuable next step.
- The construction is the industry reference, not yet confirmed as
  Stallion's own build. Checking one real Stallion sofa against it (member
  sizes, foam thickness and density, fabric metres used) and updating the
  measurements in `sofa_build.py` would calibrate every quote.
- The previous method (fixed quantities per type from
  `master_template_spec.csv`, scaled by size ratios) is kept as
  `SofaCostEngine.generate_template_scaled_bom` for reference only.
