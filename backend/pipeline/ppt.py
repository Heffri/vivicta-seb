"""One-slide PowerPoint export of an Extraction (docs/API.md). Generic, not debt-specific:
a bar chart when the fields look like maturity buckets ('due_*' keys), a table otherwise.
The whole-universe deck (build_deck) adds two debt-specific summary pages -- the maturity-wall
table and, since v180, the sector maturity wall -- both fed by the same decorated extracts.
"""
import io
import json
import re

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

from . import paths, workbench

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
    unresolved = x.get("issues", []) + x.get("basis_issues", [])  # basis lives beside the queue since it stopped blocking ready
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


def complete_buckets(x: dict) -> bool:
    """v180: the maturity wall's "complete buckets" -- the stored identity check passed and both
    total_debt and due_within_1_year carry values. Companies whose identity failed or that miss a
    bucket draw grey ("buckets incomplete") and never feed a sector's median/min/max -- a missing
    figure is never back-filled with 0, so an honest share can only come from an honest total."""
    fields = {f["key"]: f for f in x.get("fields", [])}
    check = next((c for c in x.get("checks", []) if c.get("name") == "maturity_sums_to_total"), None)
    return bool(check and check.get("passed")) \
        and fields.get("total_debt", {}).get("value") is not None \
        and fields.get("due_within_1_year", {}).get("value") is not None


def _normalize_name(name: str) -> str:
    return re.sub(r"[\W_]+", " ", name.casefold()).strip()


def _sector_map() -> dict:
    """Normalized company name -> sector from data/companies.json -- the same mapping GET /api/kb
    builds. A function, not a constant, so tests can freeze the universe instead of trusting
    data/ content (LESSONS 43)."""
    companies = json.loads(paths.companies_path().read_text(encoding="utf-8"))
    return {_normalize_name(c["name"]): c.get("sector") for c in companies}


SECTOR_WALL_PAGE_ROWS = 30  # row-units per page: company bars plus their sector headers


def _sector_blocks(extractions: list[dict]) -> list[tuple[str, list[tuple]]]:
    """(sector, [(company, share, complete, total_missing)]) in render order: sectors alphabetical
    with the unknown-sector block last, companies complete-first then by share descending. The
    share is the same currency-aware figure the /api/kb/maturity-wall endpoint reports --
    workbench.maturity_wall is reused per company, never a second unit parser."""
    sector_of = _sector_map()
    grouped: dict[str | None, list[tuple]] = {}
    for x in extractions:
        if x.get("section") != "debt_maturity":
            continue
        fields = {f["key"]: f for f in x.get("fields", [])}
        total_missing = fields.get("total_debt", {}).get("value") is None
        share = workbench.maturity_wall([x])["rows"][0]["share"]
        row = (x.get("company") or x.get("stem") or "Unknown company", share, complete_buckets(x), total_missing)
        grouped.setdefault(sector_of.get(_normalize_name(x.get("company") or "")), []).append(row)
    blocks = []
    for sector in sorted(grouped, key=lambda s: (s is None, s or "")):
        rows = grouped[sector]
        rows.sort(key=lambda r: (not r[2], r[1] is None, -(r[1] or 0), r[0]))
        blocks.append((sector or "Unknown sector", rows))
    return blocks


def _paginate_blocks(blocks: list[tuple[str, list[tuple]]], limit: int = SECTOR_WALL_PAGE_ROWS) -> list[list]:
    """Split sector blocks into pages of at most `limit` row-units (each sector header takes one).
    A sector that alone exceeds a page continues on the next one under a "(cont.)" header."""
    pages, page, used = [], [], 0
    for sector, rows in blocks:
        first, index = True, 0
        while index < len(rows):
            room = limit - used - 1  # the sector header (first or continuation) takes a row-unit too
            if room <= 0:
                pages.append(page)
                page, used = [], 0
                continue
            take = rows[index:index + room]
            page.append((sector if first else f"{sector} (cont.)", take))
            used += 1 + len(take)
            index += len(take)
            first = False
    if page:
        pages.append(page)
    return pages


