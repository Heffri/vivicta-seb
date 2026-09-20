"""One-slide PowerPoint export of an Extraction (docs/API.md). Generic, not debt-specific:
a bar chart when the fields look like maturity buckets ('due_*' keys), a table otherwise.
"""
import io

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches, Pt

BUCKET_ORDER = ["due_within_1_year", "due_1_to_5_years", "due_after_5_years"]
BUCKET_LABELS = {"due_within_1_year": "Within 1 year", "due_1_to_5_years": "1–5 years", "due_after_5_years": "> 5 years"}


def build_pptx(x: dict) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)  # 16:9
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    title = f"{x['company'] or 'Unknown company'} — {x.get('section', '').replace('_', ' ').title()}"
    sub = f"FY {x['fiscal_year'] or '—'} · {x['currency'] or ''}"
    missing = sum(f["value"] is None for f in x["fields"])
    if missing:
        sub += f" · Incomplete: {missing} {'field' if missing == 1 else 'fields'} unavailable"
    if x.get("stale"):
        sub += " · Saved result is outdated"
    _textbox(slide, title, Pt(28), bold=True, top=Inches(0.4))
    _textbox(slide, sub, Pt(14), top=Inches(0.95), color=(100, 100, 100))

    by_key = {f["key"]: f for f in x["fields"]}
    buckets = [k for k in BUCKET_ORDER if k in by_key and by_key[k]["value"] is not None]

    if len(buckets) == len(BUCKET_ORDER) and all(c["passed"] for c in x.get("checks", [])):
        _debt_chart(slide, by_key, buckets)
    else:
        _table(slide, x["fields"])

    notes = [x.get("debt_scope") or "", *x.get("warnings", [])]
    for f in x["fields"]:
        if f.get("calculation"):
            notes.append(f"{f['label']}: {f['calculation']}")
        sources = [c["source"] for c in f.get("components", [])] or [f.get("source")]
        notes.extend(f"{f['label']}, PDF page {s['page']}: {s['quote']}" for s in sources if s)
    slide.notes_slide.notes_text_frame.text = "\n\n".join(n for n in notes if n)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _debt_chart(slide, by_key, buckets):
    total = by_key.get("total_debt", {}).get("value")
    unit = next((by_key[k]["unit"] for k in buckets if by_key[k].get("unit")), "")
    if total is not None:
        _textbox(slide, f"Total debt: {total:,.0f} {unit}".replace(",", " "), Pt(20), bold=True, top=Inches(1.5))

    data = CategoryChartData()
    data.categories = [BUCKET_LABELS[k] for k in buckets]
    data.add_series("Debt due", [by_key[k]["value"] for k in buckets])
    frame = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1.2), Inches(2.2), Inches(10.9), Inches(4.6), data)
    chart = frame.chart
    chart.has_legend = False
    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.number_format = "#,##0"
    plot.data_labels.number_format_is_linked = False
    chart.value_axis.has_title = True
    chart.value_axis.axis_title.text_frame.text = unit or ""
    # python-pptx's template emits signed IDs; OOXML axis IDs are unsigned integers.
    # Keep both definitions and cross-references consistent for strict importers.
    for element in chart._chartSpace.xpath(".//c:axId | .//c:crossAx"):
        element.set("val", str(int(element.get("val")) % (1 << 32)))


def _table(slide, fields):
    rows = fields
    shape = slide.shapes.add_table(len(rows) + 1, 3, Inches(1.2), Inches(1.8), Inches(10.9), Inches(0.4 * (len(rows) + 1)))
    table = shape.table
    for c, h in enumerate(["Field", "Value", "Unit"]):
        table.cell(0, c).text = h
    for r, f in enumerate(rows, start=1):
        v = f["value"]
        table.cell(r, 0).text = f["label"]
        table.cell(r, 1).text = "Not available" if v is None else f"{v:,.6f}".rstrip("0").rstrip(".").replace(",", " ") if isinstance(v, (int, float)) else str(v)
        table.cell(r, 2).text = f["unit"] or ""


def _textbox(slide, text, size, bold=False, top=Inches(0.4), color=None):
    box = slide.shapes.add_textbox(Inches(0.6), top, Inches(12), Inches(0.6))
    p = box.text_frame.paragraphs[0]
    run = p.add_run()
    run.text = text
    run.font.size = size
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    return box
