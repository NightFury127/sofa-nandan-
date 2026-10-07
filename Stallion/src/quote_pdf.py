"""
quote_pdf.py — Build a branded A4 quotation PDF from a saved quote.

Input:  outputs/requests/<request_id>/response.json (written by api.py) plus
        the files next to it (customer photo, CAD drawing).
Output: PDF bytes.

Uses fpdf2's core fonts (Latin-1 only), so amounts are written as "INR"
rather than with the rupee sign.
"""

import io
import json
import os
from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).parent.resolve().parent
LOGO_PATH    = PROJECT_ROOT / "frontend" / "assets" / "svce-logo.png"

INK, MUTED, LINE, ACCENT = (16, 16, 15), (110, 106, 98), (210, 206, 198), (150, 128, 80)

TYPE_LABELS = {
    "1_seater": "1-seater / armchair", "2_seater": "2-seater", "3_seater": "3-seater",
    "4_seater_plus": "4-seater", "l_shape": "L-shape / sectional",
}
COST_ROWS = [
    ("Materials", "material_cost"), ("Labour", "labor_cost"), ("Finishing", "finishing_cost"),
    ("Subtotal", "subtotal"), ("Overhead", "overhead"), ("Profit", "profit"),
]

# Shown under the total. The rates in data/pricing/pricing.json are still
# placeholders, so by default the PDF says the price is indicative.
DEFAULT_NOTE = ("Indicative quotation. Prices are exclusive of GST. Quantities include a cutting allowance. "
                "Final price is subject to confirmation of materials and finish.")


def inr(value) -> str:
    """Indian digit grouping: 123456.5 -> '1,23,456.50'."""
    neg, value = value < 0, abs(float(value))
    whole, frac = f"{value:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{'-' if neg else ''}{whole}.{frac}"


def _mm(value) -> str:
    """2100.0 -> '2100'; missing -> '-'."""
    return "-" if value is None else f"{float(value):g}"


def _dark_logo() -> io.BytesIO:
    """The SVCE logo is white-on-black; invert it to black-on-white for paper."""
    img = Image.open(LOGO_PATH).convert("RGB")
    buf = io.BytesIO()
    ImageOps.invert(img).save(buf, format="PNG")
    buf.seek(0)
    return buf


def _image_fit(pdf, path: Path, x, y, max_w, max_h) -> bool:
    """Place an image inside a box, keeping its aspect ratio. False if unreadable."""
    try:
        # Opened with Pillow so any upload format works (WEBP isn't read by fpdf2 itself)
        with Image.open(path) as im:
            img = im.convert("RGB")
        w, h = img.size
        scale = min(max_w / w, max_h / h)
        pdf.image(img, x=x, y=y, w=w * scale, h=h * scale)
        return True
    except Exception:
        return False


def _find_photo(folder: Path):
    for name in ("original_image", "uploaded_image"):
        for p in sorted(folder.glob(f"{name}.*")):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                return p
    return None


