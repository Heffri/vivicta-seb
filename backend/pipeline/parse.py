"""PDF -> text, one string per page (pymupdf).

Native text first, baseline reconstruction for column-major text, and selective
local OCR for image/outlined pages. OCR text still needs numerical verification.
"""
import os
import re
from pathlib import Path

import pymupdf

_WS = re.compile(r"\s+")
_DIGIT_SPACE = re.compile(r" (?=\d)|(?<=\d) ")  # any space touching a digit
_CHARMAP = str.maketrans({"\u00a0": " ", "\u202f": " ", "\u2013": "-", "\u2212": "-"})  # NBSP, narrow NBSP, en dash, minus


PARSER_VERSION = 3  # includes selective OCR; never reuse pre-OCR empty pages
NUMERIC_RUN = 12  # consecutive letterless lines: a column-major text layer (Arion Bank prints every figure first, then every label, in no order)
_LEADERS = re.compile(r"(?:\s*\.){3,}")


class OCRUnavailable(RuntimeError):
    pass


def ocr_settings():
    return {"language": os.getenv("OCR_LANGUAGE", "eng+swe"),
            "tessdata": str(Path(os.getenv("TESSDATA_PREFIX") or Path(__file__).resolve().parents[2] / "data" / "tessdata").resolve())}


def page_texts(pdf_path, metadata: dict | None = None) -> list[str]:
    """0-based list; page n (1-based) is texts[n-1]."""
    if metadata is not None:
        metadata.update(ocr_pages=[], ocr_settings=ocr_settings())
    with pymupdf.open(pdf_path) as doc:
        return [page_text(page, metadata) for page in doc]


def page_text(page, metadata: dict | None = None) -> str:
    """Plain text; when the text layer is column-major, lines rebuilt from word coordinates instead (label and its
    figures on one line). Only then: words on a baseline also merge two tables printed side by side (AQ)."""
    text = page.get_text()
    if len(re.sub(r"\W", "", text)) < 20 and (page.get_images() or len(page.get_drawings()) > 100):
        # PyMuPDF bundles the OCR engine. Language files stay local, no report upload.
        settings = ocr_settings()
        tessdata, language = Path(settings["tessdata"]), settings["language"]
        missing = [lang for lang in language.split("+") if not (tessdata / f"{lang}.traineddata").is_file()]
        if missing:
            raise OCRUnavailable("Scanned PDF needs OCR language files. Run python scripts/setup_ocr.py (missing: " + ", ".join(missing) + ").")
        tp = page.get_textpage_ocr(language=language, dpi=200, full=True, tessdata=str(tessdata))
        if metadata is not None:
            metadata.setdefault("ocr_pages", []).append(page.number + 1)
        return _lines_from_words(page, tp)
    return text if _numeric_run(text) < NUMERIC_RUN else _lines_from_words(page)


def _numeric_run(text: str) -> int:
    best = run = 0
    for line in text.splitlines():
        if line.strip():
            run = 0 if re.search(r"[^\W\d_]", line) else run + 1
            best = max(best, run)
    return best


def _lines_from_words(page, textpage=None) -> str:
    """Words sharing a baseline (within half a word height), left to right; dot leaders dropped."""
    lines: list[tuple[float, list]] = []
    for x0, y0, x1, y1, word, *_ in page.get_text("words", textpage=textpage):
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
