"""Which pages hold the section? Deterministic keyword scoring, no LLM.

# ponytail: keyword scoring; LLM-over-TOC fallback if this misses

Scoring: distinct keywords matched (not raw counts -- a prose page saying "income
statement" five times is still prose), +5 for a keyword in the page *heading* (first 150
chars), + the number of schema field synonyms on the page, times digit density so tables
beat text; multi-year / quarterly / parent-company headings are penalised x0.1. On Atlas Copco AR 2025
this puts the consolidated income statement (p.106) first; raw counting ranked it 13th
behind the segment overview.

Next for a teammate: (1) parse the table of contents on the first ~5 pages for the
section title + page number and boost that page; (2) prefer pages whose neighbours also
score (statements span 2 pages); (3) per-schema "title" keyword that must appear in the
heading, for notes that share vocabulary with the primary statements.
"""

import re

HEADING_CHARS = 150
YEARS = re.compile(r"\b20\d\d\b")
QUARTER = re.compile(r"\bq[1-4]\b")
BOILERPLATE_SHARE = 0.10  # a line on >10% of pages is a running header/footer/nav, not content


def strip_boilerplate(texts: list[str]) -> list[str]:
    """Drop lines that repeat across many pages (Saab SV prints a 20-line nav bar on every page,
    which otherwise eats the heading window). Page numbers survive because they differ per page."""
    from collections import Counter
    freq = Counter(line for t in texts for line in set(t.splitlines()))
    limit = max(3, BOILERPLATE_SHARE * len(texts))
    return ["\n".join(l for l in t.splitlines() if freq[l] <= limit) for t in texts]


PROMPT_BUDGET = 14000  # chars of page text per LLM call; qwen3:8b runs with a 16k context and thinks out loud before the JSON


def candidate_pages(texts: list[str], schema: dict, top_n: int = 8) -> list[int]:
    """1-based page numbers, best first. The page after the best one is always second (statements span two
    pages: EPS sits on the second), then pages are dropped from the tail until the text fits PROMPT_BUDGET."""
    keywords = [k.lower() for k in schema.get("keywords", [])]
    excluded = [k.lower() for k in schema.get("exclude_keywords", [])]  # "parent company", "five-year summary"
    synonyms = sorted({s.lower() for f in schema.get("fields", []) for s in f.get("synonyms", [])})
    scored = []
    for i, text in enumerate(strip_boilerplate(texts)):
        low = " ".join(text.lower().split())  # ABB breaks "Income / Statements" across lines; it must still match "income statement"
        head = low[:HEADING_CHARS]
        distinct = sum(k in low for k in keywords)
        if not distinct:
            continue
        heading = any(k in head for k in keywords)
        fields = sum(s in low for s in synonyms)  # the statement names most of its rows; a currency note or a liabilities table does not
        density = min(sum(c.isdigit() for c in text) / max(len(text), 1), 0.2)  # tables ~0.15-0.3, prose ~0.01; capped so summaries don't win on digits
        summary = len(set(YEARS.findall(head))) >= 3 or QUARTER.search(head)  # "2023 2022 2021" / "q1 2024 q2 2024": multi-year or quarterly table
        penalty = 0.1 if summary or any(k in head for k in excluded) else 1  # Saab SV: parent-company statement outranked the group one
        scored.append(((distinct + 5 * heading + fields) * (1 + 5 * density) * penalty, i + 1))
    scored.sort(key=lambda s: (-s[0], s[1]))
    pages = [page for _, page in scored[:top_n]]
    if pages and pages[0] < len(texts):
        pages = [pages[0], pages[0] + 1] + [p for p in pages[1:] if p != pages[0] + 1]
    while len(pages) > 2 and sum(len(texts[p - 1]) for p in pages) > PROMPT_BUDGET:
        pages.pop()
    return pages
