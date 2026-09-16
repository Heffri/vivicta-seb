"""PDF -> text, one string per page (pymupdf).

Table rows are kept whole: a text layer that prints a row label on one line and its figures on the
next is rebuilt from positioned text -- block-local first (prose order is untouched), page-wide from
words only when that still leaves rows open. Prose pages pass through byte-identical to get_text().
Column-major layers (Arion Bank prints every figure first, then every label) go through the word-level
rebuild too.

Next for a teammate: scanned reports need an OCR fallback (pymupdf + tesseract via
`page.get_textpage_ocr()`).
"""
import re

import pymupdf

_WS = re.compile(r"\s+")
_DIGIT_SPACE = re.compile(r" (?=\d)|(?<=\d) ")  # any space touching a digit
_CHARMAP = str.maketrans({"\u00a0": " ", "\u202f": " ", "\u2013": "-", "\u2212": "-"})  # NBSP, narrow NBSP, en dash, minus


PARSER_VERSION = 3  # bump when page_text changes so kb.save_report rewrites cached pages.jsonl
NUMERIC_RUN = 12  # consecutive letterless lines: a column-major text layer (Arion Bank prints every figure first, then every label, in no order)
_LEADERS = re.compile(r"(?:\s*\.){3,}")


def page_texts(pdf_path) -> list[str]:
    """0-based list; page n (1-based) is texts[n-1]."""
    with pymupdf.open(pdf_path) as doc:
        return [page_text(page) for page in doc]


def page_text(page) -> str:
    """Plain text; a text layer that splits table rows (a row label on one line, its figures on the next) gets its
    lines rebuilt so each printed row is one line. Prose-only pages are returned as get_text() wrote them."""
    text = page.get_text()
    if _numeric_run(text) >= NUMERIC_RUN:
        return _lines_from_words(page)
    if not _split_rows(text):
        return text
    merged = _merge_baselines(page)
    leftover = _split_rows(merged)
    if leftover:  # rows still open: their cells sit in separate blocks. Word-level merges those, but also merges
        alt = _lines_from_words(page)  # two tables printed side by side (AQ) -- take it only when it closes more rows
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
    Blocks keep their reading order, so a prose paragraph's lines (distinct baselines) come out as before."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        rows: list[list] = []  # [y-center, height, [(x0, text)]]
        for line in block["lines"]:
            txt = "".join(s["text"] for s in line["spans"])
            if not txt.strip():
                continue
            yc, h = (line["bbox"][1] + line["bbox"][3]) / 2, line["bbox"][3] - line["bbox"][1]
            row = next((r for r in rows if abs(r[0] - yc) <= max(h, r[1]) / 2), None)
            if row is None:
                rows.append([yc, h, [(line["bbox"][0], txt)]])
            else:
                row[2].append((line["bbox"][0], txt))
        out += [_WS.sub(" ", " ".join(t for _, t in sorted(xs))).strip() for _, _, xs in sorted(rows)]
    return "\n".join(l for l in out if l)


def _numeric_run(text: str) -> int:
    best = run = 0
    for line in text.splitlines():
        if line.strip():
            run = 0 if re.search(r"[^\W\d_]", line) else run + 1
            best = max(best, run)
    return best


def _lines_from_words(page) -> str:
    """Words sharing a baseline (within half a word height), left to right; dot leaders dropped."""
    lines: list[tuple[float, list]] = []
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        yc, tol = (y0 + y1) / 2, (y1 - y0) / 2
        line = next((l for l in lines if abs(l[0] - yc) <= tol), None)
        if line is None:
            lines.append((yc, [(x0, word)]))
        else:
            line[1].append((x0, word))
    return "\n".join(_WS.sub(" ", _LEADERS.sub(" ", " ".join(w for _, w in sorted(ws)))).strip() for _, ws in sorted(lines))


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
