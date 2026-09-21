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
BUCKET_LABELS = {"due_within_1_year": "Within 1 year", "due_1_to_5_years": "1–5 years", "due_after_5_years": "> 5 years"}


def _presentation() -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)  # 16:9
    return prs


def _save(prs: Presentation) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def build_pptx(x: dict, prior_year: bool = False, per_year: bool = False) -> bytes:
    """Build the existing single-company export without changing its layout."""
    prs = _presentation()
    add_slide(prs, x, prior_year=prior_year, per_year=per_year)
    return _save(prs)


def add_slide(prs: Presentation, x: dict, prior_year: bool = False, per_year: bool = False):
    """Append the established one-company layout to a supplied presentation."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    title = f"{x['company'] or 'Unknown company'} — {x.get('section', '').replace('_', ' ').title()}"
    sub = f"FY {x['fiscal_year'] or '—'} · {x['currency'] or ''}"
    _textbox(slide, title, Pt(28), bold=True, top=Inches(0.4))
    if x.get("stale"):
        sub += " · Saved result predates current extraction settings"
    _textbox(slide, sub, Pt(14), top=Inches(0.95), color=(100, 100, 100))
    human_line = human_review_line(x)
    if human_line:
        _textbox(slide, human_line, Pt(10), top=Inches(1.25), color=(100, 100, 100))

    by_key = {f["key"]: f for f in x["fields"]}
    buckets = [k for k in BUCKET_ORDER if k in by_key and by_key[k]["value"] is not None]

    basis = (x.get("basis") or {}).get("values", {})
    status = "Ready for analyst use" if x.get("ready") else "Draft - unresolved items"
    offset = 0.3 if human_line else 0
    _textbox(slide, status, Pt(16), bold=True, top=Inches(1.35 + offset), color=(30, 100, 60) if x.get("ready") else (160, 70, 20))
    summary = " | ".join(str(basis.get(k) or "Unknown " + k) for k in ("entity", "consolidation", "currency", "scale"))
    _textbox(slide, summary[:160], Pt(12), top=Inches(1.75 + offset))
    if len(buckets) == 3 and all(c.get("passed") for c in x.get("checks", [])):
        debt_basis = f"{basis.get('debt_basis') or 'Debt basis unknown'} | Leases: {basis.get('leases') or 'unknown'}"
        _textbox(slide, debt_basis, Pt(12), top=Inches(2.05 + offset))
        # v091: the prior year rides along only when the caller asked for it (?prior_year=1) and the
        # extraction carries it; anything else renders exactly as before.
        # v109: ?per_year=1 swaps the three-bucket series for the report's own calendar-year columns
        # when the extraction carries them -- same total, the report's own granularity (a year series
        # and a bucket series on one chart would answer two different questions, so per_year wins and
        # the prior series steps aside). Without the flag or without buckets_by_year: exactly as before.
        _debt_chart(slide, by_key, buckets, x.get("prior_year") if prior_year else None,
                    x.get("buckets_by_year") if per_year else None, offset)
    else:
        _table(slide, x["fields"], offset)

    comparison = x.get("comparison") or {}
    period = f"Comparison: {comparison.get('previous_year')} to {comparison.get('current_year')} | " if comparison else ""
    unresolved = x.get("issues", [])
    counts = {kind: sum(i["kind"] == kind for i in unresolved) for kind in ("field", "basis", "check")}
    _textbox(slide, period + (f"Unresolved: {counts['field']} figures, {counts['basis']} definitions, {counts['check']} calculations. " if unresolved else "") + "Full sources and review history in speaker notes.", Pt(11), top=Inches(6.9))
    slide.notes_slide.notes_text_frame.text = json.dumps(x, ensure_ascii=False, indent=2)


def human_review_line(x: dict) -> str:
    """A visible pointer to a new analyst citation; the full history stays in notes/JSON."""
    for field in x.get("fields", []):
        review = field.get("human_review") or {}
        source = field.get("source") or {}
        if not review.get("source_verified") or not source.get("quote"):
            continue
        quote = " ".join(str(source["quote"]).split())
        if len(quote) > 110:
            quote = quote[:107].rstrip() + "…"
        components = field.get("components") or []
        return f"Human review: p.{source.get('page')} '{quote}'" + (f" — components {len(components)}" if components else "")
    return ""


def summary_row(x: dict) -> dict:
    """The deterministic maturity-wall row used on a whole-universe deck cover."""
    fields = {f["key"]: f for f in x.get("fields", [])}
    check = next((c for c in x.get("checks", []) if c.get("name") == "maturity_sums_to_total"), None)
    reviews = sorted({str((f.get("human_review") or {}).get("decision")) for f in fields.values()
                      if (f.get("human_review") or {}).get("decision")})
    return {
        "company": x.get("company") or x.get("stem") or "Unknown company",
        "total": fields.get("total_debt", {}).get("value"),
        "within_1_year": fields.get("due_within_1_year", {}).get("value"),
        "one_to_five_years": fields.get("due_1_to_5_years", {}).get("value"),
        "after_five_years": fields.get("due_after_5_years", {}).get("value"),
        "identity": "Pass" if check and check.get("passed") else "Needs review" if check else "Not checked",
        "review": ", ".join(reviews) if reviews else "Not reviewed",
    }


def build_deck(extractions: list[dict], summary: list[dict] | None = None) -> bytes:
    """Build one universe deck: a maturity-wall table followed by one established slide per company."""
    prs = _presentation()
    _summary_slide(prs, summary if summary is not None else [summary_row(x) for x in extractions])
    for x in extractions:
        add_slide(prs, x)
    return _save(prs)


def _summary_slide(prs: Presentation, rows: list[dict]):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _textbox(slide, "Debt maturity universe", Pt(28), bold=True, top=Inches(0.35))
    _textbox(slide, f"{len(rows)} saved companies · amounts exactly as stored · missing values remain unknown", Pt(12), top=Inches(0.85), color=(100, 100, 100))
    headers = ["Company", "Total", "<1y", "1–5y", ">5y", "Identity", "Review"]
    table_shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(0.6), Inches(1.15), Inches(12.1), Inches(5.95))
    table = table_shape.table
    widths = [2.8, 1.2, 1.1, 1.1, 1.1, 1.8, 3.0]
    for index, width in enumerate(widths):
        table.columns[index].width = Inches(width)
        table.cell(0, index).text = headers[index]
    for row_index, row in enumerate(rows, start=1):
        values = [row.get("company"), row.get("total"), row.get("within_1_year"), row.get("one_to_five_years"),
                  row.get("after_five_years"), row.get("identity"), row.get("review")]
        for column, value in enumerate(values):
            table.cell(row_index, column).text = _summary_value(value)
    body_size = Pt(max(3.5, min(10, 44 / max(len(rows), 1))))
    for row_index, row in enumerate(table.rows):
        for cell in row.cells:
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.size = Pt(6) if row_index == 0 else body_size
                paragraph.font.bold = row_index == 0


def _summary_value(value) -> str:
    if isinstance(value, (int, float)):
        return f"{value:,.6f}".rstrip("0").rstrip(".").replace(",", " ")
    return str(value) if value is not None else "—"


def _debt_chart(slide, by_key, buckets, prior=None, by_year=None, offset=0):
    total = by_key.get("total_debt", {}).get("value")
    unit = next((by_key[k]["unit"] for k in buckets if by_key[k].get("unit")), "")
    if total is not None:
        _textbox(slide, "Total debt: " + f"{total:,.6f}".rstrip("0").rstrip(".").replace(",", " ") + " " + unit, Pt(20), bold=True, top=Inches(2.4 + offset))

    data = CategoryChartData()
    if by_year:  # v109: the report's own calendar-year columns as the categories, one series of the same "Debt due"
        data.categories = [y["label"] for y in by_year["years"]]
        data.add_series("Debt due", [y["value"] for y in by_year["years"]])
    else:
        data.categories = [BUCKET_LABELS[k] for k in buckets]
        data.add_series("Debt due", [by_key[k]["value"] for k in buckets])
        if prior:  # v091: a second, fainter series beside each bucket, named for its own fiscal year
            data.add_series(f"FY{prior.get('fiscal_year')}", [prior.get("fields", {}).get(k, {}).get("value") for k in buckets])
    frame = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1.2), Inches(2.95 + offset), Inches(10.9), Inches(3.7 - offset), data)
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
    for element in chart._chartSpace.xpath(".//c:axId | .//c:crossAx"):
        element.set("val", str(int(element.get("val")) % (1 << 32)))


def _table(slide, fields, offset=0):
    rows = fields
    shape = slide.shapes.add_table(len(rows) + 1, 4, Inches(0.6), Inches(2.2 + offset), Inches(12.1), Inches(4.45 - offset))
    table = shape.table
    for c, h in enumerate(["Field", "Value", "Unit", "Why empty"]):
        table.cell(0, c).text = h
    for r, f in enumerate(rows, start=1):
        v = f["value"]
        table.cell(r, 0).text = f["label"]
        table.cell(r, 1).text = f"{v:,.6f}".rstrip("0").rstrip(".").replace(",", " ") if isinstance(v, (int, float)) else str(v) if v is not None else "Not available"
        table.cell(r, 2).text = f["unit"] or "Unknown"
        reason = f.get("missing_reason") or {}
        table.cell(r, 3).text = f"Why empty: {reason.get('detail')}" if v is None and reason.get("detail") else ""
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.size = Pt(10)
    table.columns[0].width = Inches(3.4)
    table.columns[1].width = Inches(1.7)
    table.columns[2].width = Inches(1.2)
    table.columns[3].width = Inches(5.8)


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