BAR_COLOR = (68, 114, 196)   # the deck chart's accent blue: a share the identity check vouches for
GREY_COLOR = (166, 166, 166)  # buckets incomplete: the bar is drawn, but nothing is vouched for
MUTED_COLOR = (100, 100, 100)


def _wall_text(slide, text, x, y, size, w=12.0, bold=False, color=None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.3))
    run = box.text_frame.paragraphs[0].add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    return box


def _sector_wall_slide(prs: Presentation, extractions: list[dict]):
    """v180 (consult-fable #2, after the summary table): "Maturity wall by sector" -- one horizontal
    bar per company (due_within_1_year / total_debt) under its sector header. Complete buckets draw
    the share; a failed/absent identity or a missing bucket draws grey with "buckets incomplete" (the
    computable share still sets the bar's length -- arithmetic on printed numbers, not a guess); a
    missing total draws "not read" with no bar at all. Nothing is inferred, no missing bucket is
    filled with 0. Pages hold at most SECTOR_WALL_PAGE_ROWS row-units (deck fonts follow
    _summary_slide's rule: shrink as the page fills)."""
    blocks = _sector_blocks(extractions)
    if not blocks:
        return
    top, bottom = 1.3, 7.15
    pitch = (bottom - top) / SECTOR_WALL_PAGE_ROWS
    for page in _paginate_blocks(blocks):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        units = sum(1 + len(rows) for _, rows in page)
        size = max(6, min(9, 250 // max(units, 1)))
        _textbox(slide, "Maturity wall by sector", Pt(28), bold=True, top=Inches(0.35))
        _textbox(slide, "Share of debt due within 1 year · grey = buckets incomplete · \"not read\" = no total debt figure · missing values are never filled with 0",
                 Pt(12), top=Inches(0.85), color=MUTED_COLOR)
        notes = []
        y = top
        for sector, rows in page:
            complete_n = sum(1 for r in rows if r[2])
            header = _wall_text(slide, sector, 0.55, y, size + 1, bold=True)
            run = header.text_frame.paragraphs[0].add_run()
            run.text = f" · {complete_n} of {len(rows)} with complete buckets"
            run.font.size = Pt(size)
            run.font.color.rgb = RGBColor(*MUTED_COLOR)
            y += pitch
            for name, share, complete, total_missing in rows:
                _wall_text(slide, name if len(name) <= 40 else name[:39] + "…", 0.55, y + 0.02, size,
                           w=2.95, color=(60, 60, 60) if complete else MUTED_COLOR)
                if share is not None:
                    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(3.6), Inches(y + pitch * 0.22),
                                                 Inches(min(max(share, 0.0), 1.0) * 7.0), Inches(pitch * 0.56))
                    bar.fill.solid()
                    bar.fill.fore_color.rgb = RGBColor(*(BAR_COLOR if complete else GREY_COLOR))
                    bar.line.fill.background()
                if total_missing:
                    value, color = "not read", MUTED_COLOR
                elif share is None:
                    # complete but no comparable share (no debt outstanding, unmatched units) keeps
                    # its honesty; incomplete buckets are the grey case the legend names
                    value, color = ("no comparable figure" if complete else "buckets incomplete"), MUTED_COLOR
                elif not complete:
                    value, color = f"{share * 100:.1f}% · buckets incomplete", MUTED_COLOR
                else:
                    value, color = f"{share * 100:.1f}%", (0, 0, 0)
                _wall_text(slide, value, 10.75, y + 0.02, size, w=2.05, color=color)
                notes.append({"company": name, "share": share, "complete": complete, "total_read": not total_missing})
                y += pitch
        slide.notes_slide.notes_text_frame.text = json.dumps({"sectors": [{"sector": sector, "rows": notes} for sector, rows in page]}, ensure_ascii=False)


def build_deck(extractions: list[dict], summary: list[dict] | None = None) -> bytes:
    """Build one universe deck: a maturity-wall table, the v180 sector wall page(s), then one
    established slide per company."""
    prs = _presentation()
    _summary_slide(prs, summary if summary is not None else [summary_row(x) for x in extractions])
    _sector_wall_slide(prs, extractions)
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
