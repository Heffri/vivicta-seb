"""One-slide PowerPoint export of an Extraction (docs/API.md). Generic, not debt-specific:
a bar chart when the fields look like maturity buckets ('due_*' keys), a table otherwise.
"""
import io
import json

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Inches, Pt

BUCKET_ORDER = ["due_within_1_year", "due_1_to_5_years", "due_after_5_years"]
BUCKET_LABELS = {"due_within_1_year": "< 1 year", "due_1_to_5_years": "1–5 years", "due_after_5_years": "> 5 years"}


def build_pptx(x: dict, prior_year: bool = False, per_year: bool = False) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)  # 16:9
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    title = f"{x['company'] or 'Unknown company'} — {x.get('section', '').replace('_', ' ').title()}"
    sub = f"FY {x['fiscal_year'] or '—'} · {x['currency'] or ''}"
    _textbox(slide, title, Pt(28), bold=True, top=Inches(0.4))
    _textbox(slide, sub, Pt(14), top=Inches(0.95), color=(100, 100, 100))

    by_key = {f["key"]: f for f in x["fields"]}
    buckets = [k for k in BUCKET_ORDER if k in by_key and by_key[k]["value"] is not None]

    basis = (x.get("basis") or {}).get("values", {})
    status = "Ready for analyst use" if x.get("ready") else "Draft - unresolved items"
    _textbox(slide, status, Pt(16), bold=True, top=Inches(1.35), color=(30, 100, 60) if x.get("ready") else (160, 70, 20))
    summary = " | ".join(str(basis.get(k) or "Unknown " + k) for k in ("entity", "consolidation", "currency", "scale"))
    _textbox(slide, summary[:160], Pt(12), top=Inches(1.75))
    if buckets:
        debt_basis = f"{basis.get('debt_basis') or 'Debt basis unknown'} | Leases: {basis.get('leases') or 'unknown'}"
        _textbox(slide, debt_basis, Pt(12), top=Inches(2.05))
        # v091: the prior year rides along only when the caller asked for it (?prior_year=1) and the
        # extraction carries it; anything else renders exactly as before.
        # v109: ?per_year=1 swaps the three-bucket series for the report's own calendar-year columns
        # when the extraction carries them -- same total, the report's own granularity (a year series
        # and a bucket series on one chart would answer two different questions, so per_year wins and
        # the prior series steps aside). Without the flag or without buckets_by_year: exactly as before.
        _debt_chart(slide, by_key, buckets, x.get("prior_year") if prior_year else None,
                    x.get("buckets_by_year") if per_year else None)
    else:
        _table(slide, x["fields"])

    comparison = x.get("comparison") or {}
    period = f"Comparison: {comparison.get('previous_year')} to {comparison.get('current_year')} | " if comparison else ""
    unresolved = x.get("issues", [])
    counts = {kind: sum(i["kind"] == kind for i in unresolved) for kind in ("field", "basis", "check")}
    _textbox(slide, period + (f"Unresolved: {counts['field']} figures, {counts['basis']} definitions, {counts['check']} calculations. " if unresolved else "") + "Full sources and review history in speaker notes.", Pt(11), top=Inches(6.9))
    slide.notes_slide.notes_text_frame.text = json.dumps(x, ensure_ascii=False, indent=2)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _debt_chart(slide, by_key, buckets, prior=None, by_year=None):
    total = by_key.get("total_debt", {}).get("value")
    unit = next((by_key[k]["unit"] for k in buckets if by_key[k].get("unit")), "")
    if total is not None:
        _textbox(slide, "Total debt: " + f"{total:,.6f}".rstrip("0").rstrip(".").replace(",", " ") + " " + unit, Pt(20), bold=True, top=Inches(2.4))

    data = CategoryChartData()
    if by_year:  # v109: the report's own calendar-year columns as the categories, one series of the same "Debt due"
        data.categories = [y["label"] for y in by_year["years"]]
        data.add_series("Debt due", [y["value"] for y in by_year["years"]])
    else:
        data.categories = [BUCKET_LABELS[k] for k in buckets]
        data.add_series("Debt due", [by_key[k]["value"] for k in buckets])
        if prior:  # v091: a second, fainter series beside each bucket, named for its own fiscal year
            data.add_series(f"FY{prior.get('fiscal_year')}", [prior.get("fields", {}).get(k, {}).get("value") for k in buckets])
    frame = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1.2), Inches(2.95), Inches(10.9), Inches(3.7), data)
    chart = frame.chart
    chart.has_legend = bool(prior and not by_year)  # one series needs no legend; two are told apart by theirs
    if prior and not by_year:  # v109: the year view has one series again -- no legend to place
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.number_format = "#,##0.######"
    plot.data_labels.number_format_is_linked = False
    chart.value_axis.has_title = True
    chart.value_axis.axis_title.text_frame.text = unit or ""


def _table(slide, fields):
    rows = fields
    shape = slide.shapes.add_table(len(rows) + 1, 3, Inches(1.2), Inches(2.2), Inches(10.9), Inches(4.45))
    table = shape.table
    for c, h in enumerate(["Field", "Value", "Unit"]):
        table.cell(0, c).text = h
    for r, f in enumerate(rows, start=1):
        v = f["value"]
        table.cell(r, 0).text = f["label"]
        table.cell(r, 1).text = f"{v:,.6f}".rstrip("0").rstrip(".").replace(",", " ") if isinstance(v, (int, float)) else str(v) if v is not None else "Unknown"
        table.cell(r, 2).text = f["unit"] or "Unknown"
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.size = Pt(14)
    table.columns[0].width = Inches(6.1)
    table.columns[1].width = Inches(2.4)
    table.columns[2].width = Inches(2.4)


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
