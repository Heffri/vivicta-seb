"""PDF -> text, one string per page (pymupdf).

Table rows are kept whole: a text layer that prints a row label on one line and its figures on the
next is rebuilt from positioned text -- block-local first (prose order is untouched), page-wide from
words only when that still leaves rows open. Prose pages pass through byte-identical to get_text().
Column-major layers (Arion Bank prints every figure first, then every label) go through the word-level
rebuild too.

The word-level rebuild is column-aware (v049): a page-wide baseline merge glues a sidebar/TOC column
into body text mid-sentence (Ratos) and interleaves two tables printed side by side (Flerie, AQ), so
the page is first cut into column regions at vertical gutters and each column is rebuilt on its own.
A cut is refused when the two sides share a row grid -- those are one table's label and figure
columns, and cutting a table is far worse than not cutting. Block-local merging chains a wrapped
cell's stacked fragments (a header printed "Between" / "1 and" / "2 years" on three lines becomes one
line again) without touching prose, whose leading is wider than the chaining tolerance. The grouping
this chaining runs within is geometric, not pymupdf's own block partition (v049b): pymupdf's block
split for a short table region -- a stacked cell, a row's label split from its figures -- changes
between its own releases (Ependion p.155's maturity header is one block under PyMuPDF 1.27.2.3 and
five under 1.28.2, same glyph boxes), so a fragment's block id is not something the chain can rely on.
_group_blocks re-derives which short blocks belong together from the same geometry _stack_cells
already trusts, before either version's block boundary is looked at.

A table header that prints as two physical lines but is matrix-transposed -- line 1 holds every
column's first fragment, line 2 holds every column's second fragment, because a header cell that needs
two lines and a neighbor that needs only one both set their single/first line at the same height (v060:
Ework p.70, XANO p.84) -- comes out of both rebuilds above in that same scrambled, two-line order: it is
neither a stacked cell (the fragments are never in one narrow column or block) nor two side-by-side
tables (every column shares the row's own baseline). `_rebuild_transposed_headers` closes this
specifically: a row with enough bare value-shaped fragments to be a table's own data row fixes that
row's column x-positions, and the 1-3 short lines directly above it (v060's transposed header) are
reread by which column's position their own words are closest to, right edge to right edge -- the same
edge a wrapped header's printer already right-aligns to its column, whether or not that column also
needed a second line. Only adopted when every word's column is unambiguous.

Next for a teammate: scanned reports need an OCR fallback (pymupdf + tesseract via
`page.get_textpage_ocr()`).
"""
import re
import os
import json
from pathlib import Path
from . import paths

import pymupdf

_WS = re.compile(r"\s+")
_DIGIT_SPACE = re.compile(r" (?=\d)|(?<=\d) ")  # any space touching a digit
_CHARMAP = str.maketrans({"\u00a0": " ", "\u202f": " ", "\u2013": "-", "\u2212": "-"})  # NBSP, narrow NBSP, en dash, minus


PARSER_VERSION = 9  # v196: collapse a duplicated PDF text layer before locating/rebuilding its rows
NUMERIC_RUN = 12  # consecutive letterless lines: a column-major text layer (Arion Bank prints every figure first, then every label, in no order)
_LEADERS = re.compile(r"(?:\s*\.){3,}")
_PURE_VALUE = re.compile(r"[\s\d.,()\-–—%*]+")  # a figures-only line ("164,155 164,155", " - "), as opposed to a label
_CHAIN_GAP = 0.1  # a stacked cell fragment's box sits this much of a line height (or less) below the one above
_CHAIN_MAX = 3  # a wrapped header cell is 2-3 fragments deep; a chain growing past that is a paragraph, not a cell
_ALIGNED = 0.8  # this fraction of either side's lines sharing a baseline with the other side = one table's columns, not two layout columns
_ROW_GAP = 3.0  # two short blocks on one baseline join _group_blocks's pool when their x-gap is under this many times the narrower one's width
_LINE_RATIO = 2.0  # _group_blocks never links two lines whose heights differ by more than this factor
_PHRASE_GAP = 4.0  # word-to-word gap _phrases treats as ordinary spacing within one phrase, not a column boundary: intra-phrase gaps measured <=1.9pt (Ework's "< 1 month", XANO's space-grouped "51"+"075"); the tightest real inter-column gap measured is 5.5pt (Ework's "years"/"counted") -- 4.0 sits with margin on both sides
_HEADER_TOL = 2.0  # a header phrase's own right edge must land within this many points of its column's right edge to be adopted: both companies' printers right-align a wrapped header phrase's last word to its column, the same edge the column's own figures right-align to; every real match measured here lands within 0.2pt
_HEADER_MAX_LINES = 3  # a transposed header is at most this many physical lines above its anchor row (v060: Ework and XANO each wrap at most 2; a 4th line reaching this deep is a different shape, not this one)

