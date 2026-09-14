"""Which pages hold the section? Deterministic keyword scoring, no LLM.

# ponytail: keyword scoring; LLM-over-TOC fallback if this misses

Scoring: distinct keywords matched (not raw counts -- a prose page saying "income
statement" five times is still prose), a x10 bonus for a keyword in the page *heading*
(first 150 chars), times digit density so tables beat text. On Atlas Copco AR 2025
this puts the consolidated income statement (p.106) first; raw counting ranked it 13th
behind the segment overview.

Next for a teammate: (1) parse the table of contents on the first ~5 pages for the
section title + page number and boost that page; (2) prefer pages whose neighbours also
score (statements span 2 pages); (3) per-schema "title" keyword that must appear in the
heading, for notes that share vocabulary with the primary statements.
"""

HEADING_CHARS = 150


def candidate_pages(texts: list[str], schema: dict, top_n: int = 8) -> list[int]:
    """1-based page numbers, best first."""
    keywords = [k.lower() for k in schema.get("keywords", [])]
    scored = []
    for i, text in enumerate(texts):
        low = text.lower()
        head = low[:HEADING_CHARS]
        distinct = sum(k in low for k in keywords)
        if not distinct:
            continue
        heading = sum(k in head for k in keywords)
        density = sum(c.isdigit() for c in text) / max(len(text), 1)  # tables ~0.15-0.3, prose ~0.01
        scored.append(((distinct + 10 * heading) * (1 + 5 * density), i + 1))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [page for _, page in scored[:top_n]]
