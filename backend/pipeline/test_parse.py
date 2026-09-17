"""Self-check for page_text table-row reconstruction. Run: python -m pipeline.test_parse"""
import re

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


NAV = ["Introduction", "Governance", "Reports", "Notes", "Sustainability", "Risk", "Control", "Audit",
       "Board", "CEO", "Strategy", "Values", "Market", "Contact"]


def _word_row(items, x, y, label, figure_x, figures):
    items.append(("text", (x, y), label))
    for j, fig in enumerate(figures.split()):
        items.append(("text", (figure_x + 70 * j, y), fig))


def _driver(items, y):
    """A column-major mini table -- every figure printed, then every label (the Arion Bank layer): twelve
    letterless lines in a row, so the page takes the word-level rebuild path these tests need."""
    words = ["Alfa row", "Beta row", "Gamma row", "Delta row", "Epsilon row", "Zeta row",
             "Eta row", "Theta row", "Iota row", "Kappa row", "Lambda row", "Mu row"]
    for i in range(12):
        items.append(("text", (150, y + 14 * i), str(1000 + i)))
    for i, w in enumerate(words):
        items.append(("text", (330, y + 200 + 14 * i), w))


def case_sidebar(mod):
    # (a) body rows with a narrow navigation sidebar on shared baselines: the sidebar's items must not be
    # glued into the body's lines (Ratos' nav column lands mid-sentence in a page-wide merge).
    items = [("text", (40, 100 + 28 * i), w) for i, w in enumerate(NAV)]
    for i, (label, figures) in enumerate([("Total borrowings", "1,234 4,567 8,901 12,345"),
                                          ("Lease liabilities", "22 33 44 55"),
                                          ("Bonds and loans", "666 777 888 999")]):
        _word_row(items, 150, 100 + 28 * i, label, 300, figures)
    _driver(items, 300)
    lines = mod.page_text(_page(items)).splitlines()
    assert not any("Introduction" in l and "borrowings" in l for l in lines), lines[:6]  # sidebar stays out of the body
    assert any(l == "Total borrowings 1,234 4,567 8,901 12,345" for l in lines), lines  # rows still close
    assert any(l.strip() == "Introduction" for l in lines), lines[:3]  # and the sidebar itself survives


def case_full_width_table(mod):
    # (b) a full-width table (a label column plus four figure columns) must not be cut into columns: the
    # label side and the figure side share every baseline, which is one table's row grid, not two columns.
    items = []
    for i, label in enumerate(["Total borrowings", "Lease liabilities", "Bonds and loans", "Other loans",
                               "Customer finance", "Overdraft facility"]):
        _word_row(items, 60, 100 + 22 * i, label, 200, "1,234 4,567 8,901 12,345")
    _driver(items, 300)
    lines = mod.page_text(_page(items)).splitlines()
    for label in ("Total borrowings", "Overdraft facility"):
        want = f"{label} 1,234 4,567 8,901 12,345"
        assert any(l == want for l in lines), lines[:8]  # rows whole, labels with figures
    assert not any("1,234" in l and not re.search(r"[^\W\d_]", l) for l in lines), lines[:8]  # the table's own figures never appear without a label: not cut apart


def case_two_tables(mod):
    # (d) two small tables printed side by side, the right one's rows set 5pt below the left one's: inside
    # the word rebuild's baseline tolerance (so a page-wide merge interleaves the two tables' rows, Flerie's
    # assets/liabilities shape) but outside the column gate's (so they are two columns, not one row grid).
    items = []
    for i, (label, figures) in enumerate([("Assets total", "2,619 3,071"), ("Loans to units", "108 214"), ("Cash at hand", "540 865")]):
        _word_row(items, 60, 100 + 18 * i, label, 170, figures)
    for i, (label, figures) in enumerate([("Other liabilities", "7,0 11,8"), ("Leasing debt", "2,1 0,9"), ("Trade payables", "1,4 0,6")]):
        _word_row(items, 330, 105 + 18 * i, label, 450, figures)
    _driver(items, 300)
    lines = mod.page_text(_page(items)).splitlines()
    assert any(l == "Assets total 2,619 3,071" for l in lines), lines[:8]  # the left table's rows stay whole
    assert not any("Assets total" in l and "Other" in l for l in lines), lines[:8]  # and never share a line with the right table
    assert not any("payables" in l and "2,619" in l for l in lines), lines[:8]


def case_stacked_header_columns(mod):
    # (e) three adjacent wrapped header cells (Ependion p.155's maturity table, v049b): each cell's own
    # stacked fragments must chain into one phrase, and neighboring cells must never interleave. Pymupdf
    # groups these fragments into blocks by its own layout heuristic, which this test does not control and
    # which changed between pymupdf releases for this exact page (one block under 1.27.2.3, five under
    # 1.28.2) -- the assertions hold on whatever blocks this pymupdf happens to produce, on either release.
    items = [
        ("text", (60, 450), "Total assets"), ("text", (60, 463), "1,234"),  # a plain split row, so the
        # page's raw text already has one open row and page_text takes the _merge_baselines path at all
        ("text", (100, 300), "Within 12"), ("text", (100, 313), "months"),
        ("text", (175, 287), "Between"), ("text", (178, 300), "1 and"), ("text", (176, 313), "2 years"),
        ("text", (240, 287), "Between"), ("text", (243, 300), "2 and"), ("text", (241, 313), "3 years"),
        ("text", (300, 313), "Total"),
    ]
    text = mod.page_text(_page(items))
    assert "Within 12 months" in text, text  # a cell split across blocks still chains (col 1)
    assert "Between 1 and 2 years" in text, text  # col 2's own three fragments, not just two of them
    assert "Between 2 and 3 years Total" in text, text  # col 3 plus the trailing Total cell
    assert "Between Between" not in text, text  # the two cells' first lines must never share a row
    assert "1 and 2 and" not in text, text  # nor their second lines


def columns(mod=p):
    """v049: the word-level rebuild is column-aware. Three layouts the page-wide baseline merge got wrong."""
    case_sidebar(mod)
    case_full_width_table(mod)
    case_two_tables(mod)
    print("parse column self-check ok")


def stacking(mod=p):
    """v049b: stacked-cell chaining does not depend on pymupdf's own block partition."""
    case_stacked_header_columns(mod)
    print("parse stacking self-check ok")


if __name__ == "__main__":
    demo()
    columns()
    stacking()