OCR_PAGE_BUDGET = int(os.getenv("OCR_PAGE_BUDGET", "40"))  # v191: pages a bounded registration pass may OCR synchronously
OCR_SECONDS_PER_PAGE = 2.2  # v191: Saab's 231-page scan measured 506s (docs/PERFORMANCE.md) -- for the budget 422's "~N min" estimate only
FRONT_PAGES = 8  # v191: report front matter always considered, mirrors locate.py's own TOC_PAGES


def _dedupe_doubled_tokens(text: str) -> str:
    """Collapse a text layer that prints nearly every adjacent token twice.

    Intel FY2025's statement layer reads ``Net Net income income $ $ 26
    26``. Repeated words make locator phrases and field synonyms disappear,
    and repeated numbers turn a three-year row into six columns. Do not rewrite
    ordinary prose that merely happens to repeat a word: this repair requires at
    least eight adjacent duplicate pairs across a substantial share of the page,
    the signature of an overlaid PDF text layer.
    """
    tokens = re.findall(r"\S+", text)
    doubled = sum(a.casefold() == b.casefold() for a, b in zip(tokens, tokens[1:]))
    if doubled < 8 or doubled * 4 < len(tokens):
        return text
    prior = None
    while text != prior:  # three overlaid copies become one too
        prior = text
        text = re.sub(r"(?<!\S)(\S+)(?:[ \t]+\1)(?!\S)", r"\1", text, flags=re.I)
    return text


class OCRBudgetExceeded(RuntimeError):
    """A bounded registration pass's own candidate set alone needs more pages than OCR_PAGE_BUDGET."""

    def __init__(self, pages_needed: int):
        self.pages_needed = pages_needed
        minutes = max(1, round(pages_needed * OCR_SECONDS_PER_PAGE / 60))
        super().__init__(f"scanned PDF: OCR would take ~{minutes} min for {pages_needed} pages")


def _bounded_ocr_keywords() -> list[str]:
    """The debt_maturity schema's own toc_keywords -- the same words locate.toc_targets already
    trusts to match a report's table-of-contents/note-index entries against a section, reused here
    (not reinvented) so a bounded OCR pass targets the pages a debt-maturity locate pass would
    actually read."""
    schema = json.loads((paths.schemas_dir() / "debt_maturity.json").read_text(encoding="utf-8"))
    return [k.lower() for k in schema.get("toc_keywords", [])]


def _locator_bound_pages(doc) -> set[int]:
    """1-based pages a bounded OCR pass will spend its budget on: the report's own front matter
    (FRONT_PAGES) plus any outline (bookmark) entry whose title hits a debt/maturity/borrowings
    keyword, +-1 page. Outline titles are PDF metadata, readable with no text layer at all, which is
    what makes a bounded pass possible before any page has been OCR'd."""
    n = doc.page_count
    bound = set(range(1, min(FRONT_PAGES, n) + 1))
    keywords = _bounded_ocr_keywords()
    for _level, title, page in doc.get_toc(simple=True):
        if not (1 <= page <= n) or not any(k in title.lower() for k in keywords):
            continue
        bound.update(p for p in (page - 1, page, page + 1) if 1 <= p <= n)
    return bound


def _looks_scanned(page, text: str) -> bool:
    return len(re.sub(r"\W", "", text)) < 20 and bool(page.get_images() or len(page.get_drawings()) > 100)


def page_texts(pdf_path, metadata: dict | None = None, ocr: str = "bounded") -> list[str]:
    """0-based list; page n (1-based) is texts[n-1]. `ocr="bounded"` (default) synchronously OCRs
    only the pages a debt-maturity locate pass could actually reach (_locator_bound_pages) when a
    page has no text layer; other such pages come back "" and are listed in metadata["ocr_pending"]
    for later, on-demand OCR (app.py's extract path) instead of costing a ten-minute registration
    request on a long scanned report. Raises OCRBudgetExceeded rather than running it when even that
    bounded set is bigger than OCR_PAGE_BUDGET. `ocr="full"` OCRs every such page unconditionally
    (pre-v191 behaviour) -- an explicit opt-in, since only the caller knows the wait is wanted."""
    if metadata is not None:
        metadata.update(ocr_pages=[], ocr_pending=[], ocr_settings=ocr_settings())
    with pymupdf.open(pdf_path) as doc:
        if ocr == "full":
            return [page_text(page, metadata) for page in doc]
        pages = list(doc)
        scanned = {p.number + 1 for p in pages if _looks_scanned(p, p.get_text())}
        bound = _locator_bound_pages(doc) if scanned else set()
        if len(scanned & bound) > OCR_PAGE_BUDGET:
            raise OCRBudgetExceeded(len(scanned))
        return [page_text(p, metadata, ocr_allowed=(p.number + 1) in bound) for p in pages]


