# Cost estimation: how quotes are priced, and where every number comes from

Last updated: 2026-10-07. Rates are researched Bengaluru / Indian market rates,
**not supplier quotes**. Replace them with the factory's real figures in the
web app (Staff → Rates) as soon as they are known; the structure stays the same.

## The method

1. **Quantities from geometry** (`src/bom_geometry.py`). The sofa's width, depth
   and height plus a fixed construction spec give each material's net quantity,
   the way a factory estimator works: frame members × section → timber volume,
   cushion volume × density → foam kg, upholstered panel area ÷ roll width →
   fabric metres, seat width ÷ spring pitch → spring count.
2. **Rates and wastage** (`data/pricing/pricing.json`). Order quantity = net ×
   (1 + wastage %); cost = order quantity × rate × grade multiplier.
3. **Labour and finishing** per sofa type (man-days × daily wage, see below).
4. **Factory price** = (materials + labour + finishing) + overhead 15% + profit 18%.
   Excludes GST.
5. **Retail equivalent** = factory price + dealer markup 40% + GST 18% — an
   estimate of what a showroom would charge for the same sofa.

## Assumed construction (mid-range Bengaluru build)

Stallion's actual build is not confirmed, so the spec below is the most common
mid-range construction. Change `CONSTRUCTION` in `bom_geometry.py` to match the
factory.

| Part | Assumption |
|---|---|
| Frame | Kiln-dried sal hardwood, 75 × 50 mm (3″ × 2″) members: base box, seat cross-rails per seat, back frame, arm frames |
| Panels | 12 mm commercial MR plywood on both arm faces, the back and the front base board |
| Seat | Zig-zag springs at 125 mm pitch, 150 mm (6″) 40-density PU foam cushions |
| Back | Elastic webbing rows at 100 mm, 100 mm 32-density cushions |
| Padding | 25 mm 28-density foam on arms and outer back |
| Cover | 54″ fabric (1.32 m usable), +20% for seams, boxing and cutting layout |
| Legs | 4, plus 2 centre legs on runs ≥ 2 m |
| Arms / seat | 150 mm arms, seat height 430 mm, legs 120 mm |

Check against industry rules of thumb (standard 2100 × 900 × 850 mm 3-seater):
**10.5 m** of fabric net (~11.5 m ordered) — Indian makers use ~10–12 m and US
yardage charts give 14–17 m for a fully skirted 84″ sofa; **12 kg** of foam;
**3.3 cft** of timber ordered.

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
| Springs | ₹22 / strip | Zig-zag spring ₹85–120/kg ([IndiaMART](https://m.indiamart.com/bnmagencies/zig-zag-spring.html)); ~0.2 kg per strip incl. clips |
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
| 1-seater | 850 × 850 × 850 | ₹8,956 | ₹16,903 | ₹27,923 |
| 2-seater | 1550 × 900 × 850 | ₹13,661 | ₹26,205 | ₹43,291 |
| 3-seater | 2100 × 900 × 850 | ₹17,679 | ₹34,575 | ₹57,118 |
| 4-seater | 2700 × 950 × 850 | ₹22,182 | ₹43,535 | ₹71,920 |
| L-shape | 2700 × 975 × 850 | ₹25,463 | ₹50,838 | ₹83,984 |

Market, 3-seater fabric sofas (Oct 2026, incl. GST): Urban Ladder sells at
₹30,999–69,999, most ₹38,999–49,999 (MRPs ₹58,499–95,999), e.g. Moreno solid
wood ₹41,999 ([Urban Ladder](https://www.urbanladder.com/collection/fabric-sofas));
Wakefit Lounger (solid wood, 32D foam) ₹27,585; Pepperfry from ~₹20,000.

The 3-seater retail equivalent (₹57,118) sits inside the market range, toward
the top. That fits the assumed spec (sal frame, 6″ 40D seat) being above budget
online brands, which use pine/rubberwood and 32D foam and sell direct without a
dealer. Only the 3-seater was checked against listings; the other types follow
the same method.

## Accuracy and what would improve it

- Material quantities: geometry-based, checked against fabric and foam rules of
  thumb. Good for comparing sizes and types.
- Rates: researched market ranges, typically ±20%. Supplier quotes for the four
  biggest items — **timber, fabric, foam and labour** (≈ 80% of the cost) — are
  the most valuable next step.
- The construction spec is assumed. Measuring one real Stallion sofa (member
  sizes, foam thickness, fabric metres used) and updating `CONSTRUCTION` would
  calibrate every quote.
- The previous method (fixed quantities per type from
  `master_template_spec.csv`, scaled by size ratios) is kept as
  `SofaCostEngine.generate_template_scaled_bom` for reference only.
