"""Which pages hold the section? Deterministic keyword scoring, no LLM.

# ponytail: keyword scoring; LLM-over-TOC fallback if this misses

Next for a teammate: (1) parse the table of contents on the first ~5 pages for the
section title + page number and boost that page; (2) require >= 2 *distinct*
keywords so a prose page saying "see the income statement on page 64" three times
does not outrank the statement itself; (3) prefer pages whose neighbours also score
(statements span 2 pages).
"""


def candidate_pages(texts: list[str], schema: dict, top_n: int = 8) -> list[int]:
    """1-based page numbers, best first. Score = keyword hits x (1 + 5 x digit density)."""
    keywords = [k.lower() for k in schema.get("keywords", [])]
    scored = []
    for i, text in enumerate(texts):
        low = text.lower()
        hits = sum(low.count(k) for k in keywords)
        if not hits:
            continue
        density = sum(c.isdigit() for c in text) / max(len(text), 1)  # tables ~0.15-0.3, prose ~0.01
        scored.append((hits * (1 + 5 * density), i + 1))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [page for _, page in scored[:top_n]]