def page_text(page, metadata: dict | None = None, ocr_allowed: bool = True) -> str:
    """Plain text; a text layer that splits table rows (a row label on one line, its figures on the next) gets its
    lines rebuilt so each printed row is one line. Prose-only pages are returned as get_text() wrote them."""
    text = _dedupe_doubled_tokens(page.get_text())
    if len(re.sub(r"\W", "", text)) < 20 and (page.get_images() or len(page.get_drawings()) > 100):
        if not ocr_allowed:
            if metadata is not None:
                metadata.setdefault("ocr_pending", []).append(page.number + 1)
            return ""
        # PyMuPDF bundles the OCR engine. Language files stay local, no report upload.
        settings = ocr_settings()
        tessdata, language = Path(settings["tessdata"]), settings["language"]
        missing = [lang for lang in language.split("+") if not (tessdata / f"{lang}.traineddata").is_file()]
        if missing:
            raise OCRUnavailable("Scanned PDF needs OCR language files. Run python scripts/setup_ocr.py (missing: " + ", ".join(missing) + ").")
        tp = page.get_textpage_ocr(language=language, dpi=200, full=True, tessdata=str(tessdata))
        if metadata is not None:
            metadata.setdefault("ocr_pages", []).append(page.number + 1)
        return _dedupe_doubled_tokens(_words_to_lines([w[:5] for w in page.get_text("words", textpage=tp)]))
    navigation = _navigation_columns(page)
    if navigation is not None:
        return _dedupe_doubled_tokens(navigation)
    if _numeric_run(text) >= NUMERIC_RUN:
        return _dedupe_doubled_tokens(_best_words(page))
    if not _split_rows(text):
        return _dedupe_doubled_tokens(text)
    merged = _merge_baselines(page)
    leftover = _split_rows(merged)
    if leftover:  # rows still open: their cells sit in separate blocks. Word-level merges those, but a page-wide
        alt = _best_words(page)  # merge also glues columns together -- _best_words cuts them apart when it safely can
        if _split_rows(alt) < leftover:
            return _dedupe_doubled_tokens(alt)
    return _dedupe_doubled_tokens(merged)


def _navigation_columns(page) -> str | None:
    """Keep a PDF's linked navigation rail separate from its financial tables.

    Baseline alignment alone can mistake a sidebar for table labels. Require
    at least five internal links to distinct pages in the outer left fifth,
    a substantial vertical span, and a genuinely empty full-height gutter.
    Keep all words, including navigation; only their reading order changes.
    """
    width, height = page.rect.width, page.rect.height
    links = [link for link in page.get_links()
             if link.get('kind') in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED)
             and isinstance(link.get('page'), int) and link['page'] >= 0
             and link['from'].x1 <= width * .2]
    if len({link['page'] for link in links}) < 5:
        return None
    if max(link['from'].y1 for link in links) - min(link['from'].y0 for link in links) < height * .25:
        return None
    edge = max(link['from'].x1 for link in links)
    words = [word[:5] for word in page.get_text('words') if word[4].strip()]
    for gap, lo, hi in _gaps(words, 0, 2):
        if gap < max(12, width * .02) or edge > (lo + hi) / 2 or lo > edge + width * .025 or hi > width * .3:
            continue
        left = [word for word in words if word[2] <= lo]
        right = [word for word in words if word[0] >= hi]
        if len(left) + len(right) != len(words) or len(right) < 20:
            continue
        regions = [left, *_cut_regions(right, width, height)]
        return '\n'.join(_words_to_lines(region) for region in regions)
    return None


def _split_rows(text: str) -> int:
    """Split-row count: a line with letters but no digits directly followed by a line with digits but no letters --
    a row label separated from its figures."""
    lines = [l for l in (l.strip() for l in text.splitlines()) if l]
    has_alpha = [any(c.isalpha() for c in l) for l in lines]
    has_digit = [any(c.isdigit() for c in l) for l in lines]
    return sum(1 for i in range(len(lines) - 1) if has_alpha[i] and not has_digit[i] and has_digit[i + 1] and not has_alpha[i + 1])


def _merge_baselines(page) -> str:
    """Lines that share a baseline (within half the taller line's height) become one line, left to right.
    Groups (see _group_blocks) keep their reading order, so a prose paragraph's lines (distinct
    baselines, and never regrouped -- it is always its own block's only group) come out as before.
    Before grouping, a cell's stacked fragments are chained back together (see _stack_cells)."""
    block_lines = [[(l["bbox"], "".join(s["text"] for s in l["spans"])) for l in block["lines"]
                     if "".join(s["text"] for s in l["spans"]).strip()]
                    for block in page.get_text("dict")["blocks"] if block["type"] == 0]
    page_w = page.rect.width
    all_rows: list[tuple[float, list[tuple[float, float, str]]]] = []
    for idxs in _group_blocks(block_lines, page_w):
        lines = [ln for i in idxs for ln in block_lines[i]]
        if not lines:
            continue
        cluster_w = max(bbox[2] for bbox, _ in lines) - min(bbox[0] for bbox, _ in lines)
        rows: list[list] = []  # [y-center, height, [(x0, x1, text)]]
        for bbox, txt in _stack_cells(lines, cluster_w, page_w):
            yc, h = (bbox[1] + bbox[3]) / 2, bbox[3] - bbox[1]
            row = next((r for r in rows if abs(r[0] - yc) <= max(h, r[1]) / 2), None)
            if row is None:
                rows.append([yc, h, [(bbox[0], bbox[2], txt)]])
            else:
                row[2].append((bbox[0], bbox[2], txt))
        rows.sort(key=lambda r: (r[0], r[1], [(x0, t) for x0, _, t in r[2]]))
        all_rows += [(yc, xs) for yc, _, xs in rows]
    all_rows = _rebuild_transposed_headers(all_rows)
    out = [_WS.sub(" ", " ".join(t for _, t in sorted((x0, t) for x0, _, t in xs))).strip() for _, xs in all_rows]
    return "\n".join(l for l in out if l)


