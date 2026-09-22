"""Candidate pages -> Extraction dict: one LLM call, then provenance check + arithmetic checks.

Next for a teammate: (1) two-pass -- first ask the model *which* candidate page is the
statement, then extract from that page alone (less context, fewer hallucinations) -- implemented
as an opt-in `EXTRACT_TWO_PASS=1` (default off, see `_select_pages`); see docs/acrylic/evidence/v043.md
and docs/acrylic/evidence/v045.md for two rounds of 30-company before/after and the group's call on
whether to flip the default;
(2) on "quote not found" retry once with the page's own rows shown back, so the model copies the
    printed line it meant instead of paraphrasing one -- opt-in `EXTRACT_QUOTE_RETRY=1` (default off,
    see `_quote_retry` and docs/acrylic/evidence/v054.md for the before/after that decides it);
(3) pick the period column explicitly (current vs prior year) instead of trusting
the model's "leftmost number" habit; (4) tune SYSTEM_PROMPT_TEMPLATE against eval/.
"""
import json
import itertools
import time
import os
import re
import unicodedata
from collections import Counter
from datetime import date

from . import kb, llm, locate
from .parse import normalize_ws, quote_on_page

SYSTEM_PROMPT_TEMPLATE = """You extract figures from a corporate annual report (Swedish or English) into JSON.

Section: {title}
{description}

Value convention: {value_convention}
Ignore statements/pages about: {exclude}. Use the consolidated (group / koncernen) statement.

Fields to extract (key | label | description | unit hint):
{field_lines}

Rules:
- Return ONE JSON object {{"fields": [...]}} with exactly one entry per key above, in that order.
- Entry: key, label, value (number, or null if not found), unit (from the table header, e.g. "MSEK"),
  period ("YYYY"), raw_label (the row label as printed), source, confidence (0..1).
- source = {{"page": <n from the "=== PAGE n ===" marker>, "quote": "<text copied verbatim from that page,
  containing the row label and the number>"}}. Copy character for character, do not reformat numbers.
  If value is null, source must be null and confidence 0.
- Report the column of the fiscal year named in the user message. Read the table's year header to find it:
  most reports print the current year first ("2025 2024"), some print it last ("2024 2025").
- value: drop thousands separators (152 340 -> 152340), "." as decimal separator, sign as printed (costs negative).
- Only rows that are printed. Never compute a value (no revenue minus costs, no EBITDA as gross profit):
  if the row is not in the statement, value is null.
- Never invent numbers. Prefer null over a guess.
- Compact JSON: no indentation, no line breaks.
"""
FEWSHOT_HEADER = """
Examples of the expected mapping from other reports in the knowledge base (row label as printed -> key), for reference only:
"""

# strict JSON schema for the model's reply = {"fields": Field[]} from docs/API.md
_FIELD = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "label": {"type": "string"},
        "value": {"type": ["number", "string", "null"]},
        "unit": {"type": ["string", "null"]},
        "period": {"type": ["string", "null"]},
        "raw_label": {"type": ["string", "null"]},
        "source": {
            "type": ["object", "null"],
            "properties": {"page": {"type": "integer"}, "quote": {"type": "string"}},
            "required": ["page", "quote"],
            "additionalProperties": False,
        },
        "confidence": {"type": "number"},
    },
    "required": ["key", "label", "value", "unit", "period", "raw_label", "source", "confidence"],
    "additionalProperties": False,
}
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"fields": {"type": "array", "items": _FIELD}},
    "required": ["fields"],
    "additionalProperties": False,
}
_SAFE_BUILTINS = {"abs": abs, "min": min, "max": max}


def debt_basis() -> str:
    """DEBT_BASIS=carrying (default) | undiscounted -- which of debt_maturity's two maturity tables
    total_debt and the buckets are read from: the borrowings note's carrying amounts (v028's basis,
    the total that ties to the balance sheet) or the liquidity-risk note's contractual undiscounted
    cash flows (includes future interest, a higher total; v089's user option). Anything but
    "undiscounted" reads "carrying", so a typo can never silently flip the basis. The schema carries
    both prompt wordings (description_undiscounted beside description) and the bucket-column reader
    swaps its two total-shaped word groups to match -- see _bucket_synonym_hits."""
    return "undiscounted" if os.getenv("DEBT_BASIS", "").strip().lower() in ("undiscounted", "contractual") else "carrying"


def _basis_text(entity: dict, basis: str) -> str:
    """The entity's description in the selected basis: a schema (or field) that opts in carries a
    "description_undiscounted" beside its "description" (debt_maturity, v089); anything else keeps
    the one description, so every other section's prompt is untouched."""
    if basis == "undiscounted" and entity.get("description_undiscounted"):
        return entity["description_undiscounted"]
    return entity.get("description", "")


def system_prompt(schema: dict, exclude_stem: str | None = None) -> str:
    basis = debt_basis()
    lines = "\n".join(
        f"- {f['key']} | {f['label']} | {_basis_text(f, basis)} | {f.get('unit_hint', '')}" for f in schema["fields"]
    )
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        title=schema.get("title", schema["name"]),
        description=_basis_text(schema, basis),
        value_convention=schema.get("value_convention", ""),
        exclude=", ".join(schema.get("exclude_keywords", [])) or "-",
        field_lines=lines,
    )
    # "gets better over time": checks-passed extractions of the same section from *other* reports, ~500 B each
    examples = kb.fewshot_examples(schema["name"], exclude_stem, int(os.getenv("FEWSHOT", "2")))
    if examples:
        prompt += FEWSHOT_HEADER + "\n".join(f"{e['company']}: {json.dumps(e['fields'], ensure_ascii=False, separators=(',', ':'))}" for e in examples)
    return prompt


def call_llm(system: str, user: str, schema: dict = RESPONSE_SCHEMA, name: str = "extraction") -> dict:
    return json.loads(llm.chat(system, user, schema, name))


PAGE_SELECT_SCHEMA = {
    "type": "object",
    "properties": {"pages": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 2}},
    "required": ["pages"],
    "additionalProperties": False,
}
PAGE_SELECT_SNIPPET = 1200  # chars of head-of-page text per candidate, after stripping running headers/page
# numbers -- long enough to reach past a front-matter breadcrumb to a note's own heading (Apotea's page 113
# opened with the report's own breadcrumb before "29. Borrowings", docs/acrylic/evidence/v043.md), not a whole table
PAGE_SELECT_KEYWORD_LINES = 20  # cap on schema-keyword-hit lines appended per candidate beyond the head
PAGE_SELECT_PROMPT = """You are given the start of {n} candidate pages from a corporate annual report (Swedish or English), each labelled with its page number. Which page holds the {title} statement itself -- the printed table of figures -- not a table of contents, a note reference, or an unrelated table?

{description}

Always name TWO pages: the primary page (the one with the table itself, must be one of the candidates above) and a companion page next to it, since a table's header or rows often continue onto the neighbouring page. Default the companion to primary+1; use primary-1 instead only if the table's own heading or first rows actually sit on the page before the primary one -- the companion does not itself have to be one of the candidates above.

Return ONE JSON object {{"pages": [primary, companion]}}, primary first. Never invent a primary page number that is not listed above."""
# PAGE_SELECT_HINTS is an explicit opt-in. Keeping the ordinary prompt as a separate literal makes
# PAGE_SELECT_HINTS absent (the release default) byte-for-byte compatible with the pre-v146 prompt.
PAGE_SELECT_HINTED_PROMPT = PAGE_SELECT_PROMPT.replace(
    "\n\nAlways name TWO pages:", "\n\n{selection_hint}\n\nAlways name TWO pages:"
)
PAGE_SELECT_DEBT_MATURITY_HINT = "Pick the page whose table states carrying amounts of borrowings / interest-bearing liabilities (the borrowings note, or the balance sheet's interest-bearing lines). Pages tagged liquidity-risk / undiscounted list contractual cash flows and are not the target unless no other candidate holds the borrowings."

# EXTRACT_QUOTE_RETRY: the follow-up call's schema is the field structure's own subset -- the key, the
# (possibly corrected) value, and the source line copied verbatim; everything else (label, unit, period,
# raw_label) the first answer already carries, and validation re-derives what matters from the quote.
_QUOTE_RETRY_FIELD = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "value": {"type": ["number", "string", "null"]},
        "source": {
            "type": ["object", "null"],
            "properties": {"page": {"type": "integer"}, "quote": {"type": "string"}},
            "required": ["page", "quote"],
            "additionalProperties": False,
        },
    },
    "required": ["key", "value", "source"],
    "additionalProperties": False,
}
QUOTE_RETRY_SCHEMA = {
    "type": "object",
    "properties": {"fields": {"type": "array", "items": _QUOTE_RETRY_FIELD}},
    "required": ["fields"],
    "additionalProperties": False,
}
QUOTE_RETRY_MAX_ROWS = 50  # rows shown per page before the value/synonym filter (_retry_rows) kicks in
QUOTE_RETRY_PROMPT = """Some of the source lines in your extraction are not printed on the page as you gave them. Below are the fields in question, and the table rows of the page each field cites, one row per numbered line.

For each field: find the row that is this field's own row -- its label names the field and its figures hold the value you reported (thousands separators may differ). Copy that row character for character as quote: the whole row, every number on it, no reformatting, no words added or dropped. Set value to what that row prints for the fiscal year. If no printed row on the page states this field's figure, set source to null -- do not pick the nearest look-alike row instead.

Fields to fix:
{field_lines}

{page_blocks}

Return ONE JSON object {{"fields": [...]}} with exactly one entry per key above, in that order.
Entry: key, value (number), source = {{"page": <n>, "quote": "<the row copied verbatim>"}}, or source = null when the page prints no such row.
- Only rows that are printed. Never compute a value. Never invent numbers. Prefer null over a guess.
- Compact JSON: no indentation, no line breaks."""


def _page_snippet(text: str, keywords: list[str]) -> str:
    """Pass-1's view of one candidate page: the first PAGE_SELECT_SNIPPET chars of text (running headers/
    footers already dropped by locate.strip_boilerplate, bare page-number lines dropped here), plus -- from
    beyond that head -- any line containing a schema keyword, prefixed with its line number. Apotea's own
    page 113 (docs/acrylic/evidence/v043.md) opens with a repeated front-matter breadcrumb before reaching
    its "29. Borrowings" heading: a plain head-of-page cut loses the heading entirely; the keyword lines
    give the model a second chance to see it, and roughly where on the page it sits."""
    lines = [l for l in text.splitlines() if not locate.FOLIO.match(l.strip())]
    head, used, i = [], 0, 0
    while i < len(lines) and used < PAGE_SELECT_SNIPPET:
        used += len(lines[i]) + 1
        head.append(lines[i])
        i += 1
    hits = [f"{n}: {l}" for n, l in enumerate(lines[i:], i + 1) if any(k in l.lower() for k in keywords)]
    out = "\n".join(head)
    if hits:
        out += "\n...\n" + "\n".join(hits[:PAGE_SELECT_KEYWORD_LINES])
    return out


def _page_title_blocks(text: str) -> list[str]:
    """The short title blocks immediately above page tables, using _table_scope's own bounded walk.
    This deliberately does not reach through intervening prose to a loose section heading: the same
    distinction lets the carrying-table guard leave MedCap's carrying table alone below its earlier
    liquidity-risk prose (v103/v111)."""
    rows = _page_rows(text)
    blocks: list[str] = []
    for i, row in enumerate(rows):
        if not i or not re.search(r"\d", row):
            continue
        title, _ = _scope_zone(rows, None, i)
        if title:
            block = " ".join(title).lower()
            if block not in blocks:
                blocks.append(block)
    return blocks


def _schema_keyword_in_title(title: str, keywords: list[str]) -> bool:
    """Whether a compact table title contains a schema keyword, tolerant only of ordinary plural
    inflection and word order. The terms come solely from schema.keywords: for example, its existing
    ``loans from banks`` matches Lime's ``Bank loans`` title, while Synsam's loans-by-currency title
    lacks the schema phrase's ``bank`` term. No company vocabulary belongs in pass 1."""
    words = {w.rstrip("s") if len(w) > 4 else w for w in re.findall(r"[^\W\d_]+", title.lower())}
    for keyword in keywords:
        terms = [w.rstrip("s") if len(w) > 4 else w for w in re.findall(r"[^\W\d_]+", keyword.lower()) if len(w) > 4]
        if terms and all(term in words for term in terms):
            return True
    return False


def _prefer_note_citations(fields: list[dict], sfs: list[dict], schema: dict, texts: list[str], pages: list[int],
                            warnings: list[str]) -> None:
    """Prefer an equally literal, field-labelled note row over a weaker duplicate citation.

    A repeated figure is not a value repair: its value, period, unit and raw label remain untouched.
    This last provenance pass only selects the better of two already printed rows in the locator's
    candidate window.  It is deliberately asymmetric: an established known-label citation is not
    displaced by another known-label row unless the latter is in a schema-keyword note title and
    the former is not.  That keeps same-kind duplicates (such as a note continued on the next page)
    stable.  A derived/unprinted source may instead move to a known-label row under a
    schema-keyword note title, and drops ``value_derived`` only once the new quote literally
    prints the value.
    """
    if schema.get("name") != "debt_maturity":
        return  # v157 is calibrated only against debt-maturity's note-page labels
    keywords = schema.get("keywords", [])
    candidates = []
    seen = set()
    for page in pages:
        if isinstance(page, int) and not isinstance(page, bool) and 1 <= page <= len(texts) and page not in seen:
            candidates.append(page)
            seen.add(page)
    title_match = {
        page: _schema_keyword_in_title(" ".join(texts[page - 1].split())[:locate.HEADING_CHARS], keywords)
        or any(_schema_keyword_in_title(title, keywords) for title in _page_title_blocks(texts[page - 1]))
        for page in candidates
    }
    for field, sf in zip(fields, sfs):
        source = field.get("source") or {}
        old_page, old_quote = source.get("page"), source.get("quote") or ""
        if field.get("value") is None or not isinstance(old_page, int) or not 1 <= old_page <= len(texts) or not old_quote:
            continue
        if old_page not in title_match:
            title_match[old_page] = _schema_keyword_in_title(
                " ".join(texts[old_page - 1].split())[:locate.HEADING_CHARS], keywords) \
                or any(_schema_keyword_in_title(title, keywords) for title in _page_title_blocks(texts[old_page - 1]))
        source_is_derived = "value_derived" in field.get("evidence", []) \
            or not quote_on_page(old_quote, texts[old_page - 1]) \
            or not _value_in_quote(field["value"], old_quote)
        source_label_known = _label_known(_row_label(old_quote), sf)
        options = []
        for order, page in enumerate(candidates):
            if page == old_page:
                continue
            for row_order, row in enumerate(_page_rows(texts[page - 1])):
                # _value_in_quote intentionally accepts a whole-number prefix of a decimal for
                # ordinary provenance repair. A preference must not move a derived 0 to prose
                # saying 0.8, so its small-number match also requires a token boundary.
                literal = _value_in_quote(field["value"], row)
                if isinstance(field["value"], (int, float)) and not isinstance(field["value"], bool) \
                        and abs(field["value"]) < 10:
                    strict = (_num_pattern(field["value"]) or "").replace(r"(?![\d])", r"(?![\d.,])")
                    literal = bool(strict and re.search(strict, _FOOTNOTE.sub("", row)))
                if not literal:
                    continue
                row_label_known = _label_known(_row_label(row), sf)
                if source_is_derived:
                    allowed = row_label_known and title_match[page]
                else:
                    # An existing note-page citation is already the kind of provenance this pass
                    # prefers.  Even an unknown-label row must not bounce between two note pages.
                    allowed = row_label_known and title_match[page] and not title_match[old_page] and (
                        not source_label_known or (not title_match[old_page] and title_match[page]))
                if allowed:
                    # All candidates are verified note-title rows. Candidate order keeps ties
                    # deterministic without displacing same-kind citations.
                    rank = (row_label_known, -order, -row_order)
                    options.append((rank, page, row))
        if not options:
            continue
        _, page, row = max(options)
        field["source"] = {"page": page, "quote": row}
        if source_is_derived and "value_derived" in field["evidence"]:
            field["evidence"].remove("value_derived")
        prior_kind = "derived" if source_is_derived else "balance sheet"
        warnings.append(f"{field['key']}: cited page {page} {row!r} (note row) instead of page {old_page} ({prior_kind})")


def _page_select_tags(schema: dict, pages: list[int], texts: list[str]) -> dict[int, list[str]]:
    """Zero-model debt-page hints for pass 1. The balance-sheet anchor is locate.balance_sheet_page
    (v139), and the liquidity title-zone test is _scope_zone, the exact bounded title-block logic used
    by _table_scope (v103/v111). A page gets at most the independent balance-sheet hint plus one
    mutually-exclusive table-basis hint; other schemas keep their existing untagged prompt."""
    if schema.get("name") != "debt_maturity":
        return {}
    undiscounted_words = [w.lower() for w in schema.get("table_scope_words", {}).get("undiscounted", [])]
    keywords = schema.get("keywords", [])
    balance_sheet = locate.balance_sheet_page(texts)
    tagged: dict[int, list[str]] = {}
    for page in pages:
        if not isinstance(page, int) or not 1 <= page <= len(texts):
            continue
        titles = _page_title_blocks(texts[page - 1])
        is_undiscounted = any(word in title for title in titles for word in undiscounted_words)
        tags: list[str] = []
        if page == balance_sheet:
            tags.append("balance sheet")
        if is_undiscounted:
            tags.append("liquidity-risk / undiscounted")
        elif any(_schema_keyword_in_title(title, keywords) for title in titles):
            tags.append("borrowings note: carrying")
        if tags:
            tagged[page] = tags
    return tagged


def _select_pages(schema: dict, pages: list[int], texts: list[str], page_select_hints: bool | None = None) -> list[int] | None:
    """EXTRACT_TWO_PASS pass 1: ask the model which of the candidate pages (locate.candidate_pages, up to
    top_n=8) holds the statement itself, from a head-of-page snippet of each (_page_snippet) -- cheaper
    than handing over the full prompt budget's worth of pages, and lets the model reach a candidate ranked
    below the top-2 that the single-pass window never shows it. The reply must name a companion page next
    to its primary pick (default primary+1, or primary-1 when the model says the table starts on the page
    before): v043 found a single-page reply loses the companion page single-pass always got for free
    (locate.candidate_pages forces pages[0]+1 into position 2 unconditionally, whether or not it scored),
    so a lone primary here is repaired the same way, not treated as a failure. None on any call failure, a
    primary outside the candidate list, or a second page that is not the primary's immediate neighbour: the
    caller then falls back to the single-pass window (pages[:2])."""
    if len(pages) < 2:
        return None
    keywords = [k.lower() for k in schema.get("keywords", [])]
    cleaned = locate.strip_boilerplate(texts)
    # A caller may override the environment for one extraction run.  v162's retry route needs an
    # ordinary first selection and a hinted second selection in the same request; None preserves
    # the v146-b environment-only behaviour for every other caller.
    hints_enabled = schema.get("name") == "debt_maturity" and (
        os.getenv("PAGE_SELECT_HINTS") == "1" if page_select_hints is None else page_select_hints
    )
    tags = _page_select_tags(schema, pages, cleaned) if hints_enabled else {}
    user = "\n\n".join(
        f"=== PAGE {n}{''.join(f' [{tag}]' for tag in tags.get(n, []))} ===\n{_page_snippet(cleaned[n - 1], keywords)}"
        for n in pages)
    selection_hint = PAGE_SELECT_DEBT_MATURITY_HINT if hints_enabled else ""
    prompt = PAGE_SELECT_HINTED_PROMPT if hints_enabled else PAGE_SELECT_PROMPT
    system = prompt.format(n=len(pages), title=schema.get("title", schema["name"]),
                           description=schema.get("description", ""), selection_hint=selection_hint)
    try:
        got = call_llm(system, user, PAGE_SELECT_SCHEMA, "page_select").get("pages")
    except Exception:
        return None
    if not isinstance(got, list) or not 1 <= len(got) <= 2 or len(set(got)) != len(got):
        return None
    if any(not isinstance(p, int) or isinstance(p, bool) for p in got):
        return None
    primary = got[0]
    if primary not in pages:
        return None
    if len(got) == 1:
        return sorted([primary, primary + 1 if primary + 1 <= len(texts) else primary - 1])
    companion = got[1]
    if companion not in (primary - 1, primary + 1) or not 1 <= companion <= len(texts):
        return None
    return sorted([primary, companion])


def _retry_rows(text: str, wants: list[tuple]) -> list[tuple[int, str]]:
    """(number, row) for the retry prompt: every _page_rows row up to QUOTE_RETRY_MAX_ROWS, past that only
    the rows matching one of the fields' values (any printed grouping, _num_pattern) or synonyms, plus two
    rows of context either side -- a statement page can carry far more rows than the question is about, and
    the numbers a whole page holds are what got the quote garbled in the first place."""
    rows = _page_rows(text)
    if len(rows) <= QUOTE_RETRY_MAX_ROWS:
        return list(enumerate(rows, 1))
    keep: set[int] = set()
    for i, row in enumerate(rows, 1):
        low = normalize_ws(row).lower()
        for value, syns in wants:
            pat = _num_pattern(value)
            if (pat and re.search(pat, row)) or any((s := normalize_ws(x).lower()) and s in low for x in syns):
                keep.update(range(max(1, i - 2), min(len(rows), i + 2) + 1))
                break
    return [(i, rows[i - 1]) for i in sorted(keep)]


def _quote_retry(by_key: dict, system: str, schema: dict, texts: list[str], pages: list[int],
                 fiscal_year, warnings: list[str]) -> dict:
    """EXTRACT_QUOTE_RETRY (default off; default decided by docs/acrylic/evidence/v054.md): one follow-up
    call after the model's first answer, before validation, for the fields that returned a value whose
    quote quote_on_page cannot find on the page it cites -- rewritten, spliced, invented, the recurring
    "quote not found" / "dropped as computed, not read" shape of every hardening round (Storytel, MEKO,
    MedCap...). The user message lists each such field's key/label/earlier value plus the _page_rows of
    its own cited page (the first candidate page when it cited none), and asks for the row copied verbatim,
    or null when no printed row states the figure. A field adopts the reply only when the new quote
    verifies on the page it names; null, missing or still-unverified replies keep the original answer, so
    the retry can never leave a field worse than the first call alone. Fields v050's _stated_zero already
    proves (a 0 the report states in words -- Creades) are not retried: the sentence is the provenance, and
    a row list could only talk the model out of it. One call, never two; any failure keeps the originals."""
    if os.getenv("EXTRACT_QUOTE_RETRY") != "1" or not texts or not pages:
        return by_key
    cands = []
    for sf in schema["fields"]:
        f = by_key.get(sf["key"])
        if not isinstance(f, dict) or f.get("value") is None:
            continue
        src = f.get("source") or {}
        if isinstance(src.get("page"), int) and 1 <= src["page"] <= len(texts):
            if str(src.get("quote") or "") and quote_on_page(src["quote"], texts[src["page"] - 1]):
                continue  # verbatim where it cites: nothing to fix
            if _stated_zero(f, sf, schema, texts):
                continue  # the report's own words already prove this 0; a row list has nothing to add
        cands.append(sf)
    if not cands:
        return by_key
    wants: dict[int, list] = {}
    lines = []
    for sf in cands:
        f = by_key[sf["key"]]
        src = f.get("source") or {}
        page = src.get("page") if isinstance(src.get("page"), int) and 1 <= src.get("page") <= len(texts) else pages[0]
        lines.append(f"- {sf['key']} | {sf.get('label', '')} | your value: {f.get('value')} | cited page: {page}")
        wants.setdefault(page, []).append((f.get("value"), sf.get("synonyms", [])))
    blocks = "\n\n".join(f"=== PAGE {p} (rows) ===\n" + "\n".join(f"{n}: {r}" for n, r in _retry_rows(texts[p - 1], wants[p]))
                         for p in sorted(wants))
    user = (f"Fiscal year to extract: {fiscal_year}\n\n" if fiscal_year else "") + \
        QUOTE_RETRY_PROMPT.format(field_lines="\n".join(lines), page_blocks=blocks)
    try:
        got = call_llm(system, user, QUOTE_RETRY_SCHEMA, "quote_retry").get("fields", [])
    except Exception as e:  # ponytail: teammates feed the error back to the model, same as the main call
        warnings.append(f"quote_retry: {type(e).__name__}: {e}")
        return by_key
    fixed = {g.get("key"): g for g in got if isinstance(g, dict) and g.get("key")}
    for sf in cands:
        g = fixed.get(sf["key"])
        if not isinstance(g, dict):
            continue
        src = g.get("source") or {}
        page, quote = src.get("page"), str(src.get("quote") or "")
        if not isinstance(page, int) or not 1 <= page <= len(texts) or not quote or not quote_on_page(quote, texts[page - 1]):
            continue  # null, or still not the printed line: the first answer stands
        old = by_key[sf["key"]]
        value = _num(g.get("value"))
        moved = "" if value == old.get("value") else f", value {old.get('value')} -> {value}"
        warnings.append(f"quote_retry: {sf['key']}: quote replaced by page {page} row {quote!r}{moved}")
        by_key[sf["key"]] = {**old, "value": value if value is not None else old.get("value"),
                             "source": {"page": page, "quote": quote}}
    return by_key


def _num(v):
    """'152 340' / '-88,5' -> number; leave anything non-numeric alone."""
    if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
        return int(v) if isinstance(v, float) and v.is_integer() else v
    t = normalize_ws(str(v)).replace(" ", "").replace(",", ".")
    try:
        f = float(t)
        return int(f) if f.is_integer() else f
    except ValueError:
        return v


def _check(check: dict, values: dict, texts: list[str] | None = None, pages: list[int] | None = None,
           fields: list[dict] | None = None, schema: dict | None = None, stated_zeros: set | None = None) -> dict:
    out = {"name": check["name"], "passed": False, "detail": ""}
    # "null_as_zero" operands (schema: Ericsson's note prints no >5y bucket — null there is a real 0, not an unanswered
    # field) count as 0 while null, but only while at least one of them is real: all buckets null would sum to 0 == total
    # and the check would pass on nothing.
    listed = [] if check.get("require_explicit_values") else check.get("null_as_zero", [])
    naz = [k for k in listed if values.get(k) is None]
    zero = set(naz)
    # v165: under require_explicit_values a bucket the maturity table prints no column for (evidence
    # "absent_in_table", the table's own header row its source) is the report's explicit absence, not the
    # model's silence -- it joins the identity as the 0 the table cannot print. But only when no other
    # operand is still an unanswered null: that one keeps its honest "missing: <field>" verdict, and the
    # proven absence must not tip a check that is missing something else into a pass or a TypeError.
    absent = set()
    if check.get("require_explicit_values") and fields:
        f_by_key = {f["key"]: f for f in fields}
        operands = [k for k in re.findall(r"\b[A-Za-z_]\w*\b", check["expr"]) if k not in _SAFE_BUILTINS]
        absent = {k for k in operands if values.get(k) is None
                  and "absent_in_table" in (f_by_key.get(k, {}).get("evidence") or [])}
        if absent and any(values.get(k) is None for k in operands if k not in absent):
            absent = set()
        zero |= absent
    # v050: all listed operands null, but the identity's remaining operand(s) are themselves stated zeros --
    # the report said in words there is no interest-bearing debt (Creades), so the buckets ARE zeros and
    # 0+0+0 == 0 is a real pass, not the "pass on nothing" the guard above exists for (nothing read at all).
    others = set(re.findall(r"\b[A-Za-z_]\w*\b", check["expr"])) - set(_SAFE_BUILTINS) - set(listed)
    all_stated = naz and len(naz) == len(listed) and bool(others) and others <= (stated_zeros or set())
    if naz and len(naz) < len(listed) and texts and schema:
        # MedCap (v041 finding 3): a bucket the model failed to extract reads identically to a bucket the report
        # never prints -- both are null -- but only the second one is really a 0. Before defaulting a null bucket
        # to 0, look for its own synonym label (same normalize_ws digit-gluing as _clean_label/v012/v014, so
        # "< 1 år" reaches a "<1 år" column header too) on the pages the check's *other*, real operands
        # were sourced from, or the candidate pages -- MedCap's due_within_1_year has no row on the carrying-amount
        # table (p.101, where total_debt/due_1_to_5_years were read) but its own "<1 år" column header sits on the
        # contractual table two pages later (still a candidate page): present, so leave it out of ns (-> "missing:
        # <field>", never a false 0) instead of zero-filling it into a hard failure.
        sf_by_key = {sf["key"]: sf for sf in schema.get("fields", [])}
        field_pages = {f["key"]: f["source"]["page"] for f in (fields or []) if f.get("source")}
        search = sorted({field_pages[k] for k in listed if k not in naz and k in field_pages} | set(pages or ()))
        # anchor on every real operand of the identity (total_debt included), not just the listed buckets:
        # the span must reach the total row, or it could stop short of the table's own bottom boundary
        operands = [k for k in re.findall(r"\b[A-Za-z_]\w*\b", check["expr"]) if k not in _SAFE_BUILTINS]
        span = _operand_table_rows(texts, fields or [], operands, naz)
        page_rows = [normalize_ws(r).lower() for p in search if 0 < p <= len(texts) for r in _page_rows(texts[p - 1])]

        def _evaluate(rows_list):
            z = {k for k in naz if not any((cs := normalize_ws(s).lower()) and cs in r
                                           for s in sf_by_key.get(k, {}).get("synonyms", []) for r in rows_list)}
            ns2 = {**values, **{k: 0 for k in z}} if naz and (len(naz) < len(listed) or all_stated) else values
            try:
                result = eval(check["expr"], {"__builtins__": {}, **_SAFE_BUILTINS}, ns2)  # ponytail: our own schema files, not user input
            except NameError as e:
                return z, False, f"missing: {e.name}"
            except Exception as e:
                return z, False, f"{type(e).__name__}: {e}"
            substituted = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: f"0 ({m.group()} null)" if m.group() in z else str(ns2.get(m.group(), m.group())), check["expr"])
            return z, bool(result), f"{check.get('detail', '')} | {substituted}".strip(" |")

        if span is not None:
            # v058: only the operands' own table -- a bucket word printed by another table on a candidate page
            # (MedCap's contractual cash-flow ">5år" header) must not block a 0 the operands' table really implies
            zero, out["passed"], out["detail"] = _evaluate([normalize_ws(r).lower() for r in span])
            if not out["passed"]:
                # v058, supervisor ruling: a scoped zero that cannot close the identity has not proven its 0s
                # enough to hard-fail the check and cap the verified fields -- v044's page-level verdict stands
                zero, out["passed"], out["detail"] = _evaluate(page_rows)
        else:
            # v058: no printable operand row / no provable table header -> v044's whole-page search, unweakened
            zero, out["passed"], out["detail"] = _evaluate(page_rows)
        return out
    ns = {**values, **{k: 0 for k in zero}} if absent or (naz and (len(naz) < len(listed) or all_stated)) else values
    try:
        result = eval(check["expr"], {"__builtins__": {}, **_SAFE_BUILTINS}, ns)  # ponytail: our own schema files, not user input
    except NameError as e:
        out["detail"] = f"missing: {e.name}"
        return out
    except Exception as e:
        out["detail"] = f"{type(e).__name__}: {e}"
        return out
    substituted = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: f"0 ({m.group()} {'absent' if m.group() in absent else 'null'})" if m.group() in zero else str(ns.get(m.group(), m.group())), check["expr"])
    out.update(passed=bool(result), detail=f"{check.get('detail', '')} | {substituted}".strip(" |"))
    return out


EXTRACT_VERSION = "2026-09-22-w198"  # bump when a pipeline change should invalidate saved extractions; the cache key used to hash 7 source files, so every commit re-ran every section (27 s each)

WEIGHTS = {"quote_on_page": 0.35, "value_in_quote": 0.20, "arith_ok": 0.20, "label_known": 0.10,
           "period_ok": 0.05, "page_is_statement": 0.05, "unit_ok": 0.05,  # docs/CONFIDENCE.md; sums to 1.0
           "value_derived": 0.20, "bs_tie": 0.0,  # a BS tie is a recorded independent fact, not a second confidence weight
           "stated_zero": 0.20,  # stands in for value_in_quote when the figure is never printed: the report says 0 in words (v050)
           "identity_all_columns": 0.0,  # a marker: an unknown label whose identity holds in every column earns label_known
           "identity_kept": 0.0,  # a marker: a column guard's own re-read lost to a value that closes the identity exactly (v066)
           "printed_nil": 0.0,  # a marker: the bucket's own cell prints a dash -- the report's explicit 0 for that window (v078)
           "sign_normalized": 0.0}  # a marker: a liabilities-negative printed sign (net-debt display); the magnitude is recorded (v101)


_DASHES = str.maketrans({"–": "-", "−": "-", " ": " "})
_SPACE_GROUPS = re.compile(r"(?<![\d,.])\d{1,3}(?:[  ]\d{3})+(?![.'\d]|,\d{3})")  # Clas Ohlson "1 478,6" is 1478.6; only a 3-digit tail after the comma is a thousands group  # Swedish thousands; "7 176,658" (note ref + number) and "1,051 969" (two columns) stay apart
_FOOTNOTE = re.compile(r"(?<=\d{3})\d\)(?=\s|$)")  # Volvo Cars "Cost of sales 3 -297,0421) -320,821": a footnote marker glued to the amount
_AMOUNT = re.compile(r"[-(]?(\d{1,3}(?:[ ,.']\d{3})*|\d+)(?:([.,])(\d{1,4}))?\)?")  # Asmodee prints EPS to four decimals: 0.1186

_SPLIT_YEAR = re.compile(r"\b(20\d\d)/(?:20)?\d\d\b")
_MONTH_RANGE = re.compile(r"(?i)\b(?:jan|feb|mar|apr|maj|may|jun|jul|aug|sep|okt|oct|nov|dec)[a-z]*\.? ?((?:20)?\d\d)\s*[-\u2013]\s*(?:jan|feb|mar|apr|maj|may|jun|jul|aug|sep|okt|oct|nov|dec)[a-z]*\.? ?(?:20)?\d\d\b")
_DEC_DATE = re.compile(r"(?i)\b(?:\d{1,2}[.:]?\s?dec[a-z]*\.?\s?,?\s?|dec[a-z]*\.?\s?\d{1,2}\s?,?\s?)(20\d\d)\b")  # December only: a fiscal year ending in December is named by that calendar year


def _year_column(text: str, fiscal_year) -> tuple[int, int] | None:
    """(position of the fiscal year, number of year columns) from the table's year header ("Note 2024 2025" -> (1, 2)).
    None without a header, when the fiscal year is not in it, or when it repeats (Volvo prints "2025 2024" per segment:
    Industrial Operations ... Volvo Group; which pair is the group is not knowable here, see _segment_column).
    A December balance date names its year ("SEK million 31 Dec 2025 31 Dec 2024", Ambea): reduced to the bare year
    before the scan, so its day/month tokens are neither amount columns nor run-breakers, and the years keep print
    order -- the first column is the first year printed (v102; a non-December date stays as printed, its calendar
    year is not the fiscal year: Rusta's FY2025 ends "30 Apr 2026", the report's own "2025/26" header rules there)."""
    run = _year_run(_DEC_DATE.sub(lambda m: m.group(1), text))
    return (run.index(str(fiscal_year)), len(run)) if run.count(str(fiscal_year)) == 1 else None


def _year_run(text: str) -> list[str]:
    """The table's year header as printed: ["2024", "2025"]; [] without one."""
    head, year = " ".join(text[:4000].split()), re.compile(r"\b20\d\d\b")  # Beijer Ref prints a contents list above the statement
    head = re.sub(r"\b\d{1,2}[/.]\d{1,2}[/.](20\d\d)\s*[-\u2013]\s*\d{1,2}[/.]\d{1,2}[/.](20\d\d)|\b(20\d\d)-\d\d-\d\d\s*[-\u2013]\s*(20\d\d)-\d\d-\d\d",
                  lambda m: m.group(2) or m.group(4), head)  # Catena "01/01/2025 -31/12/2025": the period's end year is the column
    head = re.sub(r"\b\d{1,2}[/.]\d{1,2}[/.](20\d\d)|\b(20\d\d)-\d\d-\d\d", lambda m: m.group(1) or m.group(2), head)  # "31/12/2025", "2025-12-31"
    head = re.sub(r"\b(\d\d)(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\s*[-\u2013\u2212]\s*\d{6}\b", lambda m: "20" + m.group(1), head)  # Clas Ohlson "250501 − 260430": YYMMDD range, fiscal 2025
    head = _MONTH_RANGE.sub(lambda m: "20" + m.group(1)[-2:], head)  # Asmodee "Apr 25-Mar 26 Apr 24-Mar 25": a broken fiscal year named by its first year
    head = _SPLIT_YEAR.sub(r"\1", head)  # Sectra "2025/2026 2024/2025": a broken fiscal year is one column, named by its first year
    for m in year.finditer(head):
        run, end = [m.group()], m.end()
        while (n := year.search(head, end)) and n.start() - end <= 12 and not re.search(r"\d", head[end:n.start()]):
            run.append(n.group())  # "2025 2024" or Telia's "2025 Jan-Dec 2024": one word between years is still the header
            end = n.end()
        if len(run) >= 2:
            return run
    return []


