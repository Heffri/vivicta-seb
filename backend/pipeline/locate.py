"""Which pages hold the section? Deterministic keyword scoring, no LLM.

# ponytail: keyword scoring; LLM-over-TOC fallback if this misses

Scoring: distinct keywords matched (not raw counts -- a prose page saying "income
statement" five times is still prose), +5 for a keyword in the page *heading* (first 150
chars), + the number of schema field synonyms on the page, times digit density so tables
beat text; multi-year / quarterly / parent-company headings are penalised x0.1. The report's
own table of contents is parsed first (see toc_targets) and the page it names gets the same
+5 tier -- a TOC entry names the section in the report's own voice, one strong bit of
evidence, but heading + TOC together must still beat either alone. On Atlas Copco AR 2025
this puts the consolidated income statement (p.106) first; raw counting ranked it 13th
behind the segment overview.

Next for a teammate: (1) prefer pages whose neighbours also score (statements span 2 pages);
(2) per-schema "title" keyword that must appear in the heading, for notes that share
vocabulary with the primary statements.
"""

import re

HEADING_CHARS = 150
YEARS = re.compile(r"\b20\d\d\b")
DATE = re.compile(r"\d{1,2}[/.]\d{1,2}[/.]20\d\d|20\d\d-\d\d-\d\d")
SPLIT_YEAR = re.compile(r"\b(20\d\d)/(?:20)?\d\d\b")  # Sectra "2025/2026 2024/2025": a broken fiscal year is one column, named by its first year
QUARTER = re.compile(r"\bq[1-4]\b|quarter|kvartal")
GROUP = re.compile(r"\b(group|koncern|consolidated)")
ENTITY = re.compile(r"moderbolag|parent")  # exclude_keywords naming the other entity, as opposed to a table type (segment, five-year)
BOILERPLATE_SHARE = 0.10  # a line on >10% of pages is a running header/footer/nav, not content


def strip_boilerplate(texts: list[str]) -> list[str]:
    """Drop lines that repeat across many pages (Saab SV prints a 20-line nav bar on every page,
    which otherwise eats the heading window). Page numbers survive because they differ per page."""
    from collections import Counter
    freq = Counter(line for t in texts for line in set(t.splitlines()))
    limit = max(3, BOILERPLATE_SHARE * len(texts))
    return ["\n".join(l for l in t.splitlines() if freq[l] <= limit and not TOC_LINE.search(l)) for t in texts]


TOC_LINE = re.compile(r"(?:[_.]\s*){3,}\d{1,3}\s*$")  # AAK's nav bar "Financial statements Group and Parent company_ _____124": leader dots + page number, differs per page


PROMPT_BUDGET = 14000  # chars of page text per LLM call; qwen3:8b runs with a 16k context and thinks out loud before the JSON

TOC_PAGES = 8  # contents live in the front matter (AAK's is pdf p.6)
TOC_MARK = re.compile(r"\bcontents\b|innehåll", re.I)  # the word on a contents page, not the entries
TOC_ENTRY = re.compile(r"^(.+?\S)\s*(?:[_.]\s*){2,}(\d{1,3})\s*$")  # AAK "AAK in brief________________7"
TOC_ENTRY_PLAIN = re.compile(r"^(.+?\S)\s{2,}(\d{1,3})\s*$")  # Atlas Copco "Business area: Vacuum Technique  25"
FOLIO = re.compile(r"^\s*(\d{1,3})\s*$")  # a line that is only the printed page number (AAK "145")
FOLIO_TAIL = re.compile(r"\s(\d{1,3})\s*$")  # a footer ending in it, "Atlas Copco Group 2025   2"


def _folios(text: str) -> set[int]:
    """Printed page numbers visible at the top/bottom edge of a page (its running folio)."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = set()
    for line in lines[:3] + lines[-3:]:
        m = FOLIO.match(line)
        if not m:
            m = FOLIO_TAIL.search(line)  # search: the number sits at the end of a footer line, not at the start
        if m:
            out.add(int(m.group(1)))
    return out


def _folio_offset(texts: list[str]) -> int | None:
    """printed page = pdf page + offset, one offset per report, voted across every page's folio.
    None when the report's own numbers don't agree (Ericsson prints none at the page edges): then
    the TOC can't be trusted to point at a pdf page and no boost is made."""
    from collections import Counter
    votes = Counter(i - c for i, t in enumerate(texts, 1) for c in _folios(t) if 1 <= c <= len(texts))
    if not votes:
        return None
    offset, n = votes.most_common(1)[0]
    return offset if n >= max(8, 0.08 * len(texts)) else None  # junk tails vote thinly everywhere