def _group_blocks(block_lines: list[list[tuple[tuple, str]]], page_w: float) -> list[list[int]]:
    """Which blocks (by index into block_lines) to pool into _stack_cells together, groups in first-seen
    order. Pymupdf's own block split is exactly as version-fragile as its line split within one block
    (see _stack_cells): a stacked header cell or a row split into a label piece and a figures piece can
    land in a single block on one pymupdf release and in several on another (Ependion p.155's maturity
    header, v049b). Two blocks join the same group when a line in one sits where _stack_cells would
    chain it onto a line in the other, or the two lines share a baseline (a row's label-and-figures split
    the same way a stacked cell's fragments are) -- both geometric, so the join does not depend on which
    block pymupdf put either line in. Only blocks of _CHAIN_MAX lines or fewer are eligible: a paragraph
    runs to many more lines than a wrapped cell or a split row ever does, and must never be pulled into
    another block's group -- prose stays exactly as block-scoped as before this function existed.

    A candidate join is only committed when the two groups' *combined* lines still pass _tabular (the
    same table-or-single-cell shape test _stack_cells itself gates on): four consecutive, unrelated
    two-line bio fields in a resume-style sidebar (Academedia p.33) each pass _tabular on their own (each
    is its own narrow column) and each is _blocks_link-adjacent to the next (same tight interline gap a
    genuine wrapped cell has), but pooling all four is neither narrow nor side-by-side -- it is prose that
    happens to sit close together, not a table. Rejecting that join leaves each field its own group, exactly
    as when this function did not exist. A join that does not yet look tabular can still complete once a
    third block supplies the missing side-by-side evidence (as Ependion's own two-fragment column groups
    do once merged with their neighbor column), so this is checked at every step, not just the end."""
    n = len(block_lines)
    parent = list(range(n))
    pooled = {i: block_lines[i] for i in range(n)}  # current root -> its group's pooled lines

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    short = [i for i, lines in enumerate(block_lines) if 0 < len(lines) <= _CHAIN_MAX]
    for a in range(len(short)):
        for b in range(a + 1, len(short)):
            i, j = short[a], short[b]
            ri, rj = find(i), find(j)
            if ri == rj or not _blocks_link(block_lines[i], block_lines[j]):
                continue
            merged = pooled[ri] + pooled[rj]
            width = max(bbox[2] for bbox, _ in merged) - min(bbox[0] for bbox, _ in merged)
            if not _tabular(merged, width, page_w):
                continue
            parent[ri] = rj
            pooled[rj] = merged
            del pooled[ri]
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _blocks_link(lines_a, lines_b) -> bool:
    """True if a line in a and a line in b are the same stacked cell or the same row split across the
    block boundary: either pair passes _stack_cells's own vertical-chain test (x-overlap, tight vertical
    gap -- width ratio is not: that check is against a chain's accumulated width and has no pairwise
    reading, and the _CHAIN_MAX-line cap already bounds how far off two chainable fragments' widths can
    be), or one is a bare label and the other its bare figures (exactly one side _PURE_VALUE) sharing a
    baseline within _ROW_GAP times the narrower one's width (Ependion's "Recognized .../-9,751" split
    measures 2.3x). The value/label asymmetry, not just the gap, matters: two adjacent header cells of one
    table (Ependion's "Between"/"Between" columns, gap 0.2x) share a baseline just as tightly as a split
    row does -- they are neither of them a value, so this test leaves them alone and _stack_cells's own
    column-shape gate is what decides whether either chains at all. Neither test fires across two lines
    whose heights differ by more than _LINE_RATIO: the vertical-chain gap tolerance scales with a line's
    own height (_CHAIN_GAP times the taller of the two), so a big decorative glyph (Acast's "460" stat,
    53pt tall next to normal 10pt body text) can reach far enough down the page to graze an unrelated
    paragraph's first line -- a block boundary always used to end that reach by accident; this test must
    end it on purpose."""
    for bbox_a, txt_a in lines_a:
        wa, ha = bbox_a[2] - bbox_a[0], bbox_a[3] - bbox_a[1]
        yc_a = (bbox_a[1] + bbox_a[3]) / 2
        value_a = bool(_PURE_VALUE.fullmatch(txt_a.strip()))
        for bbox_b, txt_b in lines_b:
            wb, hb = bbox_b[2] - bbox_b[0], bbox_b[3] - bbox_b[1]
            if max(ha, hb) > _LINE_RATIO * min(ha, hb):
                continue
            value_b = bool(_PURE_VALUE.fullmatch(txt_b.strip()))
            x_gap = max(bbox_a[0], bbox_b[0]) - min(bbox_a[2], bbox_b[2])
            if (value_a != value_b and abs(yc_a - (bbox_b[1] + bbox_b[3]) / 2) <= 2.5
                    and x_gap <= _ROW_GAP * min(wa, wb)):
                return True
            overlap = min(bbox_a[2], bbox_b[2]) - max(bbox_a[0], bbox_b[0])
            gap = max(bbox_a[1], bbox_b[1]) - min(bbox_a[3], bbox_b[3])
            span = max(ha, hb)
            if overlap >= 0.5 * min(wa, wb) and -0.5 * span <= gap <= _CHAIN_GAP * span:
                return True
    return False


