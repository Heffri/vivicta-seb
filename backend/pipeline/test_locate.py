"""locate.py self-check: the candidate window's structural invariants. Run: python -m pipeline.test_locate

Covers the two-shape contract of candidate_pages (v123): the forced companion page, and the budget
rule -- PROMPT_BUDGET bounds only the window prefix (what extract() ever reads as full text, its
pages[:4]); every top_n-scored page stays in the list for two-pass page selection's snippets, so an
oversized page is demoted past the window, never dropped (the ctt/humana shape: label page ranked #2-#3
cut by a whole-list trim no full-text reader was ever going to read).
"""
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


def main():
    test_companion_is_second()
    test_no_scored_page_dropped_for_budget()
    test_window_prefix_fits_budget_unless_two()
    print("locate self-check ok")


if __name__ == "__main__":
    main()