def _row_year_column(rows: list[str], i: int, fiscal_year) -> tuple[int, int] | None:
    """The year header of the table the row rows[i] belongs to: the nearest year run ABOVE it (_year_run over the
    rows[j:i] window, j walked upward from just above the row), not the page's first. A note page can stack a second
    table above the statement's (MedCap p.101: a receivables-ageing table over the maturity table), and the page's
    first header then names 2 columns for 4-amount rows, so every row derivation bails. December balance dates are
    reduced to their year first, exactly as _year_column does ("31 Dec 2025 31 Dec 2024", Ambea). The fiscal year
    once in that run -> (pos, len(run)); twice and the run's row or the one above it names Group before Parent ("Koncernen
    Moderbolaget" / "Group Parent Company") -> the first pair, Parent first -> the last; anything else -> None, the
    shape _year_column declines (Volvo's four segment pairs stay unknowable here)."""
    for j in range(i - 1, -1, -1):  # windows grow upward, so the nearest run wins: the row's own header is found before any higher table's
        run = _year_run(_DEC_DATE.sub(lambda m: m.group(1), " ".join(rows[j:i])))
        if not run:
            continue
        orphan_start = None
        # A four-column Group | Parent header can be torn into one visible two-year run below two
        # one-year orphan lines (BICO Note 20: "2025" / "2024" / "2025 2024").  The nearest
        # run alone would call it a two-column header, then the subtotal-pair closure declines the
        # four-amount rows.  Rejoin only directly adjacent calendar-year-only lines and only when
        # they double that visible run exactly; a stray date, a third fragment, or a line with any
        # non-year number remains the pre-existing nearest two-column run.
        if len(run) == 2 and _year_only_header(rows[j]):
            start = j
            while start and _year_only_header(rows[start - 1]):
                start -= 1
            joined = _year_run(_DEC_DATE.sub(lambda m: m.group(1), " ".join(rows[start:i])))
            if start < j and len(joined) == 2 * len(run):
                run, orphan_start = joined, start
        if run.count(str(fiscal_year)) == 1:
            return (run.index(str(fiscal_year)), len(run))
        if run.count(str(fiscal_year)) == 2:  # Group | Parent pairs on one page
            # The two-line date stub between the joined years and "Group Parent Company" is also
            # part of BICO's torn header.  Only the exact orphan rejoin may look those two lines
            # further up; normal repeated-year headers retain v052's one-line context.
            near_start = max((orphan_start - 2) if orphan_start is not None else (j - 1), 0)
            # Separate Group / Parent lines can precede a current/non-current
            # year header. Only extend across these exact entity headings.
            if j >= 2 and re.fullmatch(r"(?i)\s*(?:group|koncernen|parent(?: company)?|moderbolaget)\s*", rows[j - 1]) \
                    and re.fullmatch(r"(?i)\s*(?:group|koncernen|parent(?: company)?|moderbolaget)\s*", rows[j - 2]):
                near_start = j - 2
            near = " ".join(rows[near_start:j + 1]).lower()
            g, e = locate.GROUP.search(near), locate.ENTITY.search(near)
            if g and e:
                if g.start() < e.start():
                    return (run.index(str(fiscal_year)), len(run))
                return (len(run) - 1 - run[::-1].index(str(fiscal_year)), len(run))
        return None  # the nearest run wins even when it names no usable column: climbing past it would cross into the table above
    return None


def _year_only_header(row: str) -> bool:
    """True for a physical table-header line whose only parsed figures are calendar years.

    This deliberately excludes a day/month stub (``Dec 31,``) and any amount-bearing row.  It is
    used only to prove the contiguous orphan-year shape in ``_row_year_column``; it is not a broad
    heading classifier.
    """
    amounts = _row_amounts(row)
    return bool(amounts) and all(isinstance(a, int) and 1900 <= a <= 2100 for a in amounts)


def _torn_orphan_year_header(rows: list[str], i: int) -> bool:
    """Whether ``rows[i]`` belongs to the exact two-year-plus-orphan header rejoined above.

    The subtotal-pair closure may only infer a trailing blank amount in this proven four-column
    Group | Parent shape.  Keeping the shape test separate makes that one sparse-row concession
    unavailable to ordinary two- or four-column tables.
    """
    for j in range(i - 1, -1, -1):
        run = _year_run(_DEC_DATE.sub(lambda m: m.group(1), " ".join(rows[j:i])))
        if not run:
            continue
        if len(run) != 2 or not _year_only_header(rows[j]):
            return False
        start = j
        while start and _year_only_header(rows[start - 1]):
            start -= 1
        joined = _year_run(_DEC_DATE.sub(lambda m: m.group(1), " ".join(rows[start:i])))
        return start < j and len(joined) == 2 * len(run)
    return False


def _operand_table_rows(texts: list[str], fields: list[dict], keys: list[str], naz: list[str]) -> list[str] | None:
    """The rows of the table the present-label search's *real* (non-null) operands were read from (v058): each
    operand's source.quote must be an exact _page_rows row -- the anchor standard _column_values/_derived_value
    already use -- and the span per page runs from the nearest year-header row above the page's topmost anchor
    (_year_run over the growing window, _row_year_column's upward walk) down to the page's bottommost anchor,
    the Totalt row: bucket words printed by another table on the same page (MedCap's contractual cash-flow
    table, docs/acrylic/evidence/v058.md) or below the total are not this table's. None -- the caller then
    keeps v044's whole-page search instead of narrowing the guard on a guess -- when no operand's quote is a
    printed row, or when no year-header row sits above an anchored page's topmost anchor: a span from the page
    top proves no boundary (the real table may continue from the previous page -- alligo/boozt/bergman_beving,
    whose maturity headers live one page up), and zero-filling a bucket on that guess turned checks that were
    honestly missing into hard failures on the 34-stem replay."""
    anchors: dict[int, list[int]] = {}
    by_key = {f["key"]: f for f in fields}
    for k in keys:
        if k in naz:
            continue
        src = (by_key.get(k) or {}).get("source") or {}
        p = src.get("page")
        if not isinstance(p, int) or not 1 <= p <= len(texts) or not src.get("quote"):
            continue
        rows = _page_rows(texts[p - 1])
        if src["quote"] in rows:
            anchors.setdefault(p, []).append(rows.index(src["quote"]))
    if not anchors:
        return None
    out: list[str] = []
    for p, idxs in anchors.items():
        rows = _page_rows(texts[p - 1])
        top, bottom = min(idxs), max(idxs)
        header = next((j for j in range(top - 1, -1, -1) if _year_run(" ".join(rows[j:top]))), None)
        if header is None:  # no provable table top on this page: the page-level search decides, not a guess
            return None
        out.extend(rows[header:bottom + 1])
    return out


def _segment_column(text: str, fiscal_year, fields: list[dict]) -> tuple[int, int] | None:
    """Volvo prints "2025 2024" once per segment (Industrial Operations, Financial Services, Eliminations, Volvo Group) and the
    model read the tax from the first pair and the rest from the last. The fiscal-year column is the one most of the page's
    fields already sit in: (position, number of columns). None unless the year repeats in the header."""
    run = _year_run(text)
    slots = [i for i, y in enumerate(run) if y == str(fiscal_year)]
    if len(slots) < 2:
        return None
    head = " ".join(text[:4000].split()).lower()
    g, e = locate.GROUP.search(head[:300]), locate.ENTITY.search(head[:300])
    if g and e:  # Vitrolife: "Group | Parent Company" pairs on one page; the group pair is on the side named first, whatever the model read
        return (slots[0] if g.start() < e.start() else slots[-1], len(run))
    votes: Counter = Counter()
    for f in fields:
        am = _row_amounts(f["source"]["quote"], len(run))
        hit = [i for i in slots if len(am) == len(run) and am[i] == f["value"]]
        if len(hit) == 1:
            votes[hit[0]] += 1
    return (max(votes, key=lambda i: (votes[i], i)), len(run)) if votes else None  # ponytail: tie -> the rightmost pair, where the group total conventionally sits


def _row_amounts(quote: str, ncols: int | None = None, nil=0) -> list:
    """Numbers after the row label, parsed; note references ("6, 7", "G2") dropped; a lone dash is nil (0 by
    default), so columns stay aligned. With the column count known, Swedish space-grouped rows are split by it:
    "Total sales 6, 10 155 113 161 921" is a note reference plus two 6-digit amounts, which no regex can tell
    from five small numbers. nil=None for callers that must tell "not printed" apart from a printed 0 (a
    maturity-bucket column, where "-" means no debt is due in that window, not a literal zero).

    The same space-grouping can over-merge two adjacent bucket columns that happen to look like one Swedish-
    grouped number: Boozt's "Lease liabilities 441 26 78 273 63 -" (ncols=6) reads "78 273" as one 78273, a
    column short. Undone only on the narrowest evidence ncols gives: the ordinary reading is exactly one
    column short, that reading already has a nil in it (a bare "-" printed elsewhere in the same row -- one
    instrument's own row, sparse by nature; a table's own whole-table Total row sums every instrument and is
    almost never nil anywhere, so this must not start reading a coincidentally same-shaped Total row too, e.g.
    Boozt's own "Total 2,358 1,928 92 273 63 0"), and exactly one "NN NNN" token in the row could be the glue
    (two or more is a guess between candidates, so none is split) -- and even then only kept if splitting that
    one token lands on exactly ncols amounts. A genuine Swedish grouping such as "1 234 567" already has the
    header's one amount and is never split. Conversely, MTG's "85 151" would add a fifth amount to a four-
    header read, so this function deliberately leaves its ambiguous 85,151 reading intact; v144's source-row
    closure gate is the separate guard before that ambiguous reading can override an answered total."""
    q = _FOOTNOTE.sub("", quote.translate(_DASHES))
    toks = q.split()
    last_alpha = max((i for i, t in enumerate(toks) if re.search(r"[^\W\d_]", t)), default=-1)
    tail = [t.rstrip(",;") for t in toks[last_alpha + 1:]]
    if ncols and tail and all(re.fullmatch(r"-?\d{1,3}", t) for t in tail):
        for k in range(len(tail) // ncols, 0, -1):  # widest split whose leftovers all look like note references
            lead, body = tail[: len(tail) - ncols * k], tail[len(tail) - ncols * k:]
            chunks = [body[i * k:(i + 1) * k] for i in range(ncols)]
            if all(len(t) <= 2 for t in lead) and all(re.fullmatch(r"\d{3}", g) for ch in chunks for g in ch[1:]):
                return [int("".join(ch)) for ch in chunks]

    def _degroup(m: re.Match) -> str:
        return m.group(0).replace(" ", "").replace("\u00a0", "")

    def _amounts(qc: str) -> list:
        toks = qc.split()
        if re.search(r"\d\.\d{1,2}\b|\d,\d{3}\b", qc):  # "." is the decimal here, so "6,12" is a note reference, not 6.12
            toks = [t for t in toks if not re.fullmatch(r"\d{1,2},\d{1,2}", t)]
        last_alpha = max((i for i, t in enumerate(toks) if re.search(r"[^\W\d_]", t)), default=-1)
        out, noteish, small = [], [], []  # noteish: a bare one- or two-digit token; "6" / "12" is a note reference, "(19)" / "-19" (Arion) is an amount
        for t in toks[last_alpha + 1:]:
            t = t.rstrip(",;")
            if t == "-":  # Volvo "Income taxes 10 -11,669 -15,542 -1,016 -1,092 – – -12,685 -16,634": the eliminations columns are nil
                out.append(nil)
                noteish.append(False)
                small.append(False)  # Cloetta "Accrued interest 0 - - - 0": a run of nil dashes must not desync small from out/noteish, or small[0] below runs off the end
                continue
            m = _AMOUNT.fullmatch(t)
            if not m:
                continue
            if re.fullmatch(r"0[.,]\d{3}", m.group(1)) and not m.group(3):
                v = float("0." + m.group(1)[2:])  # Fenix Outdoor "0.039" / "0.693": a lone zero is never a thousands group
            else:
                v = int(re.sub(r"\D", "", m.group(1))) + (float(f"0.{m.group(3)}") if m.group(3) else 0)  # ponytail: "1,234" is read as a thousand, not a Swedish decimal
            v = -v if t[0] in "-(" else v
            out.append(int(v) if float(v).is_integer() else round(v, 4))
            noteish.append(len(re.sub(r"\D", "", t)) < 3 and not m.group(3) and t[0].isdigit())
            small.append(len(re.sub(r"\D", "", t)) < 3 and t[0].isdigit())
        if ncols:  # note references sit between the label and the amounts; after an amount a small number is a column
            while out and noteish[0]:  # Vitrolife "Net sales 4, 5 3,440 3,609 15 25": the parent company's 15 and 25 are amounts
                out, noteish, small = out[1:], noteish[1:], small[1:]
            while len(out) > ncols and small[0]:  # Clas Ohlson "Nettoomsättning 2,3 12 513,9 11 626,7": "2,3" is notes 2 and 3 once the columns are full
                out, small = out[1:], small[1:]
            return out
        return [v for v, n in zip(out, noteish) if not n]

    result = _amounts(_SPACE_GROUPS.sub(_degroup, q))  # "79 146" -> 79146 before splitting
    if ncols and len(result) == ncols - 1:
        glued = [gm for gm in _SPACE_GROUPS.finditer(q) if len(gm.group(0).split()) == 2]  # "NN NNN": one grouped number, or two adjacent bucket columns
        if len(glued) == 1:  # two or more candidates is a guess which one -- don't
            keep = glued[0]
            split = _amounts(_SPACE_GROUPS.sub(lambda m: m.group(0) if (m.start(), m.end()) == (keep.start(), keep.end()) else _degroup(m), q))
            if nil in result and len(split) == ncols:  # nil: see the docstring's Total-row caveat
                return split
    return result


_NOTE_REFS = re.compile(r"(?:[A-Z]{1,3}\.?\d{1,2}(?:[-–]\d{1,2})?[,\s]*)+")  # "IE.3", "IE.4-7", "T.1–2", "A.1 IE.8", "B1, B2"


def _page_rows(text: str) -> list[str]:
    """The page as table rows: a line with a word starts a row, the number/note lines after it belong to it
    (pymupdf prints "Gross income\\n14,753\\n14,480" as three lines). Lossy for column-major layouts."""
    rows: list[str] = []
    for line in text.splitlines():
        bare = rows and not re.search(r"\d", rows[-1])  # the row so far is a label with no figures yet
        wrapped = bare and re.match(r"\s*[a-zåäöé]", line)  # "...before items affecting" / "comparability (SEK)1 3 11.55"
        noteref = bare and _NOTE_REFS.fullmatch(line.strip())  # Atrium Ljungberg: "Net sales" / "IE.3" / "3,446": the note sits on its own line between label and figures
        if re.search(r"[^\W\d_]{2,}", line) and not wrapped and not noteref:  # "G2, G3" is a note reference, not a label
            rows.append(line.strip())
        elif rows and line.strip():
            rows[-1] += " " + line.strip()
    return rows


def _clean_label(label) -> str:
    label = re.sub(r"(?<=[^\W\d_])[⁰¹²³⁴⁵⁶⁷⁸⁹]+", "", str(label or ""))  # footnote superscript glued to the label's own word ("SEK¹" -> "SEK"), stripped before NFKC turns it into a plain digit
    label = re.sub(r"(?i)\bresult\b", "profit", unicodedata.normalize("NFKC", label))  # Ericsson prints "ﬁnancial" with a ligature  # SSAB / Elekta / Stora Enso: "Operating result", "Result before tax", "Result for the year"
    label = re.sub(r"\s*[/(]\s*\(?loss\)?|/förlust", "", normalize_ws(label), flags=re.I)  # "Profit/loss before tax", "Profit (loss)"; normalize_ws glues digits to the word before
    label = re.sub(r"(?<=[^\W\d_])\d{1,2}\)", "", label)  # footnote marker glued to the label's own word, before currency/unit strip: SSAB "SEK1)" -> "SEK", "MSEK2)" -> "MSEK"
    label = re.sub(r",?\s*\(?\b(?:[kmbt]?(?:SEK|EUR|USD|NOK|DKK|ISK|GBP)|CHF|kr)\b\)?", "", label, flags=re.I)  # Castellum "Earnings, SEK per share before and after dilution"; "Resultat per aktie (SEK)"; magnitude prefix glued to the code as one token, same shape as _UNIT below ("Revenue, MSEK", "TSEK", "kSEK", "(MSEK)")
    label = re.sub(r"(?:\s+[A-Z]{1,3}\.?\d{1,2}(?:[-–]\d{1,2})?,?)+$", "", label)  # "Net sales IE.3", "Net sales B1, B2"
    label = re.sub(r"(?:\s*\[\d{1,2}\])+", "", label)  # TRATON "Income taxes [6]"
    return re.sub(r"[\s\d,.:;*)(]+$", "", label).lower()  # drop trailing note refs


def _label_known(label, sf: dict) -> bool:
    """The printed label is one of the field's synonyms (prefix match, the synonym run through the same _clean_label as
    the label — it glues digits, so "Within 1 year" / "1–5 years" / "> 5 år" compare against within1year, 1-5years, >5år)
    and none of its exclude_labels patterns (an adjusted / diluted / continuing-operations variant of the row is not the row)."""
    rl = _clean_label(label)
    if not rl or any(re.search(p, rl) for p in sf.get("exclude_labels", [])):
        return False
    return any(rl.startswith(cleans) for s in sf.get("synonyms", []) if (cleans := _clean_label(s)))  # a synonym that cleans away to nothing would prefix-match everything


def sweep_pages(texts: list[str], field: dict, tried_pages=(), top_n: int = 3,
                ocr_pending=()) -> dict:
    """Rank untried pages containing numeric rows labelled with a field synonym.

    This is the zero-model full-document fallback: it reconstructs the same ``_page_rows`` that
    extraction validates, and delegates label comparison to ``_label_known`` so case, ligatures,
    Swedish characters, result/profit wording and maturity-window digits receive exactly the normal
    guard's normalization.  One matching row is one hit; multiple overlapping synonyms cannot
    inflate a page.  ``ocr_pending`` pages deliberately have no text yet and are counted, not guessed.
    """
    tried = {page for page in tried_pages
             if isinstance(page, int) and not isinstance(page, bool)}
    pending = {page for page in ocr_pending
               if isinstance(page, int) and not isinstance(page, bool)}
    vocabulary = [*field.get("synonyms", []), *field.get("row_synonyms", [])]
    known = {**field, "synonyms": list(dict.fromkeys(str(word) for word in vocabulary if str(word).strip()))}
    hits: dict[int, int] = {}
    skipped = 0
    for page, text in enumerate(texts, 1):
        if page in pending:
            skipped += 1
            continue
        if page in tried:
            continue
        count = 0
        for row in _page_rows(text):
            label = _row_label(row)
            tail = row[len(label):]
            if re.search(r"\d", tail) and _label_known(label, known):
                count += 1
        if count:
            hits[page] = count
    ranked = sorted(hits, key=lambda page: (-hits[page], page))
    return {"pages": ranked[:max(0, top_n)], "hits": hits, "ocr_pending_skipped": skipped}


_BS_CURRENT = re.compile(r"\b(?:current|short[ -]?term|kortfristig\w*)\b", re.I)
_BS_NONCURRENT = re.compile(r"\b(?:non[ -]?current|long[ -]?term|långfristig\w*)\b", re.I)
_BS_LEASE = re.compile(r"\b(?:lease liabilities?|leaseskulder|leasingskulder)\b", re.I)
_BS_QUALIFIER = re.compile(r"^(?:total\s+)?(?:(?:non[ -]?current|long[ -]?term|långfristig\w*|current|short[ -]?term|kortfristig\w*)\s+)+", re.I)


def _balance_sheet_tie(texts: list[str], fiscal_year, total, schema: dict) -> tuple[list[dict], bool] | None:
    """The balance-sheet counterpart of debt_maturity's carrying total, if it is deterministic.

    Only the consolidated page `locate.balance_sheet_page` selected is read.  Rows must start with the
    total field's `row_synonyms` (with a leading current/non-current classification or ``Total``
    removed only for that exact row-label comparison), and their fiscal-year cells must be named by the
    row's own year header.  At most four such rows may sum to a non-null total within the existing
    two-unit band.  We prefer a no-lease solution when both scopes close, but record whether the
    chosen proof includes a lease row.

    `total is None` is deliberately narrower: exactly one current and one non-current, non-lease
    component row are returned for the value-derived null fill.  A balance sheet cannot otherwise
    choose a debt scope that the report did not make explicit.
    """
    if schema.get("name") != "debt_maturity" or not fiscal_year:
        return None
    total_sf = next((sf for sf in schema.get("fields", []) if sf.get("key") == "total_debt"), None)
    if total_sf is None:
        return None
    page = locate.balance_sheet_page(texts)
    if not page or not 0 < page <= len(texts):
        return None
    vocab = {"synonyms": total_sf.get("row_synonyms", [])}

    def known(label: str) -> bool:
        clean = _clean_label(label)
        subjects = [clean, re.sub(r"^total\s+", "", clean), _BS_QUALIFIER.sub("", clean)]
        return any(subject and any(subject.startswith(_clean_label(s)) for s in vocab["synonyms"])
                   for subject in subjects)

    rows = _page_rows(texts[page - 1])
    candidates = []
    for i, row in enumerate(rows):
        label = _row_label(row)
        if not known(label):
            continue
        # ``_row_amounts`` intentionally preserves ambiguous Swedish grouping for its general callers.
        # "16, 25, 26 912" can mean note refs 16/25/26 + 912, but generic degrouping reads 26,912.
        # A non-null model answer still needs the strict <=2 tie before this only adds evidence; a
        # null fill has no such target, so never derive it from that ambiguous current/non-current cell.
        if total is None and re.search(r"(?:\b\d{1,2},\s*){2,}\d{1,2}\s+\d{3}\b", row):
            continue
        header = _row_year_column(rows, i, fiscal_year)
        if not header:
            continue
        col, ncols = header
        amounts = _row_amounts(row, ncols, nil=None)
        if len(amounts) != ncols or not isinstance(amounts[col], (int, float)) or isinstance(amounts[col], bool):
            continue
        clean = _clean_label(label)
        kind = "lease" if _BS_LEASE.search(clean) else "non_current" if _BS_NONCURRENT.search(clean) \
            else "current" if _BS_CURRENT.search(clean) else "other"
        candidates.append({"page": page, "index": i, "row": row, "label": label,
                           "value": amounts[col], "kind": kind})

    if total is None:
        pairs = [pair for pair in itertools.combinations(candidates, 2)
                 if {row["kind"] for row in pair} == {"current", "non_current"}
                 and not any(row["kind"] == "lease" or _clean_label(row["label"]).startswith("total") for row in pair)]
        if not pairs:
            return None
        chosen = min(pairs, key=lambda pair: tuple(row["index"] for row in pair))
        return list(chosen), False

    if not isinstance(total, (int, float)) or isinstance(total, bool):
        return None
    matches = []
    for count in range(1, min(4, len(candidates)) + 1):
        for rows_subset in itertools.combinations(candidates, count):
            if abs(sum(row["value"] for row in rows_subset) - total) <= 2:
                matches.append(rows_subset)
    if not matches:
        return None

    def order(rows_subset):
        has_lease = any(row["kind"] == "lease" for row in rows_subset)
        total_rows = sum(_clean_label(row["label"]).startswith("total") for row in rows_subset)
        return has_lease, total_rows, len(rows_subset) == 1, len(rows_subset), tuple(row["index"] for row in rows_subset)

    chosen = min(matches, key=order)
    return list(chosen), any(row["kind"] == "lease" for row in chosen)


def _row_label(row: str) -> str:
    """'Gross income 14,753 14,480' -> 'Gross income'. A number the label goes on using stays in it ("Within 1 year",
    "Inom 1 år" -> "Within 1 year" / "Inom 1 år", debt-maturity bucket rows): the amounts start at the first number
    that is not followed by a lowercase word ("14 4.74 8.32 MSEK" cuts before the 14, "8, 9, 10" is a note column)."""
    row = row.strip()
    for m in re.finditer(r"\s+(?=[-(–−]?\d)", row):
        rest = row[m.end():]
        num = re.match(r"[-(–−]?\d[\d,.']*", rest)
        if num and re.match(r"\s*[a-zåäöæø]", rest[num.end():]):  # "1 year": a label word; "1 000" / "100 MSEK" is where the amounts start
            continue
        return row[:m.start()].rstrip(" ,.:;*")
    return row.rstrip(" ,.:;*")


_CCY = re.compile(r"(?<![A-Za-z])(?:[MTk]|Mdr?)?(?:SEK|EUR|USD|NOK|DKK|GBP|CHF|ISK|PLN|EURO|[Kk][Rr]|€|\$|£)(?:m|mn|bn|k|t)?(?![A-Za-z])")  # currency codes as printed: "MSEK", "Mkr", "EUR", "€m"


def _ccy(unit) -> str:
    """'MSEK' / 'SEKm' / 'USD m' / 'SEK million' -> 'SEK' / 'USD': the currency without the scale."""
    unit = str(unit or "").translate(_SYMBOLS)  # Medicover "€m"
    c = re.sub(r"(?i)\b(m|mn|million|millions|thousand|thousands|bn|billion|k|cent|cents|öre|in|i)\b|[^A-Za-z]", "", unit).upper()  # Alvotech "USD in thousands"
    c = {"EURO": "EUR", "KR": "SEK", "KRONOR": "SEK", "MKR": "SEK", "MDKR": "SEK", "TKR": "SEK"}.get(c, c)  # Hexagon prints EPS in "Euro cent"
    if len(c) == 4 and c[0] in "MKT":  # MSEK, KSEK (Paradox), TEUR
        c = c[1:]
    if len(c) == 4 and c[-1] in "MKT":
        c = c[:-1]
    return c


_SYMBOLS = str.maketrans({"€": "EUR ", "$": "USD ", "£": "GBP "})
_UNIT = re.compile(r"(?:\b(?:[MKT](?:SEK|EUR|USD|NOK|DKK|GBP)|[MT]kr|mnkr|mdkr|(?:SEK|EUR|USD|NOK|DKK|GBP|CHF)\s?(?:m|mn|million|millions|thousand|thousands|k|bn|billion))|[€$£]\s?(?:m|mn|million|millions|thousand|thousands|k|bn|billion))\b", re.I)  # "SEK m", "USD Thousands", "€m"


def _page_unit(text: str):
    """'SEK m' / 'MSEK' / 'USD Thousands' from the statement page's header, or None."""
    m = _UNIT.search(" ".join(text[:4000].split()))
    return m.group() if m else None


def _declared_report_unit(texts: list[str]) -> tuple[str, int] | None:
    """Use an explicit report-wide amounts declaration, never currency popularity.

    Conflicting declarations stay unresolved. Local table units take precedence
    at the call site. Preserve the printed unit and page for the audit trail.
    """
    declarations: dict[str, tuple[str, int]] = {}
    for page, text in enumerate(texts, 1):
        for match in re.finditer(
            r"\bAmounts\s+(?:are\s+)?(?:stated|presented|expressed)\s+in\s+"
            r"([^.;\n]{1,35}?)\s+unless\s+(?:otherwise\s+(?:stated|specified)|(?:stated|specified)\s+otherwise)",
            " ".join(text.split()), re.I,
        ):
            unit = match.group(1).strip()
            if _UNIT.fullmatch(unit):
                declarations.setdefault(unit.lower(), (unit, page))
    return next(iter(declarations.values())) if len(declarations) == 1 else None


def _num_pattern(value) -> str | None:
    """Regex for the number as it could be printed: thousands groups with any separator, decimals with . or ,
    '168343' -> 168[ ,.']?343 ; 5424.6 -> 5[ ,.']?424[.,]6. Sign is ignored (parentheses, en dash)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    txt = repr(abs(value)) if isinstance(value, float) else str(abs(value))
    ip, _, dp = txt.partition(".")
    groups = [ip[max(0, i - 3):i] for i in range(len(ip), 0, -3)][::-1]
    pat = r"[\s,.'\u00a0]?".join(groups)
    if dp and dp != "0":
        pat += r"[.,]" + dp + "0*"  # 0.9 is printed "0.90", 11.7 as "11,70"
    return r"(?<![\d.,])" + pat + r"(?![\d])"


def _value_in_quote(value, quote: str) -> bool:
    pat = _num_pattern(value)
    return pat is not None and re.search(pat, _FOOTNOTE.sub("", quote)) is not None


def repair_value(value, quote: str):
    """The model sometimes rescales (5,424.6 -> 5424600) or drops the decimal point (11.71 -> 1171).
    The quote is verified on the page, so if the value itself is not printed there but value/10, /100 or
    /1000 is (with decimals), the printed number wins. Returns the fix or None."""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or _value_in_quote(value, quote):
        return None
    for div in (10, 100, 1000):
        cand = round(value / div, 4)
        if (cand != int(cand) or abs(cand) >= 10) and _value_in_quote(cand, quote):  # "168 343" never becomes 168.343; 230 -> "23.0" is fine
            return int(cand) if cand == int(cand) else cand
    return None


def _stated_zero(field: dict, sf: dict, schema: dict, texts: list[str]) -> bool:
    """A 0 the model returned is proven by the report's own words, not by a printed figure. Every gate
    must hold: the field's schema opted in ("zero_if_stated" -- the field-level analogue of a check's
    null_as_zero); the value is exactly 0; the quote carries no digit at all (a numeric quote is the
    existing provenance gates' job -- repair_value, the printed-zero checks -- not this one); the
    sentence sits verbatim on the cited page, whitespace/NBSP-insensitive via normalize_ws (quote_on_page
    itself requires a number token, which a prose negation structurally never has, Creades v048); the
    sentence names the field's subject (a schema keyword, one of the field's own synonyms, or one of
    zero_if_stated's own subject_terms -- bare words like "loan(s)" that real no-debt prose is written in
    but the label vocabulary must never list, Vicore Pharma / BioGaia v062); and a negation word from the
    schema's own list is present -- so a bare row label quoted alone ("Summa räntebärande skulder" off a
    column-major table) stays a drop, never becomes a 0."""
    if isinstance(field.get("value"), bool) or field.get("value") != 0 or not isinstance(sf.get("zero_if_stated"), dict):
        return False
    src = field.get("source") or {}
    quote, page = src.get("quote") or "", src.get("page")
    if not isinstance(page, int) or not 1 <= page <= len(texts) or not quote or any(c.isdigit() for c in quote):
        return False
    q = normalize_ws(quote).lower()
    if q not in normalize_ws(texts[page - 1]).lower():
        return False
    vocab = [normalize_ws(v).lower() for v in schema.get("keywords", []) + sf.get("synonyms", [])
             + sf["zero_if_stated"].get("subject_terms", [])]
    if not any(v and v in q for v in vocab):  # the sentence must be about this field's subject
        return False
    return bool(set(q.split()) & {w.lower() for w in sf["zero_if_stated"].get("negations", [])})


def _model_zero_on_dash_row(field: dict, sf: dict, texts: list[str], pages: list[int], fiscal_year) -> tuple[int, str] | None:
    """(v134) A model-answered 0 whose citation is a row the report prints as dashes: Linc p.100's
    "Räntebärande skulder – –" (the NAV reconciliation's own borrowings line, v090's standing gap) and
    Rejlers' "1-2 years - -" bucket rows quoted as one block (v097 finding 4). quote_on_page can never
    verify such a quote (a dash is no number token), and often no 0 is printed anywhere to fall back on,
    so the answer died as "computed, not read" (Linc) or survived unproven at 0.25 (Rejlers). The dash is
    the report's own printed nil (v036's convention, v078's translation), kept here under conditions all
    on the rows the quote matches on the cited page (or the statement spread): every matched row's label
    is one of the field's known synonyms (the total field's row_synonyms count -- the same vocabulary
    _bucket_total_row recognises the debt row by), and it prints no figure in the fiscal-year column
    (_row_year_column's; when no header names one, every numeric column must be a dash). v078's own
    arithmetic gate cannot run here -- an all-dash row prints no total for its nils to close against --
    and needs no successor: the model's 0 is not assembled from anything, and any row that could lend it
    a figure disqualifies the quote, either by being matched itself (a matched row printing a figure
    where the fiscal year reads is a contradiction, not a nil) or by sitting unquoted on the same page
    under one of the field's own labels with real amounts (the lease-liabilities row next to a bank-loans
    row with figures is not a zero total). A matched row _bucket_row_prior_year proves prior-year is
    refused too: last year's dash is not this year's 0. Returns (page, first qualifying row) or None."""
    if isinstance(field.get("value"), bool) or field.get("value") != 0:
        return None
    src = field.get("source") or {}
    page, quote = src.get("page"), str(src.get("quote") or "")
    if not isinstance(page, int) or not 0 < page <= len(texts) or not quote.strip():
        return None
    vocab = {"synonyms": sf.get("synonyms", []) + sf.get("row_synonyms", [])}
    nq = normalize_ws(quote).casefold()
    if not any(c.isalpha() for c in nq):
        return None
    for p in dict.fromkeys([page, *(q for q in pages[:2] if q != page)]):
        if not 0 < p <= len(texts):
            continue
        rows = _page_rows(texts[p - 1])
        hit, matched = None, set()
        for i, r in enumerate(rows):
            nr = normalize_ws(r).casefold()
            if not nr or not any(c.isalpha() for c in nr) or (nr not in nq and nq not in nr):
                continue  # not a row the quote is about
            matched.add(r)
            if not _label_known(_row_label(r), vocab) or _bucket_row_prior_year(rows, i, fiscal_year):
                return None  # the quote names a row this field is not, or last year's: the 0 is the model's, not the page's
            am = _row_amounts(r, None, nil=None)
            if am and all(a is None for a in am):
                hit = hit or r
                continue
            header = _row_year_column(rows, i, fiscal_year) if fiscal_year else None
            if header and len(am2 := _row_amounts(r, header[1], nil=None)) == header[1] and am2[header[0]] is None:
                hit = hit or r  # a figure may print in another column (prior year, carrying amount); the fiscal-year one is the dash
                continue
            return None  # the row prints a figure where the fiscal year reads: the 0 contradicts the page
        if hit is None:
            continue
        if any(r not in matched and _label_known(_row_label(r), vocab) and (am3 := _row_amounts(r, None, nil=None))
               and any(a is not None for a in am3) for r in rows):  # v134: no other figure for this field's own vocabulary may sit unquoted on the page
            continue
        return p, hit
    return None


def _signed(amounts: list, col: int, value) -> list:
    """Swedbank prints expenses positive, the field carries them negative: the whole row flips with the fiscal-year figure."""
    return [-a for a in amounts] if col < len(amounts) and amounts[col] == -value and value else amounts


def _column_values(field: dict, fields: list[dict], defaults: dict, texts: list[str], fiscal_year, anchor: str | None = None) -> list[dict] | None:
    """Per table column, the other fields' printed figures ({key: amount}), for fields whose verified quote is a full row
    of the same table layout. Lets a check be evaluated in the comparative column too. The header is the quoted row's own
    table's (_row_year_column), not the page's first -- a note page can stack two tables -- and each other field is
    admitted by the header of ITS OWN quoted row, so same-page rows of the other table are not mixed in; `anchor` stands
    in for the quote when the caller derives for a rowless field (_between_rows), and a quote that is not a printed row
    falls back to the page's own header, as before."""
    src = field.get("source") or {}
    if not src.get("page"):
        return None
    text = texts[src["page"] - 1]
    quote = src.get("quote") or anchor
    rows = _page_rows(text)
    i = rows.index(quote) if quote and quote in rows else None
    header = _row_year_column(rows, i, fiscal_year) if i is not None else _year_column(text, fiscal_year)
    if not header:
        return None
    col, ncols = header
    cols = [dict(defaults) for _ in range(ncols)]
    for g in fields:
        gs = g.get("source") or {}
        if g is field or g["value"] is None or not gs.get("page") or "quote_on_page" not in g["evidence"]:
            continue
        gtext, grows = texts[gs["page"] - 1], _page_rows(texts[gs["page"] - 1])
        gi = grows.index(gs["quote"]) if gs.get("quote") and gs["quote"] in grows else None
        gheader = _row_year_column(grows, gi, fiscal_year) if gi is not None else _year_column(gtext, fiscal_year)
        if gheader != header:
            continue
        am = _signed(_row_amounts(gs["quote"], ncols), col, g["value"])
        if len(am) == ncols and am[col] == g["value"]:
            for c in range(ncols):
                cols[c][g["key"]] = am[c]
    return cols


_FINANCIAL_LIABILITIES_ROLLFORWARD = re.compile(
    r"(?i)(?:changes?\s+in\s+financial\s+liabilities|förändring(?:ar)?\s+finansiella\s+skulder)"
)
_GENERIC_TOTAL_ROW = re.compile(r"(?i)^(?:total|summa)\b")
_ROLLFORWARD_DEBT_COMPONENT = re.compile(
    r"(?i)(?:credit\s+institutions?|creditinstitut|bank|loans?|lån|lease|leasing|interest[ -]bearing|räntebärande|borrowing\s+costs?|lånekostnad)"
)


def _rollforward_terminal_amount(row: str) -> float | None:
    """The rightmost printed figure of a roll-forward total row.

    The roll-forward has no compact year-column header for ``_row_amounts`` to
    use. Its final total can nevertheless be read without guessing at the
    preceding movement columns: retain a final Swedish thousands pair unless
    its leading token carries the previous column's minus sign.
    """
    tail = row[len(_row_label(row)):].strip().split()
    if not tail:
        return None
    token = tail[-1].rstrip(",;")
    if not re.fullmatch(r"[-(]?\d{1,3}(?:[,.']\d{3})*(?:[.,]\d{1,4})?\)?", token):
        return None
    if len(tail) >= 2 and re.fullmatch(r"\d{1,3}", tail[-2]) and re.fullmatch(r"\d{3}", token):
        token = tail[-2] + token  # "12 103" is one closing value, not two columns
    parsed = _row_amounts("amount " + token)
    return parsed[-1] if parsed else None


def _financial_liabilities_rollforward_total(rows: list[str], fiscal_year) -> tuple[float, str, str] | None:
    """The current closing total from a narrowly identified debt roll-forward.

    A page can put a currency-by-debt summary and a ``Changes in financial
    liabilities`` roll-forward beside one another. Both end in a generic
    ``Total``/``SUMMA`` row, so a model citation of the former has no row
    label for the normal synonym repair to prefer. The latter is a usable
    total only when its heading names financial liabilities, its current-year
    block contains exclusively debt/lease/borrowing-cost components. That
    leaves generic financial-liabilities tables (payables included), arbitrary
    total rows, and the comparative roll-forward alone.
    """
    year = str(fiscal_year) if fiscal_year else ""
    if not year:
        return None
    for start, heading in enumerate(rows):
        if not _FINANCIAL_LIABILITIES_ROLLFORWARD.search(heading):
            continue
        for end in range(start + 1, min(start + 31, len(rows))):
            if end > start + 1 and _FINANCIAL_LIABILITIES_ROLLFORWARD.search(rows[end]):
                break  # a second (normally comparative) roll-forward starts here
            if not _GENERIC_TOTAL_ROW.match(_row_label(rows[end])):
                continue
            # The final balance date lives in the short header block immediately
            # above the component rows (AcadeMedia: "30 juni 2025"). Do not
            # infer a fiscal year from the prior block's values.
            if year not in " ".join(rows[start:end]):
                continue
            components: list[str] = []
            j = end - 1
            while j > start:
                label = _row_label(rows[j])
                if not _ROLLFORWARD_DEBT_COMPONENT.search(label):
                    break
                components.append(label)
                j -= 1
            closing = _rollforward_terminal_amount(rows[end])
            if len(components) < 2 or closing is None:
                continue
            return closing, rows[end], _row_label(rows[end])
    return None