def _tabular(lines: list[tuple[tuple, str]], width: float, page_w: float) -> bool:
    """A block or a candidate _group_blocks pool already looks like a table or a single stacked cell:
    some baseline holds two x-disjoint lines (side by side -- a table row's columns, or two stacked
    cells' matching fragments), or the whole thing is a narrow column (a single wrapped cell, isolated by
    a wide gutter from its neighbors). A prose paragraph has one fragment per baseline and fills its
    column's width, and its lines can touch just as tightly as stacked fragments do (Atlas Copco sets
    them with zero leading), so leading alone cannot tell the two apart -- shape must."""
    bands: list[list] = []  # [yc, [bbs]]
    for bb, _ in lines:
        band = next((b for b in bands if abs(b[0] - (bb[1] + bb[3]) / 2) <= 2.5), None)
        if band is None:
            bands.append([(bb[1] + bb[3]) / 2, [bb]])
        else:
            band[1].append(bb)
    side_by_side = any(any(b[2] <= o[0] for b in bbs for o in bbs if b is not o) for _, bbs in bands)
    return side_by_side or width <= 0.15 * page_w


def _stack_cells(lines: list[tuple[tuple, str]], block_w: float, page_w: float) -> list[tuple[tuple, str]]:
    """A wrapped cell printed as stacked fragments (Ependion's maturity header: 'Between' over '1 and' over
    '2 years', each its own line) becomes one line again -- but only within a _tabular block or pool.
    Within a chainable one a fragment joins the chain above when their x-ranges overlap by half the
    narrower's width, its box sits within _CHAIN_GAP of a line height below the chain's box (stacked
    fragments touch or overlap), it is no wider than 1.5x the chain (a continuation never much exceeds the
    cell it wraps in, Nelly's next row label under a short one), the chain is under _CHAIN_MAX deep, and
    its own baseline carries no pure-figures line elsewhere in the pool (those are its row's figures --
    Morrow Bank packs label rows 11pt apart with each row's figures on its own label's baseline). Chains
    keep top-to-bottom text order."""
    if not _tabular(lines, block_w, page_w):
        return lines
    value_ycs = [(bb[1] + bb[3]) / 2 for bb, txt in lines if _PURE_VALUE.fullmatch(txt.strip())]
    chains: list[list] = []  # [x0, y0, x1, y1, [texts]]
    for bb, txt in sorted(lines, key=lambda l: (l[0][1], l[0][0])):
        yc, best, best_overlap = (bb[1] + bb[3]) / 2, None, 0
        if not any(abs(yc - v) <= 2.5 for v in value_ycs):
            for c in chains:
                overlap = min(bb[2], c[2]) - max(bb[0], c[0])
                gap = bb[1] - c[3]  # how far this fragment starts below the chain's box; negative = overlap
                span = max(bb[3] - bb[1], c[3] - c[1])
                if (overlap >= 0.5 * min(bb[2] - bb[0], c[2] - c[0]) and -0.5 * span <= gap <= _CHAIN_GAP * span
                        and bb[2] - bb[0] <= 1.5 * (c[2] - c[0]) and len(c[4]) < _CHAIN_MAX):
                    if overlap > best_overlap:
                        best, best_overlap = c, overlap
        if best is None:
            chains.append([bb[0], bb[1], bb[2], bb[3], [txt]])
        else:
            best[0], best[1], best[2], best[3] = min(best[0], bb[0]), min(best[1], bb[1]), max(best[2], bb[2]), max(best[3], bb[3])
            best[4].append(txt)
    return [((c[0], c[1], c[2], c[3]), " ".join(c[4])) for c in chains]


def _numeric_run(text: str) -> int:
    best = run = 0
    for line in text.splitlines():
        if line.strip():
            run = 0 if re.search(r"[^\W\d_]", line) else run + 1
            best = max(best, run)
    return best


def _lines_from_words(page) -> str:
    """Words sharing a baseline (within half a word height), left to right; dot leaders dropped."""
    return _words_to_lines([w[:5] for w in page.get_text("words")])


