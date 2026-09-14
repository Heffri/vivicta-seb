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
