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
line again) without touching prose, whose leading is wider than the chaining tolerance.

Next for a teammate: scanned reports need an OCR fallback (pymupdf + tesseract via
`page.get_textpage_ocr()`).
"""
import re

import pymupdf

_WS = re.compile(r"\s+")
_DIGIT_SPACE = re.compile(r" (?=\d)|(?<=\d) ")  # any space touching a digit
_CHARMAP = str.maketrans({"\u00a0": " ", "\u202f": " ", "\u2013": "-", "\u2212": "-"})  # NBSP, narrow NBSP, en dash, minus


PARSER_VERSION = 4  # bump when page_text changes so kb.save_report rewrites cached pages.jsonl
NUMERIC_RUN = 12  # consecutive letterless lines: a column-major text layer (Arion Bank prints every figure first, then every label, in no order)
_LEADERS = re.compile(r"(?:\s*\.){3,}")
_PURE_VALUE = re.compile(r"[\s\d.,()\-–—%*]+")  # a figures-only line ("164,155 164,155", " - "), as opposed to a label
_CHAIN_GAP = 0.1  # a stacked cell fragment's box sits this much of a line height (or less) below the one above
_CHAIN_MAX = 3  # a wrapped header cell is 2-3 fragments deep; a chain growing past that is a paragraph, not a cell
_ALIGNED = 0.8  # this fraction of either side's lines sharing a baseline with the other side = one table's columns, not two layout columns


def page_texts(pdf_path) -> list[str]:
    """0-based list; page n (1-based) is texts[n-1]."""
    with pymupdf.open(pdf_path) as doc:
        return [page_text(page) for page in doc]


def page_text(page) -> str:
    """Plain text; a text layer that splits table rows (a row label on one line, its figures on the next) gets its
    lines rebuilt so each printed row is one line. Prose-only pages are returned as get_text() wrote them."""
    text = page.get_text()
    if _numeric_run(text) >= NUMERIC_RUN:
        return _best_words(page)
    if not _split_rows(text):
        return text
    merged = _merge_baselines(page)
    leftover = _split_rows(merged)
    if leftover:  # rows still open: their cells sit in separate blocks. Word-level merges those, but a page-wide
        alt = _best_words(page)  # merge also glues columns together -- _best_words cuts them apart when it safely can
        if _split_rows(alt) < leftover:
            return alt
    return merged


def _split_rows(text: str) -> int:
    """Split-row count: a line with letters but no digits directly followed by a line with digits but no letters --
    a row label separated from its figures."""
    lines = [l for l in (l.strip() for l in text.splitlines()) if l]
    has_alpha = [any(c.isalpha() for c in l) for l in lines]
    has_digit = [any(c.isdigit() for c in l) for l in lines]
    return sum(1 for i in range(len(lines) - 1) if has_alpha[i] and not has_digit[i] and has_digit[i + 1] and not has_alpha[i + 1])


def _merge_baselines(page) -> str:
    """Lines of a block that share a baseline (within half the taller line's height) become one line, left to right.
    Blocks keep their reading order, so a prose paragraph's lines (distinct baselines) come out as before.
    Before grouping, a cell's stacked fragments are chained back together (see _stack_cells)."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        lines = [(l["bbox"], "".join(s["text"] for s in l["spans"])) for l in block["lines"] if "".join(s["text"] for s in l["spans"]).strip()]
        rows: list[list] = []  # [y-center, height, [(x0, text)]]
        for bbox, txt in _stack_cells(lines, block["bbox"][2] - block["bbox"][0], page.rect.width):
            yc, h = (bbox[1] + bbox[3]) / 2, bbox[3] - bbox[1]
            row = next((r for r in rows if abs(r[0] - yc) <= max(h, r[1]) / 2), None)
            if row is None:
                rows.append([yc, h, [(bbox[0], txt)]])
            else:
                row[2].append((bbox[0], txt))
        out += [_WS.sub(" ", " ".join(t for _, t in sorted(xs))).strip() for _, _, xs in sorted(rows)]
    return "\n".join(l for l in out if l)


def _stack_cells(lines: list[tuple[tuple, str]], block_w: float, page_w: float) -> list[tuple[tuple, str]]:
    """A wrapped cell printed as stacked fragments (Ependion's maturity header: 'Between' over '1 and' over
    '2 years', each its own line) becomes one line again -- but only in a block that already looks like a
    table or a single stacked cell: some baseline holds two x-disjoint lines, or the whole block is a
    narrow column. A prose paragraph has one fragment per baseline and fills its column's width, and its
    lines can touch just as tightly as stacked fragments do (Atlas Copco sets them with zero leading), so
    leading alone cannot tell the two apart -- shape must. Within a chainable block a fragment joins the
    chain above when their x-ranges overlap by half the narrower's width, its box sits within _CHAIN_GAP
    of a line height below the chain's box (stacked fragments touch or overlap), it is no wider than 1.5x
    the chain (a continuation never much exceeds the cell it wraps in, Nelly's next row label under a
    short one), the chain is under _CHAIN_MAX deep, and its own baseline carries no pure-figures line
    elsewhere in the block (those are its row's figures -- Morrow Bank packs label rows 11pt apart with
    each row's figures on its own label's baseline). Chains keep top-to-bottom text order."""
    bands: list[list] = []  # [yc, [bbs]]
    for bb, _ in lines:
        band = next((b for b in bands if abs(b[0] - (bb[1] + bb[3]) / 2) <= 2.5), None)
        if band is None:
            bands.append([(bb[1] + bb[3]) / 2, [bb]])
        else:
            band[1].append(bb)
    side_by_side = any(any(b[2] <= o[0] for b in bbs for o in bbs if b is not o) for _, bbs in bands)
    if not (side_by_side or block_w <= 0.15 * page_w):
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
            lines.append((yc, [(x0, word)]))
        else:
            line[1].append((x0, word))
    return "\n".join(_WS.sub(" ", _LEADERS.sub(" ", " ".join(w for _, w in sorted(ws)))).strip() for _, ws in sorted(lines))


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