def _words_to_lines(words) -> str:
    """The shared line rebuild: words sharing a baseline (within half a word height), left to right; dot leaders dropped."""
    lines: list[tuple[float, list]] = []
    for x0, y0, x1, y1, word in words:
        yc, tol = (y0 + y1) / 2, (y1 - y0) / 2
        line = next((l for l in lines if abs(l[0] - yc) <= tol), None)
        if line is None:
            lines.append((yc, [(x0, x1, word)]))
        else:
            line[1].append((x0, x1, word))
    lines.sort(key=lambda l: (l[0], [(x0, w) for x0, _, w in l[1]]))
    lines = _rebuild_transposed_headers(lines)
    return "\n".join(_WS.sub(" ", _LEADERS.sub(" ", " ".join(w for _, w in sorted((x0, w) for x0, _, w in ws)))).strip() for _, ws in lines)


def _is_amount(text: str) -> bool:
    """A bare value-shaped phrase: no letters at all (a figure, a lone '-'/'–' nil marker, a bare '%').
    Never true of a header phrase (Ework's "< 1 month", XANO's "Mellan 1 och 3 år"): every header phrase
    in both companies' tables keeps at least one letter alongside any digits it carries, because a range
    or a unit word is always attached: a header line built entirely of these is a table's own data row,
    not the column headers above it."""
    return bool(text) and not any(c.isalpha() for c in text)


