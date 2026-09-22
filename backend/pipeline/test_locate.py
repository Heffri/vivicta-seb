"""locate.py self-check: the candidate window's structural invariants. Run: python -m pipeline.test_locate

Covers the two-shape contract of candidate_pages (v123): the forced companion page, and the budget
rule -- PROMPT_BUDGET bounds only the window prefix (what extract() ever reads as full text, its
pages[:4]); every top_n-scored page stays in the list for two-pass page selection's snippets, so an
oversized page is demoted past the window, never dropped (the ctt/humana shape: label page ranked #2-#3
cut by a whole-list trim no full-text reader was ever going to read).
"""
import json
import pathlib
import sys

from . import locate

SCHEMA = {"keywords": ["borrowings"], "fields": [{"key": "t", "synonyms": ["total borrowings"]}]}


def check(cond, msg):
    if not cond:
        print(f"locate self-check FAILED: {msg}")
        sys.exit(1)


def test_companion_is_second():
    texts = [""] * 6
    texts[0] = "Borrowings note\n" + "total borrowings 5\n" + "z " * 300
    texts[4] = "borrowings table\n" + "z " * 300
    pages = locate.candidate_pages(texts, SCHEMA)
    check(pages and pages[0] == 1 and pages[1] == 2, f"companion rule: expected [1, 2, ...], got {pages}")


def test_no_scored_page_dropped_for_budget():
    # ctt's shape: the top-scored pages are huge, later-scored pages small. The old whole-list trim
    # popped the small ones (red, v123); they must stay in the list for pass-1's snippets.
    texts = [""] * 8
    texts[0] = "Borrowings note\n" + "x " * 3500  # ~7k chars, scores
    texts[2] = "borrowings table total borrowings 5\n" + "y " * 3300  # ~6.6k chars, scores higher
    texts[4] = "borrowings\n" + "z " * 800  # small, scores
    texts[6] = "borrowings\n" + "w " * 800  # small, scores
    pages = locate.candidate_pages(texts, SCHEMA)
    for p in (1, 3, 5, 7):
        check(p in pages, f"budget demote-not-drop: scored page {p} missing from {pages}")


def test_window_prefix_fits_budget_unless_two():
    # The pages extract() reads as full text (the first WINDOW_PAGES) fit PROMPT_BUDGET whenever the
    # list is longer than 2; the floor is 2 because the companion rule needs a pair, oversized or not.
    texts = [""] * 10
    for n, i in enumerate((0, 2, 4, 6, 8)):  # distinct lines: strip_boilerplate drops a line on >10% of pages
        texts[i] = f"borrowings note {n}\n" + chr(97 + n) * 400
    pages = locate.candidate_pages(texts, SCHEMA)
    if len(pages) > 2:
        window = pages[: min(len(pages), locate.WINDOW_PAGES)]
        total = sum(len(texts[p - 1]) for p in window)
        check(total <= locate.PROMPT_BUDGET, f"window prefix {window} sums {total} > PROMPT_BUDGET")
    check(len(pages) >= 2, f"a scored report must keep at least the companion pair, got {pages}")


def test_balance_sheet_page_joins_last():
    # v139 flerie/kabe/hansa shape: a balance-sheet page carrying no debt keyword (noscore, would-be
    # unreachable) joins the candidate list as its last entry -- appended, never ranked, so scored
    # pages keep their places and the full-text window prefix is untouched.
    texts = [""] * 5
    texts[0] = "Borrowings note\n" + "total borrowings 5\n" + "z " * 300
    texts[3] = "Balansräkning för koncernen\nMateriella anläggningstillgångar 10\nSumma tillgångar 100\n" + "q " * 100
    pages = locate.candidate_pages(texts, SCHEMA)
    check(pages and pages[0] == 1, f"companion must not outrank the scored page, got {pages}")
    check(pages[-1] == 4, f"balance-sheet page appended last, got {pages}")