def _derived_value(field: dict, texts: list[str], fiscal_year, check: dict | None = None, others: list[dict] | None = None, taken: set | None = None,
                   own_syns: set | None = None):
    """(value, quote, label) when the field's figure is proven by the rows around its quote, column by column:
    (a) the quote is a total row whose fiscal-year figure is unreadable: the 2..6 rows above sum to the row in every other
        column (Röko's text layer prints "Profit before tax 1,01 923"; 1,051 + 49 - 90 = 1,010 while 969 + 66 - 112 = 923);
    (b) the value is printed nowhere: it is the sum of the 2..8 rows ending at the quote (Catena "Current tax -56" +
        "Deferred tax -367" = -423; IPC's four rows under the "Cost of sales" heading), and the check that ties the field
        to its neighbours holds with those sums in every column, not just the fiscal year's.
    The quote becomes those rows; in (b) the label becomes the heading above them, or the rows' labels joined. No addend may be
    another field's row (`taken`): a sum over the identity's other operands restates the identity and proves nothing. When the quote
    is the field's own row (`own_syns`, its synonyms), (b) may only add rows named as part of it: Essity's "Cost of goods sold" +
    "Items affecting comparability (IAC) – cost of goods sold" closes gross profit; Sagax's "Deferred tax" never joins "Profit before tax"."""
    src = field.get("source") or {}
    text = texts[src["page"] - 1] if src.get("page") else ""
    rows = _page_rows(text)
    if src.get("quote") not in rows:
        return None
    i = rows.index(src["quote"])
    header = _row_year_column(rows, i, fiscal_year)  # row-anchored: this derivation proves the quoted row's own table, not whichever table printed first on the page
    if not header:
        return None
    col, ncols = header
    own = _row_amounts(src["quote"], ncols)
    for k in range(2, 7 if len(own) == ncols else 2):
        parts = [_row_amounts(r, ncols) for r in rows[max(i - k, 0):i]]
        if len(parts) < k or any(len(a) != ncols for a in parts):
            break  # a heading or a row without amounts ends the run of addends
        sums = [round(sum(a[c] for a in parts), 2) for c in range(ncols)]
        quote = " ".join(rows[i - k:i])
        if all(sums[c] == own[c] for c in range(ncols) if c != col) and sums[col] != field["value"] and quote_on_page(quote, text):
            return sums[col], quote, field.get("raw_label")
    if not check or others is None:
        return None
    for k in range(2, 9):
        for start in range(max(i - k, 0), i + 1):  # the k rows ending at the quote (Catena), starting at it, or just above it (IPC: the model quoted the "Gross profit" subtotal for the four rows under "Cost of sales")
            parts = [_row_amounts(r, ncols) for r in rows[start:start + k]]
            if len(parts) < k or any(len(a) != ncols for a in parts) or any(r in (taken or ()) for r in rows[start:start + k]):
                continue
            if own_syns and any(r != src["quote"] and not any(x in _clean_label(_row_label(r)) for x in own_syns) for r in rows[start:start + k]):
                continue
            sums = [round(sum(a[c] for a in parts), 2) for c in range(ncols)]
            if not all(_check(check, {**others[c], field["key"]: sums[c]})["passed"] for c in range(ncols)):
                continue
            quote = " ".join(rows[start:start + k])
            heading = rows[start - 1] if start >= 1 and not _row_amounts(rows[start - 1], ncols) else None
            if quote_on_page(quote, text):
                return sums[col], quote, _row_label(heading) if heading else " + ".join(_row_label(r) for r in rows[start:start + k])
    return None


def _between_rows(sf: dict, fields: list[dict], sfs: list[dict], defaults: dict, texts: list[str], fiscal_year, check: dict, page: int,
                  scope_words: dict | None = None, basis: str = "carrying", warnings: list[str] | None = None,
                  debt_words: list[str] | None = None, missing_events: list[tuple[tuple[str, ...], dict]] | None = None):
    """A missing operand of an identity when the model answered nothing: the full rows printed strictly between the other
    operands' rows, when their sums close the identity in every column (Addnode: "Profit after financial items 514 536",
    "Current tax -157 -154", "Deferred tax 27 20", "Profit for the year 384 402"; no total tax row exists), the one row among them
    printed with the field's label when it alone closes the identity (ABB's discontinued operations under the continuing-ops subtotal),
    or -- when nothing sits between -- the k full rows printed directly above the uppermost operand's row, where a first-year
    bucket split lives (MedCap prints "6 månader eller mindre" + "6 – 12 månader" directly above the "1 – 5 år" row, so no row is
    strictly between the operands). None of the rows may carry another field's label. (value, quote, label, number of rows) or None."""
    text = texts[page - 1]
    rows = _page_rows(text)
    idx = [rows.index(g["source"]["quote"]) for g in fields if g["value"] is not None and (g.get("source") or {}).get("page") == page
           and g["source"]["quote"] in rows and re.search(rf"\b{re.escape(g['key'])}\b", check["expr"])]
    if len(idx) < 2:
        return None
    top = min(idx)
    scope = _table_scope(rows, None, top, basis, scope_words, debt_words=debt_words) if scope_words else "unknown"
    if scope in _REFUSED_SCOPES:
        # v103/v111: no derivation out of a table the guard refuses -- anchored at the uppermost operand row,
        # the row whose table the between/window rows belong to
        if warnings is not None:
            warnings.append(f"{sf['key']}: no between-rows derivation -- {_scope_reason(rows, None, top, scope_words, scope)}; "
                            f"not read under the {basis} basis")
        if (reason := _scope_missing_reason(rows, None, top, scope_words, scope)) is not None:
            _record_missing_reason(missing_events, [sf["key"]], page=page, **reason)
        return None
    header = _row_year_column(rows, top, fiscal_year)  # row-anchored at the uppermost operand row: the rows this derivation reads sit at or directly above it
    if not header or header[1] < 2:
        return None
    col, ncols = header
    between = [r for i, r in enumerate(rows) if min(idx) < i < max(idx) and i not in idx and len(_row_amounts(r, ncols)) == ncols]  # ABB: the tax row sits between too
    others = _column_values({"source": {"page": page}}, fields, defaults, texts, fiscal_year, anchor=rows[top])  # rowless caller: anchor at the operand row
    if not others:
        return None
    if between and not any(_label_known(_row_label(r), gs) for r in between for gs in sfs if gs is not sf):
        parts = [_row_amounts(r, ncols) for r in between]
        sums = [round(sum(a[c] for a in parts), 2) for c in range(ncols)]
        quote = " ".join(between)
        known = [r for r in between if _label_known(_row_label(r), sf)]  # ABB: "Income from discontinued operations, net of tax 174 226" sits between the
        if len(known) == 1 and quote_on_page(known[0], text):  # tax and net income rows under the "continuing operations, net of tax" subtotal; the one row with the field's label is it
            am = _row_amounts(known[0], ncols)
            if all(_check(check, {**others[c], sf["key"]: am[c]})["passed"] for c in range(ncols)):
                return am[col], known[0], _row_label(known[0]), 1
        if all(_check(check, {**others[c], sf["key"]: sums[c]})["passed"] for c in range(ncols)) and quote_on_page(quote, text):
            return sums[col], quote, " + ".join(_row_label(r) for r in between), len(between)
    for k in range(2, 9):  # the window above the uppermost operand row: 2..8 full rows, the same span the sum repair reads
        start = top - k
        if start < 0:
            break
        window = rows[start:top]
        if any(len(_row_amounts(r, ncols)) != ncols for r in window):
            continue
        if any(_label_known(_row_label(r), gs) for r in window for gs in sfs if gs is not sf):
            continue
        parts = [_row_amounts(r, ncols) for r in window]
        sums = [round(sum(a[c] for a in parts), 2) for c in range(ncols)]
        quote = " ".join(window)
        if all(_check(check, {**others[c], sf["key"]: sums[c]})["passed"] for c in range(ncols)) and quote_on_page(quote, text):
            return sums[col], quote, " + ".join(_row_label(r) for r in window), k
    return None


_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_MATURITY_DATE = re.compile(rf"(?i)\b(\d{{1,2}})\s+({'|'.join(_MONTHS)})[a-z]*\.?\s+(20\d\d)\b")  # "16 Jul 2026"
_MATURITY_RANGE = re.compile(r"\b(20\d\d)\s*[-–−]\s*(20\d\d)\b")  # "2027-2030"
_MATURITY_YEAR = re.compile(r"\b(20\d\d)\b")
_DATE_BUCKET_KEYS = {"due_within_1_year", "due_1_to_5_years", "due_after_5_years"}
_DATE_BUCKET_WINDOW = 15  # rows looked back from total_debt's own row; Proact's own instrument list (v073) is 7 rows deep


def _bucket_for_date(d: date, fye: date) -> str:
    """Calendar-exact, not a fixed day-count: "within 1 year" is on or before the date exactly one year
    after fye, so a bare next-calendar-year value lands here whether or not a leap day falls in between --
    a fixed 366-day cutoff instead would tip a range's own start (e.g. "2027" against a 2025-12-31 fye is
    exactly 366 days out) into the wrong bucket and manufacture a false straddle (v073)."""
    return ("due_within_1_year" if d <= fye.replace(year=fye.year + 1) else
            "due_1_to_5_years" if d <= fye.replace(year=fye.year + 5) else "due_after_5_years")