def _phrases(frags: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """A line's (x0, x1, text) word fragments, grouped left to right into phrases: a tight gap is
    ordinary word spacing within one phrase (this is also what reglues a space-grouped thousands split,
    XANO's "51" + "075"); a wide gap is a real column boundary (see _PHRASE_GAP). Dot leaders (their own
    word per '.') carry no content and are dropped first so they never bridge two real phrases into one
    (a title row's dotted rule sitting one line above a table must not smuggle its own two label words
    into the header-rebuild scan below)."""
    out = []
    for x0, x1, text in sorted(f for f in frags if not re.fullmatch(r"\.+", f[2])):
        if out and x0 - out[-1][1] <= _PHRASE_GAP:
            out[-1] = (out[-1][0], x1, out[-1][2] + " " + text)
        else:
            out.append((x0, x1, text))
    return out


def _assign_columns(groups: list, first_x0: float, col_x1: list[float]):
    """None (some word's column is not unambiguous), or groups' phrases (top to bottom) reflowed into
    one label bucket plus one bucket per column in col_x1, each stitched top-to-bottom into a single
    phrase -- a trailing hyphen glues directly rather than spacing, so a line-wrapped word reassembles
    ("Total undis-" + "counted value" -> "Total undiscounted value")."""
    label, cols = [], [[] for _ in col_x1]
    for phrases in groups:
        claimed = set()
        for x0, x1, text in phrases:
            if x1 <= first_x0:
                label.append(text)
                continue
            dists = sorted(abs(a - x1) for a in col_x1)
            best = min(range(len(col_x1)), key=lambda i: abs(col_x1[i] - x1))
            if dists[0] > _HEADER_TOL or (len(dists) > 1 and dists[1] - dists[0] < 0.5) or best in claimed:
                return None  # a word sits too far from any column, tied between two, or repeats a column this line already claimed
            claimed.add(best)
            cols[best].append(text)

    def stitch(parts: list[str]) -> str:
        out = ""
        for part in parts:
            if not out:
                out = part
            elif out.endswith("-"):
                out = out[:-1] + part
            else:
                out = out + " " + part
        return out

    return " ".join(stitch(parts) for parts in [label, *cols] if parts)


def _header_fix(lines: list[tuple[float, list]], j: int):
    """None, or (start, end, rebuilt) if lines[j] is a table row whose own column x-positions can be
    read off (>=3 bare value-shaped phrases) and 1-3 short lines directly above it are that row's own
    column headers, matrix-transposed across physical lines (v060: Ework p.70 and XANO p.84 each print a
    table header as two lines -- one holding every column's first fragment, the next holding every
    column's second -- because a two-line column and a one-line neighbor both set their first/only line
    at the same height; plain reading order glues them in an order that matches no real column order).
    Caller replaces lines[start:end] with one rebuilt line; lines[end:] (j itself, and any line the scan
    skipped below the header) is untouched."""
    amounts = [p for p in _phrases(lines[j][1]) if _is_amount(p[2])]
    if len(amounts) < 3:
        return None
    first_x0 = amounts[0][0]
    col_x1 = [p[1] for p in amounts]

    end = j
    if end > 0:
        below = _phrases(lines[end - 1][1])
        if any(_is_amount(p[2]) for p in below) and len(below) <= 2 and all(p[1] <= first_x0 for p in below):
            end -= 1  # a bare sub-heading confined to the label column (e.g. a lone fiscal year): not part
                      # of the transposed header, but no reason it should block the search above it

    groups, start = [], end
    while start > 0 and len(groups) < _HEADER_MAX_LINES:
        phrases = _phrases(lines[start - 1][1])
        if any(_is_amount(p[2]) for p in phrases) or not any(p[1] > first_x0 for p in phrases):
            break  # a row of its own (the chain of header lines ends), or nothing here reaches the table's columns at all
        groups.insert(0, phrases)
        start -= 1

    while groups:
        rebuilt = _assign_columns(groups, first_x0, col_x1)
        if rebuilt is not None:
            return start, end, rebuilt
        groups.pop(0)  # the farthest line up is the least certain match; drop it and try the closer lines alone
        start += 1
    return None


def _rebuild_transposed_headers(lines: list[tuple[float, list]]) -> list[tuple[float, list]]:
    """lines: (yc, [(x0, x1, text)]) rows in top-to-bottom order, however the caller built them (a
    page's dict-block groups, or its raw words) -- _header_fix reads the pattern line to line and does
    not care which. A page can hold the pattern more than once (XANO prints it once per fiscal year), so
    this runs to a fixed point; every other line is returned exactly as it came in."""
    lines = list(lines)
    changed = True
    while changed:
        changed = False
        for j in range(len(lines)):
            fix = _header_fix(lines, j)
            if fix is None:
                continue
            start, end, rebuilt = fix
            lines[start:end] = [(lines[start][0], [(0.0, 0.0, rebuilt)])]
            changed = True
            break
    return lines


def _best_words(page) -> str:
    """The word-level rebuild, column-aware when that is safe to adopt: a page-wide baseline merge glues a
    sidebar's nav lines into body text mid-sentence and interleaves two tables printed side by side, so
    _columns_from_words cuts the page into columns first. The cut text wins only while it leaves no more
    split rows than the plain rebuild -- a cut that costs more rows than it closes is a wrong cut."""
    plain = _lines_from_words(page)
    cut = _columns_from_words(page)
    return cut if cut is not None and _split_rows(cut) <= _split_rows(plain) else plain


def _columns_from_words(page):
    """None (no safe cut -- callers keep the plain whole-page rebuild), or the page rebuilt one column region
    at a time, regions in reading order. See _cut_regions for what counts as a column boundary."""
    words = [w[:5] for w in page.get_text("words") if w[4].strip()]
    regions = _cut_regions(words, page.rect.width, page.rect.height)
    if len(regions) < 2:
        return None
    return "\n".join(_words_to_lines(r) for r in regions)


def _cut_regions(words, page_w: float, page_h: float, depth: int = 0):
    """XY-cut: split a region at the widest vertical gutter (an x-band empty across the region's whole height),
    else at the widest horizontal gap, and recurse; leaves come back in reading order (left before right,
    top before bottom). A vertical cut needs real content on both sides and is refused when the sides'
    baselines align row for row (_ALIGNED) -- a table's label column and figure columns share the row grid
    exactly, and cutting one table apart is far worse than leaving two tables interleaved. Horizontal cuts
    never change the text (no baseline spans them); they exist so a gutter that only spans part of the
    page height -- two tables side by side under a full-width one -- can still be found below it."""
    if depth >= 8 or len(words) < 40:
        return [words]
    for width, lo, hi in _gaps(words, 0, 2):  # vertical gutters, widest first
        if width < max(6.0, 0.008 * page_w):
            break
        left = [w for w in words if w[2] <= lo]
        right = [w for w in words if w[0] >= hi]
        if _splittable(left, right, len(words)):
            return _cut_regions(left, page_w, page_h, depth + 1) + _cut_regions(right, page_w, page_h, depth + 1)
    for width, lo, hi in _gaps(words, 1, 3):  # horizontal gaps, widest first
        if width < max(8.0, 0.012 * page_h):
            break
        top = [w for w in words if w[3] <= lo]
        bottom = [w for w in words if w[1] >= hi]
        if top and bottom:
            return _cut_regions(top, page_w, page_h, depth + 1) + _cut_regions(bottom, page_w, page_h, depth + 1)
    return [words]


def _gaps(words, lo_i: int, hi_i: int) -> list[tuple[float, float, float]]:
    """Maximal empty bands between the covered intervals on one axis, widest first: (width, end below the
    gap, start above it). A band empty in the projection is empty at every coordinate of the other axis."""
    spans = sorted((w[lo_i], w[hi_i]) for w in words)
    covered, out = [], []  # covered: merged intervals; out: gaps between them
    for lo, hi in spans:
        if covered and lo <= covered[-1][1]:
            covered[-1][1] = max(covered[-1][1], hi)
        else:
            if covered:
                out.append((lo - covered[-1][1], covered[-1][1], lo))
            covered.append([lo, hi])
    return sorted(out, reverse=True)


def _splittable(left, right, total: int) -> bool:
    """Both sides carry real content, and they are not one table's columns. Content: at least max(10, 5%)
    of the words on each side. One table: (a) the sides share a row grid -- that fraction of either side's
    baselines also appearing on the other side reaches _ALIGNED only for a table's label and figure columns
    (independent columns coincide on well under half, Ratos' two body columns land at 0.76 because both
    sit on the report's own baseline grid); (b) a near-grid pairing where one side is bare labels (almost
    no digit words) against a digit-bearing side -- a table's label column again, whose figures sit in the
    other region; (c) an aligned pair whose left line ends in a figure while the right line starts with one
    -- one row's figure run continuing across the gutter; (d) the cut tears rows: label-only lines followed
    by figure-only lines appear that the uncut rebuild keeps whole."""
    if len(left) < max(10, 0.05 * total) or len(right) < max(10, 0.05 * total):
        return False
    lines_l, lines_r = _line_texts(left), _line_texts(right)
    ycs_l, ycs_r = [y for y, _ in lines_l], [y for y, _ in lines_r]
    matched_l = sum(1 for y in ycs_l if any(abs(y - z) <= 2.5 for z in ycs_r)) / len(ycs_l)
    matched_r = sum(1 for z in ycs_r if any(abs(y - z) <= 2.5 for y in ycs_l)) / len(ycs_r)
    if max(matched_l, matched_r) >= _ALIGNED:
        return False
    digits = lambda ws: sum(any(c.isdigit() for c in w[4]) for w in ws) / len(ws)
    if min(matched_l, matched_r) >= 0.5 and min(digits(left), digits(right)) < 0.03 and max(digits(left), digits(right)) >= 0.4:
        return False
    aligned = torn = 0
    for yl, tl in lines_l:
        for yr, tr in lines_r:
            if abs(yl - yr) <= 2.5:
                aligned += 1
                if (tl[-1:].isdigit() and tr[:1].isdigit()) or (tr[-1:].isdigit() and tl[:1].isdigit()):
                    torn += 1  # a line ending in a figure over a line starting with one: a figure run crossing the gutter
    if torn and torn >= aligned / 2:  # every second aligned pair continuing a run is systematic: one table, not two columns
        return False
    cut = _words_to_lines(left) + "\n" + _words_to_lines(right)
    return _split_rows(cut) <= _split_rows(_words_to_lines(left + right))


def _line_texts(words) -> list[tuple[float, str]]:
    """One (y-center, text) per printed line of these words (baseline groups, earliest member wins)."""
    lines: list[list] = []  # [yc, [(x0, word)]]
    for x0, y0, _, y1, word in sorted(words, key=lambda w: (w[1], w[0])):
        yc = (y0 + y1) / 2
        line = next((l for l in lines if abs(yc - l[0]) <= 2.5), None)
        if line is None:
            lines.append([yc, [(x0, word)]])
        else:
            line[1].append((x0, word))
    return [(yc, " ".join(w for _, w in sorted(ws))) for yc, ws in lines]


def normalize_ws(s: str) -> str:
    """Make two renderings of the same table row compare equal.

    Collapses whitespace, maps NBSP/narrow NBSP to space and en dash / unicode minus
    to '-', then drops every space touching a digit so the Swedish thousands separator
    and column gaps vanish: "Intakter 152 340 141 902", "Intakter 152340 141902" and
    "Intakter 152<NBSP>340" all canonicalise to "Intakter152340...". Lossy: matching only.
    """
    s = _WS.sub(" ", s.translate(_CHARMAP))
    return _DIGIT_SPACE.sub("", s).strip()


_NUMTOK = re.compile(r"[-(]?[\d.,]+\)?%?")
_GAP = r"(?:[\s\d,.()\-]|\b[A-Z]\d{1,2}\b){0,24}?"  # what may sit between two quote tokens on the page: a note reference like "6,7", Skanska's "8, 9, 10, 33, 38" or Pandox's "C1, C4, C6, C7, G5"


def quote_on_page(quote: str, text: str) -> str:
    """The part of the quote that is verifiably on the page, "" if none. The whole quote first: exact
    (whitespace-insensitive), else every token in order with only note-reference junk in between, because the
    model writes "Revenue 176,658" for a row printed as "Revenue  6,7  176,658  176,481" and that *is* the row.
    Then the same for shorter suffixes, because the model also prepends the section header to the row it read
    ("Continuing operations Operating income C5 10,426" / "Earnings per share Group 15.76"). A suffix must still
    hold a label word and a number; number tokens need digit boundaries so "176" cannot claim "176,658"."""
    norm = lambda s: _WS.sub(" ", s.translate(_CHARMAP)).strip()
    toks, ntext, flat = norm(quote).split(" "), norm(text), normalize_ws(text)
    for start in range(len(toks)):
        part = toks[start:]
        if not any(c.isalpha() for t in part for c in t) or not any(_NUMTOK.fullmatch(t) for t in part):
            break  # a bare number (or a bare label) is not provenance
        cand = " ".join(part)
        if normalize_ws(cand) in flat:
            return cand
        parts = [rf"(?<![\d.,]){re.escape(t)}(?![\d.,])" if _NUMTOK.fullmatch(t) else re.escape(t) for t in part]
        if re.search(_GAP.join(parts), ntext, re.I):
            return cand
    return ""


class OCRUnavailable(RuntimeError):
    pass


def ocr_settings():
    return {"language": os.getenv("OCR_LANGUAGE", "eng+swe"),
            "tessdata": str(Path(os.getenv("TESSDATA_PREFIX") or paths.data_dir() / "tessdata").resolve())}
