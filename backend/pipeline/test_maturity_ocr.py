"""Offline component/OCR checks: python -m pipeline.test_maturity_ocr."""
from copy import deepcopy
import json
import os
import re
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

import pymupdf

from . import maturity, parse


def main():
    schema = json.loads((Path(__file__).parents[1] / "schemas/debt_maturity.json").read_text(encoding="utf8"))
    text = "Group borrowings\n2025 MSEK\nTotal 100\n2026 10\n2027 20\n2028 30\n2031 40"
    source = lambda q: {"page": 1, "quote": q}
    raw = {"scope": "group", "basis": "carrying_amount", "debt_scope": "Group borrowings", "context_source": source("Group borrowings"), "warnings": [], "fields": []}
    for sf, amounts in zip(schema["fields"], [[(100, "Total 100")], [(10, "2026 10")], [(20, "2027 20"), (30, "2028 30")], [(40, "2031 40")]]):
        raw["fields"].append(dict(key=sf["key"], unit="MSEK", period="2025", raw_label=sf["label"],
                                  components=[{"value": v, "source": source(q)} for v, q in amounts]))
    run = lambda r: maturity.validate(r, [text], [1], schema, {"fiscal_year": 2025})
    result = run(raw)
    assert result["fields"][2]["value"] == 50 and result["checks"][0]["passed"]
    assert len(result["fields"][2]["components"]) == 2
    split = deepcopy(raw)
    second = deepcopy(split["fields"][2])
    split["fields"][2]["components"] = second["components"][:1]
    second["components"] = second["components"][1:]
    split["fields"].append(second)
    assert run(split)["fields"][2]["value"] == 50  # repeated field keys must not discard earlier components
    incomplete = deepcopy(raw)
    incomplete["fields"][2]["components"].pop()
    assert all(f["value"] is None for f in run(incomplete)["fields"][1:])
    for mutation in ("duplicate", "bad_number", "bad_quote", "wrong_year", "wrong_scope", "cash_flows", "mixed_units", "empty"):
        bad = deepcopy(raw)
        f = bad["fields"][2]
        if mutation == "duplicate": f["components"].append(deepcopy(f["components"][0]))
        if mutation == "bad_number": f["components"][0]["value"] = 200
        if mutation == "bad_quote": f["components"][0]["source"]["quote"] = "2027 200"
        if mutation == "wrong_year": f["period"] = "2024"
        if mutation == "wrong_scope": bad["scope"] = "lease_only"
        if mutation == "cash_flows": bad["basis"] = "contractual_cash_flows"
        if mutation == "mixed_units": f["unit"] = "MEUR"
        if mutation == "empty": f["components"] = []
        assert run(bad)["fields"][2]["value"] is None, mutation
    assert not maturity.verified_source(source("otal 100"), [text], [1])
    page = Mock()
    page.get_images.return_value = []
    page.get_drawings.return_value = []
    page.get_links.return_value = []
    page.get_text.return_value = "Revenue 100 90"
    assert parse.page_text(page) == "Revenue 100 90"
    page.get_textpage_ocr.assert_not_called()
    with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"TESSDATA_PREFIX": root, "OCR_LANGUAGE": "eng"}):
        page.get_text.return_value = ""
        page.get_images.return_value = []
        page.get_drawings.return_value = [None] * 101  # outlined text, not an embedded image
        try:
            parse.page_text(page)
            raise AssertionError("missing OCR data must not cache empty text")
        except parse.OCRUnavailable:
            pass
        (Path(root) / "eng.traineddata").touch()
        page.get_text.side_effect = lambda kind=None, **kw: [(0, 0, 40, 10, "Revenue", 0, 0, 0), (45, 0, 60, 10, "100", 0, 0, 1)] if kind == "words" else ""
        assert parse.page_text(page) == "Revenue 100"
        assert page.get_textpage_ocr.call_args.kwargs["full"] is True
    print("maturity component and selective OCR checks passed")


def _image_page(doc, text, width=300, height=100):
    """A page with no text layer at all: `text` is rendered on a throwaway page and inserted as a
    raster image, the same shape a scanned report page has -- real OCR (not a mock) can recover it."""
    page = doc.new_page(width=width, height=height)
    src = pymupdf.open()
    src_page = src.new_page(width=width, height=height)
    src_page.insert_text((10, height / 2), text, fontsize=20)
    page.insert_image(page.rect, pixmap=src_page.get_pixmap(dpi=200))
    src.close()
    return page


def _text_page(doc, text, width=300, height=100):
    page = doc.new_page(width=width, height=height)
    page.insert_text((10, height / 2), text, fontsize=11)
    return page


