"""Self-check for page_text table-row reconstruction. Run: python -m pipeline.test_parse"""
import pymupdf

from . import parse as p


def _page(items):
    """Synthetic page: ("box", (x0, y0, x1, y1), text) is a prose block, ("text", (x, y), text) positioned words."""
    doc = pymupdf.open()
    page = doc.new_page()
    for kind, at, s in items:
        if kind == "box":
            page.insert_textbox(pymupdf.Rect(*at), s, fontsize=11)
        else:
            page.insert_text(pymupdf.Point(*at), s, fontsize=11)
    return page


def demo():
    # One page: a prose paragraph, then a table row the text layer splits (label, note ref and figures each
    # printed on their own line). The row must come out whole; the paragraph must stay as it was.
    page = _page([
        ("box", (72, 72, 523, 200), "The Group delivers compression solutions worldwide. Revenue grew in every "
                                    "segment during the year, driven by service volumes and a strong order backlog."),
        ("text", (72, 250), "Operating profit"),
        ("text", (300, 250), "5"),
        ("text", (360, 250), "1,234"),
        ("text", (430, 250), "1,123"),
    ])
    text = p.page_text(page)
    lines = text.splitlines()
    assert lines[0].startswith("The Group delivers") and lines[1].startswith("during the year"), lines[:3]  # prose order kept
    assert lines[2] == "Operating profit 5 1,234 1,123", lines[2]  # the printed row is one line again
    assert p._split_rows(text) == 0, text
    assert p.quote_on_page("Operating profit 5 1,234 1,123", text), text  # a quote read off the row still verifies

    # a prose-only page passes through byte-identical: the rebuild never fires on it
    page = _page([
        ("box", (72, 72, 523, 300), "Notes to the parent company's financial statements follow the audited "
                                    "consolidated accounts. All amounts are stated in SEK unless otherwise noted."),
    ])
    assert p.page_text(page) == page.get_text()

    # a column-major layer (every figure first, then every label) still goes through the word-level rebuild
    items = [("text", (72, 100 + 14 * i), str(1000 + i)) for i in range(12)]
    items += [("text", (300, 100 + 14 * i), f"Row label {i}") for i in range(12)]
    text = p.page_text(_page(items))
    assert "1003 Row label 3" in text, text  # each figure lands on the line of its label

    print("parse self-check ok")


if __name__ == "__main__":
    demo()