def build_quote_pdf(request_folder: Path) -> bytes:
    data = json.loads((request_folder / "response.json").read_text(encoding="utf-8"))
    q    = data.get("quote") or {}
    dims = data.get("dimensions_mm") or {}
    created = data.get("created_at")
    date_txt = datetime.fromisoformat(created).strftime("%d %b %Y") if created else datetime.now().strftime("%d %b %Y")

    pdf = FPDF(format="A4")
    # Paint the paper white. Without it the page is transparent, and viewers in
    # dark mode show near-black text on a dark page.
    pdf.set_page_background((255, 255, 255))
    pdf.set_auto_page_break(auto=True, margin=13)
    pdf.set_margins(16, 14, 16)
    pdf.add_page()
    page_w = pdf.w - pdf.l_margin - pdf.r_margin

    # ── Header ────────────────────────────────────────────────────────────────
    pdf.image(_dark_logo(), x=pdf.l_margin, y=10, h=18)
    pdf.set_xy(pdf.l_margin, 12)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*INK)
    pdf.cell(page_w, 7, "STALLION", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(page_w, 5, "FURNITURE ENGINEERING / SOFA QUOTATION", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(32)
    pdf.set_draw_color(*INK)
    pdf.line(pdf.l_margin, 32, pdf.l_margin + page_w, 32)

    # ── Quote details ─────────────────────────────────────────────────────────
    pdf.set_y(37)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*INK)
    pdf.cell(page_w, 9, "Quotation", new_x="LMARGIN", new_y="NEXT")
    details = [
        ("Quote no.", data.get("request_id", "-")),
        ("Date", date_txt),
        ("Customer", data.get("customer_name") or "-"),
        ("Sofa type", TYPE_LABELS.get(data.get("sofa_type"), data.get("sofa_type") or "-")),
        ("Dimensions", f"{_mm(dims.get('length'))} W  x  {_mm(dims.get('width'))} D  x  {_mm(dims.get('height'))} H mm"),
    ]
    if q.get("fabric_grade_label"):
        details.append(("Materials", f"{q['fabric_grade_label']}  /  {q.get('foam_grade_label', '')}"))
    pdf.ln(1)
    for label, value in details:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*MUTED)
        pdf.cell(30, 6, label.upper())
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*INK)
        pdf.cell(page_w - 30, 6, str(value), new_x="LMARGIN", new_y="NEXT")

    # ── Photo + drawing ───────────────────────────────────────────────────────
    y = pdf.get_y() + 4
    box_w, box_h = (page_w - 6) / 2, 48
    photo = _find_photo(request_folder)
    drawing = None
    if data.get("cad_preview_url"):
        cand = request_folder / Path(data["cad_preview_url"]).name
        drawing = cand if cand.exists() else None
    for i, (path, caption) in enumerate([(photo, "REFERENCE PHOTO"), (drawing, "TECHNICAL DRAWING")]):
        x = pdf.l_margin + i * (box_w + 6)
        pdf.set_draw_color(*LINE)
        pdf.rect(x, y, box_w, box_h)
        shown = bool(path) and _image_fit(pdf, path, x + 2, y + 2, box_w - 4, box_h - 9)
        pdf.set_xy(x + 2, y + box_h - 6)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*MUTED)
        pdf.cell(box_w - 4, 5, caption if shown else f"{caption} - NOT AVAILABLE")
    pdf.set_y(y + box_h + 6)

    # ── Bill of materials ─────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*INK)
    pdf.cell(page_w, 7, "Bill of materials", new_x="LMARGIN", new_y="NEXT")
    cols = [("Component", 0.34, "L"), ("Quantity", 0.16, "R"), ("Unit", 0.16, "L"),
            ("Rate (INR)", 0.16, "R"), ("Amount (INR)", 0.18, "R")]
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.set_draw_color(*INK)
    for name, frac, align in cols:
        pdf.cell(page_w * frac, 6, name.upper(), border="B", align=align)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*INK)
    pdf.set_draw_color(*LINE)
    for row in data.get("bom") or []:
        values = [row.get("component", ""), f"{float(row.get('qty', 0)):g}", row.get("unit") or "",
                  inr(row.get("unit_cost", 0)), inr(row.get("total_cost", 0))]
        for (name, frac, align), value in zip(cols, values):
            pdf.cell(page_w * frac, 6.5, str(value), border="B", align=align)
        pdf.ln()

    # ── Totals ────────────────────────────────────────────────────────────────
    pdf.ln(4)
    label_w, value_w = page_w * 0.75, page_w * 0.25
    pdf.set_font("Helvetica", "", 9)
    for label, key in COST_ROWS:
        if key not in q:
            continue
        pdf.set_text_color(*MUTED)
        pdf.cell(label_w, 6, label, align="R")
        pdf.set_text_color(*INK)
        pdf.cell(value_w, 6, inr(q[key]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*INK)
    pdf.line(pdf.l_margin + page_w * 0.55, pdf.get_y() + 1, pdf.l_margin + page_w, pdf.get_y() + 1)
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(label_w, 9, "Total (INR, excl. GST)", align="R")
    pdf.set_text_color(*ACCENT)
    pdf.cell(value_w, 9, inr(q.get("final_quotation_price", 0)), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(page_w, 4, os.environ.get("STALLION_PDF_NOTE", DEFAULT_NOTE), align="R")

    # ── Footer (auto page break off, or writing near the bottom adds a page) ──
    pdf.set_auto_page_break(auto=False)
    pdf.set_y(-13)
    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(page_w, 7, "Generated by Stallion - Sri Venkateshwara College of Engineering, Bengaluru")

    return bytes(pdf.output())