def text_pdf_image_cover_without_tessdata():
    """w204: a real text PDF is classified as a book, not one page at a time.

    An image-only cover must not make registration depend on OCR language files when the body has
    a substantial text layer.  The cover stays blank/pending for possible on-demand OCR.
    """
    with tempfile.TemporaryDirectory() as root:
        root = Path(root)
        doc = pymupdf.open()
        _image_page(doc, "Annual report cover")
        body = "Annual report financial statements borrowings and maturity information " * 5
        for n in range(2, 6):
            _text_page(doc, f"Page {n} {body}", width=2600)
        path = root / "text-with-image-cover.pdf"
        doc.save(path)
        doc.close()

        missing = root / "no-tessdata"
        with patch.dict(os.environ, {"TESSDATA_PREFIX": str(missing), "OCR_LANGUAGE": "eng+swe"}):
            meta = {}
            texts = parse.page_texts(path, meta)
        assert texts[0] == "", repr(texts[0])
        assert meta["ocr_pending"] == [1], meta
        assert meta["ocr_unavailable"] == [], meta
        assert all("financial statements" in text for text in texts[1:]), texts[1:]
    print("text PDF with image-only cover and no OCR files self-check ok")


def _bounded_fixture(tmp_path):
    """16 pages: 3 (front matter), 14/15/16 (an outline entry's ±1 window) and 11 (neither) are
    scanned; page 15's own outline title carries a debt_maturity toc_keyword ("Borrowings").
    Everything else has a normal text layer. v191."""
    doc = pymupdf.open()
    _text_page(doc, "Cover page")
    _text_page(doc, "Table of contents")
    _image_page(doc, "Front matter scan")            # 3: within FRONT_PAGES
    for n in range(4, 11):
        _text_page(doc, f"Body text page {n}")        # 4-10: ordinary text
    _image_page(doc, "Should stay pending")           # 11: outside every window
    _text_page(doc, "Body text page 12")
    _text_page(doc, "Body text page 13")
    _image_page(doc, "Borrowings prior page")         # 14: toc hit - 1
    _image_page(doc, "Borrowings maturity table", width=420)  # 15: the toc hit itself
    _image_page(doc, "Borrowings next page")          # 16: toc hit + 1
    doc.set_toc([[1, "Note 24 Borrowings", 15]])
    path = tmp_path / "scanned.pdf"
    doc.save(path)
    doc.close()
    return path


def bounded_ocr():
    """v191: registration OCR is bounded to the pages a debt-maturity locate pass could reach, a
    page budget refuses a synchronous pass that is bigger than that, ocr="full" is an unconditional
    opt-in, and a page left ocr_pending can be OCR'd individually later (app.py's on-demand top-up
    before /extract uses exactly this: a bare parse.page_text() call on the one page it needs).
    Exercises real OCR (not a mocked textpage, unlike main()'s checks above) to prove the recovered
    text actually lands on the right page -- skipped, not red, on a clone that never ran
    scripts/setup_ocr.py."""
    if not parse.ocr_ready():
        print("bounded OCR self-check skipped: OCR language files missing -- run python scripts/setup_ocr.py")
        return
    with tempfile.TemporaryDirectory() as root:
        path = _bounded_fixture(Path(root))

        meta = {}
        texts = parse.page_texts(path, meta)
        assert meta["ocr_pages"] == [3, 14, 15, 16], meta["ocr_pages"]  # front matter + toc hit +-1
        assert meta["ocr_pending"] == [11], meta["ocr_pending"]  # scanned, but outside every window
        assert texts[10] == "", repr(texts[10])  # pending page comes back blank, not OCR'd
        assert "Front matter scan" in texts[2], texts[2]
        assert "Borrowings prior page" in texts[13], texts[13]
        assert "Borrowings maturity table" in texts[14], texts[14]
        assert "Borrowings next page" in texts[15], texts[15]
        assert texts[0].strip() == "Cover page"  # an ordinary text-layer page is untouched

        with patch.object(parse, "OCR_PAGE_BUDGET", 3):  # the bounded set alone (4 pages) already exceeds it
            try:
                parse.page_texts(path, {})
                raise AssertionError("bounded OCR over budget must raise")
            except parse.OCRBudgetExceeded as e:
                assert e.pages_needed == 5, e.pages_needed  # every scanned page report-wide, not just the bounded set
                assert re.search(r"~\d+ min for 5 pages", str(e)), str(e)

            full_meta = {}  # explicit opt-in bypasses the same budget entirely
            full_texts = parse.page_texts(path, full_meta, ocr="full")
            assert full_meta["ocr_pages"] == [3, 11, 14, 15, 16], full_meta["ocr_pages"]
            assert full_meta["ocr_pending"] == []
            assert "Should stay pending" in full_texts[10], full_texts[10]

        with pymupdf.open(path) as doc:  # the on-demand top-up primitive: page_text() alone, no ocr_allowed=False gate
            assert "Should stay pending" in parse.page_text(doc[10])
    print("bounded OCR self-check ok")


if __name__ == "__main__":
    main()
    text_pdf_image_cover_without_tessdata()
    bounded_ocr()