def _maturity_bucket(row: str, fye: date) -> str | None:
    """Which debt_maturity bucket a row's own printed maturity falls into, relative to the balance sheet
    date `fye`: a day-month-year date ("16 Jul 2026") is a point, bucketed directly; a year range
    ("2027-2030") is bucketed by its own start, but only when its end lands in the SAME bucket -- a range
    straddling a boundary proves nothing about which side the debt sits on, so it returns "straddle" rather
    than guess; a bare year ("2026") is its own Jan-1..Dec-31 span, checked the same way. A row naming its
    own maturity three times or more is never a candidate -- a loan's own line names it once (a range
    twice); three-plus is a running header or a repeated watermark that _page_rows glued into one row
    (Proact's own page prints one such line, v073), not a printed instrument."""
    if len(_MATURITY_YEAR.findall(row)) > 2:
        return None
    m = _MATURITY_DATE.search(row)
    if m:
        d = date(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        return _bucket_for_date(d, fye)
    m = _MATURITY_RANGE.search(row)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
    else:
        m = _MATURITY_YEAR.search(row)
        if not m:
            return None
        start = end = int(m.group(1))
    lo, hi = _bucket_for_date(date(start, 1, 1), fye), _bucket_for_date(date(end, 12, 31), fye)
    return lo if lo == hi else "straddle"


def _balance_sheet_date(window: list[str], fiscal_year) -> date:
    """The date maturities are measured from: 31 Dec of fiscal_year by default, or the day/month a
    caption in the table's own window states for that year (Proact and Nederman both print "31 Dec
    2025" anyway; a fiscal year ending on another date would print its own day/month here instead). A
    candidate date only counts when nothing _row_amounts recognises as an amount follows it on the same
    row -- an instrument's OWN due-date row states its own maturity, immediately followed by its own
    carrying amount (or a nil "-"), and must never be mistaken for the table's caption."""
    for r in window:
        m = _MATURITY_DATE.search(r)
        if m and int(m.group(3)) == int(fiscal_year) and not _row_amounts(r[m.end():]):
            return date(int(fiscal_year), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
    return date(int(fiscal_year), 12, 31)


def _date_bucket_derive(schema: dict, fields: list[dict], texts: list[str], fiscal_year,
                        basis: str = "carrying", warnings: list[str] | None = None,
                        missing_events: list[tuple[tuple[str, ...], dict]] | None = None) -> dict[str, tuple] | None:
    """{key: (value, quote, page, raw_label)} for however many of debt_maturity's three buckets a date-
    per-instrument note proves, when the model answered null on some or all of them: Proact prints one row
    per loan/lease -- label, then its own due date/year/year-range, then its carrying amount -- instead of
    bucket rows or bucket columns (docs/acrylic/evidence/v063.md gap 2, v073). A third maturity shape
    besides those two, so it gets its own function alongside _between_rows, tried at the same "missing
    operand" trigger point in extract().

    Scoped to total_debt's own table the way _operand_table_rows anchors elsewhere (v058): a bounded
    window of rows immediately above total_debt's own verified row, not a page-wide search. Reusing
    _operand_table_rows itself does not fit this shape -- its year-header boundary test (_year_run) fires
    on a bare year-RANGE value ("2027-2030") as if it were a 2-column table header, cutting the window
    down to one row before it ever reaches the instruments above. Amounts come from each row's own last
    printed number: a single-column list like this has no year header for _row_year_column to key a
    column off. Buckets the model already filled are left alone -- this only ever proposes values, never
    overwrites one -- and the caller adopts them only when they close maturity_sums_to_total exactly.
    None here means no qualifying row was found near the total, not that none exists elsewhere on the page."""
    ident = _identity_parts(schema)
    if not ident or not fiscal_year:
        return None
    total_key, part_keys = ident
    if set(part_keys) != _DATE_BUCKET_KEYS:
        return None  # the day/year/range bucketing below is this schema's own three durations, not a generic split
    by_key = {f["key"]: f for f in fields}
    total = by_key.get(total_key) or {}
    src = total.get("source") or {}
    page = src.get("page")
    if not isinstance(total.get("value"), (int, float)) or isinstance(total["value"], bool) \
            or not isinstance(page, int) or not (0 < page <= len(texts)) or not src.get("quote"):
        return None
    text = texts[page - 1]
    rows = _page_rows(text)
    if src["quote"] not in rows:
        return None
    ti = rows.index(src["quote"])
    scope = _table_scope(rows, None, ti, basis, schema.get("table_scope_words"),
                         debt_words=_debt_subject_words(schema) if schema.get("table_scope_words") else None) \
        if schema.get("table_scope_words") else "unknown"
    if scope in _REFUSED_SCOPES:
        # v103/v111: no date-bucket derivation out of a table the guard refuses -- anchored at total_debt's
        # own verified row, whose window the instrument rows above it belong to
        if warnings is not None:
            warnings.append(f"{total_key}: no date-bucket derivation -- {_scope_reason(rows, None, ti, schema['table_scope_words'], scope)}; "
                            f"not read under the {basis} basis")
        if (reason := _scope_missing_reason(rows, None, ti, schema["table_scope_words"], scope)) is not None:
            _record_missing_reason(missing_events, part_keys, page=page, **reason)
        return None
    window = rows[max(0, ti - _DATE_BUCKET_WINDOW):ti]
    fye = _balance_sheet_date(window, fiscal_year)
    sums: dict[str, float] = {}
    contrib: dict[str, list[tuple[int, str]]] = {}
    for i, r in enumerate(window):
        bucket = _maturity_bucket(r, fye)
        if bucket == "straddle":
            span = _MATURITY_RANGE.search(r)
            amounts = _row_amounts(r)
            disclosed = [{
                "span": span.group(0) if span else _row_label(r),
                "amount": amounts[-1] if amounts else None,
                "unit": total.get("unit"),
                "page": page,
                "quote": r,
            }]
            _record_missing_reason(
                missing_events, part_keys, "straddle",
                f"The report's {disclosed[0]['span']} interval crosses a standard maturity-bucket boundary, so it cannot be assigned without guessing.",
                page=page, quote=r, disclosed=disclosed,
            )
            return None  # a year range this table prints straddles a bucket boundary -- no safe read of ANY row here
        if bucket is None:
            continue
        amounts = _row_amounts(r)
        if not amounts:
            continue
        sums[bucket] = round(sums.get(bucket, 0) + amounts[-1], 2)
        contrib.setdefault(bucket, []).append((i, r))
    if not sums:
        return None
    first = min(i for rs in contrib.values() for i, _ in rs)
    quote = " ".join(window[first:])
    if not quote_on_page(quote, text):
        return None
    return {k: (v, quote, page, " + ".join(_row_label(r) for _, r in contrib[k])) for k, v in sums.items()}


_SPAN_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
               "ett": 1, "två": 2, "tre": 3, "fyra": 4, "fem": 5}  # the small number words real tables print
_SPAN_NUM = r"(\d{1,3}|one|two|three|four|five|ett|två|tre|fyra|fem)"
_SPAN_UNIT = r"(years?|år|months?|månader|mån)"


def _bucket_span(label) -> tuple[int, float] | None:
    """(lo_months, hi_months) for a maturity row label that names its own interval -- "0–6 months",
    "7–12 months", "6 months or less", "6 månader eller mindre", "6 – 12 månader", "1–2 years",
    "2–5 years", "1 – 5 år", "between 1 and 2 years", "mellan 1 år och 2 år" (each operand its own
    unit, v104: "mellan 3 månader och 1 år"), "later than 1 year but within 3 years", "högst 2 år",
    ">5 years", "mer än 5 år" -- or None when the label names no interval, never a guess. An
    unbounded upper bound is inf. Used by _finer_split_rows only; interval GEOMETRY, not the bucket
    vocabulary -- v088's rejected schema fix proved these wordings must not enter the synonym lists
    the column scanner also reads ("0-6 months" in due_within_1_year.synonyms leaks into
    _bucket_synonym_hits and changes _bucket_header's read), so this parser shares nothing with it.
    Deliberately not units: bare "y"/"yr" (Stillfront's component wording "Repayment within 2–5 yr."
    is a duration label, not a maturity interval) and day wording like "-30 dgr" (XANO's finer
    day/month columns are the subtotal-column mechanism's territory, v078)."""
    t = " ".join(str(label or "").strip().lower().translate(_DASHES).split())

    def months(tok, unit) -> int:
        return (int(tok) if tok.isdigit() else _SPAN_WORDS[tok]) * (1 if re.fullmatch(r"months?|månader|mån", unit) else 12)

    m = re.fullmatch(rf"{_SPAN_NUM}\s*-\s*{_SPAN_NUM}\s+{_SPAN_UNIT}", t)  # "0-6 months", "1 - 5 år"
    if m:
        return (months(m.group(1), m.group(3)), months(m.group(2), m.group(3))) \
            if months(m.group(1), m.group(3)) <= months(m.group(2), m.group(3)) else None
    m = re.fullmatch(rf"(?:between|mellan)\s+{_SPAN_NUM}\s*(?:{_SPAN_UNIT})?\s+(?:and|och)\s+{_SPAN_NUM}\s+{_SPAN_UNIT}", t)
    if m:  # "between 1 and 2 years", "mellan 1 och 5 år" -- and Svedbergs p.132's long forms, where EACH
        # operand names its own unit ("mellan 3 månader och 1 år" = [3,12], "mellan 2 år och 5 år" = [24,60])
        lo, hi = months(m.group(1), m.group(2) or m.group(4)), months(m.group(3), m.group(4))
        return (lo, hi) if lo <= hi else None
    m = re.fullmatch(rf"(?:later than|senare än)\s+{_SPAN_NUM}\s*{_SPAN_UNIT}?\s+(?:but|men)\s+(?:within|inom)\s+{_SPAN_NUM}\s+{_SPAN_UNIT}", t)
    if m:  # "later than 1 year but within 3 years": both ends named, units may differ
        return (months(m.group(1), m.group(2) or m.group(4)), months(m.group(3), m.group(4)))
    for pat, open_low in ((rf"(?:less than|under|mindre än|högst|<)\s*{_SPAN_NUM}\s+{_SPAN_UNIT}", True),  # "< 1 år", "mindre än 3 månader", "högst 2 år"
                          (rf"(?:within|inom)\s+{_SPAN_NUM}\s+{_SPAN_UNIT}", True),  # "Within one year"
                          (rf"{_SPAN_NUM}\s+{_SPAN_UNIT}\s+(?:or less|eller mindre)", True),  # "6 månader eller mindre"
                          (rf"(?:more than|over|later than|after|mer än|senare än|efter|över|>)\s*{_SPAN_NUM}\s+{_SPAN_UNIT}", False),
                          (rf"{_SPAN_NUM}\s+{_SPAN_UNIT}\s+(?:or more|eller mer)", False)):
        m = re.fullmatch(pat, t)
        if m:  # open-ended: the closed end is 0 below / inf above the named bound
            n = months(m.group(1), m.group(2))
            return (0, n) if open_low else (n, float("inf"))
    return None


def _span_bucket(span: tuple[int, float]) -> str | None:
    """Which debt_maturity bucket a label's whole interval falls inside: [0,12] months = within 1
    year, [12,60] = 1–5 years, [60,inf) = after 5 -- the schema's own value_convention ("sum
    whichever of the report's own columns fall entirely inside a bucket's range"). None when the
    span crosses a boundary ("3–7 years" is [36,84]): the table's own granularity cannot decide
    which side of 5 years that debt sits on, and the caller abandons the whole derivation."""
    lo, hi = span
    if hi <= 12:
        return "due_within_1_year"
    if lo >= 12 and hi <= 60:
        return "due_1_to_5_years"
    if lo >= 60:
        return "due_after_5_years"
    return None


_TORN_DASHES = {**_DASHES, ord("—"): "-"}  # Svedbergs' torn maturity rows print the parent-company nils as em dashes ("11 896 19 122 — —")
_TORN_GROUP = re.compile(r"(?<![\d,.])\d{1,3}[ ]\d{3}(?![.'\d]|,\d{3})")  # ONE space-group per match, not _SPACE_GROUPS' greedy run: the
# torn rows' own cells are adjacent 3-digit groups ("Summa 496 405 886 478 432 824 609 480"), and a greedy degroup would fuse all eight into one number


def _finer_split_rows(fields: list[dict], schema: dict, texts: list[str], fiscal_year,
                      warnings: list[str], values: dict, filled: set, basis: str = "carrying",
                      missing_events: list[tuple[tuple[str, ...], dict]] | None = None) -> None:
    """A maturity note that prints one row per FINER interval (Rusta Note 11: "0–6 months 523 /
    7–12 months 516 / 1–2 years 969 / 2–5 years 2,184 / >5 years 2,431 / Total 6,624") splits a
    bucket over several sibling rows no existing repair sums: _statement_row deliberately declines
    two rows matching one field (v058), _between_rows' window stops at any row another bucket field
    labels ("1–2 years" is a due_1_to_5_years synonym, so the guard fires -- exactly why Rusta
    stayed "missing" through v088), and _fill_bucket_columns reads one row's columns, not rows.

    Scope: the contiguous interval-labelled rows directly above total_debt's own verified row --
    the walk stops at the first row that names no interval, so a table stacked above (Rusta's own
    right-of-use table, a parent-company note) is never reached. Each row's amount is its fiscal-
    year column (_row_year_column on the total's own row, page-level _year_column when that table
    prints no parseable year header -- Rusta's "30 Apr 2026 30 Apr 2025" is not a _year_run); a
    torn side-by-side page (Svedbergs p.132, the maturity table and the financing-changes note
    printed in two columns) reads each row's own columns label-anchored (row_amounts below).
    Rows are bucketed by the whole span of their label (_bucket_span); a boundary-crossing span
    aborts everything. Adoption is identity-gated, the _date_bucket_derive rule: only when the
    three bucket sums close maturity_sums_to_total within _check's own tolerance (Rusta: 523+516
    + 969+2,184 + 2,431 = 6,623 ≈ 6,624 -- the identity, not any label vocabulary, decides; the
    wrong column would sum 975+3,062+2,633 = 6,670 and fail it). A bucket with a single row is
    that row's literal figure, left to the existing single-row paths (no new behaviour); a bucket
    the table prints no row for stays null (schema: "null if the table has no such row", and
    _check's require_explicit_values keeps it honestly "missing"); a field whose current value
    already matches its sum keeps the model's own evidence."""
    ident = _identity_parts(schema)
    if not ident or not fiscal_year or set(ident[1]) != _DATE_BUCKET_KEYS:
        return
    total_key, part_keys = ident
    sc = next((c for c in schema.get("checks", []) if c.get("identity") and re.search(rf"\b{re.escape(total_key)}\b", c["expr"])), None)
    if not sc:
        return
    by_key = {f["key"]: f for f in fields}
    total = by_key.get(total_key) or {}
    src = total.get("source") or {}
    page = src.get("page")
    if not isinstance(total.get("value"), (int, float)) or isinstance(total["value"], bool) \
            or not isinstance(page, int) or not (0 < page <= len(texts)) or not src.get("quote"):
        return
    text = texts[page - 1]
    rows = _page_rows(text)
    if src["quote"] not in rows:
        return
    ti = rows.index(src["quote"])
    scope = _table_scope(rows, None, ti, basis, schema.get("table_scope_words"),
                         debt_words=_debt_subject_words(schema) if schema.get("table_scope_words") else None) \
        if schema.get("table_scope_words") else "unknown"
    if scope in _REFUSED_SCOPES:
        # v103/v111: no finer-split derivation out of a table the guard refuses -- anchored at total_debt's
        # own verified row, the row whose table the sibling rows above it belong to
        warnings.append(f"{total_key}: no finer-split derivation -- {_scope_reason(rows, None, ti, schema['table_scope_words'], scope)}; "
                        f"not read under the {basis} basis")
        if (reason := _scope_missing_reason(rows, None, ti, schema["table_scope_words"], scope)) is not None:
            _record_missing_reason(missing_events, part_keys, page=page, **reason)
        return
    header = _row_year_column(rows, ti, fiscal_year) or _year_column(text, fiscal_year)
    if not header:
        return  # no column the fiscal year is provably in
    col, ncols = header

    def row_amounts(row: str, label: str) -> list:
        """The row's own `ncols` amounts: the ordinary last-alpha read (_row_amounts) first -- byte-
        identical on clean pages -- falling to the label-anchored read for a TORN page. Svedbergs
        p.132 prints the maturity table and the financing-changes note side by side, and pymupdf
        glues the note's lines onto the maturity rows ("Mellan 2 år och 5 år 11 896 19 122 — —
        Förändringar leasingskuld 360 125 ...", the Summa row too), so the last alpha token sits
        inside the glued text and the ordinary read returns the OTHER table's figures (or none).
        With the label known (_row_label), this table's own columns are what prints between the
        label and the next label word: amounts left to right, a lone dash as the printed nil (the
        _row_amounts convention, em dashes included), the first lettered token ending the row, and
        anything else unparseable ending it too -- no guessing past it."""
        am = _row_amounts(row, ncols)
        if len(am) == ncols:
            return am
        cells: list = []
        for tok in _TORN_GROUP.sub(lambda m: m.group(0).replace(" ", ""),
                                   row.translate(_TORN_DASHES)[len(label):].lstrip(" ,.:;*")).split():
            if re.search(r"[^\W\d_]", tok):
                break  # the next label's first word: this table's columns are over
            if tok == "-":
                cells.append(0)
                continue
            m = _AMOUNT.fullmatch(tok)
            if not m:
                break
            v = int(re.sub(r"\D", "", m.group(1))) + (float(f"0.{m.group(3)}") if m.group(3) else 0)
            cells.append(-v if tok[0] in "-(" else v)
        return cells

    if len(row_amounts(rows[ti], _row_label(rows[ti]))) != ncols:
        return  # the total row itself does not line up with the year header
    idxs: dict[str, list[int]] = {}
    read: dict[int, list] = {}
    for i in range(ti - 1, -1, -1):
        label = _row_label(rows[i])
        span = _bucket_span(label)
        if span is None:
            break  # the first row that names no interval ends this table's data rows
        bucket = _span_bucket(span)
        if bucket is None:
            amounts = row_amounts(rows[i], label)
            disclosed = [{
                "span": label,
                "amount": amounts[col] if len(amounts) == ncols else None,
                "unit": total.get("unit"),
                "page": page,
                "quote": rows[i],
            }]
            _record_missing_reason(
                missing_events, part_keys, "straddle",
                f"The report's {label} interval crosses a standard maturity-bucket boundary, so it cannot be assigned without guessing.",
                page=page, quote=rows[i], disclosed=disclosed,
            )
            return  # a span crossing a bucket boundary ("3-7 years"): no safe split of ANY row here
        amounts = row_amounts(rows[i], label)
        if len(amounts) != ncols:
            break  # a wrapped header line or a note row: not a data row of this table
        read[i] = amounts
        idxs.setdefault(bucket, []).append(i)
    sums = {k: round(sum(read[i][col] for i in ii), 2) for k, ii in idxs.items()}
    if not sums or not _check(sc, {**values, total_key: total["value"], **{k: sums.get(k, 0) for k in part_keys}})["passed"]:
        return
    for key in part_keys:
        rs = [rows[i] for i in sorted(idxs.get(key, []))]  # print order: the quote is the siblings joined as printed
        if len(rs) < 2:
            continue
        value = sums[key]
        current = by_key[key]["value"]
        if isinstance(current, (int, float)) and not isinstance(current, bool) and abs(current - value) <= 2:
            continue  # agrees with the model's own read: its evidence already covers it
        quote = " ".join(rs)
        if not quote_on_page(quote, text):
            return  # non-contiguous siblings: no verbatim quote, no adoption
        label = " + ".join(_row_label(r) for r in rs)
        prefix = "model returned null" if current is None else f"{current} reads one finer-split row and misses its siblings"
        warnings.append(f"{key}: {prefix}; the rows above the total ({label}) sum to {value} in the {fiscal_year} column, closing {sc['name']}")
        by_key[key].update(value=value, period=str(fiscal_year), raw_label=label, source={"page": page, "quote": quote},
                           evidence=["quote_on_page"] if _value_in_quote(value, quote) else ["quote_on_page", "value_derived"])
        values[key] = value
        filled.add(key)


# v126: the row-window wording of a borrowings note that classifies each instrument's balance by
# repayment timing instead of printing bucket rows -- Stillfront Note 21 p.109 ("Repayment within
# 2–5 yr. 620 1,170" per component, "Current liability 675 862", "Repayment after more than 5 yr.
# 4 –"). Scoped to the "repayment" prefix: bare yr/y stays a non-unit in _bucket_span (v096's
# deliberate exclusion, unit-table-pinned) and must stay one everywhere else.
_REPAY_UNIT = r"(?:years?|år|yr\.?|y|months?|månader|mån)"
_SPAN_NUM_NC = r"(?:\d{1,3}|one|two|three|four|five|ett|två|tre|fyra|fem)"  # _SPAN_NUM without its capture group: the groups here are the wording's own operands
_REPAY_ROW = re.compile(
    rf"(?i)\brepayment\s+(?:within\s+({_SPAN_NUM_NC})\s*[-–—]\s*({_SPAN_NUM_NC})\s*({_REPAY_UNIT})"
    rf"|within\s+({_SPAN_NUM_NC})\s*({_REPAY_UNIT})"
    rf"|after\s+more\s+than\s+({_SPAN_NUM_NC})\s*({_REPAY_UNIT}))")
_CURRENT_ROW = re.compile(
    r"(?<![\w-])(?:current|kortfristig\w*|short[ -]term)\s+(?:liabilit(?:y|ies)|portion|parts?|del(?:ar)?)(?![\w-])",
    re.I)
_TOTAL_ROW_WORD = re.compile(r"(?i)\b(?:totalt?|summa|sum)\b")


def _wording_months(tok: str, unit: str) -> int:
    """The wording's own operand in months: a year-ish unit ("years?", "år", "yr.", "y") is twelve, a
    month unit one; the operand is a digit or one of _SPAN_WORDS' small number words."""
    return (int(tok) if tok.isdigit() else _SPAN_WORDS[tok]) * (12 if unit[0] in "yå" else 1)


def _wording_window(w: str) -> tuple[int, float] | None:
    """(lo, hi) months for one repayment/current wording (whitespace-joined) -- the window half of
    the v126 grammar, split out of _row_bucket_span for v156's subtotal guard, which must know the
    window a TOTAL-labelled row names (a thing _row_bucket_span itself refuses to sit in a family)."""
    rm = _REPAY_ROW.search(w)
    if not rm:
        return (0, 12)  # the current classification IS the within-1-year window (v110's family)
    g = rm.groups()
    if g[0] is not None:  # "Repayment within 2–5 yr."
        lo, hi = _wording_months(g[0], g[2]), _wording_months(g[1], g[2])
        return (lo, hi) if lo <= hi else None
    if g[3] is not None:  # "Repayment within 1 yr."
        return (0, _wording_months(g[3], g[4]))
    return (_wording_months(g[5], g[6]), float("inf"))  # "Repayment after more than 5 yr."


def _row_bucket_span(row: str) -> tuple[tuple[int, float], str] | None:
    """(window, wording) for a maturity-note row whose repayment-timing wording sits at or inside it --
    the clean interval label ("0–6 months 523 490", _bucket_span on _row_label) or, glued two-column
    pages being what they are (Stillfront p.109: "Bond loans 2,835 2,829 Repayment within 2–5 yr. 620
    1,170"), the LAST repayment/current wording whose tail is amounts-only ("Current liability (overdraft
    facilities) – –" is a different classification, its alpha tail says so). A total word before the
    wording ("Total ... within 1 year") refuses the row: a total never joins a sum of its own parts."""
    label = _row_label(row)
    span = _bucket_span(label)
    if span is not None and not re.search(r"[^\W\d_]", row[len(label):]):
        return (span, label)
    matches = sorted([*_REPAY_ROW.finditer(row), *_CURRENT_ROW.finditer(row)],
                     key=lambda m: m.start(), reverse=True)
    for m in matches:
        if _TOTAL_ROW_WORD.search(row[:m.start()]):
            continue
        if re.search(r"[^\W\d_]", row[m.end():]):
            continue  # wording not at the row's figure edge: what follows is another row's label, not this row's amounts
        w = " ".join(m.group(0).split())
        win = _wording_window(w)
        if win is not None:
            return (win, w)
    return None


def _close(a, b) -> bool:
    """The v126 tolerance: equal within ±2 absolute or ±0.5% -- rounding of independently rounded rows."""
    return abs(a - b) <= 2 or (b and abs(a - b) <= 0.005 * abs(b))


def _window_row_sum(field: dict, fields: list[dict], schema: dict, texts: list[str], fiscal_year,
                    pages: list[int], scope_words: dict | None, basis: str,
                    warnings: list[str], missing_events: list[tuple[tuple[str, ...], dict]] | None = None) -> tuple[str, str, int, str, str, int] | None:
    """v126 (Stillfront Note 21, p.109): a bucket value the model computed by summing the note's own
    repayment-timing rows -- 710 = the current-classified rows (675 + 35), 5152 = the five "Repayment
    within 2–5 yr." component rows (620 + 2,835 + 649 + 984 + 64) -- printed as ONE number nowhere,
    so the computed-not-read guard drops it. The note's rows prove the sum without any label
    vocabulary: every row of one page whose window (_row_bucket_span -> _span_bucket) falls entirely
    inside THIS bucket's range, at least two of them, summed in the one column where the note's own
    total row ties to the already-verified total_debt -- when that sum IS the model's value, the page
    itself is the provenance and the value keeps as value_derived. Windows, not vocabulary: "Repayment
    within 2–5 yr." parses by its geometry and "Current liability" by its classification, so no
    schema word list grows (v088's rule). Returns (quote, raw_label, n, first, last, page) or None."""
    key = field["key"]
    if key not in _DATE_BUCKET_KEYS or not isinstance(field.get("value"), (int, float)) or isinstance(field["value"], bool):
        return None
    by_key = {g["key"]: g for g in fields}
    total = by_key.get("total_debt") or {}
    tsrc = total.get("source") or {}
    if not isinstance(total.get("value"), (int, float)) or isinstance(total.get("value"), bool) \
            or not isinstance(tsrc.get("page"), int) or not tsrc.get("quote"):
        return None
    for p in sorted({tsrc["page"], *[q for q in pages[:2] if isinstance(q, int)]}):  # the field's cited page first, then the statement spread
        if not 0 < p <= len(texts):
            continue
        text = texts[p - 1]
        rows = _page_rows(text)
        if tsrc["quote"] not in rows:  # the column gate needs the note's own total row, on this very page
            continue
        ti = rows.index(tsrc["quote"])
        scope = _table_scope(rows, None, ti, basis, scope_words,
                             debt_words=_debt_subject_words(schema) if scope_words else None) if scope_words else "unknown"
        if scope in _REFUSED_SCOPES:
            # v103/v111: no derivation out of a table the guard refuses -- anchored at total_debt's own row
            warnings.append(f"{key}: no window-rows derivation -- {_scope_reason(rows, None, ti, scope_words, scope)}; "
                            f"not read under the {basis} basis")
            if (reason := _scope_missing_reason(rows, None, ti, scope_words, scope)) is not None:
                _record_missing_reason(missing_events, [key], page=p, **reason)
            return None
        header = _row_year_column(rows, ti, fiscal_year) or _year_column(text, fiscal_year)
        if not header:
            continue  # no column the fiscal year is provably in
        col, ncols = header
        tam = _row_amounts(tsrc["quote"], ncols)
        if len(tam) != ncols or not _close(tam[col], total["value"]):
            continue  # the total row does not line up with the year header, or this column is not the verified total's: no read
        fam: list[tuple[int, str, str, list]] = []
        for i, r in enumerate(rows):
            if i == ti:
                continue
            got = _row_bucket_span(r)
            if not got or _span_bucket(got[0]) != key:
                continue  # another window's row (or no window): never this bucket's summand
            am = _row_amounts(r, ncols)
            if len(am) != ncols:
                continue  # a wrapped header line or furniture row between components
            fam.append((i, r, got[1], am))
        if len(fam) < 2:
            continue
        value = field["value"]
        s = round(sum(am[col] for _, _, _, am in fam), 2)
        if not _close(s, value):
            continue
        rs = [r for _, r, _, _ in fam]
        joined = " ".join(rs)
        verified = quote_on_page(joined, text)
        quote = verified if verified == joined else rs[0]  # contiguous rows quote joined (v096's form); scattered ones quote their first row
        label = " + ".join(w for _, _, w, _ in fam)
        return quote, label, len(fam), fam[0][2], fam[-1][2], p
    return None


def _window_subtotal_row(row: str, key: str) -> bool:
    """v156: does this row print the bucket's OWN subtotal -- a total word in the label with the
    bucket's window wording at the row's figure edge ("Total Repayment within 2–5 yr. 200 190",
    v126's counter-example page)? The window is then already a printed row's own read -- the
    single-row paths' territory -- and the on-null walk must not derive over it: a family that
    disagrees with a printed subtotal of its own window is the report's inconsistency, a human's
    question, not a sum to redo. "Summa inom 1 år" (XANO) names no v126 wording and guards nobody."""
    if not _BARE_TOTAL.search(_row_label(row)):
        return False
    matches = sorted([*_REPAY_ROW.finditer(row), *_CURRENT_ROW.finditer(row)],
                     key=lambda m: m.start(), reverse=True)
    for m in matches:
        if re.search(r"[^\W\d_]", row[m.end():]):
            continue  # not at the figure edge: another row's wording glued on, not this row's own
        win = _wording_window(" ".join(m.group(0).split()))
        return win is not None and _span_bucket(win) == key
    return False


def _window_rows_derive(fields: list[dict], schema: dict, texts: list[str], fiscal_year,
                        pages: list[int], scope_words: dict | None, basis: str,
                        warnings: list[str], values: dict, filled: set) -> None:
    """v156: v126's window family, deriving on a NULL bucket answer (v096's adoption on the
    identity) instead of only keeping a sum the model itself answered and had dropped. Same family
    and column gates as _window_row_sum, reused verbatim: rows of one page whose window
    (_row_bucket_span -> _span_bucket) falls entirely inside THIS bucket's range, at least two of
    them, summed in the one column where the note's own total row ties to the already-verified
    total_debt -- which is what makes "the table's total row" and "the verified total_debt" the
    same number here. What replaces the model's own value is the closure gate: the family sum plus
    the other buckets' already-read values (a bucket still null contributes 0 -- its rows would
    sit inside the total too, so a partial family cannot close and nothing is derived) must reach
    that total, the arithmetic v096 adopts on, through maturity_sums_to_total. A page that already
    prints the window's own subtotal (_window_subtotal_row) stands the walk down for the bucket:
    that row is the bucket's read, and a family disagreeing with it is not ours to settle. Every
    decline is silent (v110's convention) -- the write is the only warning this walk emits."""
    ident = _identity_parts(schema)
    if not ident or not fiscal_year or set(ident[1]) != _DATE_BUCKET_KEYS:
        return
    total_key, part_keys = ident
    sc = next((c for c in schema.get("checks", []) if c.get("identity") and re.search(rf"\b{re.escape(total_key)}\b", c["expr"])), None)
    if not sc:
        return
    by_key = {f["key"]: f for f in fields}
    total = by_key.get(total_key) or {}
    tsrc = total.get("source") or {}
    if not isinstance(total.get("value"), (int, float)) or isinstance(total.get("value"), bool) \
            or not isinstance(tsrc.get("page"), int) or not tsrc.get("quote"):
        return
    for key in part_keys:
        cur = by_key[key]
        if cur.get("value") is not None or key in filled:
            continue  # a read (or already-derived) bucket is nobody's null to fill
        for p in sorted({tsrc["page"], *[q for q in pages[:2] if isinstance(q, int)]}):
            if not 0 < p <= len(texts):
                continue
            text = texts[p - 1]
            rows = _page_rows(text)
            if tsrc["quote"] not in rows:  # the column gate needs the note's own total row, on this very page
                continue
            ti = rows.index(tsrc["quote"])
            scope = _table_scope(rows, None, ti, basis, scope_words,
                                 debt_words=_debt_subject_words(schema) if scope_words else None) if scope_words else "unknown"
            if scope in _REFUSED_SCOPES:
                continue  # v103/v111: no derivation out of a refused table -- silently, this walk writes or it says nothing
            header = _row_year_column(rows, ti, fiscal_year) or _year_column(text, fiscal_year)
            if not header:
                continue  # no column the fiscal year is provably in
            col, ncols = header
            tam = _row_amounts(tsrc["quote"], ncols)
            if len(tam) != ncols or not _close(tam[col], total["value"]):
                continue  # the total row does not line up with the year header, or this column is not the verified total's
            if any(_window_subtotal_row(r, key) for i, r in enumerate(rows) if i != ti):
                break  # the window's own subtotal is printed on this page: the printed row's read, not a sum to derive
            fam: list[tuple[str, str, list]] = []
            for i, r in enumerate(rows):
                if i == ti:
                    continue
                got = _row_bucket_span(r)
                if not got or _span_bucket(got[0]) != key:
                    continue  # another window's row (or no window): never this bucket's summand
                am = _row_amounts(r, ncols)
                if len(am) != ncols:
                    continue  # a wrapped header line or furniture row between components
                fam.append((r, got[1], am))
            if len(fam) < 2:
                continue
            s = round(sum(am[col] for _, _, am in fam), 2)
            gate = {**{k: 0 for k in part_keys}, key: s, total_key: total["value"]}
            for k in part_keys:  # the other buckets' already-read values ride along; a null one stays 0
                if k == key:
                    continue
                v = by_key[k].get("value")
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    gate[k] = v
            if not _check(sc, gate)["passed"]:
                continue  # the closure does not hold: nothing derived
            rs = [r for r, _, _ in fam]
            joined = " ".join(rs)
            verified = quote_on_page(joined, text)
            quote = verified if verified == joined else rs[0]  # contiguous rows quote joined (v096's form); scattered ones quote their first row
            label = " + ".join(w for _, w, _ in fam)
            warnings.append(f"{key}: derived as the sum of {len(fam)} rows inside its window on page {p} "
                            f"({fam[0][1]!r} … {fam[-1][1]!r}); closes on {total['value']}")
            cur.update(value=s, period=str(fiscal_year), raw_label=label, source={"page": p, "quote": quote},
                       evidence=["quote_on_page"] if _value_in_quote(s, quote) else ["quote_on_page", "value_derived"])
            values[key] = s
            filled.add(key)
            break


_NONCURRENT_WORDS = ("långfristig", "non-current", "noncurrent", "long-term", "long term")  # v110: the two
_CURRENT_WORDS = ("kortfristig", "current", "short-term", "short term")  # section-heading families, structure not vocabulary
_PAIR_TITLE_WINDOW = 9  # rows the section heading may sit below the note title (BICO's torn three-line year header occupies the ninth)
_PAIR_SECTION_WINDOW = 14  # rows a section's own rows may span before its Summa
_PAIR_TAIL_WINDOW = 6  # rows after the second Summa that may still print the block's own grand total


def _subtotal_pair_fill(fields: list[dict], sfs: list[dict], schema: dict, texts: list[str], pages: list[int],
                        fiscal_year, warnings: list[str], values: dict, filled: set, basis: str = "carrying",
                        missing_events: list[tuple[tuple[str, ...], dict]] | None = None) -> None:
    """v110: a borrowings note split into a non-current and a current section, each closed by its own
    Summa/Total row, with NO third grand-total row anywhere in the block (NOTE Not 19, p.107:
    "Långfristiga skulder ... Summa 228 861 250 023 / Kortfristiga skulder ... Summa 595 420 380 108").
    The maturity buckets such a note names are exactly two -- everything non-current and everything
    current -- so it proves total_debt (A + B, value_derived; the sum is printed nowhere, which is the
    gap: the model's own 824,281 was dropped as computed-not-read while the two Summa rows sit right
    there) and due_within_1_year (B, the current section's own printed subtotal). The other two
    buckets stay null -- the note prints nothing that splits them (Ambea/Karnov's family, v088's
    "current/non-current granularity only" gap 2; recorded, not forced).

    Structural, not vocabulary-driven (no schema edit, v088's ruling): a note TITLE row (a debt word
    of total_debt's own synonyms + row_synonyms -- v131: or the note-family subject wording
    "financial liabilities" / "finansiella skulder", the one debt word the schema lists all lack;
    printing no figures) heads a section heading A
    (Långfristiga/Non-current/Long-term), then A's detail rows, then A's Summa; directly below, past
    furniture only, a section heading B (Kortfristiga/Current/Short-term), B's rows, B's Summa; and
    no total-shaped row within _PAIR_TAIL_WINDOW rows after B's Summa -- a block that prints its own
    grand total (Ambea G18's "Total interest-bearing liabilities 12,643") is that total's shape, not
    this one. Both Summas must sit in one year header (_row_year_column, agreeing), and each
    section's own detail rows must close to its Summa in EVERY column -- the note's own arithmetic
    is what proves a bare "Summa" row is its section's subtotal and not another table's (a third
    Summa interleaved from a stacked table breaks the section walk or fails this closure). Declines
    are silent (counter-examples must replay byte-identical); the model's own non-null total that
    DISAGREES with A+B declines too -- the note and the model then name different scopes, a human's
    question, not a repair's. Corroboration (the model's total matching, or the prose conversion of
    A+B -- NOTE's p.109 "räntebärande skulder 824,2 (630,0) MSEK") only names itself in the warning;
    without it the adoption still stands on the two closures, at value_derived confidence."""
    ident = _identity_parts(schema)
    if not ident or not fiscal_year or set(ident[1]) != _DATE_BUCKET_KEYS or basis != "carrying" \
            or "due_within_1_year" not in ident[1]:
        return
    total_key, part_keys = ident
    total_sf = next((sf for sf in sfs if sf["key"] == total_key), None)
    if not total_sf:
        return
    by_key = {f["key"]: f for f in fields}
    debt_words = sorted({w for w in (" ".join(str(s).translate(_DASHES).lower().split())
                                     for s in total_sf.get("synonyms", []) + total_sf.get("row_synonyms", [])) if w})
    title_words = debt_words + ["financial liabilities", "finansiella skulder"]  # v131: the note-family
    # subject wording -- Enea's note heads its table "Financial liabilities 2025 2024 2025 2024"
    # (heading-like: the year row IS the header), and the schema's own lists name totals and instrument
    # rows, never the note's subject line, so the walk had no title to start from. Both phrases print
    # across the corpus (data/kb: 172 / 30 stems). Title gate only: _prose_total keeps debt_words.

    def _heading_like(r: str) -> bool:  # prints no figures, or only calendar years (a header line)
        return all(isinstance(a, int) and 1900 <= a <= 2100 for a in _row_amounts(r))

    def _section_heading(r: str) -> bool:
        """A compact current/non-current heading, not prose that happens to name its two scopes.

        BICO's accounting-principles sentence says "non-current or current liabilities" directly
        above the torn date header.  It is figure-free, so it is heading-like furniture, but it
        cannot be the section heading that starts a subtotal block.  Real headings remain short;
        the paragraph/full-stop gate leaves them, and existing wrapped heading handling, intact.
        """
        return (_heading_like(r) and _vocab(r) is not None and not r.rstrip().endswith(".")
                and len(re.findall(r"[^\W\d_]+", r)) <= 8)

    def _vocab(r: str) -> str | None:  # which section family a heading names; "non-current" contains "current", so A rules first
        # v131: the non-breaking hyphen U+2011 is a print variant of the dash _DASHES already folds --
        # Enea p.76 heads section A "Non‑current liabilities, interest‑bearing", and untranslated the
        # ASCII tail "current" still matches, filing the NON-current heading under B (A rules first
        # only while the hyphen normalizes). Patched here, not in the shared _DASHES: the table feeds
        # every other gate in the file, and this walk is where the shape is proven to print (the corpus
        # prints U+2011 headings for no other debt_maturity-replayable stem).
        lab = " ".join(_row_label(r).translate(_DASHES).replace("‑", "-").lower().split())
        if any(w in lab for w in _NONCURRENT_WORDS):
            return "A"
        return "B" if any(w in lab for w in _CURRENT_WORDS) else None

    def _subtotal_row(r: str) -> bool:  # a bare Total/Totalt/Summa label carrying a real (non-year) figure
        return bool(_BARE_TOTAL.search(_row_label(r))) and any(not (isinstance(a, int) and 1900 <= a <= 2100)
                                                               for a in _row_amounts(r))

    def _find_pair(rows: list[str]) -> tuple | None:
        """(hA, sumA, hB, sumB) of the first qualifying block on the page, or None."""
        for t, r in enumerate(rows):
            if not _heading_like(r) or not any(w in " ".join(r.translate(_DASHES).lower().split()) for w in title_words):
                continue
            hA = next((i for i in range(t + 1, min(t + 1 + _PAIR_TITLE_WINDOW, len(rows)))
                       if _section_heading(rows[i]) and _vocab(rows[i]) == "A"), None)
            if hA is None or any(not _heading_like(rows[i]) for i in range(t + 1, hA)):
                continue  # printed figures before any section heading: a table, not a sectioned note
            sumA = next((i for i in range(hA + 1, min(hA + 1 + _PAIR_SECTION_WINDOW, len(rows))) if _subtotal_row(rows[i])), None)
            if sumA is None or any(_section_heading(rows[i]) for i in range(hA + 1, sumA)):
                continue  # section A runs into another section before its own Summa: never totalled alone
            hB = next((i for i in range(sumA + 1, min(sumA + 1 + _PAIR_SECTION_WINDOW, len(rows)))
                       if _section_heading(rows[i]) and _vocab(rows[i]) == "B"), None)
            if hB is None or any(not _heading_like(rows[i]) for i in range(sumA + 1, hB)):
                continue  # another table's rows between the two Summas (the stacked-table shape): not one note
            sumB = next((i for i in range(hB + 1, min(hB + 1 + _PAIR_SECTION_WINDOW, len(rows))) if _subtotal_row(rows[i])), None)
            if sumB is None or any(_section_heading(rows[i]) for i in range(hB + 1, sumB)):
                continue
            tail = next((i for i in range(sumB + 1, min(sumB + 1 + _PAIR_TAIL_WINDOW, len(rows)))
                         if not _heading_like(rows[i])), None)
            if tail is not None and (_BARE_TOTAL.search(_row_label(rows[tail])) or _label_known(_row_label(rows[tail]), total_sf)):
                continue  # the block prints its own grand total after the sections: that row is total_debt's own read
            return hA, sumA, hB, sumB
        return None

    def _closes(h: int, si: int, am: list, allow_torn_trailing_blank: bool = False) -> bool:
        """The section's own rows sum to its Summa in every column.

        In the exact BICO-style torn Group | Parent header, a printer can omit only the final
        blank Parent comparative cell (three values under a proven four-column header).  Restoring
        that trailing nil still requires every column to close; any other short row declines.
        """
        parts = []
        for i in range(h + 1, si):
            r = rows[i]
            if _heading_like(r):
                # v156 (Sdiptech p.110): a data row can LOOK like furniture here --
                # "Liabilities to credit institutions 10 10" reads [] without ncols (both cells
                # small enough to filter out as note references), "Other liabilities** 2 4" the
                # same way behind its footnote stars. The section's own ncols read of the
                # star-stripped row arbitrates: ncols real (non-year) figures make it a data row;
                # anything else stays the wrapped label it looked like.
                a = _row_amounts(r.replace("*", " "), ncols)
                if not (len(a) == ncols and not all(isinstance(v, int) and 1900 <= v <= 2100 for v in a)):
                    continue  # a wrapped label line
            else:
                a = _row_amounts(r, ncols)
                if len(a) != ncols and "*" in r:
                    # v156 (Sdiptech p.110): a bare footnote star between the label and the figures
                    # breaks the all-digits tail the ncols split needs, so the space-grouped cells
                    # read fused ("Contingent considerations * 597 910" -> 597910; the split-back is
                    # a nil-gated Boozt case). Retry the star-stripped row under the section's own
                    # ncols read; the per-column closure below still decides, so a wrong un-fusion
                    # declines exactly as before.
                    a2 = _row_amounts(r.replace("*", " "), ncols)
                    if len(a2) == ncols:
                        a = a2
            if allow_torn_trailing_blank and len(a) == ncols - 1:
                a.append(0)
            if len(a) != ncols:
                return False
            parts.append(a)
        return bool(parts) and all(abs(round(sum(a[c] for a in parts), 2) - am[c]) <= 2 for c in range(ncols))

    def _prose_total(pair_total) -> int | None:  # a candidate page's prose printing the total (NOTE p.109's "824,2 MSEK")
        for q in dict.fromkeys([p for p in pages if isinstance(p, int) and 0 < p <= len(texts)]):
            for r in _page_rows(texts[q - 1]):
                if not any(w in " ".join(r.translate(_DASHES).lower().split()) for w in debt_words):
                    continue
                for tok in re.findall(r"\d{1,3}(?:[  ]\d{3})+(?:[.,]\d{1,2})?|\d+[.,]\d{1,2}|\d{4,}", r):
                    v = float(tok.replace(" ", "").replace(" ", "").replace(",", "."))
                    if abs(v - pair_total) <= 2 or abs(v - pair_total / 1000) <= 0.1:
                        return q
        return None

    cited = {by_key[k]["source"]["page"] for k in (total_key, *part_keys)
             if isinstance((by_key[k].get("source") or {}).get("page"), int)}
    scope_words = schema.get("table_scope_words")
    for page in dict.fromkeys([p for p in pages[:2] if isinstance(p, int) and 0 < p <= len(texts)]
                              + sorted(p for p in cited if 0 < p <= len(texts))):
        rows = _page_rows(texts[page - 1])
        pair = _find_pair(rows)
        if not pair:
            continue
        hA, sumA, hB, sumB = pair
        if scope_words and _table_scope(rows, None, sumB, basis, scope_words,
                                        debt_words=_debt_subject_words(schema)) in _REFUSED_SCOPES:
            continue  # the wrong-table guard: a table the guard refuses is not a subtotal pair either
        header = _row_year_column(rows, sumA, fiscal_year)
        if not header or header != _row_year_column(rows, sumB, fiscal_year):
            continue  # the two Summas must share one year header -- one note, one table
        col, ncols = header
        amA, amB = _row_amounts(rows[sumA], ncols), _row_amounts(rows[sumB], ncols)
        sparse_torn_group = ncols == 4 and _torn_orphan_year_header(rows, sumA) and _torn_orphan_year_header(rows, sumB)
        if len(amA) != ncols or len(amB) != ncols or not _closes(hA, sumA, amA, sparse_torn_group) \
                or not _closes(hB, sumB, amB, sparse_torn_group):
            continue
        pair_total = round(amA[col] + amB[col], 2)
        model_total = by_key[total_key].get("value")
        if isinstance(model_total, (int, float)) and not isinstance(model_total, bool) and abs(model_total - pair_total) > 2:
            continue  # the note's own subtotals and the model's total name different scopes: not this repair's call
        span = " ".join(rows[sumA:sumB + 1])  # both Summa rows verbatim, contiguously (a two-row join is not a page substring)
        if not quote_on_page(span, texts[page - 1]):
            continue
        corroborated = None
        if isinstance(model_total, (int, float)) and not isinstance(model_total, bool):
            corroborated = "the model's own total"
        elif (q := _prose_total(pair_total)) is not None:
            corroborated = f"page {q} prose"
        note = f"; corroborated by {corroborated}" if corroborated else "; no printed or model total corroborates -- the two closures alone prove it"
        current = by_key[total_key]["value"]
        if not (isinstance(current, (int, float)) and not isinstance(current, bool) and abs(current - pair_total) <= 2):
            label = f"{_row_label(rows[sumA])} ({_row_label(rows[hA])}) + {_row_label(rows[sumB])} ({_row_label(rows[hB])})"
            prefix = "model returned null" if current is None else f"{current} disagrees with the note's own sections"
            warnings.append(f"{total_key}: {prefix}; the note's two section subtotals on page {page} sum to "
                            f"{pair_total} ({amA[col]} + {amB[col]}), each closing on its own rows{note}")
            by_key[total_key].update(value=pair_total, period=str(fiscal_year), raw_label=label,
                                     source={"page": page, "quote": span}, evidence=["quote_on_page", "value_derived"])
            values[total_key] = pair_total
            filled.add(total_key)
        w1y = by_key["due_within_1_year"]
        if not (isinstance(w1y["value"], (int, float)) and not isinstance(w1y["value"], bool) and abs(w1y["value"] - amB[col]) <= 2):
            prefix = "model returned null" if w1y["value"] is None else f"{w1y['value']} is not the current section's own subtotal"
            warnings.append(f"due_within_1_year: {prefix}; {amB[col]} is printed in the note's current-section Summa "
                            f"row on page {page} ({rows[sumB]!r}){note}")
            w1y.update(value=amB[col], period=str(fiscal_year), raw_label=_row_label(rows[sumB]),
                       source={"page": page, "quote": rows[sumB]}, evidence=["quote_on_page"])
            values["due_within_1_year"] = amB[col]
            filled.add("due_within_1_year")
        _record_missing_reason(
            missing_events, ["due_1_to_5_years", "due_after_5_years"], "noncurrent_only",
            "The report separates current and non-current debt only; it does not split non-current debt into the 1–5 years and >5 years standard buckets.",
            page=page, quote=span,
        )
        return  # one adoption per extraction: the note that validated is the borrowings note


_BUCKET_BOUNDARY = {  # the schema's own synonyms cover most of this (dash-normalised below, so "1–2 years" matches
    # the schema's "1-2 years"); these patch gaps a plain header_synonyms literal-substring entry (case-
    # insensitive, no word boundary, scanned over the whole 25-row window _bucket_header searches, not just the
    # header line itself) cannot safely express. HANDOFF's examples use the plain English symbol form the schema
    # only states in Swedish ("< 1 år", "> 5 år"), e.g. Cloetta's "< 1 year". "Due" (Ework p.70's own column,
    # v069, docs/acrylic/evidence/v069.md) needs more than that: a bare header_synonym "due" fires on ordinary
    # prose the same 25-row window routinely carries above a debt-maturity table -- proven on Ework's own p.70/71
    # ("...risk due to assets...", "Past due accounts receivable...", "...not yet due...", a dozen+ hits) -- so
    # this alternative is scoped case-sensitive (real column headers print "Due", capitalised; prose "due" almost
    # never is) and excludes the one capitalised false positive a scan like this would still invite, a sentence
    # opening "Due to ...".
    "due_within_1_year": re.compile(r"(?i:<\s*1\s*years?\b)|\bDue\b(?!\s+to\b)"),
    "due_after_5_years": re.compile(r"(?i)>\s*5\s*years?\b"),
}
_BARE_TOTAL = re.compile(r"(?i)\btotalt?\b|\bsumma\b")
_YEAR_TAIL = re.compile(r"(?i)\b(?:later|thereafter|senare|övriga år)\b")
_SUBTOTAL_PHRASES = {"summa inom 1 år", "total within 1 year"}  # a printed within-1-year subtotal column
# (XANO p.84's "Summa inom 1 år"): its own finer day/month sub-columns to its left must not also be summed in

# v095: the schema's own three-bucket grid in months -- the same fixed 1/5-year semantics _bucket_year_hits
# states in year positions ("1 year out = due_within_1_year, 2-5 years out = due_1_to_5_years, further out =
# due_after_5_years"). A maturity column whose bounds are not these (Karnell's ">3 years") crosses a bucket
# boundary somewhere its header does not name, so no bucket can claim it without guessing the split.
_OFFGRID_OPEN_HI = re.compile(r"(?i)(?:>|över|over|mer än|more than|senare än|later than|efter|after)\s*(\d{1,2})\s*(?:years?|år)\b")
_OFFGRID_OPEN_LO = re.compile(r"(?i)(?:<|under|mindre än|less than|fewer than)\s*(\d{1,2})\s*(?:years?|år)\b")
_OFFGRID_RANGE = re.compile(r"(?i)(?<![\d.,])(\d{1,2})\s*-\s*(\d{1,2})\s*(?:years?|år)\b")
_BUCKET_WINDOW = {  # (lo, hi) months, hi None = open-ended; keys without a window simply never take an off-grid 0
    "due_within_1_year": (0, 12),
    "due_1_to_5_years": (12, 60),
    "due_after_5_years": (60, None),
}
_BUCKET_GRID = tuple(sorted({b for lo, hi in _BUCKET_WINDOW.values() for b in (lo, hi) if b is not None}))  # (12, 60)


def _identity_parts(schema: dict) -> tuple[str, list[str]] | None:
    """(total_key, part_keys) read from the schema's own identity check ("parts sum to total") via null_as_zero
    and expr -- generic, not a debt_maturity-only hook wired in by field name: any schema whose check has the
    same shape (>=2 null_as_zero operands and exactly one other field in expr) qualifies."""
    for sc in schema.get("checks", []):
        parts = sc.get("null_as_zero")
        if not (sc.get("identity") and parts and len(parts) >= 2):
            continue
        keys = set(re.findall(r"\b[A-Za-z_]\w*\b", sc["expr"])) - set(_SAFE_BUILTINS)
        others = keys - set(parts)
        if len(others) == 1:
            return next(iter(others)), parts
    return None


def _identity_closes(key: str, value, values: dict, defaults: dict, schema: dict) -> bool:
    """True when `key`'s current `value` -- about to be overwritten by a column-position guess -- already closes
    one of the schema's own identity checks exactly (_check's own tolerance), against at least two OTHER
    operands that are themselves already-read, real values: a lone total (everything else null_as_zero) would
    make a sum identity trivially true and prove nothing about `value` (Proact, v066: 312,458 for
    due_within_1_year is column 1 of 3, but 312,458 + due_1_to_5_years' own 166,153 closes
    maturity_sums_to_total against total_debt's own 478,611 exactly -- a date-per-instrument sum no column
    re-read can reproduce, docs/acrylic/evidence/v063.md gap 2)."""
    for sc in schema.get("checks", []):
        if not sc.get("identity") or not re.search(rf"\b{re.escape(key)}\b", sc["expr"]):
            continue
        operands = set(re.findall(r"\b[A-Za-z_]\w*\b", sc["expr"])) - set(_SAFE_BUILTINS) - {key}
        real = [k for k in operands if isinstance(values.get(k), (int, float)) and not isinstance(values.get(k), bool)]
        if len(real) >= 2 and _check(sc, {**defaults, **values, key: value})["passed"]:
            return True
    return False


def _bucket_synonym_hits(text: str, bucket_sfs: dict, total_sf: dict | None = None,
                         ignore_syns: list | None = None, basis: str = "carrying") -> list[tuple[int, int, str]]:
    """[(start, end, key)] for every maturity-bucket synonym of every field in bucket_sfs found in text, dash-
    normalised (so "1–2 years" matches the schema's "1-2 years"), plus _BUCKET_BOUNDARY's English-symbol patch.
    A finer split that maps to the same key twice (Cloetta: "1–2 years" and "2–5 years" are both due_1_to_5_years)
    keeps both hits -- each is its own table column, later summed by _bucket_assign. Also reads each field's own
    header_synonyms -- month-span/day-range header wording _label_known (row-label matching) never sees, v046's
    deliberate gap between the two lists. A hit whose synonym is one of _SUBTOTAL_PHRASES is tagged "key:subtotal"
    so _bucket_header can make it override, not add to, its own finer columns already seen to its left. The span
    (not just the start) lets _bucket_header drop a hit that sits nested inside another, wider one -- two
    synonyms matching pieces of the one same printed phrase (XANO's "Summa inom 1 år": the bare word "Summa" and
    the plain synonym "inom 1 år" each match a piece of the one subtotal phrase already matched whole; Ework's
    own header_synonym "3 months" is a literal substring of its own "1-3 months") is one column, not two.

    v076, same span discipline: total_sf's own header_synonyms are carrying-amount wording (schema) -- a header
    column of that wording is the total column itself (the report's stated total_debt basis), tagged apart from a
    bare Total word as "total:carrying" so _bucket_header can prefer it when both shapes appear on one line; the
    schema's ignore_header_synonyms (undiscounted/contractual total wording, printed beside the carrying column)
    tag "_ignore" -- a real, counted column that is never assigned.

    v089: which word group fills which tag follows the basis (debt_basis()): under the default "carrying" it is
    exactly as above; under "undiscounted" the two groups swap -- "total:carrying" is the *total-slot* tag whatever
    wording fills it, so the ignore_header_synonyms wording (the liquidity note's own undiscounted/contractual
    total) claims the total slot and the carrying wording becomes the ignored column. Everything downstream of the
    tags (_bucket_header's slot preference and bare-Total demotion, the v085 contiguous-run fallback, _bucket_
    assign's _ignore skip) is basis-symmetric and reads unchanged; the over valve and the dash-to-0 gate then
    compare buckets against the slot's figure, which is the identity's basis by construction."""
    htext = text.translate(_DASHES)
    hits = []
    for key, sf in bucket_sfs.items():
        for syn in sf.get("synonyms", []) + sf.get("header_synonyms", []):
            tag = f"{key}:subtotal" if syn.lower() in _SUBTOTAL_PHRASES else key
            hits.extend((m.start(), m.end(), tag) for m in re.finditer(re.escape(syn.translate(_DASHES)), htext, re.I))
        if key in _BUCKET_BOUNDARY:
            hits.extend((m.start(), m.end(), key) for m in _BUCKET_BOUNDARY[key].finditer(htext))
    if total_sf:
        basis_total_syns = total_sf.get("header_synonyms", [])
        ignored_syns = list(ignore_syns or [])
        if basis == "undiscounted":  # the liquidity note's own undiscounted total is the basis here
            basis_total_syns, ignored_syns = ignored_syns, basis_total_syns
        hits.extend((m.start(), m.end(), "total:carrying") for syn in basis_total_syns
                    for m in re.finditer(re.escape(syn.translate(_DASHES)), htext, re.I))
    else:
        ignored_syns = list(ignore_syns or [])
    for syn in ignored_syns:
        hits.extend((m.start(), m.end(), "_ignore") for m in re.finditer(re.escape(syn.translate(_DASHES)), htext, re.I))
    return hits


def _offgrid_hits(text: str, taken: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    """[(start, end, tag)] for maturity-window header wording no bucket word claimed -- ">3 years", "over 2
    years", "1-4 years", "mer än 3 år" -- whose bounds (in months) sit off the schema's own 1/5-year bucket
    grid (_BUCKET_WINDOW): a real column of this table that no bucket can claim without guessing where the
    boundary it straddles splits it. Tagged "offgrid:<lo>-<hi>|<phrase>" (hi empty = open-ended); _bucket_header
    counts the tag as a column of its own -- the 3-header-keys-vs-4-printed-amounts length valve Karnell's p.106
    died on -- and _bucket_assign never assigns it, exactly like _ignore. The one thing such a column can still
    prove is its own nil (v078's dash convention, one level up): no debt is due in that window at all, so every
    bucket the window covers outright is a 0 and the straddled boundary stops being uncertain
    (_fill_bucket_columns); a printed value there is an honest decline, never a guess. A phrase whose span a
    bucket word already matched (the schema's own "1-3 years" finer split of due_1_to_5_years, "> 5 years" via
    _BUCKET_BOUNDARY) belongs to that word, and so does any phrase whose bounds land exactly on the grid
    ("mer än 5 år" IS due_after_5_years' own window): whatever today's reading of those is, it stands."""
    htext = text.translate(_DASHES)
    found = [(m.start(), m.end(), int(m.group(1)) * 12, None) for m in _OFFGRID_OPEN_HI.finditer(htext)]
    found += [(m.start(), m.end(), 0, int(m.group(1)) * 12) for m in _OFFGRID_OPEN_LO.finditer(htext)]
    found += [(m.start(), m.end(), int(m.group(1)) * 12, int(m.group(2)) * 12) for m in _OFFGRID_RANGE.finditer(htext)]
    found.sort()
    out = []
    spans = list(taken)
    for s, e, lo, hi in found:
        if lo in _BUCKET_GRID and (hi is None or hi in _BUCKET_GRID):
            continue
        if any(s < te and ts < e for ts, te in spans):  # a bucket word's span, or an earlier phrase's
            continue
        out.append((s, e, f"offgrid:{lo}-{'' if hi is None else hi}|{htext[s:e].strip()}"))
        spans.append((s, e))
    return out


def _drop_nested_hits(hits: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Drop any (start, end, key) hit whose span sits entirely inside another hit's own, strictly wider span in
    the same list -- one printed header phrase matched by two overlapping synonyms (or a bare Total/Summa word
    and a synonym, see _bucket_synonym_hits) is one column, not two, and an uncorrected double-count is
    indistinguishable from a genuinely wider table to _bucket_header's own column-count safety valve. Ties
    (identical span) are left alone -- two different keys matching the exact same text is a real ambiguity, not
    this function's call to resolve."""
    return [h for h in hits if not any(os <= h[0] and h[1] <= oe and (oe - os) > (h[1] - h[0]) for os, oe, _ in hits)]


def _year_span(head: str, pos: int, y: str) -> str:
    """The printed form of a calendar-year column header (v109): the bare year, plus an immediately
    adjacent open-end marker -- ">2031", "2031+", "2030–" name a window that runs past the year, and
    the label keeps the report's own wording instead of a bare year that under-states the window."""
    s, e = pos, pos + len(y)
    while s > 0 and head[s - 1] == ">":
        s -= 1
    while e < len(head) and head[e] in "+–-":
        e += 1
    return head[s:e]


def _bucket_year_hits(text: str, fiscal_year, labels: list | None = None) -> list[tuple[int, str]]:
    """A maturity table whose columns are calendar years rather than named buckets ("2026 2027 2028 Later"):
    [(position, key)] classifying each ascending year found right after fiscal_year (1 year out =
    due_within_1_year, 2-5 years out = due_1_to_5_years, further out or a trailing "Later"/"thereafter"/
    "senare"/"övriga år" = due_after_5_years). [] without >=2 such years. `labels`, when a list is
    passed, receives each column's own printed label in the same order (the year as printed, the
    tail word verbatim) -- v109's buckets_by_year source; every pre-existing caller passes nothing
    and gets exactly the old behaviour."""
    if not fiscal_year:
        return []
    run = _year_run(text)
    start = next((i for i, y in enumerate(run) if int(y) == int(fiscal_year) + 1), None)
    if start is None or len(run) - start < 2:
        return []
    head = " ".join(text[:4000].split())
    hits, pos = [], -1
    for i, y in enumerate(run[start:], start=1):
        pos = head.find(y, pos + 1)
        hits.append((pos, "due_within_1_year" if i == 1 else "due_1_to_5_years" if i <= 5 else "due_after_5_years"))
        if labels is not None:
            labels.append(_year_span(head, pos, y))
    tail = _YEAR_TAIL.search(head[pos:])
    if tail:
        hits.append((pos + tail.start(), "due_after_5_years"))
        if labels is not None:
            labels.append(tail.group())
    return hits


_SCOPE_TITLE_MAX = 100  # v103: a table's own title is a standalone short line; prose definitions and torn
# multi-column glue are not (Boozt p.121's own table title is 73 chars, the prose sentence above it that
# names "contractual undiscounted amounts" is 181 -- the cap is what keeps the marker on the title block
# and off the section prose above it)
_CARRY_COLUMN = re.compile(r"(?i)\bcarrying\b|\bredovisat\b|\bbokfört\b|\bbook value\b")  # v103: carrying-
# column wording, a superset of total_debt's own header_synonyms ("carrying amount" / "carrying value" /
# "redovisat värde" / "bokfört värde") -- plus "book value" (Humble's own column header) and the bare word
# "carrying", because a torn header can break the phrase while the word still names the column (Ework's
# real p.70: "Total undis- Carrying kSEK Due < 1 month ... counted value amount"). Deliberately not added
# to header_synonyms: that list re-tags the total slot (v076) and must not change meaning.
_DEBT_SUBJECT_WORDS = ("interest-bearing", "interest bearing", "räntebärande", "borrowings", "borrowing",  # v111:
                       "lease liabilities", "lease liability", "upplåning")  # the bare borrowing-scope words
# beside the total field's own vocabulary -- the rescue list of the non-debt-subject rule: a table whose
# title or rows name borrowings, leases or interest-bearing debt is a debt table whatever else it says.
_GROUP_SECTION_WORDS = ("group", "koncernen", "koncern", "koncernens", "consolidated", "the group")  # the
# section-heading families that re-open the Group's own tables after a Parent Company block
_PARENT_NOTES_CONTINUATION = re.compile(
    r"(?i)^(?:(?:the\s+)?parent company(?:'s)? notes|notes to the parent company|"
    r"moder(?:bolagets|företagets) noter|noter till moder(?:bolaget|företaget))(?:\s+(?:continued|forts\.?))?$"
)
_SEC_HEADING_SUFFIX = re.compile(r"(?i)\s*[,;:]?\s*(?:msek|sek\s*m|sekm|sek|meur|eur\s*m|usd\s*m|cad\s*m|"
                                 r"gbp\s*m|mkr|mdkk|dkk|nok|isk|tkr|ksek|kkr|million|milljoner|mn)\s*$")
_REFUSED_SCOPES = ("undiscounted", "all_liabilities", "non_debt", "parent", "cash_flow", "lease_only")
# v103's two refusals + v111's two + v155's cash-flow movement table + v186's unmarked lease schedule
_CASH_FLOW_STATEMENT = re.compile(r"(?i)\b(?:consolidated\s+)?statement\s+of\s+cash\s+flows?\b|\bcash\s+flow\s+statement\b")
_FINANCING_ACTIVITY_MOVEMENT = re.compile(r"(?i)\bchanges?\s+in\s+(?:financing|financial)\s+activities\b")
_GROSS_VALUE_MATURITY = re.compile(r"(?i)\bgross\s+values?\b")
_GROSS_VALUE_BLOCK_YEAR = re.compile(r"(?i)^\s*(20\d\d)\b.*\bmaturity\b")
_LEASE_ONLY_CONTEXT = re.compile(
    r"(?i)\b(?:leased premises|lease liabilities?|leasing liabilit(?:y|ies)|leaseskulder|leasingskulder|leasingavtal)\b"
)
_BORROWING_CONTEXT = re.compile(
    r"(?i)\b(?:borrowings?|loans?|bank debt|debt|interest[ -]bearing|räntebärande|upplåning|"
    r"liabilities to credit institutions?|skulder till kreditinstitut|carrying (?:amount|value)s?|"
    r"redovisat värde|bokfört värde)\b"
)
_GENERIC_MATURITY_ROW = re.compile(
    r"(?i)^(?:total|summa|totalt|amount)$|"
    r"\b(?:within|less than|under|after|more than|later than|over)\s+(?:one|five|\d+)\s*(?:months?|years?)\b|"
    r"\bbetween\s+(?:one|\d+)\s+and\s+(?:one|five|\d+)\s+(?:months?|years?)\b|"
    r"\b\d+\s*[-–]\s*\d+\s*(?:months?|years?)\b|"
    r"\b(?:inom|mindre än|under|efter|senare än|över)\s+(?:ett|en|fem|\d+)\s*(?:månader|år)\b|"
    r"\bmellan\s+(?:ett|en|\d+)\s+och\s+(?:ett|en|fem|\d+)\s+(?:månader|år)\b"
)
_MATURITY_BUCKET_PHRASE = re.compile(
    r"(?i)\b(?:within|less than|under|after|more than|later than|over)\s+(?:one|five|\d+)\s*(?:months?|years?)\b|"
    r"\bbetween\s+(?:one|\d+)\s+and\s+(?:one|five|\d+)\s+(?:months?|years?)\b|"
    r"(?:^|\s)[<>]\s*\d+\s*(?:months?|years?)\b|\b\d+\s*[-–]\s*\d+\s*(?:months?|years?)\b|"
    r"\b(?:inom|mindre än|under|efter|senare än|över)\s+(?:ett|en|fem|\d+)\s*(?:månader|år)\b|"
    r"\bmellan\s+(?:ett|en|\d+)\s+och\s+(?:ett|en|fem|\d+)\s+(?:månader|år)\b"
)


def _debt_subject_words(schema: dict) -> list[str]:
    """v111: the borrowing-scope vocabulary of the identity's own total field (synonyms + row_synonyms) plus
    the bare subject words -- what the non-debt-subject rule rescues on: a table whose title or own rows
    name borrowings, leases or interest-bearing debt is a debt table whatever else its title says."""
    ident = _identity_parts(schema)
    tsf = next((sf for sf in schema.get("fields", []) if sf["key"] == (ident[0] if ident else "total_debt")), None)
    words = {" ".join(str(s).translate(_DASHES).lower().split())
             for s in (tsf or {}).get("synonyms", []) + (tsf or {}).get("row_synonyms", [])}
    return sorted({w for w in (words | set(_DEBT_SUBJECT_WORDS)) if w})


def _section_heading(row: str, parent_words: list[str]) -> str | None:
    """v111: "parent" | "group" | None -- which entity a short standalone row names as a SECTION heading. The
    heading is the entity word alone, trailing unit/date furniture excepted ("Parent Company, MSEK 31 Dec 2025
    31 Dec 2024" and "Moderbolaget 2025 2024" are headings -- Momentum p.117, Svedbergs p.132): everything
    from the first digit-bearing token on is furniture, and a trailing unit word may follow it. A row naming
    BOTH entities is v052's paired-column header ("Koncernen ... Moderbolaget ...", one table's two column
    groups), never a section heading; and a prose line that merely mentions an entity ("Moderbolaget har
    inga ...") never survives the equality -- v103's short-standalone-line rule, tightened to the entity
    word itself."""
    low = " ".join(row.translate(_DASHES).lower().split())
    if not low or len(low) > _SCOPE_TITLE_MAX:
        return None
    parents = [" ".join(w.translate(_DASHES).lower().split()) for w in parent_words]
    has_parent, has_group = any(w in low for w in parents), any(w in low for w in _GROUP_SECTION_WORDS)
    if has_parent and has_group:
        return None
    toks = low.split()
    label = " ".join(toks[:next((i for i, t in enumerate(toks) if re.search(r"\d", t)), len(toks))])
    label = " ".join(_SEC_HEADING_SUFFIX.sub("", label).strip(" ,;:·|-–—").split())
    if has_parent and label in parents:
        return "parent"
    return "group" if label in _GROUP_SECTION_WORDS else None


def _nearest_entity_section(rows: list[str], i: int, parent_words: list[str], max_back: int = 25) -> str | None:
    """v111: the entity of the nearest section heading above rows[i] -- the first parent/group heading the
    upward walk meets decides: a table under a Group heading is the Group's whatever sits further up, and a
    Parent Company section holds until a Group/Koncernen/Consolidated heading re-opens the Group's own
    tables (Momentum p.117's "Group, MSEK" heading below Note 23's Parent block). None when the window
    holds no entity heading at all."""
    for j in range(i - 1, max(0, i - max_back) - 1, -1):
        got = _section_heading(rows[j], parent_words)
        if got is not None:
            # PDF text can put the column-group headings on separate lines:
            # Group / Parent / Current 2025 2024 2025 2024. This is one
            # shared table, not a new Parent section. Require adjacent entity
            # headings and an immediately following repeated year pair.
            if j > 0 and _section_heading(rows[j - 1], parent_words) not in (None, got):
                header = rows[j:j + 2]
                years = _year_run(" ".join(header))
                if len(years) == 4 and years[:2] == years[2:] and years[0] != years[1]:
                    if _row_year_column(rows, i, int(years[0])) is not None:
                        return "group"
            return got
    return None


def _parent_notes_continuation(rows: list[str], i: int, parent_words: list[str]) -> str | None:
    """v186: the exact page-boundary Parent Company-notes running heading holding rows[i].

    Balco p.101 repeats ``THE PARENT COMPANY'S NOTES`` at the physical page boundary, but PDF text
    order leaves it as the terminal row after the table, outside v111's upward section walk. Only an
    exact notes heading among the first/last two page rows extends that scope. A subsequent explicit
    Group/Koncernen/Consolidated section heading closes it, just as it closes v111's ordinary Parent
    Company block; a generic occurrence of "parent" in prose remains insufficient.
    """
    if not rows or not (0 <= i < len(rows)):
        return None
    boundary = sorted(set(range(min(2, len(rows)))) |
                      set(range(max(0, len(rows) - 2), len(rows))))
    for j in boundary:
        heading = " ".join(rows[j].translate(_DASHES).strip(" ,;:|-").split())
        if not _PARENT_NOTES_CONTINUATION.fullmatch(heading):
            continue
        # A boundary marker after the candidate is a repeated running heading in PDF text order.
        # In either ordering, any explicit Group heading before the candidate re-opens Group scope.
        start = j + 1 if j < i else 0
        if any(_section_heading(rows[k], parent_words) == "group" for k in range(start, i)):
            continue
        return rows[j]
    return None


def _lease_only_maturity_context(rows: list[str], i_header: int | None, i_total: int) -> str | None:
    """v186: lease-context row proving a generic maturity row belongs to an unmarked lease schedule.

    G5 p.92 tears the titleless schedule directly onto a ``Movement of leased premises`` roll-forward.
    It has generic Total/interval rows but no borrowing, debt or carrying row. Require all three facts:
    a lease marker in this table's bounded local zone, at least two maturity-bucket phrases around the
    candidate, and a generic Total/bucket candidate with no borrowing/carrying signal. Thus an ordinary
    Group borrowings table which happens to include leases remains readable, and Sedana's lease-liability
    balance-sheet Total (no bucket ladder) remains outside this predicate.
    """
    if not (0 <= i_total < len(rows)):
        return None
    label = " ".join(_row_label(rows[i_total]).translate(_DASHES).strip(" ,;:|-").split())
    if not _GENERIC_MATURITY_ROW.search(label):
        return None
    title, body = _scope_zone(rows, i_header, i_total)
    local = [*title, *body, rows[i_total]]
    if any(" ".join(row.translate(_DASHES).lower().strip(" ,;:|-").split()) in _GROUP_SECTION_WORDS
           for row in local):
        return None  # an explicit Group section owns its lease schedule (Rusta p.115)
    lease_row = next((row for row in local if _LEASE_ONLY_CONTEXT.search(row)), None)
    if lease_row is None or any(_BORROWING_CONTEXT.search(row) for row in local):
        return None
    nearby = rows[max(0, i_total - 25):min(len(rows), i_total + 3)]
    if sum(len(_MATURITY_BUCKET_PHRASE.findall(_row_label(row))) for row in nearby) < 2:
        return None
    return lease_row


def _scope_zone(rows: list[str], i_header: int | None, i_total: int) -> tuple[list[str], list[str]]:
    """v103: (title_rows, body_rows) of the table the row rows[i_total] sits in. The body is the rows
    directly above i_total that carry a digit, contiguously -- a maturity table's data rows all print
    figures, so prose, footnotes and section text break the walk (MedCap's carrying table ends at its own
    title because the prose above it names amounts), and a quote stitched or prose-written far below a
    table never walks back up into it (Storytel's covenants sentence). The title block is the digit-free
    rows above the body, short ones only (_SCOPE_TITLE_MAX): a section heading above prose stays
    unreachable (Boozt's "LIQUIDITY RISK" must not brand the all-liabilities table below prose that
    names it, and MedCap's "LIKVIDITETSRISK" must not brand the carrying table under it). Both zones
    bounded by 25 rows (v085's window); i_header, when the caller knows the table's own header row, is
    the walk's floor -- the block of a stacked page never climbs into the table above."""
    lo = max(0, i_total - 25)
    floor = i_header if isinstance(i_header, int) and 0 <= i_header < i_total else lo - 1
    j = i_total - 1
    while j > floor and j >= lo and re.search(r"\d", rows[j]):
        j -= 1
    body = rows[j + 1:i_total]
    title: list[str] = []
    k = j
    while k >= lo:
        row = rows[k]
        if k != j and re.search(r"\d", row):
            break  # prose that names figures, or a table stacked above: the title block is over
        if len(row) > _SCOPE_TITLE_MAX and not (k == j and i_header is not None):
            break  # the caller's own header row (a floor stop) is table furniture, not prose -- uncapped
        title.append(row)
        k -= 1
    return title, body


def _gross_value_prior_year_block(rows: list[str], i_total: int, fiscal_year) -> int | None:
    """The explicitly headed prior-year block of a gross-value maturity table.

    A gross-value table may print the fiscal year's block immediately above its
    predecessor.  The ordinary year selector sees the next *maturity* years
    in the predecessor's column headers and can mistake one for the report
    period.  This only reports a conflict when the table's own short title
    says ``gross values`` and the nearest block heading is a different year;
    carrying-value rows and current-year gross blocks remain available to
    their existing mechanisms.
    """
    if not fiscal_year:
        return None
    title, _ = _scope_zone(rows, None, i_total)
    if not any(_GROSS_VALUE_MATURITY.search(row) for row in title):
        return None
    for j in range(i_total - 1, max(0, i_total - 25) - 1, -1):
        match = _GROSS_VALUE_BLOCK_YEAR.match(rows[j])
        if match:
            year = int(match.group(1))
            return year if year != int(fiscal_year) else None
    return None


def _table_scope(rows: list[str], i_header: int | None, i_total: int, basis: str = "carrying",
                 scope_words: dict | None = None, debt_scoped: bool = False,
                 debt_words: list[str] | None = None) -> str:
    """v103: which maturity table the row rows[i_total] belongs to, for the wrong-table guard:
    "carrying" -- the table prints a carrying-amount column (Ework, Instalco, Bergman & Beving,
        Humble's "Book value"): readable under both bases, whatever its title says -- the title's
        "undiscounted" names the other column, and reading the carrying column is exactly v076;
    "undiscounted" -- the liquidity note's undiscounted table (title/header markers, no carrying
        column): refused under the carrying basis (v097's two mis-scoped fills -- RVRC's 220 read off
        the "Maturity analysis regarding non-discounted liabilities" Total row, Lime's 66,396 off the
        "Liquidity risk - Group" Borrowing row), and allowed under the undiscounted basis, where it is
        the table v089 reads, unless its own shape makes it "all_liabilities";
    "all_liabilities" -- a marker-carrying table read on a row that is not debt-scoped while non-debt
        liability rows (trade payables, accounts payable, ...) sit between its header and that row:
        refused under both bases -- trade payables are not debt on either one (RVRC's Total row sums
        payables 119 and expected returns 34 into total_debt with the identity endorsing it). Under
        the carrying basis the title rule already refuses the whole table, so this verdict only ever
        surfaces under the undiscounted basis, where the title rule steps aside for v089's read;
    "non_debt" -- v111: the table's own title block names a non-debt subject (contract liabilities,
        revenue-recognition timing, customer advances, warranty, provisions, ...) and no borrowing-
        scope word in title or body rows: its bucket-shaped rows time somebody else's liability, not
        debt -- refused under BOTH bases (Volati p.177's "Timing of revenue recognition, contract
        liabilities", whose "Within 1 year 87" the column-order repair wrote over the model's own
        correct current-total 192 with). A debt word anywhere in the table's title or own rows
        rescues it -- debt words win;
     "parent" -- v111/v186: the table sits in a Parent Company / Moderbolaget / Moderföretaget section
         (the nearest entity section heading above it, _nearest_entity_section) that no Group/
         Koncernen/Consolidated heading has since closed: the Group's total must not take buckets from
         the parent's own table -- refused under both bases (Momentum p.111's parent lease maturity
         "Within 1 year 2" against the Group's 622 balance-sheet total). v052's paired Koncernen|
         Moderbolaget column headers are one table's two column groups, not section headings, and keep
         their own read. v186 additionally recognises only an exact page-boundary Parent Company-notes
         running heading (Balco p.101), still closed by a new Group heading;
     "lease_only" -- v186: a generic Total/bucket row belongs to an otherwise unmarked lease maturity
         schedule: its bounded local context names leases, prints at least two maturity buckets, and has
         no borrowing/debt/carrying row. Refused under both bases (G5 p.92); a normal Group borrowings
         table which includes a lease row and a lease balance-sheet Total without a bucket ladder stay;
     "cash_flow" -- v155: the cited row itself names a cash-flow statement, or its own short table
         title jointly names a financing-activities movement and cash flow. A movement closing balance
         is not a carrying debt or maturity figure, even when it looks plausible; a navigation/sidebar
         mention elsewhere on the page is deliberately insufficient;
     "unknown" -- no marker provable on the page: exactly today's behaviour, no refusal. A markerless
        all-liabilities table (Karnell's earn-outs and accounts-payable rows) is NOT refused here:
        v095's debt-row-first ordering already governs it, and a bare word-list refusal would take
        label-pinned reads off balance sheets and torn pages (Alligo, RaySearch, Svedbergs,
        Stillfront, Hexatronic -- the five a full-corpus dry run caught before this shipped).

    `basis` resolves which table the extraction is told to read (debt_basis()); `debt_scoped` says the
    caller's row names the borrowing scope itself (the total field's own row vocabulary) -- only
    consulted under the undiscounted basis, where a debt row of the liquidity note is the legitimate
    read (Lime's Borrowing row) while its grand-total row is not. `debt_words` (_debt_subject_words)
    is the non-debt rule's rescue list."""
    words = scope_words or {}
    und_words = [w.lower() for w in words.get("undiscounted", [])]
    all_words = [w.lower() for w in words.get("all_liabilities", [])]
    nd_words = [w.lower() for w in words.get("non_debt_subject", [])]
    parent_words = [w.lower() for w in words.get("parent_company", [])]
    if not und_words and not all_words and not nd_words and not parent_words:
        return "unknown"  # a schema that opts out (every section but debt_maturity) keeps today's behaviour
    title, body = _scope_zone(rows, i_header, i_total)
    tlow = " ".join(r.translate(_DASHES).lower() for r in title)
    blow = " ".join(r.translate(_DASHES).lower() for r in body)
    # v155: a cash-flow movement row can close on a plausible borrowing balance but is not a
    # carrying-amount or maturity table. Require the target row itself to name the statement, or
    # both parts of the financing-activity movement title to live in this table's short title/body:
    # navigation/sidebar labels elsewhere on a page must never classify an unrelated table.
    scope_text = " ".join((*title, *body))
    if _CASH_FLOW_STATEMENT.search(rows[i_total]) or (_FINANCING_ACTIVITY_MOVEMENT.search(scope_text)
                                                       and re.search(r"(?i)\bcash[ -]?flow\b", scope_text)):
        return "cash_flow"
    if _CARRY_COLUMN.search(tlow) or _CARRY_COLUMN.search(blow) \
            or _CARRY_COLUMN.search(rows[i_total].translate(_DASHES)):
        return "carrying"  # the table's own carrying column -- the carrying read, both bases (v076/v085)
    if nd_words and any(w in tlow for w in nd_words) \
            and not any(w in tlow for w in (debt_words or ())) \
            and not any(w in blow for w in (debt_words or ())):
        return "non_debt"  # the table's own subject is not debt; a borrowing word in title or rows rescues it
    if parent_words and (_nearest_entity_section(rows, i_total, parent_words) == "parent"
                         or _parent_notes_continuation(rows, i_total, parent_words) is not None):
        return "parent"  # the parent's own table: wrong entity for the Group's total, either basis
    if not any(w in tlow for w in und_words):
        if _lease_only_maturity_context(rows, i_header, i_total) is not None:
            return "lease_only"  # unmarked generic maturity rows from a local lease-only schedule
        return "unknown"  # no title/header marker inside the walk's reach: nothing provable to refuse on
    if basis == "undiscounted" and (debt_scoped or not any(w in blow for w in all_words)):
        return "unknown"  # v089's own table: the debt-scoped read of it is the basis's legitimate read
    if basis == "undiscounted":
        return "all_liabilities"
    return "undiscounted"


def _scope_reason(rows: list[str], i_header: int | None, i_total: int, scope_words: dict | None,
                  scope: str = "undiscounted") -> str:
    """The 'table <row> is undiscounted / is an all-liabilities table (<word> among its rows) / is a
    non-debt subject table / sits in the Parent Company section' half of a guard warning -- names the
    row the marker matched, so the warning points at the page."""
    words = scope_words or {}
    und_words = [w.lower() for w in words.get("undiscounted", [])]
    all_words = [w.lower() for w in words.get("all_liabilities", [])]
    nd_words = [w.lower() for w in words.get("non_debt_subject", [])]
    parent_words = [w.lower() for w in words.get("parent_company", [])]
    title, body = _scope_zone(rows, i_header, i_total)
    if scope == "parent":
        if hit := _parent_notes_continuation(rows, i_total, parent_words):
            return f"the Parent Company notes continuation {hit.strip()!r} holds this table"
        for j in range(i_total - 1, max(0, i_total - 25) - 1, -1):
            if _section_heading(rows[j], parent_words) == "parent":
                return f"the Parent Company section {rows[j].strip()!r} holds this table"
    if scope == "non_debt":
        hit = next((r for r in title if any(w in r.translate(_DASHES).lower() for w in nd_words)), None)
        frag = (hit if hit is not None else (title[0] if title else rows[i_total])).strip()
        return f"table {frag!r} is a non-debt subject table"
    if scope == "cash_flow":
        return f"row {rows[i_total].strip()!r} is in a cash-flow statement"
    if scope == "lease_only":
        hit = _lease_only_maturity_context(rows, i_header, i_total)
        return f"generic row {rows[i_total].strip()!r} belongs to a lease-only maturity schedule ({(hit or '').strip()!r}; no borrowing/carrying row)"
    hit = next((r for r in title if any(w in r.translate(_DASHES).lower() for w in und_words)), None)
    frag = (hit if hit is not None else (title[0] if title else rows[i_total])).strip()
    if scope != "all_liabilities":
        return f"table {frag!r} is undiscounted"
    word = next((w for w in all_words if w in " ".join(r.translate(_DASHES).lower() for r in body)), None)
    return f"table {frag!r} is an all-liabilities table ({word!r} among its rows)"


_MISSING_REASON_PRIORITY = {
    "absent_in_table": 100,
    "offgrid_span": 90,
    "straddle": 80,
    "noncurrent_only": 70,
    "lease_table_only": 60,
    "parent_only": 60,
    "not_found": 0,
}


def _record_missing_reason(events: list[tuple[tuple[str, ...], dict]] | None, keys, code: str, detail: str,
                           page: int | None = None, quote: str | None = None, disclosed: list[dict] | None = None) -> None:
    """Keep a known refusal/mapping gap separate from warnings until the final null fields are known.

    Repairs later in extract() may still turn the same field into a proven value, so this records only
    facts already established at the existing decision point. _attach_missing_reasons() writes the
    attachment only if the final standard debt field is still null.
    """
    if events is None or code not in _MISSING_REASON_PRIORITY:
        return
    reason = {"code": code, "detail": detail}
    if page is not None:
        reason["page"] = page
    if quote:
        reason["quote"] = quote
    if disclosed:
        reason["disclosed"] = disclosed
    events.append((tuple(keys), reason))


def _scope_missing_reason(rows: list[str], i_header: int | None, i_total: int, scope_words: dict | None,
                          scope: str) -> dict | None:
    """The two named wrong-scope mechanisms which the debt API can safely describe.

    The wider scope guard also rejects cash-flow, all-liabilities and non-debt tables. Those remain
    correctly rejected, but are not relabelled as either a parent or lease table just to fill a code.
    """
    title, body = _scope_zone(rows, i_header, i_total)
    if scope == "parent":
        words = [w.lower() for w in (scope_words or {}).get("parent_company", [])]
        quote = _parent_notes_continuation(rows, i_total, words) or next(
            (r for r in reversed(rows[max(0, i_total - 25):i_total])
             if _section_heading(r, words) == "parent"), None)
        return {
            "code": "parent_only",
            "detail": "Only the Parent Company section was found; it is not the Group borrowing schedule.",
            "quote": quote,
        }
    if scope in ("undiscounted", "lease_only"):
        quote = next((r for r in (*title, *body) if _BS_LEASE.search(r) or _LEASE_ONLY_CONTEXT.search(r)), None)
        if quote:
            return {
                "code": "lease_table_only",
                "detail": "Only a lease-liabilities maturity table was found; it is not the Group borrowing schedule.",
                "quote": quote,
            }
    return None


def _attach_missing_reasons(fields: list[dict], schema: dict, pages: list[int], events: list[tuple[tuple[str, ...], dict]]) -> None:
    """Attach one structured reason to each final null standard debt field, never changing a value."""
    if schema.get("name") != "debt_maturity":
        return
    keys = {"total_debt", "due_within_1_year", "due_1_to_5_years", "due_after_5_years"}
    by_key = {f.get("key"): f for f in fields}
    gathered: dict[str, list[dict]] = {key: [] for key in keys}
    for event_keys, reason in events:
        for key in event_keys:
            if key in gathered:
                gathered[key].append(reason)
    page_list = ", ".join(str(page) for page in dict.fromkeys(pages) if isinstance(page, int) and page > 0)
    searched = f"candidate page{'s' if ',' in page_list else ''} {page_list}" if page_list else "the candidate pages"
    for key in keys:
        field = by_key.get(key)
        if not field:
            continue
        if field.get("value") is not None:
            field.pop("missing_reason", None)
            continue
        if "absent_in_table" in (field.get("evidence") or []):
            source = field.get("source") or {}
            reason = {
                "code": "absent_in_table",
                "detail": "The maturity table does not print a column for this window.",
            }
            if source.get("page") is not None:
                reason["page"] = source["page"]
            if source.get("quote"):
                reason["quote"] = source["quote"]
        else:
            candidates = gathered[key]
            reason = max(candidates, key=lambda item: _MISSING_REASON_PRIORITY[item["code"]]) if candidates else {
                "code": "not_found",
                "detail": f"No valid figure was read from {searched}.",
            }
        field["missing_reason"] = reason
        if not field.get("source") and reason.get("page") and reason.get("quote"):
            # A null already has this precedent for absent_in_table: the source proves the absence or
            # refusal, not a value, and lets the ordinary page pane open the cited report page.
            field["source"] = {"page": reason["page"], "quote": reason["quote"]}


def _scope_header(rows: list[str], i_total: int, bucket_sfs: dict, max_back: int = 25) -> int | None:
    """Index of the nearest row above i_total that names a bucket of its own (_bucket_synonym_hits over
    the schema's bucket fields): the fill gate's known header row for _table_scope -- in a row-per-bucket
    table that nearest row is itself a bucket-labelled data row, still a correct floor for the walk."""
    for j in range(i_total - 1, max(0, i_total - max_back) - 1, -1):
        if any(k.split(":")[0] not in ("total", "_ignore")
               for _, _, k in _bucket_synonym_hits(rows[j], bucket_sfs)):
            return j
    return None


_TORN_BUCKET_START = re.compile(r"(?i)(?P<within>\bwithin\s+\d{1,2})\s+(?P<later>later\s+than)\s*$")
_TORN_BARE_YEAR = re.compile(r"(?i)(?<![\w-])year\b")
_TORN_FIVE_YEARS = re.compile(r"(?i)(?<![\d\-–])\b5\s+years?\b")
_TORN_BUCKET_CONTEXT = re.compile(r"(?i)^\s*due\s+for\s+payment\s+as\s+follows:\s*")


def _rejoin_torn_bucket_headers(rows: list[str]) -> list[str]:
    """Join the two physical tiers of a narrowly proven bucket header, without changing source rows.

    CTT's print order puts ``Within 1 Later than`` at the end of one row and its two continuations
    (a bare ``year`` and ``5 years``) in the immediately following row.  Reading the rows in order
    leaves the second phrase as a lone ``5 years`` and loses the after-five-years column.  The two
    top fragments and the two matching continuations are required together: not-adjacent rows,
    another top fragment, or a non-bucket continuation return byte-identical rows.  The transformed
    copy is only a header-reading aid; quotes and indices still point to the original page rows.
    """
    fixed = list(rows)
    for i in range(len(rows) - 1):
        top, bottom = rows[i], rows[i + 1]
        start = _TORN_BUCKET_START.search(top)
        bare_year = _TORN_BARE_YEAR.search(bottom)
        five_years = list(_TORN_FIVE_YEARS.finditer(bottom))
        five_years = five_years[-1] if five_years else None  # ``4-5 years`` is an earlier, complete middle column
        context = _TORN_BUCKET_CONTEXT.match(bottom)
        if not start or not bare_year or not five_years or not context or bare_year.start() > five_years.start():
            continue
        # ``Later than`` must genuinely be missing below: otherwise this is already a complete
        # header, and reparsing it would double-count a column.
        if re.search(r"(?i)\blater\s+than\s+5\s+years?\b", bottom):
            continue
        fixed[i] = " ".join(part for part in (top[:start.start()].strip(), start["within"], bare_year.group()) if part)
        remainder = _TORN_BUCKET_CONTEXT.sub("", bottom[:bare_year.start()] + bottom[bare_year.end():], count=1)
        five_years = list(_TORN_FIVE_YEARS.finditer(remainder))[-1]
        fixed[i + 1] = " ".join((remainder[:five_years.start()] + " " + start["later"] + " " + remainder[five_years.start():]).split())
    return fixed


def _bucket_header(rows: list[str], idx: int, bucket_sfs: dict, fiscal_year, max_back: int = 25,
                   total_sf: dict | None = None, ignore_syns: list | None = None, basis: str = "carrying",
                   year_cols: list | None = None) -> list[str] | None:
    """The ordered column keys of the maturity-bucket table whose grand-total sits on rows[idx]: each bucket hit
    above it, in print order, plus a "total" slot wherever a bare Total/Summa/Totalt column header is seen. A
    due_within_1_year subtotal column (_SUBTOTAL_PHRASES, e.g. XANO's "Summa inom 1 år") overrides, not adds to,
    its own finer day/month columns already seen to its left in this same header. Read from a generous window of
    the rows above idx, not just the one right above it: pymupdf sometimes wraps a two-line column header (Summa
    / inom 1 år) into two of _page_rows' rows, and the note's own heading and instrument rows sit between the
    header and the total row. Within one row, a hit nested inside another, wider hit is dropped before counting
    (_drop_nested_hits) -- see its own docstring and _bucket_synonym_hits'. None without >=2 distinct bucket
    keys -- a page that merely mentions one bucket word in passing prose is not a bucket-column table. Falls
    back to a literal calendar-year header (_bucket_year_hits) when no named bucket reaches that bar.

    v076: a carrying-amount phrase (total_sf's own header_synonyms) on a bucket-naming line fills the total slot
    itself, and an undiscounted/contractual phrase (ignore_syns) on that same line becomes an "_ignore" column --
    counted, never assigned. Both are dropped from lines that name no bucket (prose and note titles in the same
    25-row window, v069's bare-"due" lesson). When the window carries a carrying hit anywhere, no bare Total word
    in it claims the total slot any more -- on bucket-naming lines the bare word is demoted to _ignore (a
    competing total-shaped column beside the carrying one, v028), on prose lines it is dropped; without a
    carrying hit anywhere, the _ignore tags are dropped and every bare word keeps today's behaviour: the total
    slot.

    v085: a carrying/ignore phrase dropped above for naming no bucket on its own line is kept aside, not
    discarded outright, when it sits in an unbroken run of such lines directly touching the header's own last
    bucket-naming line -- Instalco p.128 wraps a genuine third header tier ("31/12/2025 Carrying amount
    receivables/ payables", "Total contractual cash flows") across two lines of its own, neither naming a
    bucket, both directly above the "Within 6 months / 6-12 months / 1-5 years / Later than 5 years" line that
    does, nothing else in between. The run stops at the first line with neither a bucket word nor a carrying/
    ignore word of its own -- Ework's own prose danger ("...reflected in the carrying amount...") and note
    title ("...undiscounted cash flows") sit six-plus lines further back on its real p.70, past "The Group"
    naming neither, so the run never reaches them, unlike a blanket window-wide scan (confirmed against the
    real page: without the stop, both leak in and misread the *other* row on the same page, Lease liabilities,
    as this table's own total -- and on Ependion's real p.155, two unrelated "...corresponds to carrying
    amount..." sentences leak in the same way and wrongly demote the real header's own bare Total to _ignore,
    turning an already-correct fill into a false decline). Only consulted when no bucket-naming line in the
    window already claims a carrying hit on its own (otherwise it would double what a same-line read, v076,
    already found -- the false-total-word inflation v076 fenced) AND only when nothing between the header's
    own last bucket-naming line and idx itself prints its own amounts: Instalco's own page prints a *second*
    candidate row of exactly this shape one note-section down -- the whole table's own grand "Total" row,
    summing debt with non-debt liabilities alike (Accounts payable, Contingent consideration) -- separated
    from the header by the four instrument rows in between; those rows' own printed amounts close the header
    block before it ever reaches that far, so the fallback stays unavailable for that row exactly as it was
    before this lane (a bare Total/Summa row's own scope is _bucket_total_row's question, not this function's
    -- left declined here, not silently handed a column reading it was never entitled to). Appended after
    every bucket-naming line's own hits (every table seen so far prints its total-shaped columns last, and
    _bucket_total_row's own column-count valve still has the final say).

    v089: `basis` (debt_basis()) only re-tags which word group is the total slot and which is ignored
    (_bucket_synonym_hits); every rule here is basis-symmetric and reads unchanged.

    v095: a maturity-window phrase no bucket word matched and off the 1/5-year grid (">3 years", _offgrid_hits)
    is counted as a column of its own -- the alignment the 3-vs-4 length valve denied Karnell -- but never as
    one of the >=2 distinct bucket keys this function requires (a page mentioning one bucket word plus ">3
    years" in prose is still not a bucket-column table), and never assigned a bucket (_bucket_assign skips the
    tag). Only amount-free rows contribute one (the bare-Total rule, v060: a row printing "1-3 years 523" is a
    row-per-bucket table's own data row, not this table's column header).

    v109: `year_cols`, when a list is passed, receives the calendar-year fallback's own column labels
    (see _bucket_year_hits) -- buckets_by_year's "year header -> column" mapping, exposed where it is
    computed instead of re-derived. Every pre-existing caller passes nothing and is unchanged."""
    window = _rejoin_torn_bucket_headers(rows[max(0, idx - max_back):idx])
    per_row = []
    row_ci = []  # v085: this row's own total:carrying/_ignore hits, kept aside because it names no bucket of
    # its own -- a candidate for the contiguous-run fallback below, not yet admitted
    bucket_pos = []  # window positions of rows that do name a bucket of their own
    amounts_present = [bool(_row_amounts(row)) for row in window]
    for pos, row in enumerate(window):
        bare_total = [(m.start(), m.end(), "total") for m in _BARE_TOTAL.finditer(row.translate(_DASHES))] if not amounts_present[pos] else []
        # a bare Total/Summa only marks a header column when its own row carries no amounts -- a row that
        # prints "Total 96 173" is another table's own data row (Boozt p.121's earlier receivables-ageing
        # note, still inside the 25-row window), not a column header wrapped above idx (v060)
        row_hits = _bucket_synonym_hits(row, bucket_sfs, total_sf, ignore_syns, basis)
        if not amounts_present[pos]:  # v095: the off-grid phrase is a header column only on an amount-free row --
            row_hits += _offgrid_hits(row, [(s, e) for s, e, _ in row_hits])  # the bare-Total rule (v060), see docstring
        if any(k.split(":")[0] not in ("total", "_ignore") for _, _, k in row_hits):
            bucket_pos.append(pos)
            row_ci.append([])
        else:
            row_ci.append([h for h in row_hits if h[2] in ("total:carrying", "_ignore")])
            row_hits = [h for h in row_hits if h[2].split(":")[0] not in ("total", "_ignore")]
        per_row.append((row_hits, bare_total))
    # v076: when the header carries a carrying-amount column anywhere in the window, it -- not a bare Total
    # word -- is the total slot (v028), so every bare Total/Summa hit in the window is demoted to _ignore: a
    # bare word on a bucket-naming line belongs to this header only when no carrying column exists ("Total
    # undiscounted value" alone keeps today's reading); anywhere else ("…of the total balance for accounts…",
    # Ework's own p.70 prose two tables above) it is prose that would shift every column after it by one the
    # moment the carrying read makes the window's hit count match the row's amounts -- seen live in v076's
    # first real-page run, caught by the over valve, and fenced here at the source.
    has_carry = any(k == "total:carrying" for row_hits, _ in per_row for _, _, k in row_hits)
    hits_tail = []
    if not has_carry and bucket_pos and not any(amounts_present[bucket_pos[-1] + 1:]):
        tail = []
        for pos in range(bucket_pos[-1] - 1, -1, -1):
            if not row_ci[pos]:
                break
            tail.append(row_ci[pos])
        tail.reverse()
        if any(k == "total:carrying" for hs in tail for _, _, k in hs):
            has_carry = True
            hits_tail = [key for hs in tail for _, _, key in sorted(_drop_nested_hits(hs))]
    hits = []
    for row_hits, bare_total in per_row:
        if has_carry:
            # demoted only on header lines (a bucket-naming row's bare word is this header's own secondary
            # total column); dropped from prose rows -- counted, an amount-free prose row's bare word would
            # pad the column count back up and break the very alignment the carrying read restores
            if any(k.split(":")[0] not in ("total", "_ignore") for _, _, k in row_hits):
                bare_total = [(s, e, "_ignore") for s, e, _ in bare_total]
            else:
                bare_total = []
        else:
            row_hits = [h for h in row_hits if h[2] != "_ignore"]
        hits.extend(key for _, _, key in sorted(_drop_nested_hits(row_hits + bare_total)))
    hits.extend(hits_tail)
    hits = ["total" if k == "total:carrying" else k for k in hits]
    # v095: an offgrid column counts toward the column list (alignment) but never toward the >=2 distinct bucket
    # keys this valve requires -- one bucket word plus ">3 years" in prose is not a bucket-column table
    if len({k.split(":")[0] for k in hits if k.split(":")[0] not in ("total", "_ignore", "offgrid")}) < 2:
        year_hits, year_labels = None, None
        for row in window:
            row_labels: list[str] = []
            yh = _bucket_year_hits(row, fiscal_year, labels=row_labels)
            if len({k for _, k in yh}) >= 2:
                year_hits, year_labels = sorted(yh), row_labels
                break
        if not year_hits:
            return None
        hits = [key for _, key in year_hits] + (["total"] if any(_BARE_TOTAL.search(r) for r in window) else [])
        if year_cols is not None:
            # v109: the native calendar-year columns behind these keys, one label per column in
            # print order ("total", when present, is appended after them above) -- buckets_by_year's
            # source, recorded only when this fallback is what produced the header
            year_cols.extend(year_labels)
    original = hits
    for j, k in enumerate(original):  # a subtotal column wins over its own finer columns already counted to its left
        if k.endswith(":subtotal"):
            real = k[:-len(":subtotal")]
            hits = ["_excluded" if h == real and i < j else h for i, h in enumerate(hits)]
            hits[j] = real
    return hits


def _bucket_total_row(rows: list[str], total_sf: dict, bucket_sfs: dict | None = None, fiscal_year=None,
                       known_total=None, warnings: list[str] | None = None, ignore_syns: list | None = None,
                       basis: str = "carrying") -> list[int]:
    """Indices of rows that could be a maturity table's grand-total row: the total field's own synonym ("Summa
    räntebärande skulder"), or a bare Total/Totalt/Summa -- a schema's total-field synonyms are themselves
    phrased as row labels ("total borrowings"), but plenty of reports print just the bare word on the total row
    of a table that is already, by construction, about borrowings (the page only got here as a debt_maturity
    candidate), e.g. Cloetta's and Ework's own maturity notes. Appended (not substituted -- a page can have both
    a bare-Total row that turns out to be the wrong scope, Ework's own all-liabilities "Total" row, and the real
    debt row further down; the caller already tries each candidate in order and moves on when one doesn't pan
    out): rows whose label is a debt synonym (total_sf's own schema-level row_synonyms, Ependion's bucket row is
    labelled "Borrowing", Boozt's "Lease liabilities") *and* that read a real bucket header above them with a column count matching
    their own printed amounts -- so Ependion's four unrelated "Bank loans" per-currency rows (no bucket header
    over them at all) are never candidates to begin with. Multiple survivors first narrow by year (v084):
    Swedish reports often stack two whole maturity tables on one page, this year's and last year's, each under
    its own "31 december <year>" header but printing the identical row label -- a same-labelled row that
    _bucket_row_prior_year proves belongs to the fiscal year's predecessor is dropped from contention, and if
    that leaves exactly one survivor it wins outright (Tången p.62: "Lån Kreditinstitut" printed once under
    "31 december 2025" and once under "31 december 2024", identical label, four bucket amounts each -- excluding
    the 2024 row leaves the 2025 one alone). Two same-labelled rows that are *not* distinguishable this way (both
    name the same year, or neither names one at all) are untouched by this step and fall through unresolved, on
    purpose -- only known_total (the model's own already-sourced total_debt, if any) narrows next -- the row that
    itself prints that figure wins (Ework p.70: only the short-term interest-bearing liabilities row prints
    156,410; the page's own "Lease liabilities" row and the prior-year block's rows don't). Still ambiguous after
    both is not a guess this function will make -- dropped, with a warning, not a pick.

    v095: a bare Total/Totalt/Summa row is the table's grand total of whatever the table sums -- Karnell's
    all-liabilities "Total 72.2 354.4 107.0 533.5" includes earn-outs, put/call options and accounts payable --
    while a row named by the total field's own wording ("Total interest-bearing liabilities") or a debt-row
    candidate names the borrowing scope itself. When both kinds survive, the debt-scoped rows are tried first
    and the bare table totals last; with no debt-scoped row the order (and behaviour) is exactly today's. The
    scope of a bare Total row is this function's question precisely because no schema key can express it: v088's
    own experiment (claiming ">3 years" for due_after_5_years) opened Karnell's header and filled 533.5 with the
    identity check passing -- a wrong-scope value endorsed by its own check -- until this rule put the
    interest-bearing row (397.2) ahead of it."""
    hits = [i for i, r in enumerate(rows) if len(_row_amounts(r)) >= 2
            and (_label_known(_row_label(r), total_sf) or _clean_label(_row_label(r)) in ("total", "totalt", "summa"))]
    if not bucket_sfs:
        return hits
    proper = [i for i in hits if _label_known(_row_label(rows[i]), total_sf)]  # the total field's own wording
    bare = [i for i in hits if i not in proper]  # a bare table total, whatever the table sums
    debt_sf = {"synonyms": total_sf.get("row_synonyms", [])}
    candidates = []
    for i, r in enumerate(rows):
        if i in hits or len(_row_amounts(r)) < 2 or not _label_known(_row_label(r), debt_sf):
            continue
        col_keys = _bucket_header(rows, i, bucket_sfs, fiscal_year, total_sf=total_sf, ignore_syns=ignore_syns, basis=basis)
        if col_keys and len(_row_amounts(r, len(col_keys), nil=None)) == len(col_keys):
            candidates.append(i)
    if len(candidates) > 1:
        not_prior = [i for i in candidates if not _bucket_row_prior_year(rows, i, fiscal_year)]
        if len(not_prior) == 1:
            candidates = not_prior
    if len(candidates) > 1 and isinstance(known_total, (int, float)):
        narrowed = [i for i in candidates if any(a is not None and abs(a - known_total) <= 2 for a in _row_amounts(rows[i]))]
        if narrowed:
            candidates = narrowed
    if len(candidates) > 1:
        if warnings is not None:
            warnings.append(f"{total_sf['key']}: {len(candidates)} candidate debt rows for the bucket table "
                             f"({', '.join(repr(_row_label(rows[i])) for i in candidates)}) -- ambiguous, none used")
        candidates = []
    return proper + candidates + bare  # v095: debt-scoped rows outrank bare table totals, see docstring


def _bucket_assign(amounts: list, col_keys: list[str]) -> dict[str, float | None]:
    """{key: value} from a row's amounts by column key: a key spanning more than one column (a finer split,
    "1-2 years" + "2-5 years" both due_1_to_5_years) is their sum; a key whose every column is nil (None, not a
    printed 0) is None overall -- "-" in a maturity table means no debt is due in that window. Keeping None here
    (not a 0) leaves "nothing to sum" distinguishable from a column the table does not print at all; v078's
    write site (_fill_bucket_columns) is the one place that None is translated into the report's explicit 0,
    and only when the selected row's own arithmetic proves it."""
    out: dict[str, float | None] = {}
    for key in dict.fromkeys(col_keys):
        if key == "_ignore":  # v076: a counted-but-unassigned total-shaped column (undiscounted beside carrying).
            continue  # Skipping it here also keeps it out of the caller's over valve -- with future interest an
        # undiscounted total exceeds the carrying total, which is ordinary, never grounds to reject the row.
        if key.startswith("offgrid:"):  # v095: a counted column whose window no bucket claims exactly (">3
            continue  # years"); its nil is resolved by the caller's span logic, never assigned here -- and kept
        # out of the over valve the same way _ignore is.
        vals = [amounts[i] for i, k in enumerate(col_keys) if k == key and amounts[i] is not None]
        out[key] = round(sum(vals), 2) if vals else None
    return out


def _bucket_row_prior_year(rows: list[str], idx: int, fiscal_year) -> bool:
    """True when the candidate row's own year -- named inline, or by the nearest header run above it (_year_run,
    the same nearest-run-wins upward walk _row_year_column uses) -- is the fiscal year's predecessor and not the
    fiscal year itself. A maturity table whose header stacks both years' own totals must not lend its prior-year
    row to this year's buckets, even when one of its columns also happens to print this year's total (Net
    Insight's prior-year 'Total 81,489 57,647' row, v066)."""
    if not fiscal_year:
        return False
    fy, prior = str(fiscal_year), str(int(fiscal_year) - 1)
    run = _year_run(rows[idx]) or next((r for j in range(idx - 1, -1, -1) if (r := _year_run(" ".join(rows[j:idx])))), None)
    if run:
        return prior in run and fy not in run
    # v076: Ework p.70 stacks its two maturity tables printing ONE year label each, which _page_rows glues as
    # lone trailing tokens ("… Carrying amount 2025", "… 2,866,462 2024") -- no _year_run anywhere, so the walk
    # above saw nothing and the prior-year valve never fired; the 2024 table's own Total row then read under the
    # 2025 header four rows up the moment the carrying slot brought its key count level with its 8 amounts.
    # Same nearest-window walk over lone year tokens: the nearest year named above the row answers alone.
    lone = next((ys for j in range(idx - 1, -1, -1) if (ys := re.findall(r"\b20\d\d\b", " ".join(rows[j:idx])))), None)
    return bool(lone) and prior in lone and fy not in lone


_CURRENT_SUBTOTAL = re.compile(r"(?i)(?<![\w-])current\b|\bkortfristig\w*\b")  # v125: current-portion wording,
# already the schema's own (w1y synonyms "borrowings, current", "kortfristiga räntebärande skulder"); the
# Total/Totalt/Summa half of the sub-total shape is _BARE_TOTAL, and the field's own synonyms _label_known


def _table_break_between(rows: list[str], a: int, b: int, bucket_sfs: dict) -> bool:
    """v125: a table boundary sits strictly between rows[a] and rows[b] -- a digit-free line (a table's own
    title, a wrapped section header, prose) or a row naming maturity buckets of its own (a stacked table's
    column header, the v095/v060 amount-free-header shape, whether or not its date stamp carries digits).
    A table's own data rows all carry figures and name no header of their own, so a contiguous block of them
    is one table."""
    lo, hi = sorted((a, b))
    return any(not re.search(r"\d", rows[j])
               or any(k.split(":")[0] not in ("total", "_ignore")
                      for _, _, k in _bucket_synonym_hits(rows[j], bucket_sfs))
               for j in range(lo + 1, hi))


def _model_own_printed(current, sf: dict, texts: list[str], walk: list[int], bucket_sfs: dict,
                       page: int, idx: int) -> tuple[int, str] | None:
    """v125: (page, row) of the model's own answer for one field, when the answer is a printed sub-total of
    its own table -- (a) the value printed verbatim on a row of this walk's own candidate window, (b) that
    row's label a known synonym of the field or a sub-total/total shape (Total/Totalt/Summa via _BARE_TOTAL,
    the schema's current-portion wording current/kortfristig), and (c) the row not in the table this
    column-order read came from (another page, or the same page with a table boundary between the two).
    All three, because the page's column order must keep winning inside the very table the model misread
    (Cloetta's disagree case, v052's paired columns, v068's prior-year column -- there the cited row IS the
    read row, or the two rows share one table): what this stops is the read reaching across into another
    table's columns over a value the model took from its own table's printed total (Viscaria: the note's
    printed current sub-total 661.8, overwritten by 2.2 from the undiscounted per-instrument lease table's
    column order two pages back, v088's Volati family)."""
    for p in walk:
        if not (0 < p <= len(texts)):
            continue
        rws = _page_rows(texts[p - 1])
        for r in rws:
            if not _value_in_quote(current, r):
                continue
            rl = _row_label(r)
            if not (_label_known(rl, sf) or _BARE_TOTAL.search(rl) or _CURRENT_SUBTOTAL.search(rl)):
                continue
            if p != page or _table_break_between(rws, rws.index(r), idx, bucket_sfs):
                return p, r
    return None


def _fill_bucket_columns(fields: list[dict], sfs: list[dict], schema: dict, texts: list[str], pages: list[int],
                          fiscal_year, warnings: list[str], values: dict, filled: set, basis: str = "carrying",
                          selected: dict | None = None,
                          missing_events: list[tuple[tuple[str, ...], dict]] | None = None) -> None:
    """A maturity-bucket note that prints on one row, columns = buckets, instead of one row per bucket (Cloetta's
    borrowings note: "Total 197 22 1,377 9 1,605" under a header of "< 1 year / 1-2 years / 2-5 years / > 5 years
    / Total") -- a shape none of this file's other repairs cover, since _year_column finds no year in a bucket
    header and every repair built on it (_column_values, _derived_value, _between_rows) bails out before it can
    even try (docs/acrylic/evidence/v035.md, "the dominant failure mode"). Column order comes from the header
    text itself, so this reads the shape in general, not one company's table: find the header (_bucket_header),
    zip the row's own numbers to it (_bucket_assign), and either fill a null field or -- if the model's own
    answer disagrees by more than the check's own rounding tolerance -- let the page win, exactly like every
    other repair in this file (Pandox, Getinge, ...).

    v095: a header column whose maturity window is off the schema's 1/5-year grid (Karnell's ">3 years",
    _offgrid_hits) is counted for the alignment but never assigned. Its nil on the operand row resolves the
    windows it covers outright (">3 years" = [36 months, infinity) printing "-" => due_after_5_years, whose
    whole window it spans, is the report's 0; due_1_to_5_years keeps the "1-3 years" column it already read),
    written only when the row's own arithmetic closes -- v078's dash gate, one level up from the bucket's own
    column to a column the table named its own way. A value in that column is an honest decline with a warning
    that names the boundary straddled; a wrong guess there would be endorsed by the very identity check that
    should be catching it (v088's ">3 years" experiment filled the all-liabilities Total 533.5 and passed).

    v091: an optional `selected` dict receives {page, idx, col_keys} for the row this function actually
    read (recorded past the last valve -- only the writes can still be no-ops, when the model's own
    answers already agree with the table). _prior_year_fill's bucket-column prior-year source; every
    pre-existing caller passes nothing and behaves exactly as before.

    v109: when the pick's header was the calendar-year fallback, `selected` also receives
    "year_labels" (one printed label per year column, from _bucket_header's year_cols) --
    _buckets_by_year_fill's source. Same-table by construction: the years are the very columns
    the three buckets above were summed out of. `selected` additionally receives "scan_pages" (the
    walk's own page set, statement spread first) whether or not any pick was found on them --
    _buckets_by_year_fill's row-shaped fallback scans the same pages this reader walked.

    v125: the disagree branch keeps the model's own answer when that answer is itself a printed
    sub-total of its own table (_model_own_printed): the note's "Total current liabilities 661.8"
    must not be overwritten by the 2.2 a lease row's column order yields in the liquidity note's
    undiscounted per-instrument table two pages back (Viscaria, v088's Volati family) -- the
    warning names both rows. A bucket the model left null still fills: the rule protects an
    answered value, not a missing one.

    v144: an answered model total needs one further proof before this column-order re-read can
    replace it: the source row's own bucket columns must add back to its own total column within
    the schema's ±2 rounding tolerance.  A table can otherwise align by column count while a
    space-separated pair is read as one Swedish thousands number (MTG's "85 151" -> 85,151),
    creating an arbitrary total from a row that does not reconcile itself.  A null model total
    remains the existing fill path's responsibility; this gate only protects an answer from an
    unproved override.  If a persisted answer already cites that same unclosed row (an earlier
    column-order repair replayed as model input), it has no independent provenance to preserve,
    so it is discarded rather than perpetuating the bad derived total."""
    ident = _identity_parts(schema)
    if not ident:
        return
    total_key, part_keys = ident
    bucket_sfs = {sf["key"]: sf for sf in sfs if sf["key"] in part_keys}
    total_sf = next((sf for sf in sfs if sf["key"] == total_key), None)
    if len(bucket_sfs) != len(part_keys) or not total_sf:
        return
    ignore_syns = schema.get("ignore_header_synonyms", [])  # v076: undiscounted/contractual total wording
    # (which of the two total-shaped word groups is the total slot and which is ignored follows the
    # basis -- v089's debt_basis(), threaded down to _bucket_synonym_hits through the calls below)
    scope_words = schema.get("table_scope_words")  # v103: the wrong-table guard's marker vocabulary
    debt_subj = _debt_subject_words(schema) if scope_words else None  # v111: the non-debt rule's rescue list
    debt_vocab = {"synonyms": total_sf.get("synonyms", []) + total_sf.get("row_synonyms", [])}
    by_key = {f["key"]: f for f in fields}
    cited = {by_key[k]["source"]["page"] for k in (total_key, *part_keys) if by_key[k]["source"]}
    if selected is not None:
        # v109: this walk's own page set, recorded before any valve runs -- a page holding only a year-ROWS
        # table records no pick of its own (below), and _buckets_by_year_fill's row-shaped fallback still
        # gets the exact pages the column read tried: statement spread first, then the model's citations
        selected["scan_pages"] = [p for p in dict.fromkeys([p for p in pages[:2] if p] + sorted(cited))
                                  if isinstance(p, int) and 0 < p <= len(texts)]
    walk = list(dict.fromkeys([p for p in pages[:2] if p] + sorted(cited)))  # v125: also _model_own_printed's window
    for page in walk:
        if not (0 < page <= len(texts)):
            continue
        rows = _page_rows(texts[page - 1])
        candidates = _bucket_total_row(rows, total_sf, bucket_sfs, fiscal_year, by_key[total_key]["value"], warnings, ignore_syns, basis)
        if not candidates:
            continue
        matched = [i for i in candidates if fiscal_year and str(fiscal_year) in " ".join(rows[max(0, i - 25):i])]
        for idx in (matched or candidates):
            year_labels: list[str] = []  # v109: the calendar-year fallback's own labels, when this header is one
            col_keys = _bucket_header(rows, idx, bucket_sfs, fiscal_year, total_sf=total_sf, ignore_syns=ignore_syns,
                                      basis=basis, year_cols=year_labels)
            if not col_keys:
                continue
            amounts = _row_amounts(rows[idx], len(col_keys), nil=None)
            if len(amounts) != len(col_keys):
                continue
            if gross_prior_year := _gross_value_prior_year_block(rows, idx, fiscal_year):
                warnings.append(f"{total_key}: column reading of {rows[idx]!r} declined -- gross-value maturity "
                                f"block is headed {gross_prior_year}, not {fiscal_year}")
                continue
            # the row names the borrowing scope itself ("Total interest-bearing liabilities", "Borrowings") --
            # or, for a bare Total/Summa row, the table's own title/body does and no all-liabilities row
            # (trade payables, earn-outs) sits in it. Only such a row may earn the identity marker below:
            # Karnell's markerless all-liabilities "Total 72.2 454.4 - 526.6" closes on its own arithmetic
            # too, and closing alone is a self-referential proof, not identification (v088/v095).
            debt_row = _label_known(_row_label(rows[idx]), debt_vocab)
            if scope_words:  # v103/v111: the wrong-table guard -- a table the guard refuses is not filled from,
                hdr_i = _scope_header(rows, idx, bucket_sfs)  # whatever row of it happens to align
                scope = _table_scope(rows, hdr_i, idx, basis, scope_words, debt_scoped=debt_row, debt_words=debt_subj)
                if scope in _REFUSED_SCOPES:
                    warnings.append(f"{total_key}: column reading of {rows[idx]!r} declined -- "
                                    f"{_scope_reason(rows, hdr_i, idx, scope_words, scope)}; refused under the {basis} basis")
                    if (reason := _scope_missing_reason(rows, hdr_i, idx, scope_words, scope)) is not None:
                        _record_missing_reason(missing_events, [total_key, *part_keys], page=page, **reason)
                    continue
                if not debt_row:
                    # _scope_zone's title walk stops at the first digit-bearing row, and a column header
                    # ("< 1 year", "31 Dec 2025") is one -- so climb the short rows above the header
                    # ourselves: title, unit and date furniture are all short; the first long row is prose.
                    # ponytail: a debt table stacked right above lends its title; bounded by 25 rows.
                    top = hdr_i if hdr_i is not None else idx
                    k = top - 1
                    while k >= max(0, idx - 25) and len(rows[k]) <= _SCOPE_TITLE_MAX:
                        k -= 1
                    zone = " ".join(r.translate(_DASHES).lower() for r in rows[k + 1:idx])
                    debt_row = any(w in zone for w in (debt_subj or ())) and not any(w in zone for w in (x.lower() for x in scope_words.get("all_liabilities", [])))
            # v095: the off-grid columns this header printed (">3 years") -- counted for the alignment above,
            # never assigned. A value in one is an honest decline: where its window crosses the 1/5-year
            # boundaries the split is a guess no check can verify (a counterfactual Karnell printing 173 under
            # ">3 years" is 1-5-years money or after-5-years money with equal right). A nil (the dash) resolves
            # exactly the windows it covers outright -- handled after _bucket_assign, with the same arithmetic
            # gate v078's own dash-to-0 answers to.
            off_cols = []
            for j, k in enumerate(col_keys):
                if not k.startswith("offgrid:"):
                    continue
                span, phrase = k[len("offgrid:"):].split("|", 1)
                lo_s, hi_s = span.split("-")
                off_cols.append((int(lo_s), int(hi_s) if hi_s else None, phrase, amounts[j]))
            valued = [c for c in off_cols if c[3] is not None]
            if valued:
                named = []
                for lo, hi, phrase, amt in valued:
                    straddled = [b // 12 for b in _BUCKET_GRID if lo < b < (hi if hi is not None else 1 << 30)]
                    where = (f"straddles the {' and '.join(f'{y}-year' for y in straddled)} boundar{'y' if len(straddled) == 1 else 'ies'}"
                             if straddled else "is not on the 1/5-year bucket boundaries")
                    named.append(f"'{phrase}' {amt} {where}")
                warnings.append(f"{total_key}: column reading of {rows[idx]!r} declined -- {', '.join(named)}")
                for lo, hi, phrase, amount in valued:
                    boundaries = [b for b in _BUCKET_GRID if lo < b < (hi if hi is not None else 1 << 30)]
                    affected = [key for key in part_keys if any(
                        _BUCKET_WINDOW[key][0] <= boundary and
                        (_BUCKET_WINDOW[key][1] is None or boundary <= _BUCKET_WINDOW[key][1])
                        for boundary in boundaries
                    )]
                    disclosed = [{
                        "span": phrase,
                        "amount": amount,
                        "unit": by_key[total_key].get("unit"),
                        "page": page,
                        "quote": rows[idx],
                    }]
                    _record_missing_reason(
                        missing_events, affected, "offgrid_span",
                        f"The report discloses {phrase}, which crosses a standard maturity-bucket boundary and cannot be mapped without guessing.",
                        page=page, quote=rows[idx], disclosed=disclosed,
                    )
                continue
            derived = _bucket_assign(amounts, [total_key if k == "total" else k for k in col_keys])
            og_cover = {}  # v095: key -> the nil off-grid column whose window covers the bucket whole
            for key in part_keys:
                if key in derived:
                    continue  # the bucket has columns of its own; its all-dash case is v078's question, not this one
                w = _BUCKET_WINDOW.get(key)
                if w is None:
                    continue
                cover = next((c for c in off_cols if c[3] is None and c[0] <= w[0]
                              and (w[1] is None if c[1] is None else w[1] is not None and c[1] >= w[1])), None)
                if cover is not None:
                    derived[key] = 0
                    og_cover[key] = cover
            if sum(v is not None for v in derived.values()) < 2:
                continue  # one recognised column proves nothing about the row's shape
            total_val = derived.get(total_key)
            over = {k: v for k, v in derived.items() if k != total_key and v is not None and total_val is not None and v > total_val + 2}
            if over:
                # Acast: two stacked calendar-year tables (this year, prior year) end in their own bare "Total" row;
                # the wrong-year row's own header can still be read as *a* bucket header of the same column count by
                # coincidence, producing a bucket bigger than the row's own total -- never true of a real maturity
                # table (every bucket is part of the total). The column reading is untrustworthy across the whole
                # row, not just the one field that happens to look wrong, so every field here keeps the model's own
                # answer rather than have one column "fixed" out of a header that was never really aligned to begin with.
                warnings.append(f"{total_key}: column reading of {rows[idx]!r} rejected -- {', '.join(f'{k} {v}' for k, v in over.items())} "
                                 f"exceed{'s' if len(over) == 1 else ''} its own total {total_val}; model's own values kept")
                continue
            row_label = _row_label(rows[idx])
            if "total" not in col_keys and (_label_known(row_label, total_sf) or _clean_label(row_label) in ("total", "totalt", "summa")):
                # Net Insight (v066): a Total*/Summa* row with no total column among its own header's keys can
                # never be checked against its own stated total -- the `over` valve above has nothing to compare
                # to (derived has no total_key entry at all), so it stays blind to a wrong column-order read
                # instead of catching it. Left for another path rather than trusted ungated.
                warnings.append(f"{total_key}: {rows[idx]!r} is a Total*/Summa* row with no total column in its "
                                 f"own header ({', '.join(col_keys)}); its own total cannot be checked, left for another path")
                continue
            if _bucket_row_prior_year(rows, idx, fiscal_year):
                warnings.append(f"{total_key}: {rows[idx]!r} names fiscal year {int(fiscal_year) - 1}, not {fiscal_year}; not this year's bucket row")
                continue
            if selected is not None and "idx" not in selected:
                # v091: the first valve-passing pick stands -- a later candidate that also passed every
                # valve would have to be a second table this page already read under the same header.
                selected.update(page=page, idx=idx, col_keys=list(col_keys))
                if year_labels and len(year_labels) == len(col_keys) - (1 if col_keys[-1:] == ["total"] else 0):
                    # v109: this pick's columns are the report's own calendar years (the header
                    # fallback), one label per year column -- recorded for buckets_by_year; a
                    # named-bucket or carrying-column header leaves year_labels empty and records nothing
                    selected["year_labels"] = list(year_labels)
                # v165: buckets this header maps no column to -- the header was parsed, and fewer than
                # all of its windows are printed -- are the report's explicit absence, not the model's
                # silence: the value stays null, the header row becomes the field's source, and _check
                # counts the operand as 0 under require_explicit_values. A bucket with a column of its
                # own (even an all-dash one -- v078's question, and only the row's own arithmetic turns
                # that dash into a 0) or one an off-grid column spans whole (v095's question) is a
                # different, printed kind of null and stays unmarked; a bucket the model answered keeps
                # its own evidence. Bucket-column shape only: recorded on this pick, which no row-shaped
                # or prose reading ever produces.
                off_spans = []
                for k in col_keys:
                    if k.startswith("offgrid:"):
                        span, _phrase = k[len("offgrid:"):].split("|", 1)
                        lo_s, hi_s = span.split("-")
                        off_spans.append((int(lo_s), int(hi_s) if hi_s else None))
                hdr = next((r for r in reversed(rows[max(0, idx - 25):idx])
                            if any(k.split(":")[0] not in ("total", "_ignore")
                                   for _, _, k in _bucket_synonym_hits(r, bucket_sfs, total_sf, ignore_syns, basis))
                            or len({k for _, k in _bucket_year_hits(r, fiscal_year)}) >= 2), None)
                for key in part_keys:
                    w = _BUCKET_WINDOW.get(key)
                    if key in col_keys or (w is not None and any(lo <= w[0] and (w[1] is None or (hi is not None and hi >= w[1]))
                                                                 for lo, hi in off_spans)):
                        continue  # this window is printed, off-grid coverage included
                    if hdr is None or by_key[key]["value"] is not None:
                        continue  # no header row to cite, or the model read this window elsewhere
                    by_key[key].update(source={"page": page, "quote": hdr}, evidence=["absent_in_table"])
                    warnings.append(f"{key}: the maturity table on page {page} prints no column for this "
                                    f"window ({hdr!r}); not printed in this report")
            # v078: a bucket whose every column on this row prints a dash is not unprinted -- the report is
            # saying "no debt is due in this window" (v036's own nil convention, one level down), which is a
            # 0, not the null this path carried until now. Two gates before a dash says 0: the row must print
            # a total for its buckets to close against, and the real buckets must sum to it within the
            # check's own ±2 with the dashes read as 0 -- the row's own arithmetic is the proof. A total
            # sitting alone over dash columns is a misparsed row, not a zero-debt report; zeros written there
            # would turn an honest "missing" into a manufactured failure. The translation lives only here, at
            # the write: _row_amounts keeps nil=None for its other callers, _bucket_assign keeps None for
            # "nothing to sum", and _check's null-bucket guards never see a translated value. A bucket this
            # table prints no column for at all (key absent from derived) is not a dash: stays null.
            nil_keys = [k for k in part_keys if k in derived and derived[k] is None]
            # v095: an off-grid-covered 0 is exactly as provisional as v078's dash-to-0 -- written only when the
            # row's own arithmetic proves it, the same closure gate; the zeros join the sum (43.5 + 353.7 + 0 ==
            # 397.2 IS the proof of the 0, Karnell). Unproven, the covered bucket keeps its null.
            # `_excluded` is a finer column superseded by its table's own subtotal; it must not
            # be counted a second time when proving the row closes (XANO's 4,090 + 8,680 +
            # 38,305 are already represented by its printed within-one-year subtotal 51,075).
            bucket_sum = round(sum(v for k, v in derived.items() if k in part_keys and v is not None), 2)
            closes = isinstance(total_val, (int, float)) and abs(bucket_sum - total_val) <= 2
            if nil_keys and not closes:
                nil_keys = []
            if og_cover and not closes:
                for k in og_cover:
                    del derived[k]
                og_cover = {}
            acted = False
            for key in (total_key, *part_keys):
                value = derived.get(key)
                nil = value is None and key in nil_keys  # all-dash bucket on a row whose own arithmetic closes
                if nil:
                    value = 0
                current = by_key[key]["value"]
                if key == total_key and current is not None and total_key not in filled and not closes:
                    source = by_key[key].get("source") or {}
                    if source.get("page") == page and normalize_ws(str(source.get("quote") or "")) == normalize_ws(rows[idx]):
                        warnings.append(f"{key}: dropped {current} -- its column-order source row {rows[idx]!r} "
                                        f"does not close ({bucket_sum:g} != {total_val:g}, ±2 rounding)")
                        by_key[key].update(value=None, raw_label=None, source=None, evidence=[])
                        values[key] = None
                        continue
                if value is None or (isinstance(current, (int, float)) and abs(current - value) <= 2):
                    # the model's own answer, quoted from this very row, is identified by the same proof as a
                    # column-read one -- the row closes (label_known via the identity marker, see the write below).
                    # "Total 197 22 1,377 9 1,605" is a bare label no synonym list can own; its arithmetic can.
                    src = by_key[key].get("source") or {}
                    if value is not None and closes and debt_row and src.get("page") == page and normalize_ws(str(src.get("quote") or "")) == normalize_ws(rows[idx]) \
                            and "identity_all_columns" not in by_key[key]["evidence"]:
                        by_key[key]["evidence"].append("identity_all_columns")
                    continue  # nothing to add, or agrees with the model's own answer -- its evidence already covers it
                if key == total_key and current is not None and total_key not in filled and not closes:
                    warnings.append(f"{key}: kept the model's own {current} -- the column-order row {rows[idx]!r} "
                                    f"does not close ({bucket_sum:g} != {total_val:g}, ±2 rounding)")
                    continue
                prefix = "model returned null" if current is None else f"{current} disagrees with the maturity table"
                if nil:
                    warnings.append(f"{key}: {prefix}; a dash is printed in the row's own column for it ({rows[idx]!r}) -- "
                                    f"no debt due in that window, the report's explicit 0")
                elif key in og_cover:  # v095: the 0 is derived from a dash, but in a column of the table's own
                    # naming, not the bucket's (no "> 5 years" column exists) -- so value_derived, not printed_nil
                    warnings.append(f"{key}: {prefix}; no debt due in that window -- the row prints a dash in its "
                                    f"'{og_cover[key][2]}' column ({rows[idx]!r}), which spans it whole")
                else:
                    if isinstance(current, (int, float)) and \
                            (own := _model_own_printed(current, bucket_sfs.get(key, total_sf), texts, walk,
                                                       bucket_sfs, page, idx)):
                        warnings.append(f"{key}: kept the model's own {current} -- printed on page {own[0]} as "
                                        f"{own[1]!r}; column-order read {value} from {rows[idx]!r} not applied")
                        continue
                    warnings.append(f"{key}: {prefix}; {value} read from {rows[idx]!r} by its column order")
                # score_field derives value_in_quote itself from quote_on_page; only value_derived (a sum with no
                # literal quote, e.g. two finer bucket columns) needs to be pre-seeded, or it would double-count.
                # a row whose buckets sum to its own total is this table's identity holding in every column
                # -- the same proof that earns an unknown year-column row label_known (identity_all_columns, weight
                # 0, score_field turns it into label_known). Only when it closes AND the row or its table names the
                # borrowing scope (debt_row above): a row that does not add up is not identified by anything, and
                # its check fails on top; a bare Total of an unnamed table is not identified by adding up either.
                by_key[key].update(value=value, period=str(fiscal_year) if fiscal_year else by_key[key]["period"],
                                    raw_label=_row_label(rows[idx]), source={"page": page, "quote": rows[idx]},
                                    evidence=(["quote_on_page", "printed_nil"] if nil else
                                              ["quote_on_page", "value_derived"] if key in og_cover else
                                              ["quote_on_page"] if _value_in_quote(value, rows[idx]) else
                                              ["quote_on_page", "value_derived"]) + (["identity_all_columns"] if closes and debt_row else []))
                values[key] = value
                filled.add(key)
                acted = True
            if acted:
                return


def _statement_row(rows: list[str], sf: dict, ncols: int) -> str | None:
    """The field's row on a statement page: the full row whose label is exactly a synonym ("Operating profit" for a bank's
    profit before tax; the synonym through the same _clean_label as the label — "Within 1 year" is exactly within1year),
    else the one full row with a known, unexcluded label prefix. None when ambiguous -- including when two different
    full rows each match a different synonym of the SAME field (v058's month-range wording makes MedCap's "6 månader
    eller mindre" and "6 – 12 månader" rows both due_within_1_year): that is a finer split summing to the bucket, no
    single row is the field, and the statement-row fill must leave it to the identity machinery, not claim the first
    row's figure as the bucket."""
    full = [r for r in rows if len(_row_amounts(r, ncols)) == ncols]
    syn = {c for s in sf.get("synonyms", []) if (c := _clean_label(s))}  # a synonym that cleans away to nothing would match every labelless row
    hits = [r for r in full if _clean_label(_row_label(r)) in syn]
    if len(hits) == 1:
        return hits[0]
    cands = [r for r in full if _label_known(_row_label(r), sf)]
    return cands[0] if len(cands) == 1 else None


_NET_DEBT_LABEL = re.compile(r"(?i)\bnet(?:to)?[\s-]*(?:interest[ -]bearing[\s-]*)?(?:debt|skuld(?:er)?|liabilit\w*)")


def _normalize_sign(fields, sfs, schema, texts, warnings, values):
    """v101: a debt total or bucket printed under a liabilities-negative sign convention -- net-debt and
    capital-management presentations print cash positive and every debt row negative (Catella's
    "Total interest-bearing liabilities −1,474 −2,735" net-debt profile, Scandi Standard's "Gross debt
    December 31 2025 (Note 21) −2,021 −286 −2,307" financing reconciliation, FM Mattsson's
    "Räntebärande skulder (not 37) -89 532 -93 727" capital-risk note) -- carries its magnitude with a
    minus, and a quote-verified negative passes every gate as-is. These fields' semantics is a carrying
    amount of borrowings, so when the sign is the table's presentation rather than the debt's -- the
    quoted row holds other negative amounts beside the field's own, or the rows of the same table
    (the contiguous amount-bearing run around the quote row) do -- the field records the magnitude:
    value flipped, evidence `sign_normalized` (a 0-weight marker, like identity_kept), one warning.
    Called before the final checks recompute, so the identity closes on carrying positives (a
    mixed-sign table's printed rows would close on their printed signs only when every operand flips
    together -- the normalization, not the identity's tolerance, decides here).

    NOT flipped: a row labelled as net debt ("Net debt", "Nettoskuld", "Net interest-bearing debt") --
    there the negative can be a genuine net-cash position, and total_debt must not point at a net-debt
    row at all. The shape is recorded in a warning and left as printed, never repaired here (the label
    vocabulary of v048/v083 judges what points there)."""
    ident = _identity_parts(schema)
    if not ident or set(ident[1]) != _DATE_BUCKET_KEYS:
        return
    total_key, part_keys = ident
    for sf, f in zip(sfs, fields):
        if sf["key"] != total_key and sf["key"] not in part_keys:
            continue
        v = f.get("value")
        src = f.get("source") or {}
        page = src.get("page")
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v >= 0 \
                or "quote_on_page" not in f.get("evidence", []) \
                or not src.get("quote") or not isinstance(page, int) or not 0 < page <= len(texts):
            continue
        if _NET_DEBT_LABEL.search(_clean_label(f.get("raw_label"))):
            warnings.append(f"{sf['key']}: {v} is printed under a net-debt label ({f.get('raw_label')!r}); left as printed -- a negative there can be a genuine net-cash position, and {total_key} does not point at a net-debt row")
            continue
        same_row = any(a < 0 for a in _row_amounts(src["quote"]) if a != v)
        if not same_row:
            rows = _page_rows(texts[page - 1])
            qi = next((i for i, r in enumerate(rows) if r == src["quote"] or quote_on_page(src["quote"], r)), None)
            if qi is not None:  # the quote row's own table: the contiguous run of amount-bearing rows around it
                lo = hi = qi
                while lo - 1 >= 0 and _row_amounts(rows[lo - 1]):
                    lo -= 1
                while hi + 1 < len(rows) and _row_amounts(rows[hi + 1]):
                    hi += 1
                same_row = any(a < 0 for j in range(lo, hi + 1) if j != qi for a in _row_amounts(rows[j]))
        if not same_row:
            continue
        warnings.append(f"{sf['key']}: {v} printed with a liabilities-negative sign convention; recorded as {-v}")
        f["value"] = values[sf["key"]] = -v
        f["evidence"].append("sign_normalized")


def score_field(field: dict, sf: dict, checks: list[dict], schema: dict, currency, fiscal_year, statement_pages: set[int],
                texts: list[str] | None = None) -> None:
    """Fill field["evidence"] and field["confidence"] from what the backend itself verified. Never the model's opinion."""
    ev = field["evidence"]  # may already hold quote_on_page
    src = field["source"] or {}
    if "quote_on_page" in ev and _value_in_quote(field["value"], src.get("quote", "")):
        ev.append("value_in_quote")
    mine = [c for c, sc in zip(checks, schema.get("checks", [])) if re.search(rf"\b{re.escape(field['key'])}\b", sc["expr"])]
    failed = [c for c in mine if not c["passed"] and not c["detail"].startswith("missing:")]  # a check with a missing operand is n/a, not failed
    if not failed:
        ev.append("arith_ok")  # vacuously true for fields no check references (eps)
    # scoring-only vocabulary: the field's synonyms, its row wording (debt_maturity's row_synonyms -- "Borrowings",
    # "Lease liabilities" are known total rows even though selection keeps them apart) and its own label; never
    # header_synonyms, whose "Total" would identify any row
    vocab = {**sf, "synonyms": sf.get("synonyms", []) + sf.get("row_synonyms", []) + [sf.get("label", "")]}
    if _label_known(field.get("raw_label"), vocab) or "value_derived" in ev or "identity_all_columns" in ev:
        ev.append("label_known")  # a derived sum, or an unknown row, is identified by the check holding in every column, not by a printed label
    if fiscal_year and str(field.get("period")) == str(fiscal_year):
        ev.append("period_ok")
    if field.get("key") == "total_debt" and texts and (tie := _balance_sheet_tie(texts, fiscal_year, field.get("value"), schema)):
        tied_rows, _ = tie
        evidence = " + ".join(row["label"] for row in tied_rows)
        ev.append("bs_tie")
        field["raw_label"] = f"{field.get('raw_label') or sf.get('label')} (ties to BS: {evidence})"
    if src.get("page") in statement_pages:
        ev.append("page_is_statement")
    unit = str(field.get("unit") or "")
    if unit and currency and (unit.upper() == str(currency).upper() or (sf.get("unit_hint") == "currency_per_share" and _ccy(unit) == _ccy(currency))):
        ev.append("unit_ok")  # EPS in SEK when the statement is in MSEK / SEKm / SEK million
    if "value_derived" in ev and "value_in_quote" in ev:
        ev.remove("value_in_quote")  # a derived value stands in for the printed one, never both (v097 saw 1.2 when a derivation's own quote happened to contain the sum)
    score = min(sum(WEIGHTS[e] for e in ev), 1.0)
    if "quote_on_page" not in ev:
        score = min(score, 0.25)  # no verifiable provenance
    if "quote_on_page" in ev and "value_in_quote" not in ev and "value_derived" not in ev:
        score = min(score, 0.50)  # the row is on the page but this number is not in it
    if failed:
        score = min(score, 0.50)  # contradicts its neighbours
    if fiscal_year and re.fullmatch(r"\d{4}", str(field.get("period"))) and "period_ok" not in ev:
        score = min(score, 0.50)  # another year's figure
    field["confidence"] = round(score, 3)


def _prior_year_fill(fields: list[dict], sfs: list[dict], schema: dict, texts: list[str], fiscal_year,
                     bucket_pick: dict) -> dict | None:
    """(v091) The prior fiscal year's figures for the identity's own fields, as `prior_year` metadata --
    a deterministic re-read of the same table the current year came from, never a model answer. Two
    sources, exactly the two that read today's values deterministically:

    (a) buckets-as-columns (`bucket_pick`, what _fill_bucket_columns recorded): the same-labelled row
        of the prior year's own block on the same page -- Tången p.62 stacks whole "31 december 2025"
        and "31 december 2024" tables with identical row labels, Ework p.70 stacks "2025"/"2024"
        blocks -- proven prior-year by _bucket_row_prior_year, lined up with the SAME col_keys, read
        through _bucket_assign. A bucket whose prior-year cells all print dashes is the report's
        explicit 0 (v078's convention, one year back); the total must be a real figure.
    (b) buckets-as-rows (no pick): the prior-year COLUMN of the very rows that supplied the current
        values -- MedCap p.101's "Koncernen Moderbolaget / 2025-12-31 2024-12-31 2025-12-31
        2024-12-31" header names the Group's prior-year column. Each field is admitted only when the
        fiscal-year column of its own quoted rows reproduces its current value (the _column_values
        admission), every admitted field must share one header (page, fiscal column, prior column,
        column count), and the prior column comes from the same nearest-run walk _row_year_column
        uses, with _row_year_column's own answer as the divergence guard. A field with no page-verified
        row quote (a date-per-instrument sum, Proact v073) never admits, so date-shaped notes and
        model-only answers give no prior year.

    The gate is the schema's own identity, run on the prior year's EXPLICIT values -- the shipped
    require_explicit_values rule applied to FY-1: a bucket with no prior-year figure is absent from
    the sum, never zero-filled (and a bucket that would have mattered makes the closure fail, which
    is the point). The key is written only when the total and at least two buckets were read and the
    read buckets sum to the total within the check's own ±2; anything less returns None and the
    extraction carries no prior_year key at all, not a null one. The basis needs no threading of its
    own: (a) reuses the pick _fill_bucket_columns recorded under the live debt_basis() -- same table,
    same total slot -- and (b) has no total-slot dimension."""
    ident = _identity_parts(schema)
    if not ident or not fiscal_year or set(ident[1]) != _DATE_BUCKET_KEYS:
        return None
    total_key, part_keys = ident
    prior_fy = int(fiscal_year) - 1
    sc = next((c for c in schema.get("checks", []) if c.get("identity")
               and re.search(rf"\b{re.escape(total_key)}\b", c["expr"])), None)
    if sc is None:
        return None

    def _numeric(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    reads: dict[str, tuple] | None = None
    if bucket_pick.get("page") and 0 < bucket_pick["page"] <= len(texts):
        rows = _page_rows(texts[bucket_pick["page"] - 1])
        idx, col_keys = bucket_pick["idx"], bucket_pick["col_keys"]
        label = _row_label(rows[idx]) if 0 <= idx < len(rows) else None
        if label and not _bucket_row_prior_year(rows, idx, fiscal_year):
            cands = [(j, am) for j, r in enumerate(rows)
                     if j != idx and _row_label(r) == label and _bucket_row_prior_year(rows, j, fiscal_year)
                     and len(am := _row_amounts(r, len(col_keys), nil=None)) == len(col_keys)]
            if len(cands) == 1:  # no twin, or two indistinguishable twins: no prior year, never a guess
                j, am = cands[0]
                derived = _bucket_assign(am, [total_key if k == "total" else k for k in col_keys])
                reads = {}
                for k in (total_key, *part_keys):
                    if k not in derived:
                        continue  # the prior-year table prints no column of its own for this bucket
                    v = derived[k]
                    if k == total_key and not _numeric(v):
                        continue  # a dash or missing total anchors nothing
                    reads[k] = (0 if v is None else v, bucket_pick["page"], rows[j])
    if reads is None:
        def _row_range(rows: list[str], quote: str):
            if quote in rows:
                i = rows.index(quote)
                return i, i + 1
            for a, r in enumerate(rows):  # a derived quote is contiguous rows joined with single spaces
                if not quote.startswith(r):
                    continue
                join, b = r, a + 1
                while b < len(rows) and len(join) < len(quote):
                    join += " " + rows[b]
                    b += 1
                if join == quote:
                    return a, b
            return None

        def _prior_column(rows: list[str], i: int):
            """(prior_col, fy_col, ncols) from the nearest year run above rows[i]: _row_year_column's
            own upward walk and its Group|Parent pair rule, mirrored for the prior year. The fiscal
            column must agree with _row_year_column's own answer, or the read declines -- never a
            second opinion alongside the one the current year already trusted."""
            for j in range(i - 1, -1, -1):
                run = _year_run(_DEC_DATE.sub(lambda m: m.group(1), " ".join(rows[j:i])))
                if not run:
                    continue
                fy = [p for p, y in enumerate(run) if y == str(fiscal_year)]
                pr = [p for p, y in enumerate(run) if y == str(prior_fy)]
                take = (pr[0], fy[0]) if len(fy) == 1 and len(pr) == 1 else None
                if take is None and len(fy) == 2 and len(pr) == 2:  # Group | Parent pairs, same rule as _row_year_column
                    near = " ".join(rows[max(j - 1, 0):j + 1]).lower()
                    g, e = locate.GROUP.search(near), locate.ENTITY.search(near)
                    if g and e:
                        first = g.start() < e.start()
                        take = (pr[0] if first else pr[-1], fy[0] if first else fy[-1])
                if take is None or _row_year_column(rows, i, fiscal_year) != (take[1], len(run)):
                    return None
                return (*take, len(run))
            return None

        reads, headers = {}, set()
        for f in fields:
            if f["key"] not in (total_key, *part_keys) or not _numeric(f.get("value")):
                continue
            src = f.get("source") or {}
            page, quote = src.get("page"), src.get("quote")
            if not isinstance(page, int) or not 0 < page <= len(texts) or not quote \
                    or "quote_on_page" not in f.get("evidence", []):
                continue  # a model-only answer has no printed row to mirror a year column off
            rows = _page_rows(texts[page - 1])
            rng = _row_range(rows, quote)
            pc = _prior_column(rows, rng[0]) if rng else None
            if pc is None:
                continue
            pcol, fcol, ncols = pc
            ams = [_row_amounts(r, ncols, nil=None) for r in rows[rng[0]:rng[1]]]
            if any(len(am) != ncols for am in ams) \
                    or round(sum(am[fcol] for am in ams if am[fcol] is not None), 2) != f["value"]:
                continue  # the field's own rows in their own fiscal-year column must reproduce it
            headers.add((page, fcol, pcol, ncols))
            pv = round(sum(am[pcol] for am in ams if am[pcol] is not None), 2)
            reads[f["key"]] = (pv if any(am[pcol] is not None for am in ams) else 0, page, quote)
        if len(headers) != 1 or total_key not in reads:  # fields from more than one table, or no total
            reads = None
    if not reads:
        return None
    total = reads.get(total_key, (None,))[0]
    buckets = {k: v for k, v in reads.items() if k in part_keys}
    if not _numeric(total) or len(buckets) < 2 \
            or abs(round(sum(v[0] for v in buckets.values()), 2) - total) > 2:
        return None  # the total and at least two buckets read, closing within the check's own tolerance
    absent = [k for k in part_keys if k not in buckets]
    detail = f"{sc.get('detail', '')} | abs((" + " + ".join(str(buckets[k][0]) for k in part_keys if k in buckets) \
        + f") - {total}) <= 2" + (f" ({', '.join(absent)}: no prior-year figure in this table)" if absent else "")
    return {
        "fiscal_year": prior_fy,
        "fields": {k: {"value": reads[k][0], "source": {"page": reads[k][1], "quote": reads[k][2]}}
                   for k in (total_key, *part_keys) if k in reads},
        "check": {"passed": True, "detail": detail.strip(" |")},
    }


def _year_cols_read(texts: list[str], fiscal_year, bucket_pick: dict, total, basis: str) -> dict | None:
    """(v109) The column-shaped source: the year columns _fill_bucket_columns already aligned, re-read
    on the pick's own row (see _buckets_by_year_fill). The pick's recorded page/idx/col_keys/year_labels
    must still line up exactly; any decline is None."""
    page = bucket_pick.get("page")
    if not isinstance(page, int) or not 0 < page <= len(texts):
        return None
    rows = _page_rows(texts[page - 1])
    idx, col_keys, labels = bucket_pick["idx"], bucket_pick["col_keys"], bucket_pick["year_labels"]
    ntail = 1 if col_keys[-1:] == ["total"] else 0
    if not 0 <= idx < len(rows) or len(labels) + ntail != len(col_keys):
        return None  # the recorded labels no longer line up with the recorded columns
    amounts = _row_amounts(rows[idx], len(col_keys), nil=None)
    if len(amounts) != len(col_keys):
        return None
    vals = [0 if a is None else a for a in amounts[:len(labels)]]  # v078: a dash in the row's own year column is the report's explicit 0
    if total > 0 and any(v < 0 for v in vals) and all(v <= 0 for v in vals):
        vals = [-v for v in vals]  # v101's liabilities-negative display convention, one level finer: the years are magnitudes too
    if abs(round(sum(vals), 2) - total) > 2:
        return None  # the years must close on the same total the three buckets answer to
    return {"basis": basis,
            "years": [{"label": label, "value": vals[i], "source": {"page": page, "quote": rows[idx]}}
                      for i, label in enumerate(labels)]}


def _year_figure(tok: str):
    """(v109) One printed figure of a year-ROWS table: an amount by _row_amounts' own convention
    (_AMOUNT, sign included), or a lone dash -- the report's explicit 0 (v078, one window finer).
    None for anything else: the row shapes this reader takes print exactly one figure per year, so a
    second number or a word is another table glued on (Acast p.68's side-by-side page) and no
    deterministic column choice survives it."""
    t = tok.rstrip(",;").translate(_DASHES)
    if t == "-":
        return 0
    m = _AMOUNT.fullmatch(t)
    if m:
        v = int(re.sub(r"\D", "", m.group(1))) + (float(f"0.{m.group(3)}") if m.group(3) else 0)
        return -v if t[0] in "-(" else v
    return None


def _after_label_figure(row: str, label: str):
    """(v109) Exactly one printed figure after the row's label and nothing else: a bare Total row's own
    total ("Total 579,797"), an open-end tail year's figure ("Thereafter 260", "2031 and later 169").
    None when the row prints two figures (BTS p.92's stacked "Total 579,797 420,953" above the year
    table is the liabilities table's own row, two columns), none, or anything unparseable."""
    toks = _FOOTNOTE.sub("", row[len(label):] if label and row.startswith(label) else row).translate(_DASHES).split()
    return _year_figure(toks[0]) if len(toks) == 1 else None


def _inline_year_pairs(row: str, fiscal_year) -> list[tuple[str, float]] | None:
    """(v109) The row-shaped calendar-year table as pymupdf tears it: one line of "<year> <figure>"
    pairs, ascending from fiscal_year+1 (BTS p.92: "SEK thousands 12-31-25 2026 77,141 2027 39 2028
    300,039 2029 202,539 2030 39" above "Total 579,797"). Parsed from the row's own end -- the last
    token a figure, the one before it its year, alternating left while each year is exactly the
    previous one minus 1; whatever sits left of the first year is the table's own label/furniture
    ("SEK thousands 12-31-25") and stays unread. The strict -1 chain is the valve: a year the report
    skips breaks it, and an unrelated year+number pair ("in 2026 3.00 per share") cannot chain.
    >=2 pairs and the leftmost year = fiscal_year+1, else None."""
    toks = _FOOTNOTE.sub("", row).translate(_DASHES).split()
    pairs: list[tuple[str, float]] = []
    i, expect = len(toks) - 1, None
    while i >= 1:
        v = _year_figure(toks[i])
        if v is None:
            break
        y = int(toks[i - 1]) if re.fullmatch(r"20\d\d", toks[i - 1]) else None
        if y is None or (expect is not None and y != expect):
            break
        pairs.append((toks[i - 1], v))
        expect, i = y - 1, i - 2
    pairs.reverse()
    return pairs if len(pairs) >= 2 and int(pairs[0][0]) == int(fiscal_year) + 1 else None


def _year_rows_read(schema: dict, texts: list[str], fiscal_year, bucket_pick: dict, total, basis: str) -> dict | None:
    """(v109) The row-shaped source: a maturity table printing one figure per calendar year, torn by
    pymupdf into a single "<year> <figure>"-pairs row (the visual shape is one row per year; the text
    layer inlines it -- every clean row-shaped year table in the corpus arrives this way). Scanned on
    the pages the column reader itself walked (the pick's recorded scan_pages, statement spread
    first). Valves, all structural: the pairs must chain from fiscal_year+1 (_inline_year_pairs);
    below them at most one open-end tail row ("Thereafter 260", "2031 and later 169" -- _YEAR_TAIL on
    its own label, one figure); then the table's own bare Total row, printing exactly one figure --
    BTS p.92's stacked two-column "Total 579,797 420,953" above the years declines here, it is the
    liabilities table's row. The years (tail included) must close on that printed total AND on the
    extraction's total_debt, both within the check's own ±2 -- Ericsson p.97's lease years close on
    their own printed 1,838 and are refused on total_debt 32,703, which is the gate doing its work.
    v103's wrong-table guard runs on the total row; declines are silent (a metadata key, not a fill).

    Deliberately not read: the untorn one-row-per-year form (nothing in the corpus exercises it --
    BTS p.93's own NOTE 21 is the shape, and it declines anyway: non-current only, first year 2027
    = fiscal_year+2, total 548,320 = a narrower scope than total_debt), and date/interval notes
    (v073/v096 territory)."""
    scope_words = schema.get("table_scope_words")
    for page in bucket_pick.get("scan_pages") or []:
        rows = _page_rows(texts[page - 1])
        for i, row in enumerate(rows):
            pairs = _inline_year_pairs(row, fiscal_year)
            if not pairs:
                continue
            items = [(label, v, row) for label, v in pairs]
            j = i + 1
            if j < len(rows):  # one optional open-end tail year below the printed years
                label = _row_label(rows[j])
                if label and _YEAR_TAIL.search(label):
                    tail = _after_label_figure(rows[j], label)
                    if tail is None:
                        continue  # a tail year whose figure cannot be read one-column: no closure, no key
                    items.append((label, tail, rows[j]))
                    j += 1
            if j >= len(rows):
                continue
            trow, tlabel = rows[j], _row_label(rows[j])
            printed = _after_label_figure(trow, tlabel) if tlabel else None
            if not tlabel or not _BARE_TOTAL.search(tlabel) or printed is None:
                continue  # the table prints no clean one-figure total row of its own: nothing proves the years are its whole story
            if scope_words and _table_scope(rows, None, j, basis, scope_words,
                                            debt_words=_debt_subject_words(schema)) in _REFUSED_SCOPES:
                continue  # v103's wrong-table refusal, silently -- a metadata key, not a fill. v157: the whole
                # refusal list, not the two v103 knew: essity_2025 p.151's non_debt ladder passes the pair form
            vals = [v for _, v, _ in items]
            if total > 0 and any(v < 0 for v in vals) and all(v <= 0 for v in vals):
                vals = [-v for v in vals]  # v101's liabilities-negative display convention, the row shape's own form
            if abs(round(sum(vals), 2) - printed) > 2 or abs(round(sum(vals), 2) - total) > 2:
                continue  # the years must close on the table's own printed total and on total_debt, the identity's own gate
            return {"basis": basis,
                    "years": [{"label": lab, "value": vals[k], "source": {"page": page, "quote": q}}
                              for k, (lab, _, q) in enumerate(items)]}
    return None


def _year_ladder(text: str, fiscal_year, schema: dict) -> tuple[list[tuple[str, float, str]], float, str] | None:
    """The page's own calendar-year debt maturity ladder: ([(label, value, row)], its printed total,
    that total's row), or None. _year_rows_read's valve chain without the one gate that needs a
    total_debt -- pairs chaining from fiscal_year+1, at most one open-end tail row, a mandatory
    bare-Total row printing exactly one figure that the years close on, and a table scope that is not
    refused. The loose version of this test (">=3 years plus any total token") fires on 94 pages in 52
    reports because _BARE_TOTAL matches "total|totalt|summa" on nearly any table; the full chain fires
    on 2 pages in the whole corpus (ABB p.89, BTS p.92), which is what makes it safe to score and read
    from. ponytail: no negatives -- both corpus ladders print positives, and v101's liabilities-negative
    convention is _normalize_sign's job, downstream of the only caller that fills. A printed dash year
    is 0 and rides along (v078)."""
    if not fiscal_year:
        return None
    scope_words, debt_words = schema.get("table_scope_words"), _debt_subject_words(schema)
    rows = _page_rows(text)
    for i, row in enumerate(rows):
        pairs = _inline_year_pairs(row, fiscal_year)
        if not pairs:
            continue
        items = [(label, v, row) for label, v in pairs]
        j = i + 1
        if j < len(rows) and (label := _row_label(rows[j])) and _YEAR_TAIL.search(label):
            tail = _after_label_figure(rows[j], label)
            if tail is None:
                continue
            items.append((label, tail, rows[j]))
            j += 1
        if j >= len(rows):
            continue
        tlabel = _row_label(rows[j])
        printed = _after_label_figure(rows[j], tlabel) if tlabel else None
        if not tlabel or not _BARE_TOTAL.search(tlabel) or printed is None:
            continue
        if any(v < 0 for _, v, _ in items) or abs(round(sum(v for _, v, _ in items), 2) - printed) > 2:
            continue  # the years must be the whole of the table's own printed total, the identity's own tolerance
        if scope_words and _table_scope(rows, None, j, "carrying", scope_words, debt_words=debt_words) in _REFUSED_SCOPES:
            continue  # ABB's own p.88 intangible-amortization ladder is this shape and must not score
        return items, printed, rows[j]
    return None


def year_row_table(text: str, fiscal_year, schema: dict) -> bool:
    """Does this page print a calendar-year debt ladder? locate.scored_pages' shape evidence: such a
    ladder names its buckets with bare years, so the page matches no bucket synonym ("within 1 year",
    "1-5 years") and scores no shape at all without this -- ABB's p.89 lost to the instrument table on
    p.90 for exactly that reason."""
    return _year_ladder(text, fiscal_year, schema) is not None


_LADDER_SUBSET_GAP = 0.10  # the ladder may restate the total (ABB: principal 8,247 vs carrying 7,905, 4.3%)


def _year_ladder_fill(fields: list[dict], sfs: list[dict], schema: dict, texts: list[str], pages: list[int],
                      fiscal_year, bucket_pick: dict, warnings: list[str], values: dict, filled: set) -> None:
    """The calendar-year ladder as ANSWERS. _buckets_by_year_fill reads the same table but writes only
    `buckets_by_year` metadata -- its docstring says so outright -- so a US-GAAP issuer whose note is a
    bare year ladder (ABB p.89: "2026 442 ... Thereafter 4,013 / Total 8,247") left nulls no matter how
    well the shape parsed. Fills only buckets the model left null, and only when:
      - the years close on the table's OWN printed total (_year_ladder's hard gate), and
      - that total is not smaller than total_debt and within 10% of it.
    Both gates together are what refuse Ericsson p.97, whose operating-lease ladder closes on its own
    printed 1,838 against a total_debt of 32,703: a lease subset is strictly smaller and nowhere near.
    No scope word can do that job -- _table_scope reads "unknown" on it either way and "lease
    liabilities" is one of total_debt's own row synonyms.

    The summed bucket quotes the whole glued ladder row, which carries alphabetic tokens and so passes
    quote_on_page where a bare "2026 442" cannot, and is tagged value_derived -- _window_rows_derive's
    convention. A ladder with no tail row leaves due_after_5_years null, never 0."""
    ident = _identity_parts(schema)
    if not ident or set(ident[1]) != _DATE_BUCKET_KEYS:
        return
    by_key = {sf["key"]: f for sf, f in zip(sfs, fields)}
    if all(by_key[k].get("value") is not None for k in ident[1]):
        return  # nothing to fill
    total = values.get(ident[0])
    if not isinstance(total, (int, float)) or isinstance(total, bool) or total <= 0:
        return
    for page in bucket_pick.get("scan_pages") or pages[:2]:
        if not 0 < page <= len(texts):
            continue
        got = _year_ladder(texts[page - 1], fiscal_year, schema)
        if not got:
            continue
        items, printed, trow = got
        if printed < total or abs(printed - total) > _LADDER_SUBSET_GAP * total:
            continue  # a subset ladder (Ericsson's leases) or a different table entirely
        buckets: dict[str, list[tuple[float, str]]] = {k: [] for k in ident[1]}
        for label, v, row in items:
            year = int(label) if re.fullmatch(r"20\d\d", label) else None
            key = ("due_within_1_year" if year == int(fiscal_year) + 1
                   else "due_1_to_5_years" if year and year <= int(fiscal_year) + 5
                   else "due_after_5_years")
            buckets[key].append((v, row))
        # The model usually reads PART of a ladder: ABB's own re-run answered 442 and 4,013 and left the
        # middle null, because "2027 1,143 2028 591 2029 837 2030 1,221" is four printed rows and one
        # bucket. Complete it -- but only where the model's own answers agree with the same ladder row
        # for row. A disagreement anywhere means the two of us are reading different tables, and mixing
        # them is how a plausible wrong number gets made: leave the whole page alone and let it flag.
        sf_of = {sf["key"]: sf for sf in sfs}
        if any((mine := by_key[k].get("value")) is not None
               and (not buckets[k] or abs(round(sum(x for x, _ in buckets[k]), 2) - mine) > 2) for k in ident[1]):
            return
        wrote = []
        for key, got_rows in buckets.items():
            if not got_rows:
                continue  # no tail row: due_after_5_years stays null, never a fabricated 0
            mine, v = by_key[key].get("value"), round(sum(x for x, _ in got_rows), 2)
            # An agreed answer keeps its value and takes the ladder's citation, because the model cites a
            # year row the way the report prints it: "2026" is a label no schema can name and "2026 442"
            # is a quote with no word in it, so ABB's own correct 442 arrived with neither label_known nor
            # quote_on_page and asked for a human anyway. Only where the model's own label is unnameable:
            # a row it could name is its own evidence and is left alone.
            if mine is not None and _label_known(by_key[key].get("raw_label"), sf_of[key]):
                continue
            wrote.append(key if mine is None else f"{key} (re-cited)")
            quote = got_rows[0][1]
            by_key[key].update(value=v, period=str(fiscal_year), raw_label=key.replace("_", " "),
                               source={"page": page, "quote": quote},
                               evidence=["quote_on_page"] if _value_in_quote(v, quote) else ["quote_on_page", "value_derived"])
            values[key] = v
            filled.add(key)
        if not wrote:
            return  # every bucket the ladder prints was already answered: nothing read, nothing to re-cite
        warnings.append(f"{', '.join(wrote)} read from the calendar-year ladder on page {page}, closing on "
                        f"its own printed total {printed:g}")
        # The ladder restates the total on its own basis (ABB: principal 8,247 on p.89 against the p.90
        # instrument table's carrying 7,905) and the model cited the other one. Left alone, three honest
        # nulls become three right numbers plus a FAILING identity -- strictly more review, not less. Move
        # total_debt to the row the buckets actually sum to, but only when the model's own citation is a
        # bare "Total" whose label the schema cannot name (_label_known): a row the model COULD name
        # ("Total interest-bearing liabilities") is a deliberate choice and outranks this one. Tested on
        # the evidence list instead, this gate reads as always-true -- label_known lands downstream.
        tf = by_key.get(ident[0])
        total_sf = next((sf for sf in sfs if sf["key"] == ident[0]), None)
        cited = _row_label(((tf or {}).get("source") or {}).get("quote") or "")
        if tf and abs(printed - total) > 2 and not (total_sf and _label_known(cited, total_sf)):
            warnings.append(f"{ident[0]}: {total:g} re-cited to the maturity table's own total {printed:g} on "
                            f"page {page} -- the buckets sum to it, and {total:g} was read off a bare Total row")
            tf.update(value=printed, period=str(fiscal_year), raw_label=_row_label(trow),
                      source={"page": page, "quote": trow}, evidence=["quote_on_page"])
            values[ident[0]] = printed
            filled.add(ident[0])
        return


def _buckets_by_year_fill(schema: dict, texts: list[str], fiscal_year, bucket_pick: dict, values: dict,
                          basis: str = "carrying") -> dict | None:
    """(v109) The report's own calendar-year maturity columns as top-level `buckets_by_year` metadata --
    Kristian's "every year its own bucket" question, answered with the report's own granularity whenever
    the report itself prints it, never derived. Two sources, column shape first: (a) the year columns
    the bucket-column reader already aligned (_fill_bucket_columns' recorded pick, whose header was
    _bucket_year_hits' calendar-year fallback -- a named-bucket or carrying-column header records no
    year labels), re-read on the pick's own row; (b) the row-shaped fallback (_year_rows_read) when no
    column pick was recorded. One entry per printed year, label as printed ("2026" ... the tail word
    "Later"/"Thereafter"/"2031 and later", or an open-end year "2031+"/">2031" per _year_span), value
    from that year, a dash the report's explicit 0 (v078's convention, one window finer). Same basis
    the current year's own fields were read on (debt_basis()), exactly the way v091's prior year rides.

    The gate is the schema's own identity against the extraction's total_debt: the years must sum to
    the field's own value within the check's own ±2, the tolerance maturity_sums_to_total already
    answers to (the row source must close on the table's own printed total too); anything less returns
    None and the extraction carries no buckets_by_year key at all, not a null one. The three bucket
    fields themselves are untouched -- their summation of these same years is v036/v095's, unchanged."""
    if not fiscal_year:
        return None
    ident = _identity_parts(schema)
    if not ident or set(ident[1]) != _DATE_BUCKET_KEYS:
        return None
    total = values.get(ident[0])
    if not isinstance(total, (int, float)) or isinstance(total, bool):
        return None
    if bucket_pick.get("year_labels"):
        if (cols := _year_cols_read(texts, fiscal_year, bucket_pick, total, basis)) is not None:
            return cols
    return _year_rows_read(schema, texts, fiscal_year, bucket_pick, total, basis)


def extract(texts: list[str], pages: list[int], schema: dict, report_meta: dict,
            page_select_hints: bool | None = None, fixed_pages: bool = False) -> dict:
    extraction_started = time.perf_counter()
    model_seconds, attempts = 0.0, 0
    fiscal_year = report_meta.get("fiscal_year")
    basis = debt_basis()  # v089: which maturity table total_debt and the buckets are read from
    system, warnings, raw = system_prompt(schema, report_meta.get("stem")), [], []
    nonnull = lambda fs: sum(isinstance(f, dict) and f.get("value") is not None for f in fs)
    # An analyst-directed fill supplies its complete evidence window. It must not be replaced by
    # locator ranking, pass-one selection or a timeout fallback to a different window.
    windows = [tuple(pages if fixed_pages else pages[:2])]  # the ordinary statement spread starts quick (four pages timed out on NOBA / Nordnet)
    two_pass_pages = None  # pass 1's own pick, if EXTRACT_TWO_PASS is on and it succeeded -- also stands in for
    if not fixed_pages and os.getenv("EXTRACT_TWO_PASS") == "1" and len(pages) >= 2:  # pages[:2] below wherever that means "the statement", not "cast a wider net"
        selected = _select_pages(schema, pages, texts, page_select_hints)
        if selected:
            warnings.append(f"two_pass: page {selected} selected from candidates {pages}")
            windows = [tuple(selected)]
            two_pass_pages = selected
            if schema.get("name") == "debt_maturity":
                # Repairs must start from the note the model selected too.
                # Otherwise a rejected liquidity/lease table at pages[:2]
                # can silently fill gaps in a different borrowing scope.
                pages = list(dict.fromkeys([*selected, *pages]))
        else:
            warnings.append(f"two_pass: page selection failed or illegal for candidates {pages}; fell back to the single-pass window")
    while windows:
        attempt = windows.pop()
        user = (f"Fiscal year to extract: {fiscal_year}\n\n" if fiscal_year else "") + \
            "\n\n".join(f"=== PAGE {n} ===\n{texts[n - 1]}" for n in attempt)
        call_started = time.perf_counter()
        attempts += 1
        try:
            got = call_llm(system, user).get("fields", [])
        except Exception as e:  # ponytail: teammates feed the error back to the model
            model_seconds += time.perf_counter() - call_started
            warnings.append(f"llm: {type(e).__name__}: {e} (pages {list(attempt)})")
            if not fixed_pages and "timeout" in type(e).__name__.lower() and len(attempt) > 1 and pages:
                windows = [tuple(pages[:1])]  # IPC: pages 10-11 never answer, page 10 alone does in a minute; a hung single page ends it
            continue
        model_seconds += time.perf_counter() - call_started
        if nonnull(got) > nonnull(raw):
            raw = got
        # v157: and for debt, widen when the identity comes back with two or more holes in it. Two
        # answered fields of four passes the test above, and it is exactly the shape of a confidently
        # read wrong table: BTS p.93's NOTE 21 is non-current borrowings only, so the model answered a
        # total and one bucket off it, closed nothing, and never saw the real maturity note two pages
        # earlier (p.92, rank 3 -- outside the first window, inside the widened one). ONE hole is the
        # ordinary case of a report that prints no >5-year row, and widening on it would buy a second
        # model call for most debt extractions and find nothing.
        holes = 0
        if schema.get("name") == "debt_maturity" and (ident := _identity_parts(schema)):
            got_by_key = {g.get("key"): g for g in raw if isinstance(g, dict)}
            holes = sum(got_by_key.get(k, {}).get("value") is None for k in (ident[0], *ident[1]))
        if (2 * nonnull(raw) < len(schema["fields"]) or holes >= 2) and len(attempt) == 2 and len(pages) > 2:
            windows = [tuple(pages[:4])]  # the first window did not settle it: widen once
    by_key = {f.get("key"): f for f in raw if isinstance(f, dict)}
    by_key = _quote_retry(by_key, system, schema, texts, pages, fiscal_year, warnings)
    scope_words = schema.get("table_scope_words")  # v103/v111: the wrong-table guard's marker vocabulary
    debt_voc = _debt_subject_words(schema) if scope_words else None  # v111: the non-debt rule's rescue list
    total_voc = {"synonyms": []}  # the total field's own row vocabulary, for the guard's debt_scoped calls
    if scope_words and (ident_sf := _identity_parts(schema)):
        tsf = next((sf for sf in schema["fields"] if sf["key"] == ident_sf[0]), None)
        total_voc = {"synonyms": (tsf or {}).get("synonyms", []) + (tsf or {}).get("row_synonyms", [])}

    fields, filled, sfs, stated_zeros, gated_fills, missing_events = [], set(), [], set(), set(), []
    for sf in schema["fields"]:
        if sf.get("fallback_synonyms") and pages and not any(_label_known(_row_label(r), sf) for r in _page_rows(texts[pages[0] - 1])):
            # a bank prints no "profit before tax" row: its "Operating profit" is the line before tax (NOBA); its top line is "Total operating income"
            sf = {**sf, "synonyms": sf["synonyms"] + sf["fallback_synonyms"]}
        sfs.append(sf)
        f = by_key.get(sf["key"]) or {}
        field = {
            "key": sf["key"], "label": sf["label"], "value": _num(f.get("value")),
            "unit": f.get("unit"), "period": _SPLIT_YEAR.sub(lambda m: m.group(1), str(f.get("period"))) if f.get("period") else f.get("period"), "raw_label": f.get("raw_label"),
            "source": f.get("source") or None, "confidence": 0.0, "evidence": [],  # the model's own confidence is ignored, see docs/CONFIDENCE.md
        }
        if field["value"] is None and not field["source"] and pages and fiscal_year:
            # Telia: the model answered null although "Income after financial items 7,300 6,234" is printed on the statement
            # page under a synonym label. Fill it from the page; everything below then verifies it like a model answer.
            first = texts[pages[0] - 1]
            h = _year_column(first, fiscal_year)  # page-level, not row-anchored: the statement spread's first header is the statement's own, and no quote exists yet to anchor to
            if h and (hit := _statement_row(frows := _page_rows(first), sf, h[1])):  # SEB "Basic earnings per share, SEK"
                hi = frows.index(hit)
                gscope = _table_scope(frows, None, hi, basis, scope_words,
                                      debt_scoped=_label_known(_row_label(hit), total_voc),
                                      debt_words=debt_voc) if scope_words else "unknown"
                if gscope in _REFUSED_SCOPES:
                    # v111: the wrong-table guard on this fill's own read too -- a bucket-shaped row of a
                    # non-debt table or a Parent Company section is not the statement row this mechanism wants
                    warnings.append(f"{sf['key']}: model returned null, fill from page {pages[0]} row {hit!r} refused -- "
                                    f"{_scope_reason(frows, None, hi, scope_words, gscope)}")
                    gated_fills.add(sf["key"])  # the statement-spread fill below stays silent for the same row
                else:
                    am = _row_amounts(hit, h[1])
                    warnings.append(f"{sf['key']}: model returned null, filled from page {pages[0]} row {hit!r}")
                    field.update(value=am[h[0]], period=str(fiscal_year), raw_label=_row_label(hit), source={"page": pages[0], "quote": hit})
                    filled.add(sf["key"])
        src = field["source"]
        if field["value"] is not None and not src:  # contract: no source, no value
            warnings.append(f"{sf['key']}: value without source dropped")
            field["value"] = None
        elif src:
            page, quote = src.get("page"), src.get("quote") or ""
            if not (isinstance(page, int) and 1 <= page <= len(texts)):
                warnings.append(f"{sf['key']}: source page {page} out of range")
                fields.append(field)
                continue
            rows = _page_rows(texts[page - 1])
            verified = quote_on_page(quote, texts[page - 1])
            if not verified:
                # Getinge: the model wrote "Profit before tax 3,145" for the row "Profit after financial items 3,145"; Sandvik
                # cited the tax note for a figure printed on the statement page. The number under a known synonym label on the
                # cited page or the statement spread is still provenance; the printed label and page win.
                for p in [page] + [q for q in pages[:2] if q != page]:
                    hit = next((r for r in _page_rows(texts[p - 1]) if _label_known(_row_label(r), sf) and _value_in_quote(field["value"], r)), None)
                    if hit:
                        warnings.append(f"{sf['key']}: quote replaced by page {p} row {hit!r}")
                        verified, field["raw_label"], page, src["page"], rows = hit, _row_label(hit), p, p, _page_rows(texts[p - 1])
                        break
            if not verified:
                nil_row = _model_zero_on_dash_row(field, sf, texts, pages, fiscal_year) \
                    if field["value"] == 0 and not isinstance(field["value"], bool) else None
                if nil_row:  # v134: the dash row the model read is the report's own printed nil -- before the printed-0
                    nil_page, nil_quote = nil_row  # fallback below, since a 0 printed elsewhere (Rejlers' "0.8 per cent") proves nothing about this row
                    warnings.append(f"{sf['key']}: 0 kept -- {nil_quote!r} prints a dash in the fiscal-year column under a known label (printed nil)")
                    field.update(raw_label=_row_label(nil_quote), period=str(fiscal_year) if fiscal_year else field.get("period"),
                                 source={"page": nil_page, "quote": nil_quote})
                    field["evidence"] += ["quote_on_page", "printed_nil"]
                    stated_zeros.add(sf["key"])  # the same standing as a stated zero: a 0 no printed digit proves, the page's own nil marker does
                    fields.append(field)
                    continue
                nearby = sorted({page, *pages[:2]})
                if not any(_value_in_quote(field["value"], texts[p - 1]) for p in nearby if 0 < p <= len(texts)):
                    if not _stated_zero(field, sf, schema, texts):
                        # Sectra: "Net sales" minus "Goods for resale" offered as gross profit with a quote that is not on the page. A number
                        # printed nowhere on the cited page or the statement spread was computed or invented, and the rules say null then.
                        warnings.append(f"{sf['key']}: {field['value']} is printed on none of pages {nearby}; dropped as computed, not read")
                        field.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
                        fields.append(field)
                        continue
                    # Creades (v048): "Investmentföretaget har varken räntebärande skulder eller kundfordringar" -- a prose
                    # no-debt statement never contains the digit _value_in_quote needs; the sentence itself is the provenance.
                    warnings.append(f"{sf['key']}: 0 is printed on none of pages {nearby}; kept on the report's own words, page {page}: {src.get('quote')!r}")
                    field["evidence"] += ["quote_on_page", "stated_zero"]
                    stated_zeros.add(sf["key"])
                warnings.append(f"{sf['key']}: quote not found on page {page}")
            else:
                field["evidence"].append("quote_on_page")
                src["quote"] = verified  # the row that is actually on the page (model may prepend a section header)
                fixed = repair_value(field["value"], verified)
                if fixed is not None:
                    warnings.append(f"{sf['key']}: value {field['value']} rescaled to {fixed} as printed in the quote")
                    field["value"] = fixed
                header = _year_column(texts[page - 1], fiscal_year) if fiscal_year else None  # page-level, not row-anchored: this verifies the model's own read of the page's main statement, it does not derive across tables (left to _derived_value/_between_rows/_column_values)
                ncols = header and header[1]
                row = src["quote"] = next((r for r in rows if quote_on_page(verified, r)), verified)  # the full printed row, all columns
                amounts = _row_amounts(row, ncols)
                if header and len(amounts) == ncols and field["value"] in amounts and amounts[header[0]] != field["value"]:
                    warnings.append(f"{sf['key']}: {field['value']} is not the {fiscal_year} column, {amounts[header[0]]} is")  # Sandvik prints 2024 first
                    field["value"], field["period"] = amounts[header[0]], str(fiscal_year)
                elif header and len(amounts) == ncols and amounts[header[0]] == field["value"] and str(field.get("period")) != str(fiscal_year):
                    warnings.append(f"{sf['key']}: {field['value']} sits in the {fiscal_year} column, which the model dated {field.get('period')}; period set to {fiscal_year}")  # Asmodee: "Apr 25-Mar 26" stamped 2026
                    field["period"] = str(fiscal_year)
                if header and len(amounts) == ncols and abs(field["value"]) not in {abs(a) for a in amounts} and _label_known(_row_label(row), sf)                         and not _value_in_quote(field["value"], row) \
                        and not any(abs(field["value"] * k - amounts[header[0]]) <= abs(amounts[header[0]]) * 1e-3 + 1 for k in (1e3, 1e6, 1e-3, 1e-6)):
                    # Pandox: "Bruttoresultat 4 222 3 855" returned as 3622. The row is the field's own (known label) and holds one figure per
                    # year column, so the printed figure wins over the model's misreading; a value off by a factor of 1000 is a unit mix-up, left alone.
                    # Not when the value is printed in the row (Beijer Alma "Rörelseresultat 9 952 1 091": note 9 and 952, which the column parser reads as 9952).
                    # Atrium Ljungberg: 3446 quoted as "Net sales, project and construction work 488 528" is the next row, "Net sales IE.3 3,446 3,516",
                    # whose label is exactly a synonym: that row is the quote
                    syn = {x.lower() for x in sf.get("synonyms", [])}
                    exact = next((r for r in rows if r != row and len(_row_amounts(r, ncols)) == ncols and _clean_label(_row_label(r)) in syn
                                  and _row_amounts(r, ncols)[header[0]] == field["value"]), None)
                    if exact:
                        warnings.append(f"{sf['key']}: {field['value']} is not printed in {_row_label(row)!r}; it is the {fiscal_year} figure of {_row_label(exact)!r}")
                        row = src["quote"] = exact
                        amounts, field["raw_label"], field["period"] = _row_amounts(exact, ncols), _row_label(exact), str(fiscal_year)
                    else:
                        warnings.append(f"{sf['key']}: {field['value']} is not printed in {_row_label(row)!r}; the row's {fiscal_year} figure is {amounts[header[0]]}")
                        field["value"], field["period"] = amounts[header[0]], str(fiscal_year)
                if field["value"] == 0 and header and len(amounts) == ncols and 0 not in amounts:
                    # Wihlborgs without chain-of-thought: 0 for operating_profit, quoting "Operating surplus 3,107 2,996". A real zero is
                    # printed ("Other income 0 3"); an unprinted one is the model's stand-in for null (a known row took its figure above)
                    warnings.append(f"{sf['key']}: 0 is not printed in {_row_label(row)!r}; dropped, a zero the model made up stands for null")
                    field.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
                    fields.append(field)
                    continue
                if field["value"] in amounts and not _label_known(field.get("raw_label"), sf) and _label_known(_row_label(row), sf):
                    warnings.append(f"{sf['key']}: labelled {field.get('raw_label')!r} by the model; the row is printed as {_row_label(row)!r}")  # Castellum: "Income" for "Rental and service income"
                    field["raw_label"] = _row_label(row)
                titled = set(re.findall(r"\b20\d\d\b", texts[page - 1][:200])) if not header and fiscal_year else set()
                if len(titled) == 1 and str(fiscal_year) not in titled and str(field.get("period")) == str(fiscal_year):
                    y = titled.pop()  # Pandox: "Not C1, forts. KONCERNEN 2024" — a segment note for the prior year, no year header, stamped 2025 by the model
                    warnings.append(f"{sf['key']}: page {page} is headed {y}, not {fiscal_year}; period set to {y}")
                    field["period"] = y
                if header and _clean_label(field.get("raw_label")) != _clean_label(_row_label(row)) and _label_known(field.get("raw_label"), sf) \
                        and _clean_label(_row_label(row)) not in {x.lower() for x in sf.get("synonyms", [])}:  # Atrium: the quoted row *is* "Net sales"; the model's label named the sub-row above it
                    # Lundbergs: the model paired "Rörelseresultat 16 077" with the row below it; the row printed with that label is the quote,
                    # and its figure the value ("Nettoomsättning m m" prints 28 781, not the 30 615 subtotal on the next row)
                    own = next((r for r in rows if _clean_label(_row_label(r)) == _clean_label(field["raw_label"]) and len(_row_amounts(r, ncols)) == ncols), None)
                    if not own and any(_clean_label(_row_label(row)) in {x.lower() for x in gs.get("synonyms", [])} for gs in schema["fields"] if gs["key"] != sf["key"]):
                        # Nordea: "Operating profit: Net profit for the year" 4840, quoting the net profit row -- another field's own row; the row
                        # printed with the label's known part, "Operating profit 6,316 6,548", is the bank's profit before tax
                        rl = _clean_label(field["raw_label"])
                        syn = max((x.lower() for x in sf.get("synonyms", []) if rl.startswith(x.lower())), key=len, default=None)
                        own = next((r for r in rows if _clean_label(_row_label(r)) == syn and len(_row_amounts(r, ncols)) == ncols), None) if syn else None
                    if own and own != row:
                        am = _row_amounts(own, ncols)
                        warnings.append(f"{sf['key']}: quoted {_row_label(row)!r}; the {field['raw_label']!r} row prints {am[header[0]]}"
                                        + ("" if am[header[0]] == field["value"] else f", not {field['value']}"))
                        row = src["quote"] = own
                        amounts, field["value"], field["period"] = am, am[header[0]], str(fiscal_year)
                if header and any(re.search(p, _clean_label(_row_label(row))) for p in sf.get("exclude_labels", [])):
                    # Securitas: "...before and after dilution and before items affecting comparability 11.55" is the adjusted
                    # EPS; Saab: "efter utspädning" is diluted. The statement row with a known, unexcluded label wins.
                    alt = _statement_row(rows, sf, ncols)
                    if alt:
                        amounts = _row_amounts(alt, ncols)
                        warnings.append(f"{sf['key']}: {_row_label(row)!r} {field['value']} is a variant row; {_row_label(alt)!r} {amounts[header[0]]} is the statement row")
                        row = src["quote"] = alt
                        field["value"], field["raw_label"], field["period"] = amounts[header[0]], _row_label(alt), str(fiscal_year)
                    else:  # Catena (property company): "Net operating surplus" offered as operating profit, which the statement does not present
                        warnings.append(f"{sf['key']}: {_row_label(row)!r} {field['value']} dropped: an excluded label, and the statement has no {sf['label'].lower()} row")
                        field.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
                        fields.append(field)
                        continue
                if sf["key"] == "total_debt" and _GENERIC_TOTAL_ROW.match(_row_label(row)) \
                        and not _label_known(field.get("raw_label"), sf):
                    # AcadeMedia's page has two generic SUMMA rows: a currency split and
                    # the closing total of a debt roll-forward. Prefer the latter only
                    # when _financial_liabilities_rollforward_total proves its narrow
                    # heading/component/closure shape; generic totals otherwise remain
                    # model-owned rather than guessed at.
                    rollforward = _financial_liabilities_rollforward_total(rows, fiscal_year)
                    if rollforward and rollforward[0] != field["value"]:
                        value, roll_row, roll_label = rollforward
                        warnings.append(f"{sf['key']}: generic total {field['value']} replaced by financial-liabilities "
                                        f"roll-forward closing total {value}")
                        field["value"], field["raw_label"], field["period"] = value, roll_label, str(fiscal_year)
                        row = src["quote"] = roll_row
                        amounts = _row_amounts(row, ncols)
                label, i = _row_label(row), rows.index(row) if row in rows else -1
                if not _label_known(field.get("raw_label"), sf) and i >= 0:
                    # ABB: "Basic earnings per share" is a heading, the figure sits on the sub-row "Net income 2.59 2.13"
                    heading = next((h for h in rows[max(i - 4, 0):i][::-1] if _label_known(_row_label(h), sf)), None)
                    if heading and header and len(am := _row_amounts(heading, ncols)) == ncols:
                        # SEB: "Operating profit 38,898" two rows above the quoted "NET PROFIT 31,063" is no heading but the bank's profit
                        # before tax row itself; a row printed with the field's label and every column is the field, whatever sits under it
                        warnings.append(f"{sf['key']}: quoted {label!r} {field['value']}; the {_row_label(heading)!r} row above it prints {am[header[0]]}")
                        row = src["quote"] = heading
                        amounts, field["value"], field["raw_label"], field["period"] = am, am[header[0]], _row_label(heading), str(fiscal_year)
                    elif heading:
                        field["raw_label"] = f"{_row_label(heading)}: {label}"
                # Securitas: "Sales 155 054" is summed with "Sales, acquired business" into "Total sales 155 113"
                total = next((r for r in rows if re.match(rf"(?i)total\s+{re.escape(label)}\b", _row_label(r)) and _label_known(_row_label(r), sf)), None)
                if header and total and len(tot := _row_amounts(total, ncols)) == ncols:
                    warnings.append(f"{sf['key']}: {label!r} {field['value']} replaced by {_row_label(total)!r} {tot[header[0]]}")
                    field["value"], field["raw_label"], src["quote"] = tot[header[0]], _row_label(total), total
                # SCA: "Revenue 23,447" = "Net sales 20,427" + "Other operating income 3,020" is a subtotal, not revenue
                if header and i >= 2 and sf.get("excludes") and len(amounts) == ncols:
                    parts = [(r, _row_amounts(r, ncols)) for r in rows[i - 2:i]]
                    if all(len(a) == ncols for _, a in parts) and all(abs(sum(a[c] for _, a in parts) - amounts[c]) <= 2 for c in range(ncols)):
                        for (part, pa), (other, _) in (parts, parts[::-1]):
                            if _label_known(_row_label(part), sf) and any(e in _row_label(other).lower() for e in sf["excludes"]):
                                warnings.append(f"{sf['key']}: {label!r} {field['value']} is a subtotal including {_row_label(other)!r}; {_row_label(part)!r} {pa[header[0]]} is the row")
                                field["value"], field["raw_label"], src["quote"] = pa[header[0]], _row_label(part), part
                                break
        fields.append(field)

    segs = {}
    seg_defaults = {sf["key"]: sf["default"] for sf in schema["fields"] if "default" in sf}
    for page in sorted({f["source"]["page"] for f in fields if f["source"] and "quote_on_page" in f["evidence"]}):
        on_page = [f for f in fields if f["value"] is not None and f["source"] and f["source"].get("page") == page]
        seg = _segment_column(texts[page - 1], fiscal_year, on_page) if fiscal_year else None
        if not seg:
            continue
        col, ncols = segs[page] = seg
        snapshot = {g["key"]: g["value"] for g in fields if isinstance(g["value"], (int, float)) and not isinstance(g["value"], bool)}
        for f in on_page:  # Volvo: income tax read from the Industrial Operations pair, the other rows from Volvo Group
            am = _row_amounts(f["source"]["quote"], ncols)
            if len(am) == ncols and am[col] != f["value"]:
                if _identity_closes(f["key"], f["value"], snapshot, seg_defaults, schema):
                    # value_derived (not just a marker): the later "printed on none of pages, dropped as
                    # computed" guard (Sectra) drops any non-null value that is not literally printed nearby
                    # unless it is already explained -- an identity-proven value needs the same standing a
                    # row-sum derivation gets, or keeping it here would be undone a few steps later (v066).
                    f["evidence"] += ["identity_kept", "value_derived"]
                    warnings.append(f"{f['key']}: {f['value']} kept: closes the identity exactly, even though column {col + 1} of {ncols} prints {am[col]}")
                    continue
                warnings.append(f"{f['key']}: {f['value']} is another segment's column; the page's rows are read from column {col + 1} of {ncols}, which prints {am[col]}")
                f["value"], f["period"] = am[col], str(fiscal_year)
    if pages and fiscal_year and (h := _year_column(texts[pages[0] - 1], fiscal_year) or segs.get(pages[0])):  # page-level, not row-anchored: statement-spread fill, no quote to anchor to
        first = _page_rows(texts[pages[0] - 1])
        for sf, f in zip(sfs, fields):  # Volvo: profit before tax answered as "Income for the period * 34,707 50,576", a row the page does not print;
            if "quote_on_page" in f["evidence"] or not (hit := _statement_row(first, sf, h[1])):  # the statement's own "Income after financial items" row is the answer
                continue
            hi = first.index(hit)
            gscope = _table_scope(first, None, hi, basis, scope_words,
                                  debt_scoped=_label_known(_row_label(hit), total_voc),
                                  debt_words=debt_voc) if scope_words else "unknown"
            if gscope in _REFUSED_SCOPES:
                # v111: the wrong-table guard on this fill's own read too -- the mechanism that filled
                # Volati's w1y with the contract-liabilities timing row over the model's own 192, and
                # Momentum's buckets out of the parent's lease table (both pages[0], both label-exact)
                if f["value"] is not None or sf["key"] not in gated_fills:
                    warnings.append(f"{sf['key']}: fill from page {pages[0]} row {hit!r} refused -- "
                                    f"{_scope_reason(first, None, hi, scope_words, gscope)}")
                continue
            am = _row_amounts(hit, h[1])
            reason = "model returned null" if f["value"] is None else f"{f['value']} is not printed on the statement"
            warnings.append(f"{sf['key']}: {reason}; filled from page {pages[0]} row {hit!r}")
            f.update(value=am[h[0]], period=str(fiscal_year), raw_label=_row_label(hit), source={"page": pages[0], "quote": hit}, evidence=["quote_on_page"])
            filled.add(sf["key"])

    by_key = {f["key"]: f for f in fields}
    for sf, f in zip(sfs, fields):  # Lundbergs: "Rörelseresultat 16 077" offered as gross profit and as operating profit; the row belongs to the key whose label it is
        if f["value"] is None or _label_known(f.get("raw_label"), sf):
            continue
        twin = next((g for g, gs in zip(fields, sfs) if g is not f and g["value"] is not None and g["source"] == f["source"] and _label_known(g.get("raw_label"), gs)), None)
        if twin:
            warnings.append(f"{sf['key']}: {f.get('raw_label')!r} {f['value']} dropped: the same row as {twin['key']}, and not a {sf['label'].lower()} label")
            f.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
    for sf, f in zip(sfs, fields):  # Stora Enso: "Materials and services" offered as cost of sales in a by-nature statement with no gross profit
        req = sf.get("requires")
        if req and f["value"] is not None and by_key[req]["value"] is None and not _label_known(f.get("raw_label"), sf):
            warnings.append(f"{sf['key']}: {f.get('raw_label')!r} {f['value']} dropped: not a known {sf['label'].lower()} label and the statement has no {req}")
            f.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
    # v103/v111: the wrong-table guard on the model's own citations -- a field whose verified quote is a row
    # of a table the guard refuses carries that table's scope, not the borrowings note's (v097's stored
    # RVRC/Lime answers; v111's Volati timing row and Momentum parent rows). Null it and say so; a carrying
    # total quoted from another page stays (RVRC's own Note 21 row one page earlier is exactly that). A
    # quote that is no printed row at all (stitched, or a prose sentence the stated-zero path proved) is
    # left to the provenance gates that own it.
    if scope_words:
        for sf, f in zip(sfs, fields):
            src = f.get("source") or {}
            page = src.get("page")
            if f["value"] is None or sf["key"] in stated_zeros or not isinstance(page, int) \
                    or not 0 < page <= len(texts) or not src.get("quote"):
                continue
            qrows = _page_rows(texts[page - 1])
            qi = next((i for i, r in enumerate(qrows) if r == src["quote"] or quote_on_page(src["quote"], r)), None)
            if qi is None:
                continue
            scope = _table_scope(qrows, None, qi, basis, scope_words,
                                 debt_scoped=_label_known(_row_label(qrows[qi]), total_voc),
                                 debt_words=debt_voc)
            gross_prior_year = _gross_value_prior_year_block(qrows, qi, fiscal_year)
            if scope in _REFUSED_SCOPES or gross_prior_year is not None:
                reason = _scope_reason(qrows, None, qi, scope_words, scope) if scope in _REFUSED_SCOPES else \
                    f"gross-value maturity block is headed {gross_prior_year}, not {fiscal_year}"
                warnings.append(f"{sf['key']}: {f['value']} from {src['quote'][:70]!r} refused -- "
                                f"{reason}; not read under the {basis} basis")
                if (missing_reason := _scope_missing_reason(qrows, None, qi, scope_words, scope)) is not None:
                    _record_missing_reason(missing_events, [sf["key"]], page=page, **missing_reason)
                f.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
    values = {f["key"]: f["value"] for f in fields if isinstance(f["value"], (int, float))}
    units = Counter(f["unit"] for f in fields if f["unit"])
    periods = Counter(f["period"] for f in fields if re.fullmatch(r"\d{4}", str(f["period"])))
    defaults = {sf["key"]: sf["default"] for sf in schema["fields"] if "default" in sf}  # optional rows (discontinued ops) count as 0
    checks = [_check(c, {**defaults, **values}, texts=texts, pages=pages, fields=fields, schema=schema, stated_zeros=stated_zeros) for c in schema.get("checks", [])]
    for c, sc in zip(checks, schema.get("checks", [])):  # NCC: "Result from sales of Group companies 20" offered as discontinued operations; the identity holds without it
        if c["passed"] or c["detail"].startswith("missing:") or not sc.get("identity"):
            continue
        for sf, f in zip(sfs, fields):
            k = sf["key"]
            if k in defaults and k in values and not _label_known(f.get("raw_label"), sf) and re.search(rf"\b{re.escape(k)}\b", sc["expr"]) \
                    and _check(sc, {**defaults, **values, k: defaults[k]})["passed"]:
                warnings.append(f"{k}: {f.get('raw_label')!r} {f['value']} dropped: not a known {sf['label'].lower()} label, and {c['name']} holds without it")
                f.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
                del values[k]
                c.update(_check(sc, {**defaults, **values}, texts=texts, pages=pages, fields=fields, schema=schema, stated_zeros=stated_zeros))
                break
    for c, sc in zip(checks, schema.get("checks", [])):
        if c["passed"] or c["detail"].startswith("missing:") or not sc.get("identity"):
            continue
        for sf, f in zip(sfs, fields):  # SEB prints "Income tax expense 7,835": expenses unsigned; the check decides the sign
            if sf.get("expense") and isinstance(f["value"], (int, float)) and f["value"] > 0 and re.search(rf"\b{re.escape(f['key'])}\b", sc["expr"]) \
                    and "quote_on_page" in f["evidence"] and _check(sc, {**defaults, **values, f["key"]: -f["value"]})["passed"]:
                warnings.append(f"{f['key']}: printed unsigned as {f['value']}; stored as {-f['value']} (an expense), which makes {c['name']} pass")
                f["value"] = values[f["key"]] = -f["value"]
                c.update(_check(sc, {**defaults, **values}, texts=texts, pages=pages, fields=fields, schema=schema, stated_zeros=stated_zeros))
                break
    for c, sc in zip(checks, schema.get("checks", [])):
        missing = c["detail"].split(": ", 1)[1] if c["detail"].startswith("missing: ") else next(  # ABB: discontinued operations answered null, defaulted
            (k for k in defaults if not c["passed"] and values.get(k) is None and re.search(rf"\b{re.escape(k)}\b", sc["expr"])), None)  # to 0, and the identity fails by its row
        if sc.get("identity") and missing and pages and fiscal_year:
            key = missing  # Addnode after two LLM timeouts: no tax answer, and the statement prints no total tax row
            sf, f = next(((s, g) for s, g in zip(sfs, fields) if g["key"] == key), (None, None))
            fix = f and f["value"] is None and _between_rows(sf, fields, sfs, defaults, texts, fiscal_year, sc, pages[0],
                                                               scope_words, basis, warnings, debt_voc, missing_events)
            if fix:
                warnings.append(f"{key}: model returned null; {fix[1]!r} sits between the other rows of {c['name']} and closes it in every column")
                f.update(value=fix[0], period=str(fiscal_year), raw_label=fix[2], source={"page": pages[0], "quote": fix[1]},
                         evidence=["quote_on_page", "value_derived" if fix[3] > 1 else "identity_all_columns"])
                values[key] = fix[0]
                filled.add(key)
                c.update(_check(sc, {**defaults, **values}, texts=texts, pages=pages, fields=fields, schema=schema, stated_zeros=stated_zeros))
            elif (dated := _date_bucket_derive(schema, fields, texts, fiscal_year, basis, warnings, missing_events)):
                # a date-per-instrument note (Proact, v073): _between_rows just found fewer than two other real
                # operands to sit between, but a date-shaped note can prove every null bucket at once, so this
                # is tried independently rather than only for the one key `missing` happened to name
                fillable = {k: v for k, v in dated.items() if by_key[k]["value"] is None}
                candidate = {**values, **{k: v[0] for k, v in fillable.items()}}
                if fillable and _check(sc, {**defaults, **candidate})["passed"]:
                    for k, (value, quote, dpage, label) in fillable.items():
                        warnings.append(f"{k}: model returned null; instrument rows on page {dpage} sum by maturity date to {value}, closing {c['name']} exactly: {quote!r}")
                        # value_derived stands in for value_in_quote (WEIGHTS, never both): a single-row bucket's own
                        # amount is a literal printed number like any other verified quote, only a multi-row sum is "derived"
                        by_key[k].update(value=value, period=str(fiscal_year), raw_label=label, source={"page": dpage, "quote": quote},
                                         evidence=["quote_on_page"] if _value_in_quote(value, quote) else ["quote_on_page", "value_derived"])
                        values[k] = value
                        filled.add(k)
                    c.update(_check(sc, {**defaults, **values}, texts=texts, pages=pages, fields=fields, schema=schema, stated_zeros=stated_zeros))
        if c["detail"].startswith("missing:") or not sc.get("identity"):  # only an equality proves a sum of rows; margin_sanity would accept anything
            continue
        for f, sf in zip(fields, sfs):  # an operand whose figure is proven by the rows around its quote: Röko "1,01", Catena's two tax rows
            if f["value"] is None or not re.search(rf"\b{re.escape(f['key'])}\b", sc["expr"]) or "quote_on_page" not in f["evidence"] \
                    or "value_derived" in f["evidence"] or (c["passed"] and _value_in_quote(f["value"], f["source"]["quote"])):
                continue
            taken = {g["source"]["quote"] for g in fields if g is not f and g["value"] is not None and g.get("source")}  # Nordea: tax row + net profit row offered as net profit
            own_syns = {cl for s in sf.get("synonyms", []) if (cl := _clean_label(s))}  # the synonyms through the same _clean_label as the rows' labels ("Within 1 year" is within1year); a synonym that cleans away to nothing must not match every row
            own_row = _value_in_quote(f["value"], f["source"]["quote"]) \
                    and _clean_label(f.get("raw_label")) == _clean_label(_row_label(f["source"]["quote"]))  # IPC: "Cost of sales" heading over a "Production costs"
            # row is not the row. Deliberately not also gated on that label being a *known* synonym (Nelly: "Kortfristiga"
            # 36,2 is due_within_1_year's own row, printed and labelled faithfully, but the schema has no bare
            # "kortfristiga" synonym -- requiring one here left the row uncounted as "its own", so the unrestricted
            # search below was free to fold in "Långfristiga" (non-current) as if it belonged, overwriting a correct
            # current-portion read with the current+non-current total)
            # Sagax: "Profit before tax 4,485" is the row; it may be corrected by the rows above it summing differently (Röko), or joined by a
            # row named as part of it (Essity), never by any other neighbour ("Profit before tax + Deferred tax") -- the tax row's problem
            fix = _derived_value(f, texts, fiscal_year, sc, _column_values(f, fields, defaults, texts, fiscal_year), taken,
                                 own_syns if own_row else None)
            if fix and _check(sc, {**defaults, **values, f["key"]: fix[0]})["passed"]:
                if fix[0] != f["value"]:
                    warnings.append(f"{f['key']}: {f['value']} fails {c['name']}; {fix[1]!r} sums to {fix[0]} in every column, which passes")
                else:
                    warnings.append(f"{f['key']}: {f['value']} is not printed; it is the sum of {fix[1]!r}, and {c['name']} holds with those rows in every column")
                f["value"], f["source"]["quote"], f["raw_label"], values[f["key"]] = fix[0], fix[1], fix[2], fix[0]
                f["evidence"].append("value_derived")
                c.update(_check(sc, {**defaults, **values}, texts=texts, pages=pages, fields=fields, schema=schema, stated_zeros=stated_zeros))
                break
    for f, sf in zip(fields, sfs):  # Sectra (by nature): net sales minus goods for resale offered as gross profit, quoting "Total income 3,689,793"
        src = f["source"] or {}
        if f["value"] is None or "value_derived" in f["evidence"] or not src.get("page") or f["key"] in stated_zeros \
                or _value_in_quote(f["value"], src.get("quote", "")):
            continue
        nearby = sorted({src["page"], *pages[:2]})
        if not any(_value_in_quote(f["value"], texts[q - 1]) for q in nearby if 0 < q <= len(texts)):  # nothing above could read or derive it
            # MedCap (v051): the model's own quote spans two printed rows ("6 månader eller mindre" + "6 – 12
            # månader") concatenated as if one -- quote_on_page verifies (both rows really are contiguous on the
            # page), so this field never reaches the _between_rows rescue above, which only fires for a field the
            # model returned null outright. Same rows, same rescue, one more entry point before giving up on it.
            fix = None
            if pages and fiscal_year:
                others_fields = [g for g in fields if g is not f]  # exclude f's own (about-to-be-dropped) quote from the operand search below
                for sc in schema.get("checks", []):
                    if sc.get("identity") and re.search(rf"\b{re.escape(f['key'])}\b", sc["expr"]):
                        fix = _between_rows(sf, others_fields, sfs, defaults, texts, fiscal_year, sc, pages[0],
                                             scope_words, basis, warnings, debt_voc, missing_events)
                        if fix:
                            break
            if fix:
                warnings.append(f"{f['key']}: {f['value']} is printed on none of pages {nearby}; {fix[1]!r} sums to {fix[0]} and closes the identity in every column")
                f.update(value=fix[0], period=str(fiscal_year), raw_label=fix[2], source={"page": pages[0], "quote": fix[1]},
                         evidence=["quote_on_page", "value_derived"])
                values[f["key"]] = fix[0]
                filled.add(f["key"])
                continue
            # Stillfront (v126): the value is the note's own sum of repayment-timing rows of one window
            # (the five "Repayment within 2–5 yr." component rows, the current-classified rows) -- the
            # page proves it in the total-tying column even though no row prints it. Anything else
            # computed or invented still drops below.
            win = _window_row_sum(f, fields, schema, texts, fiscal_year, pages, scope_words, basis, warnings, missing_events) \
                if pages and fiscal_year else None
            if win:
                quote, raw, n, first, last, p = win
                warnings.append(f"{f['key']}: {f['value']} is the sum of {n} rows on page {p} inside its window ({first!r} … {last!r}); kept as value_derived")
                f.update(value=f["value"], period=str(fiscal_year), raw_label=raw, source={"page": p, "quote": quote},
                         evidence=["quote_on_page", "value_derived"])
                values[f["key"]] = f["value"]
                filled.add(f["key"])
                continue
            nil_row = _model_zero_on_dash_row(f, sf, texts, pages, fiscal_year) \
                if f["value"] == 0 and not isinstance(f["value"], bool) else None
            if nil_row:  # v134: the same printed-nil rule at this drop site -- a quote a stray digit made verifiable
                nil_page, nil_quote = nil_row  # still sits on an all-dash row the page prints (see _model_zero_on_dash_row)
                warnings.append(f"{f['key']}: 0 kept -- {nil_quote!r} prints a dash in the fiscal-year column under a known label (printed nil)")
                f.update(raw_label=_row_label(nil_quote), period=str(fiscal_year) if fiscal_year else f.get("period"),
                         source={"page": nil_page, "quote": nil_quote})
                f["evidence"] += ["quote_on_page", "printed_nil"] if "quote_on_page" not in f["evidence"] else ["printed_nil"]
                stated_zeros.add(f["key"])
                continue
            warnings.append(f"{f['key']}: {f['value']} is printed on none of pages {nearby}; dropped as computed, not read")
            f.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
            values.pop(f["key"], None)
    for sf, f in zip(sfs, fields):  # requires, again: a gross profit dropped just now takes Sectra's "Goods for resale" with it
        req = sf.get("requires")
        if req and f["value"] is not None and by_key[req]["value"] is None and not _label_known(f.get("raw_label"), sf):
            warnings.append(f"{sf['key']}: {f.get('raw_label')!r} {f['value']} dropped: not a known {sf['label'].lower()} label and the statement has no {req}")
            f.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
            values.pop(sf["key"], None)
    bucket_pick: dict = {}  # v091: the bucket-column table's own selected row, recorded by _fill_bucket_columns
    _fill_bucket_columns(fields, sfs, schema, texts, pages, fiscal_year, warnings, values, filled, basis, bucket_pick, missing_events)
    _finer_split_rows(fields, schema, texts, fiscal_year, warnings, values, filled, basis, missing_events)  # the bucket-ROW finer split (Rusta), beside the bucket-column reader above
    _subtotal_pair_fill(fields, sfs, schema, texts, pages, fiscal_year, warnings, values, filled, basis, missing_events)  # v110: non-current + current section subtotals, no printed grand total (NOTE Not 19)
    _window_rows_derive(fields, schema, texts, fiscal_year, pages, scope_words, basis, warnings, values, filled)  # v156: a null bucket derived from its window's printed rows when they close on the total (v126's family, on null)
    _year_ladder_fill(fields, sfs, schema, texts, pages, fiscal_year, bucket_pick, warnings, values, filled)  # v157: all three buckets null and the note is a bare calendar-year ladder (ABB p.89)
    _normalize_sign(fields, sfs, schema, texts, warnings, values)  # v101: liabilities-negative printed totals/buckets record their magnitude; the identity below closes on carrying positives
    if schema.get("name") == "debt_maturity" and fiscal_year:
        total = next((field for field in fields if field["key"] == "total_debt"), None)
        tie = _balance_sheet_tie(texts, fiscal_year, None, schema) if total and total["value"] is None else None
        if tie:
            tied_rows, _ = tie
            page = tied_rows[0]["page"]
            rows = _page_rows(texts[page - 1])
            start, end = min(row["index"] for row in tied_rows), max(row["index"] for row in tied_rows)
            span = " ".join(rows[start:end + 1])
            if quote_on_page(span, texts[page - 1]):  # a derived source must still be one contiguous page citation
                value = round(sum(row["value"] for row in tied_rows), 2)
                label = " + ".join(row["label"] for row in tied_rows)
                warnings.append(f"total_debt: model returned null; balance-sheet current/non-current rows on page {page} "
                                f"sum to {value} ({label})")
                total.update(value=value, period=str(fiscal_year), raw_label=label,
                             source={"page": page, "quote": span}, evidence=["quote_on_page", "value_derived"])
                values["total_debt"] = value
                filled.add("total_debt")
    checks = [_check(c, {**defaults, **values}, texts=texts, pages=pages, fields=fields, schema=schema, stated_zeros=stated_zeros) for c in schema.get("checks", [])]
    for c, sc in zip(checks, schema.get("checks", [])):
        if not c["passed"] or not sc.get("identity"):
            continue
        for f, sf in zip(fields, sfs):  # Addnode: "Purchases of goods and services" sits between net sales and gross profit and closes the identity in both years
            src = f["source"] or {}
            if f["value"] is None or _label_known(f.get("raw_label"), sf) or "quote_on_page" not in f["evidence"] or not re.search(rf"\b{re.escape(f['key'])}\b", sc["expr"]):
                continue
            rws = _page_rows(texts[src["page"] - 1])
            ri = rws.index(src["quote"]) if src.get("quote") and src["quote"] in rws else None
            header = _row_year_column(rws, ri, fiscal_year) if ri is not None else _year_column(texts[src["page"] - 1], fiscal_year)  # row-anchored like _column_values below: both must name the field's own table
            others = _column_values(f, fields, defaults, texts, fiscal_year)
            if not header or header[1] < 2 or others is None:
                continue  # one column is one equation; two independent years name the row
            own = _signed(_row_amounts(src["quote"], header[1]), header[0], f["value"])
            if len(own) == header[1] and own[header[0]] == f["value"] and all(_check(sc, {**others[k], f["key"]: own[k]})["passed"] for k in range(header[1])):
                warnings.append(f"{f['key']}: {f['raw_label']!r} is not a known {sf['label'].lower()} label, but {c['name']} holds with that row in every column")
                f["evidence"].append("identity_all_columns")
    currency = units.most_common(1)[0][0] if units else (_page_unit(texts[pages[0] - 1]) if pages else None)
    if not currency and schema.get("name") == "debt_maturity":
        declared = _declared_report_unit(texts)
        if declared:
            currency, unit_page = declared
            warnings.append(f"currency: {currency} from the explicit report-wide amounts declaration on page {unit_page}; no unit printed in the selected table")
    if currency and pages:  # Evolution: a Swedish issuer reporting in EUR; the model votes SEK from habit, the statement names only EUR
        spread = {_ccy(t) for q in pages[:2] for t in _CCY.findall(texts[q - 1])}
        doc = Counter(_ccy(t) for t in _CCY.findall(" ".join(texts)))
        if spread and _ccy(currency) not in spread and doc and doc.most_common(1)[0][0] in spread:
            new = doc.most_common(1)[0][0]
            warnings.append(f"currency: the model says {currency}, but the statement names only {'/'.join(sorted(spread))} and the report mostly {new}; {new} it is")
            swap = lambda u: re.sub(re.escape(_ccy(u)), new, str(u).translate(_SYMBOLS).upper()) if _ccy(u) == _ccy(currency) else u
            for f in fields:
                f["unit"] = swap(f["unit"]) if f["unit"] else f["unit"]
            currency = swap(currency)
    for f, sf in zip(fields, sfs):
        if currency and (f["key"] in filled or (not f["unit"] and (f["source"] or {}).get("page") in pages[:2])):
            # a row filled from the page, or one the model returned without a unit, has the statement's unit
            f["unit"] = _ccy(currency) if sf.get("unit_hint") == "currency_per_share" else currency
    fiscal_year = fiscal_year or (int(periods.most_common(1)[0][0]) if periods else None)
    statement_pages = set(two_pass_pages or pages[:2])  # the locator's statement spread: best page + the one after it; pass 1's own pick under EXTRACT_TWO_PASS
    _prefer_note_citations(fields, sfs, schema, texts, pages, warnings)
    for sf, field in zip(sfs, fields):
        if field["value"] is not None:
            score_field(field, sf, checks, schema, currency, fiscal_year, statement_pages, texts)
    _attach_missing_reasons(fields, schema, pages, missing_events)

    out = {
        "report_id": report_meta.get("report_id"),
        "company": report_meta.get("company"),
        "fiscal_year": fiscal_year,
        "currency": currency,
        "section": schema["name"],
        "maturity_basis": basis,  # v089: the maturity basis these fields were read on (debt_maturity only uses it today); the analyst-confirmed `basis` object is a different key
        "fields": fields,
        "checks": checks,
        "warnings": warnings,
    }
    if (prior := _prior_year_fill(fields, sfs, schema, texts, fiscal_year, bucket_pick)) is not None:
        out["prior_year"] = prior  # v091: the prior year's own figures, identity-gated on explicit values; no key at all when they cannot be read deterministically
    if (by_year := _buckets_by_year_fill(schema, texts, fiscal_year, bucket_pick, values, basis)) is not None:
        out["buckets_by_year"] = by_year  # v109: the report's own calendar-year columns, identity-gated on total_debt; no key at all when the report prints named buckets or the years cannot be read deterministically
    out["timings"] = {"model": round(model_seconds, 3), "attempts": attempts, "validate": round(time.perf_counter() - extraction_started - model_seconds, 3)}
    return out


# EXTRACT_SECOND_PASS is deliberately a narrow follow-up, rather than another whole-report run. The
# first extraction has already had all its normal selection and repair opportunities; this retry asks
# once per still-empty required field on the locator's first three pages. If that stays empty, w198's
# zero-model sweep may make one last fixed-page call on up to three untried synonym-hit pages. Both let
# the ordinary provenance/scope gates decide whether a candidate can replace that null.
SECOND_PASS_MAX_FIELDS = 3
SECOND_PASS_GAAP_HINT = "US GAAP / IFRS common labels may differ; match the field meaning, not just its exact English wording."


def _second_pass_schema(schema: dict, sf: dict) -> dict:
    """A one-field view of the ordinary schema, with its complete synonym vocabulary made explicit.

    ``extract(..., fixed_pages=True)`` keeps the response contract and every validation pass in one
    place.  Removing arithmetic checks here is intentional: a one-field answer cannot prove an
    identity on its own; the full result is rechecked only after an accepted candidate is copied back.
    """
    synonyms = list(dict.fromkeys(
        str(word) for word in [*sf.get("synonyms", []), *sf.get("row_synonyms", [])]
        if str(word).strip()
    ))
    field = dict(sf)
    description = _basis_text(sf, debt_basis())
    field["description"] = " ".join(part for part in (
        description,
        "Synonyms to search verbatim: " + "; ".join(synonyms) + "." if synonyms else "",
        SECOND_PASS_GAAP_HINT,
    ) if part)
    return {**schema, "fields": [field], "checks": []}


def _second_pass_scope_ok(field: dict, sf: dict, schema: dict, texts: list[str]) -> bool:
    """Keep the debt wrong-table refusal explicit at the write-back seam too.

    ``extract`` already applies this guard.  Checking it here means a future fixed-page caller cannot
    accidentally turn an otherwise-valid quote from a parent, lease or undiscounted table into an
    automatic correction merely by changing the extraction internals.
    """
    scope_words = schema.get("table_scope_words")
    source = field.get("source") or {}
    page, quote = source.get("page"), source.get("quote") or ""
    if not scope_words:
        return True
    if not isinstance(page, int) or not 1 <= page <= len(texts):
        return False
    rows = _page_rows(texts[page - 1])
    index = next((i for i, row in enumerate(rows) if row == quote or quote_on_page(quote, row)), None)
    if index is None:
        return False
    identity = _identity_parts(schema)
    total_sf = next((candidate for candidate in schema.get("fields", [])
                     if identity and candidate.get("key") == identity[0]), None)
    total_vocabulary = {"synonyms": (total_sf or {}).get("synonyms", []) + (total_sf or {}).get("row_synonyms", [])}
    scope = _table_scope(rows, None, index, debt_basis(), scope_words,
                         debt_scoped=_label_known(_row_label(rows[index]), total_vocabulary),
                         debt_words=_debt_subject_words(schema))
    return scope not in _REFUSED_SCOPES


def _recheck_after_second_pass(result: dict, schema: dict, texts: list[str], pages: list[int]) -> None:
    """Use the same full-result arithmetic input as the two-run merge's recheck."""
    fields = result.get("fields", [])
    values = {field["key"]: field["value"] for field in fields
              if isinstance(field, dict) and isinstance(field.get("value"), (int, float))
              and not isinstance(field.get("value"), bool)}
    defaults = {sf["key"]: sf["default"] for sf in schema.get("fields", []) if "default" in sf}
    stated_zeros = {field["key"] for field in fields if isinstance(field, dict)
                    and "stated_zero" in field.get("evidence", [])}
    result["checks"] = [_check(check, {**defaults, **values}, texts=texts, pages=pages, fields=fields,
                               schema=schema, stated_zeros=stated_zeros)
                        for check in schema.get("checks", [])]


def second_pass(result: dict, texts: list[str], pages: list[int], schema: dict, report_meta: dict) -> dict:
    """Fill at most three required first-pass nulls through bounded fixed-page calls.

    A candidate is eligible only if the normal fixed-page extraction has retained it and it still has
    a literal quote/value/known-label trail on one of the supplied pages. If the locator window leaves
    a field null, the deterministic sweep ranks numeric synonym rows across the document and supplies
    at most three untried pages for one final call. Null, malformed, out-of-window and wrong-scope
    replies leave the first-pass null untouched.
    """
    started = time.perf_counter()
    window = []
    for page in pages:
        if isinstance(page, int) and not isinstance(page, bool) and 1 <= page <= len(texts) and page not in window:
            window.append(page)
        if len(window) == 3:
            break
    by_key = {field.get("key"): field for field in result.get("fields", []) if isinstance(field, dict)}
    wanted = [sf for sf in schema.get("fields", [])
              if not sf.get("optional") and by_key.get(sf.get("key"), {}).get("value") is None][:SECOND_PASS_MAX_FIELDS]
    stats = {"calls": 0, "seconds": 0.0, "model": 0.0, "validate": 0.0}
    if not wanted:
        return stats

    for sf in wanted:
        def try_pages(target_pages: list[int]) -> dict | None:
            if not target_pages:
                return None
            follow_up = extract(texts, target_pages, _second_pass_schema(schema, sf), report_meta,
                                fixed_pages=True)
            timings = follow_up.get("timings", {})
            stats["calls"] += timings.get("attempts", 0)
            stats["model"] += timings.get("model", 0.0)
            stats["validate"] += timings.get("validate", 0.0)
            candidate = next((field for field in follow_up.get("fields", [])
                              if field.get("key") == sf["key"]), None)
            source = candidate.get("source") if isinstance(candidate, dict) else None
            page = source.get("page") if isinstance(source, dict) else None
            quote = source.get("quote") if isinstance(source, dict) else ""
            vocabulary = {**sf, "synonyms": sf.get("synonyms", []) + sf.get("row_synonyms", [])
                          + [sf.get("label", "")]}
            accepted = bool(
                candidate and candidate.get("value") is not None and isinstance(page, int)
                and page in target_pages
                and "quote_on_page" in candidate.get("evidence", [])
                and "value_in_quote" in candidate.get("evidence", [])
                and "label_known" in candidate.get("evidence", [])
                and quote_on_page(quote, texts[page - 1])
                and _value_in_quote(candidate["value"], quote)
                and _label_known(candidate.get("raw_label"), vocabulary)
                and _second_pass_scope_ok(candidate, sf, schema, texts)
            )
            return candidate if accepted else None

        candidate = try_pages(window)
        source_kind, target_pages = "locator", window
        if candidate is None:
            swept = sweep_pages(texts, sf, tried_pages=window, top_n=3,
                                ocr_pending=report_meta.get("ocr_pending", []))
            target_pages = swept["pages"]
            candidate = try_pages(target_pages)
            source_kind = "full-text sweep"
        if candidate is None:
            result.setdefault("warnings", []).append(
                f"second_pass: {sf['key']} remained null; no candidate passed the existing provenance "
                "and scope guards on locator or full-text sweep pages"
            )
            continue
        candidate.setdefault("evidence", []).append("second_pass")
        if source_kind == "full-text sweep":
            candidate["evidence"].append("fulltext_sweep")
        page = candidate["source"]["page"]
        for index, field in enumerate(result.get("fields", [])):
            if isinstance(field, dict) and field.get("key") == sf["key"] and field.get("value") is None:
                result["fields"][index] = candidate
                result.setdefault("warnings", []).append(
                    f"second_pass: {sf['key']} filled from {source_kind} pages {target_pages} with page {page}"
                )
                break
    _recheck_after_second_pass(result, schema, texts, pages)
    stats["seconds"] = round(time.perf_counter() - started, 3)
    stats["model"] = round(stats["model"], 3)
    stats["validate"] = round(stats["validate"], 3)
    return stats
