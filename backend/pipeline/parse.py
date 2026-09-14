"""PDF -> text, one string per page (pymupdf).

Next for a teammate: plain `page.get_text()` loses table structure, so a row label
and its numbers can land on separate lines. Try `page.find_tables()` or
`get_text("blocks")` sorted by (y, x) so each table row becomes one line -- that
helps both keyword locating and verbatim quote matching. Scanned reports need an
OCR fallback (pymupdf + tesseract via `page.get_textpage_ocr()`).
"""
import re

import pymupdf

_WS = re.compile(r"\s+")
_DIGIT_SPACE = re.compile(r" (?=\d)|(?<=\d) ")  # any space touching a digit
_CHARMAP = str.maketrans({"\u00a0": " ", "\u202f": " ", "\u2013": "-", "\u2212": "-"})  # NBSP, narrow NBSP, en dash, minus


def page_texts(pdf_path) -> list[str]:
    """0-based list; page n (1-based) is texts[n-1]."""
    with pymupdf.open(pdf_path) as doc:
        return [page.get_text() for page in doc]


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
_GAP = r"[\s\d,.()\-]{0,24}?"  # what may sit between two quote tokens on the page: a note reference like "6,7" or Skanska's "8, 9, 10, 33, 38"


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
