"""Locate and annotate cited evidence without changing the cached source PDF.

Full passages are preferred. For PDF tables whose label and values live in separate
text blocks, phrases anchor matching amounts on the same printed row. We never
highlight a number merely because it appears somewhere else on the page.
"""
import re

import pymupdf

KEYWORD_COLOR = (0.55, 0.78, 1.0)
NUMBER_COLOR = (1.0, 0.83, 0.25)
_NUMBER = re.compile(r"^[($€£−–+-]*\d[\d.,'’]*[%)]*[,;:.]?$", re.UNICODE)
_BORING = {"and", "the", "for", "with", "from", "was", "were", "million", "millions", "msek", "sek", "och", "att", "till"}


def _number_in_quote(word: str, quote: str) -> bool:
    # Preserve punctuation and sign, allowing only whitespace variation. A quoted
    # 203 must never select 2030 (or vice versa), and 12 must not select 12.5.
    value = word.strip("$€£,;:")
    pattern = re.escape(value).replace(r"\ ", r"\s+")
    return bool(re.search(r"(?<![\d.,])" + pattern + r"(?!\d|[.,]\d)", quote))


def _inside(word, regions):
    rect = pymupdf.Rect(word[:4])
    return any((rect & region).get_area() >= rect.get_area() * 0.5 for region in regions)


def _same_row(word, region):
    rect = pymupdf.Rect(word[:4])
    overlap = min(rect.y1, region.y1) - max(rect.y0, region.y0)
    return overlap >= min(rect.height, region.height) * 0.5 and rect.x0 >= region.x0 - 2


def locate(page, quotes):
    words = page.get_text("words")
    all_keywords, all_numbers = {}, {}
    matched_quotes = 0

    def add(target, word):
        rect = pymupdf.Rect(word[:4])
        target[tuple(round(v, 2) for v in rect)] = rect

    for quote in dict.fromkeys(quotes):
        keywords, numbers = {}, {}
        quote = " ".join(quote.split())
        if not re.search(r"[^\W\d_]", quote):
            continue  # a bare number supplies no context to disambiguate repeats
        full = [quad.rect for quad in page.search_for(quote, quads=True)]
        if full:
            for word in words:
                if not _inside(word, full):
                    continue
                if _NUMBER.fullmatch(word[4]):
                    if _number_in_quote(word[4], quote):
                        add(numbers, word)
                elif any(c.isalpha() for c in word[4]):
                    add(keywords, word)
        else:
            # Splitting at digits extracts intact labels/phrases rather than a bag
            # of common keywords. Each candidate amount must share an anchor row.
            candidates = [w for w in words if _NUMBER.fullmatch(w[4]) and _number_in_quote(w[4], quote)]
            phrases = [p.strip(" \t\n.,;:()[]$€£%−–-<>=") for p in re.split(r"\d[\d.,'’]*", quote)]
            for phrase in dict.fromkeys(phrases):
                significant = [w for w in re.findall(r"[^\W\d_]+", phrase.lower()) if len(w) >= 3 and w not in _BORING]
                if not significant:
                    continue
                for anchor in page.search_for(phrase):
                    row_numbers = [w for w in candidates if _same_row(w, anchor)]
                    if re.search(r"\d", quote) and not row_numbers:
                        continue
                    for word in words:
                        if _inside(word, [anchor]) and any(c.isalpha() for c in word[4]):
                            add(keywords, word)
                    for word in row_numbers:
                        add(numbers, word)
        if keywords or numbers:
            matched_quotes += 1
        all_keywords.update(keywords)
        all_numbers.update(numbers)
    return {"keywords": list(all_keywords.values()), "numbers": list(all_numbers.values()),
            "matched_quotes": matched_quotes, "total_quotes": len(set(quotes))}


def response(page, found):
    # MuPDF text is in unrotated coordinates; page images honor page.rotation.
    return {"page": page.number + 1, "width": page.rect.width, "height": page.rect.height,
            **{kind: [list(rect * page.rotation_matrix) for rect in found[kind]] for kind in ("keywords", "numbers")},
            "matched_quotes": found["matched_quotes"], "total_quotes": found["total_quotes"]}


def annotate(page, found):
    for kind, color in (("keywords", KEYWORD_COLOR), ("numbers", NUMBER_COLOR)):
        if not found[kind]:
            continue
        annotation = page.add_highlight_annot([pymupdf.Quad(rect.tl, rect.tr, rect.bl, rect.br) for rect in found[kind]])
        annotation.set_colors(stroke=color)
        annotation.set_opacity(0.55)
        annotation.set_info(title="Source evidence", content="Cited figures" if kind == "numbers" else "Cited keywords")
        annotation.update()