def test_parent_and_summary_balance_sheets_not_companions():
    # The parent-company statement and the five-year summary both print a balance sheet; neither is
    # the group one the debt note ties to, and v123 measured BS title words crowding ranked pages out.
    texts = [""] * 6
    texts[0] = "Borrowings note\n" + "total borrowings 5\n" + "z " * 300
    texts[2] = "Balansräkning för moderbolaget\nSumma tillgångar 100\n" + "q " * 100
    texts[4] = "Femårsöversikt balansräkning 2025 2024 2023 2022 2021\nSumma tillgångar 100\n" + "q " * 100
    pages = locate.candidate_pages(texts, SCHEMA)
    check(3 not in pages and 5 not in pages, f"parent/summary BS pages must not join the window, got {pages}")


def test_no_bare_liability_class_keywords():
    # v163: b29c4b0 added the bare keyword "financial liabilities" to the debt schema. It heads
    # every fair-value and financial-instruments note, so those pages crowded the real maturity
    # note out of the first windows. Measured over the 106 labelled debt reports, the labelled
    # page sat in the top 4 of the candidates for 80 of them before that keyword and 72 after;
    # narrowing it to the phrase "maturity of financial liabilities" scores 83.
    #
    # A page-ranking fixture cannot catch this -- the crowding is competition among a real
    # report's hundred-odd pages, and any three-page fixture ranks the maturity note first
    # whichever keyword is in the list (tried, it passed with the bad keyword in place). So the
    # guard is on the vocabulary itself: these terms name a balance-sheet line item, not a
    # maturity table, and belong in a phrase or not at all.
    bare = {"financial liabilities", "lease liabilities", "maturity", "thereafter", "liabilities"}
    for schema_name in ("debt_maturity",):
        kws = {k.lower() for k in json.loads(
            (pathlib.Path(__file__).resolve().parents[1] / "schemas" / f"{schema_name}.json").read_text(
                encoding="utf-8"))["keywords"]}
        check(not (kws & bare), f"{schema_name}: bare keyword(s) {sorted(kws & bare)} -- use a phrase")


def test_amd_item_8_statement_beats_supplementary_label():
    """AMD FY2025's printed p.60 (PDF p.72) is an income statement, not an excluded supplement.

    The Item 8 heading contains the US 10-K boilerplate ``supplementary data`` before the
    actual ``Consolidated Statements of Operations`` title.  It must retain the ordinary
    heading/table score, otherwise ten weaker discussion pages crowd the statement out of
    the top-ten candidate list.
    """
    schema = json.loads((pathlib.Path(__file__).resolve().parents[1] / "schemas" / "income_statement.json").read_text(
        encoding="utf-8"))
    # Compact fixture from AMD FY2025 PDF p.72 (printed p.60).  The ten preceding pages
    # model the discussion/note pages that really outranked it before this regression fix.
    decoys = [
        f"Management discussion {n}\nNet revenue {100 + n} 90\nGross profit {80 + n} 70\n"
        f"Operating income {60 + n} 50\nProfit before tax {40 + n} 30\n"
        for n in range(10)
    ]
    amd_statement = (
        "ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA\n"
        "Advanced Micro Devices, Inc.\nConsolidated Statements of Operations\n"
        "Year Ended December 27, 2025 December 28, 2024\n"
        "Net revenue $ 34,639 $ 25,785\nCost of sales 16,456 12,114\n"
        "Gross profit 17,152 12,725\nOperating income 3,694 1,900\n"
        "Other income (expense), net 577 181\n"
        "Income from continuing operations before income taxes 4,140 1,989\n"
        "Income tax provision (benefit) (103) 381\nNet income $ 4,335 $ 1,641\n"
    )
    pages = locate.candidate_pages([*decoys, amd_statement], schema, fiscal_year=2025)
    check(11 in pages, f"AMD Item 8 statement was excluded from candidates: {pages}")


def main():
    test_companion_is_second()
    test_no_scored_page_dropped_for_budget()
    test_window_prefix_fits_budget_unless_two()
    test_balance_sheet_page_joins_last()
    test_parent_and_summary_balance_sheets_not_companions()
    test_no_bare_liability_class_keywords()
    test_amd_item_8_statement_beats_supplementary_label()
    print("locate self-check ok")


if __name__ == "__main__":
    main()