def toc_targets(texts: list[str], schema: dict) -> dict[int, str]:
    """pdf page -> the contents-line title naming it, for section pages the report's own TOC points at.
    Parsed from the raw front-matter text (strip_boilerplate drops TOC_LINE lines as scoring noise --
    this reads the same lines as signal first). Empty when there is no contents page, the title matches
    nothing, or printed pages can't be aligned to pdf pages: a wrong guess would boost a random page,
    so none is made."""
    hits: dict[int, str] = {}
    toc_page = next((t for t in texts[:TOC_PAGES] if TOC_MARK.search(" ".join(t.lower().split()))), None)
    offset = _folio_offset(texts)
    if toc_page is None or offset is None:
        return hits
    entries, prev = [], None  # Atlas Copco puts the number alone on the line after the title
    for line in toc_page.splitlines():
        line = line.strip()
        if not line:
            continue
        m = FOLIO.match(line)
        if m and prev and not prev[-1].isdigit():  # pairs only right after a title-looking line
            entries.append((prev, int(m.group(1))))
            prev = None
            continue
        m = TOC_ENTRY.match(line) or TOC_ENTRY_PLAIN.match(line)
        if m:
            entries.append((m.group(1), int(m.group(2))))
            prev = None
        else:
            prev = line
    words = [k.lower() for k in schema.get("keywords", []) + schema.get("toc_keywords", [])]
    excluded = [k.lower() for k in schema.get("exclude_keywords", [])]
    for title, printed in entries:
        page = printed + offset
        if not (1 <= page <= len(texts)) or printed not in _folios(texts[page - 1]):
            continue  # the target page doesn't carry that printed number: numbering drifts, no boost
        low = " ".join(title.lower().split())
        if any(k in low for k in words) and not any(k in low for k in excluded):
            hits.setdefault(page, low)
    return hits


def candidate_pages(texts: list[str], schema: dict, top_n: int = 8) -> list[int]:
    """1-based page numbers, best first. The page after the best one is always second (statements span two
    pages: EPS sits on the second), then pages are dropped from the tail until the text fits PROMPT_BUDGET."""
    keywords = [k.lower() for k in schema.get("keywords", [])]
    excluded = [k.lower() for k in schema.get("exclude_keywords", [])]  # "parent company", "five-year summary"
    synonyms = sorted({s.lower() for f in schema.get("fields", []) for s in f.get("synonyms", [])})
    toc = toc_targets(texts, schema)
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
        raw_head = " ".join(texts[i].lower().split())[:HEADING_CHARS]  # Medicover: the "5-year financial summary" title and its "2025" "2024" lines are on enough pages to be stripped as boilerplate
        years = [YEARS.findall(SPLIT_YEAR.sub(r"\1", DATE.sub("", h))) for h in (head, raw_head)]  # AQ prints the income statement and comprehensive income side by side, each headed "01/01/2025 31/12/2025 ...": dates, not a multi-year table
        summary = any(len(set(y)) >= 4 or len(y) >= 5 for y in years) or QUARTER.search(head)  # "2023 2022 2021" / "Oct-Dec 2025 Jul-Sep 2025 ...": multi-year or quarterly table
        group_at = (GROUP.search(head) or re.compile(r"$").search(head)).start()
        parent = any(k in head and (head.index(k) < group_at or not ENTITY.search(k)) for k in excluded)  # Pandox: "KONCERNEN 2024 Rörelsesegment" is a segment note whatever precedes it. Saab SV: parent-company statement outranked the group one;
        penalty = 0.1 if summary or parent else 1  # Vitrolife prints "Group | Parent Company" columns on one page: group first, so not a parent page
        scored.append(((distinct + 5 * heading + fields + 5 * (i + 1 in toc)) * (1 + 5 * density) * penalty, i + 1))
    scored.sort(key=lambda s: (-s[0], s[1]))
    pages = [page for _, page in scored[:top_n]]
    if pages and pages[0] < len(texts):
        pages = [pages[0], pages[0] + 1] + [p for p in pages[1:] if p != pages[0] + 1]
    while len(pages) > 2 and sum(len(texts[p - 1]) for p in pages) > PROMPT_BUDGET:
        pages.pop()
    return pages
