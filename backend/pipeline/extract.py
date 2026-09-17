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
import os
import re
import unicodedata
from collections import Counter

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


def system_prompt(schema: dict, exclude_stem: str | None = None) -> str:
    lines = "\n".join(
        f"- {f['key']} | {f['label']} | {f.get('description', '')} | {f.get('unit_hint', '')}" for f in schema["fields"]
    )
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        title=schema.get("title", schema["name"]),
        description=schema.get("description", ""),
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


def _select_pages(schema: dict, pages: list[int], texts: list[str]) -> list[int] | None:
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
    user = "\n\n".join(f"=== PAGE {n} ===\n{_page_snippet(cleaned[n - 1], keywords)}" for n in pages)
    system = PAGE_SELECT_PROMPT.format(n=len(pages), title=schema.get("title", schema["name"]), description=schema.get("description", ""))
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
    listed = check.get("null_as_zero", [])
    naz = [k for k in listed if values.get(k) is None]
    zero = set(naz)
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
        if span is not None:
            # v058: only the operands' own table -- a bucket word printed by another table on a candidate page
            # (MedCap's contractual cash-flow ">5år" header) must not block a 0 the operands' table really implies
            rows = [normalize_ws(r).lower() for r in span]
        else:
            # v058: no printable operand row to anchor a table boundary to -> v044's whole-page search, unweakened
            rows = [normalize_ws(r).lower() for p in search if 0 < p <= len(texts) for r in _page_rows(texts[p - 1])]
        zero = {k for k in naz if not any((cs := normalize_ws(s).lower()) and cs in r
                                           for s in sf_by_key.get(k, {}).get("synonyms", []) for r in rows)}
    # v050: all listed operands null, but the identity's remaining operand(s) are themselves stated zeros --
    # the report said in words there is no interest-bearing debt (Creades), so the buckets ARE zeros and
    # 0+0+0 == 0 is a real pass, not the "pass on nothing" the guard above exists for (nothing read at all).
    others = set(re.findall(r"\b[A-Za-z_]\w*\b", check["expr"])) - set(_SAFE_BUILTINS) - set(listed)
    all_stated = naz and len(naz) == len(listed) and bool(others) and others <= (stated_zeros or set())
    ns = {**values, **{k: 0 for k in zero}} if naz and (len(naz) < len(listed) or all_stated) else values
    try:
        result = eval(check["expr"], {"__builtins__": {}, **_SAFE_BUILTINS}, ns)  # ponytail: our own schema files, not user input
    except NameError as e:
        out["detail"] = f"missing: {e.name}"
        return out
    except Exception as e:
        out["detail"] = f"{type(e).__name__}: {e}"
        return out
    substituted = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: f"0 ({m.group()} null)" if m.group() in zero else str(ns.get(m.group(), m.group())), check["expr"])
    out.update(passed=bool(result), detail=f"{check.get('detail', '')} | {substituted}".strip(" |"))
    return out


WEIGHTS = {"quote_on_page": 0.35, "value_in_quote": 0.20, "arith_ok": 0.20, "label_known": 0.10,
           "period_ok": 0.05, "page_is_statement": 0.05, "unit_ok": 0.05,  # docs/CONFIDENCE.md; sums to 1.0
           "value_derived": 0.20,  # stands in for value_in_quote when the printed number is unreadable, never both
           "stated_zero": 0.20,  # stands in for value_in_quote when the figure is never printed: the report says 0 in words (v050)
           "identity_all_columns": 0.0}  # a marker: an unknown label whose identity holds in every column earns label_known


_DASHES = str.maketrans({"–": "-", "−": "-", " ": " "})
_SPACE_GROUPS = re.compile(r"(?<![\d,.])\d{1,3}(?:[  ]\d{3})+(?![.'\d]|,\d{3})")  # Clas Ohlson "1 478,6" is 1478.6; only a 3-digit tail after the comma is a thousands group  # Swedish thousands; "7 176,658" (note ref + number) and "1,051 969" (two columns) stay apart
_FOOTNOTE = re.compile(r"(?<=\d{3})\d\)(?=\s|$)")  # Volvo Cars "Cost of sales 3 -297,0421) -320,821": a footnote marker glued to the amount
_AMOUNT = re.compile(r"[-(]?(\d{1,3}(?:[ ,.']\d{3})*|\d+)(?:([.,])(\d{1,4}))?\)?")  # Asmodee prints EPS to four decimals: 0.1186

_SPLIT_YEAR = re.compile(r"\b(20\d\d)/(?:20)?\d\d\b")
_MONTH_RANGE = re.compile(r"(?i)\b(?:jan|feb|mar|apr|maj|may|jun|jul|aug|sep|okt|oct|nov|dec)[a-z]*\.? ?((?:20)?\d\d)\s*[-\u2013]\s*(?:jan|feb|mar|apr|maj|may|jun|jul|aug|sep|okt|oct|nov|dec)[a-z]*\.? ?(?:20)?\d\d\b")


def _year_column(text: str, fiscal_year) -> tuple[int, int] | None:
    """(position of the fiscal year, number of year columns) from the table's year header ("Note 2024 2025" -> (1, 2)).
    None without a header, when the fiscal year is not in it, or when it repeats (Volvo prints "2025 2024" per segment:
    Industrial Operations ... Volvo Group; which pair is the group is not knowable here, see _segment_column)."""
    run = _year_run(text)
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
    first header then names 2 columns for 4-amount rows, so every row derivation bails. The fiscal year once in that
    run -> (pos, len(run)); twice and the run's row or the one above it names Group before Parent ("Koncernen
    Moderbolaget" / "Group Parent Company") -> the first pair, Parent first -> the last; anything else -> None, the
    shape _year_column declines (Volvo's four segment pairs stay unknowable here)."""
    for j in range(i - 1, -1, -1):  # windows grow upward, so the nearest run wins: the row's own header is found before any higher table's
        run = _year_run(" ".join(rows[j:i]))
        if not run:
            continue
        if run.count(str(fiscal_year)) == 1:
            return (run.index(str(fiscal_year)), len(run))
        if run.count(str(fiscal_year)) == 2:  # Group | Parent pairs on one page
            near = " ".join(rows[max(j - 1, 0):j + 1]).lower()  # the run's own row and the one above it
            g, e = locate.GROUP.search(near), locate.ENTITY.search(near)
            if g and e:
                if g.start() < e.start():
                    return (run.index(str(fiscal_year)), len(run))
                return (len(run) - 1 - run[::-1].index(str(fiscal_year)), len(run))
        return None  # the nearest run wins even when it names no usable column: climbing past it would cross into the table above
    return None


def _operand_table_rows(texts: list[str], fields: list[dict], keys: list[str], naz: list[str]) -> list[str] | None:
    """The rows of the table the present-label search's *real* (non-null) operands were read from (v058): each
    operand's source.quote must be an exact _page_rows row -- the anchor standard _column_values/_derived_value
    already use -- and the span per page runs from the nearest year-header row above the page's topmost anchor
    (_year_run over the growing window, _row_year_column's upward walk; the page top when no header sits above,
    so a headerless table never narrows the search) down to the page's bottommost anchor, the Totalt row: bucket
    words printed by another table on the same page (MedCap's contractual cash-flow table, docs/acrylic/evidence/
    v058.md) or below the total are not this table's. None when no operand's quote is a printed row -- quotes the
    model composed rather than copied give no provable table boundary, and the caller then keeps v044's
    whole-page search instead of narrowing the guard on a guess."""
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
        span_top = next((j for j in range(top - 1, -1, -1) if _year_run(" ".join(rows[j:top]))), 0)
        out.extend(rows[span_top:bottom + 1])
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
    maturity-bucket column, where "-" means no debt is due in that window, not a literal zero)."""
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
    q = _SPACE_GROUPS.sub(lambda m: m.group(0).replace(" ", "").replace(" ", ""), q)  # "79 146" -> 79146 before splitting
    toks = q.split()
    if re.search(r"\d\.\d{1,2}\b|\d,\d{3}\b", q):  # "." is the decimal here, so "6,12" is a note reference, not 6.12
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
    sentence names the field's subject (a schema keyword or one of the field's own synonyms); and a
    negation word from the schema's own list is present -- so a bare row label quoted alone ("Summa
    räntebärande skulder" off a column-major table) stays a drop, never becomes a 0."""
    if isinstance(field.get("value"), bool) or field.get("value") != 0 or not isinstance(sf.get("zero_if_stated"), dict):
        return False
    src = field.get("source") or {}
    quote, page = src.get("quote") or "", src.get("page")
    if not isinstance(page, int) or not 1 <= page <= len(texts) or not quote or any(c.isdigit() for c in quote):
        return False
    q = normalize_ws(quote).lower()
    if q not in normalize_ws(texts[page - 1]).lower():
        return False
    vocab = [normalize_ws(v).lower() for v in schema.get("keywords", []) + sf.get("synonyms", [])]
    if not any(v and v in q for v in vocab):  # the sentence must be about this field's subject
        return False
    return bool(set(q.split()) & {w.lower() for w in sf["zero_if_stated"].get("negations", [])})


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


def _between_rows(sf: dict, fields: list[dict], sfs: list[dict], defaults: dict, texts: list[str], fiscal_year, check: dict, page: int):
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


_BUCKET_BOUNDARY = {  # the schema's own synonyms cover most of this (dash-normalised below, so "1–2 years" matches
    # the schema's "1-2 years"); these patch the one gap HANDOFF's examples use that the schema only states in
    # Swedish ("< 1 år", "> 5 år") -- reports also print the plain English symbol form, e.g. Cloetta's "< 1 year".
    "due_within_1_year": re.compile(r"(?i)<\s*1\s*years?\b"),
    "due_after_5_years": re.compile(r"(?i)>\s*5\s*years?\b"),
}
_BARE_TOTAL = re.compile(r"(?i)\btotalt?\b|\bsumma\b")
_YEAR_TAIL = re.compile(r"(?i)\b(?:later|thereafter|senare|övriga år)\b")


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


def _bucket_synonym_hits(text: str, bucket_sfs: dict) -> list[tuple[int, str]]:
    """[(position, key)] for every maturity-bucket synonym of every field in bucket_sfs found in text, dash-
    normalised (so "1–2 years" matches the schema's "1-2 years"), plus _BUCKET_BOUNDARY's English-symbol patch.
    A finer split that maps to the same key twice (Cloetta: "1–2 years" and "2–5 years" are both due_1_to_5_years)
    keeps both hits -- each is its own table column, later summed by _bucket_assign."""
    htext = text.translate(_DASHES)
    hits = []
    for key, sf in bucket_sfs.items():
        for syn in sf.get("synonyms", []):
            hits.extend((m.start(), key) for m in re.finditer(re.escape(syn.translate(_DASHES)), htext, re.I))
        if key in _BUCKET_BOUNDARY:
            hits.extend((m.start(), key) for m in _BUCKET_BOUNDARY[key].finditer(htext))
    return hits


def _bucket_year_hits(text: str, fiscal_year) -> list[tuple[int, str]]:
    """A maturity table whose columns are calendar years rather than named buckets ("2026 2027 2028 Later"):
    [(position, key)] classifying each ascending year found right after fiscal_year (1 year out =
    due_within_1_year, 2-5 years out = due_1_to_5_years, further out or a trailing "Later"/"thereafter"/
    "senare"/"övriga år" = due_after_5_years). [] without >=2 such years."""
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
    tail = _YEAR_TAIL.search(head[pos:])
    if tail:
        hits.append((pos + tail.start(), "due_after_5_years"))
    return hits


def _bucket_header(rows: list[str], idx: int, bucket_sfs: dict, fiscal_year, max_back: int = 25) -> list[str] | None:
    """The ordered column keys of the maturity-bucket table whose grand-total sits on rows[idx]: each bucket hit
    above it, in print order, plus a "total" slot wherever a bare Total/Summa/Totalt column header is seen.
    Read from a generous window of the rows above idx, not just the one right above it: pymupdf sometimes wraps
    a two-line column header (Summa / inom 1 år) into two of _page_rows' rows, and the note's own heading and
    instrument rows sit between the header and the total row. None without >=2 distinct bucket keys -- a page
    that merely mentions one bucket word in passing prose is not a bucket-column table. Falls back to a literal
    calendar-year header (_bucket_year_hits) when no named bucket reaches that bar."""
    window = rows[max(0, idx - max_back):idx]
    hits = []
    for row in window:
        row_hits = _bucket_synonym_hits(row, bucket_sfs) + [(m.start(), "total") for m in _BARE_TOTAL.finditer(row.translate(_DASHES))]
        hits.extend(key for _, key in sorted(row_hits))
    if len({k for k in hits if k != "total"}) < 2:
        year_hits = None
        for row in window:
            yh = _bucket_year_hits(row, fiscal_year)
            if len({k for _, k in yh}) >= 2:
                year_hits = sorted(yh)
                break
        if not year_hits:
            return None
        hits = [key for _, key in year_hits] + (["total"] if any(_BARE_TOTAL.search(r) for r in window) else [])
    return hits


def _bucket_total_row(rows: list[str], total_sf: dict) -> list[int]:
    """Indices of rows that could be a maturity table's grand-total row: the total field's own synonym ("Summa
    räntebärande skulder"), or a bare Total/Totalt/Summa -- a schema's total-field synonyms are themselves
    phrased as row labels ("total borrowings"), but plenty of reports print just the bare word on the total row
    of a table that is already, by construction, about borrowings (the page only got here as a debt_maturity
    candidate), e.g. Cloetta's and Ework's own maturity notes."""
    return [i for i, r in enumerate(rows) if len(_row_amounts(r)) >= 2
            and (_label_known(_row_label(r), total_sf) or _clean_label(_row_label(r)) in ("total", "totalt", "summa"))]


def _bucket_assign(amounts: list, col_keys: list[str]) -> dict[str, float | None]:
    """{key: value} from a row's amounts by column key: a key spanning more than one column (a finer split,
    "1-2 years" + "2-5 years" both due_1_to_5_years) is their sum; a key whose every column is nil (None, not a
    printed 0) is None overall, not a fabricated 0 -- "-" in a maturity table means no debt is due in that
    window, same principle as the bucket fields' own "null if the table has no such row" rule, one level down."""
    out: dict[str, float | None] = {}
    for key in dict.fromkeys(col_keys):
        vals = [amounts[i] for i, k in enumerate(col_keys) if k == key and amounts[i] is not None]
        out[key] = round(sum(vals), 2) if vals else None
    return out


def _fill_bucket_columns(fields: list[dict], sfs: list[dict], schema: dict, texts: list[str], pages: list[int],
                          fiscal_year, warnings: list[str], values: dict, filled: set) -> None:
    """A maturity-bucket note that prints on one row, columns = buckets, instead of one row per bucket (Cloetta's
    borrowings note: "Total 197 22 1,377 9 1,605" under a header of "< 1 year / 1-2 years / 2-5 years / > 5 years
    / Total") -- a shape none of this file's other repairs cover, since _year_column finds no year in a bucket
    header and every repair built on it (_column_values, _derived_value, _between_rows) bails out before it can
    even try (docs/acrylic/evidence/v035.md, "the dominant failure mode"). Column order comes from the header
    text itself, so this reads the shape in general, not one company's table: find the header (_bucket_header),
    zip the row's own numbers to it (_bucket_assign), and either fill a null field or -- if the model's own
    answer disagrees by more than the check's own rounding tolerance -- let the page win, exactly like every
    other repair in this file (Pandox, Getinge, ...)."""
    ident = _identity_parts(schema)
    if not ident:
        return
    total_key, part_keys = ident
    bucket_sfs = {sf["key"]: sf for sf in sfs if sf["key"] in part_keys}
    total_sf = next((sf for sf in sfs if sf["key"] == total_key), None)
    if len(bucket_sfs) != len(part_keys) or not total_sf:
        return
    by_key = {f["key"]: f for f in fields}
    cited = {by_key[k]["source"]["page"] for k in (total_key, *part_keys) if by_key[k]["source"]}
    for page in dict.fromkeys([p for p in pages[:2] if p] + sorted(cited)):
        if not (0 < page <= len(texts)):
            continue
        rows = _page_rows(texts[page - 1])
        candidates = _bucket_total_row(rows, total_sf)
        if not candidates:
            continue
        matched = [i for i in candidates if fiscal_year and str(fiscal_year) in " ".join(rows[max(0, i - 25):i])]
        for idx in (matched or candidates):
            col_keys = _bucket_header(rows, idx, bucket_sfs, fiscal_year)
            if not col_keys:
                continue
            amounts = _row_amounts(rows[idx], len(col_keys), nil=None)
            if len(amounts) != len(col_keys):
                continue
            derived = _bucket_assign(amounts, [total_key if k == "total" else k for k in col_keys])
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
            acted = False
            for key in (total_key, *part_keys):
                value = derived.get(key)
                current = by_key[key]["value"]
                if value is None or (isinstance(current, (int, float)) and abs(current - value) <= 2):
                    continue  # nothing to add, or agrees with the model's own answer -- its evidence already covers it
                warnings.append(f"{key}: {'model returned null' if current is None else f'{current} disagrees with the maturity table'}; "
                                 f"{value} read from {rows[idx]!r} by its column order")
                # score_field derives value_in_quote itself from quote_on_page; only value_derived (a sum with no
                # literal quote, e.g. two finer bucket columns) needs to be pre-seeded, or it would double-count
                by_key[key].update(value=value, period=str(fiscal_year) if fiscal_year else by_key[key]["period"],
                                    raw_label=_row_label(rows[idx]), source={"page": page, "quote": rows[idx]},
                                    evidence=["quote_on_page"] if _value_in_quote(value, rows[idx]) else ["quote_on_page", "value_derived"])
                values[key] = value
                filled.add(key)
                acted = True
            if acted:
                return


def _statement_row(rows: list[str], sf: dict, ncols: int) -> str | None:
    """The field's row on a statement page: the full row whose label is exactly a synonym ("Operating profit" for a bank's
    profit before tax; the synonym through the same _clean_label as the label — "Within 1 year" is exactly within1year),
    else the one full row with a known, unexcluded label prefix. None when ambiguous."""
    full = [r for r in rows if len(_row_amounts(r, ncols)) == ncols]
    syn = {c for s in sf.get("synonyms", []) if (c := _clean_label(s))}  # a synonym that cleans away to nothing would match every labelless row
    hit = next((r for r in full if _clean_label(_row_label(r)) in syn), None)
    if hit:
        return hit
    cands = [r for r in full if _label_known(_row_label(r), sf)]
    return cands[0] if len(cands) == 1 else None


def score_field(field: dict, sf: dict, checks: list[dict], schema: dict, currency, fiscal_year, statement_pages: set[int]) -> None:
    """Fill field["evidence"] and field["confidence"] from what the backend itself verified. Never the model's opinion."""
    ev = field["evidence"]  # may already hold quote_on_page
    src = field["source"] or {}
    if "quote_on_page" in ev and _value_in_quote(field["value"], src.get("quote", "")):
        ev.append("value_in_quote")
    mine = [c for c, sc in zip(checks, schema.get("checks", [])) if re.search(rf"\b{re.escape(field['key'])}\b", sc["expr"])]
    failed = [c for c in mine if not c["passed"] and not c["detail"].startswith("missing:")]  # a check with a missing operand is n/a, not failed
    if not failed:
        ev.append("arith_ok")  # vacuously true for fields no check references (eps)
    if _label_known(field.get("raw_label"), sf) or "value_derived" in ev or "identity_all_columns" in ev:
        ev.append("label_known")  # a derived sum, or an unknown row, is identified by the check holding in every column, not by a printed label
    if fiscal_year and str(field.get("period")) == str(fiscal_year):
        ev.append("period_ok")
    if src.get("page") in statement_pages:
        ev.append("page_is_statement")
    unit = str(field.get("unit") or "")
    if unit and currency and (unit.upper() == str(currency).upper() or (sf.get("unit_hint") == "currency_per_share" and _ccy(unit) == _ccy(currency))):
        ev.append("unit_ok")  # EPS in SEK when the statement is in MSEK / SEKm / SEK million
    score = sum(WEIGHTS[e] for e in ev)
    if "quote_on_page" not in ev:
        score = min(score, 0.25)  # no verifiable provenance
    if "quote_on_page" in ev and "value_in_quote" not in ev and "value_derived" not in ev:
        score = min(score, 0.50)  # the row is on the page but this number is not in it
    if failed:
        score = min(score, 0.50)  # contradicts its neighbours
    if fiscal_year and re.fullmatch(r"\d{4}", str(field.get("period"))) and "period_ok" not in ev:
        score = min(score, 0.50)  # another year's figure
    field["confidence"] = round(score, 3)


def extract(texts: list[str], pages: list[int], schema: dict, report_meta: dict) -> dict:
    fiscal_year = report_meta.get("fiscal_year")
    system, warnings, raw = system_prompt(schema, report_meta.get("stem")), [], []
    nonnull = lambda fs: sum(isinstance(f, dict) and f.get("value") is not None for f in fs)
    windows = [tuple(pages[:2])]  # the statement spread first: a quick call (four pages timed out on NOBA / Nordnet)
    two_pass_pages = None  # pass 1's own pick, if EXTRACT_TWO_PASS is on and it succeeded -- also stands in for
    if os.getenv("EXTRACT_TWO_PASS") == "1" and len(pages) >= 2:  # pages[:2] below wherever that means "the statement", not "cast a wider net"
        selected = _select_pages(schema, pages, texts)
        if selected:
            warnings.append(f"two_pass: page {selected} selected from candidates {pages}")
            windows = [tuple(selected)]
            two_pass_pages = selected
        else:
            warnings.append(f"two_pass: page selection failed or illegal for candidates {pages}; fell back to the single-pass window")
    while windows:
        attempt = windows.pop()
        user = (f"Fiscal year to extract: {fiscal_year}\n\n" if fiscal_year else "") + \
            "\n\n".join(f"=== PAGE {n} ===\n{texts[n - 1]}" for n in attempt)
        try:
            got = call_llm(system, user).get("fields", [])
        except Exception as e:  # ponytail: teammates feed the error back to the model
            warnings.append(f"llm: {type(e).__name__}: {e} (pages {list(attempt)})")
            if "timeout" in type(e).__name__.lower() and len(attempt) > 1 and pages:
                windows = [tuple(pages[:1])]  # IPC: pages 10-11 never answer, page 10 alone does in a minute; a hung single page ends it
            continue
        if nonnull(got) > nonnull(raw):
            raw = got
        if 2 * nonnull(raw) < len(schema["fields"]) and len(attempt) == 2 and len(pages) > 2:
            windows = [tuple(pages[:4])]  # most fields came back empty: widen once
    by_key = {f.get("key"): f for f in raw if isinstance(f, dict)}
    by_key = _quote_retry(by_key, system, schema, texts, pages, fiscal_year, warnings)

    fields, filled, sfs, stated_zeros = [], set(), [], set()
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
            if h and (hit := _statement_row(_page_rows(first), sf, h[1])):  # SEB "Basic earnings per share, SEK"
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
    for page in sorted({f["source"]["page"] for f in fields if f["source"] and "quote_on_page" in f["evidence"]}):
        on_page = [f for f in fields if f["value"] is not None and f["source"] and f["source"].get("page") == page]
        seg = _segment_column(texts[page - 1], fiscal_year, on_page) if fiscal_year else None
        if not seg:
            continue
        col, ncols = segs[page] = seg
        for f in on_page:  # Volvo: income tax read from the Industrial Operations pair, the other rows from Volvo Group
            am = _row_amounts(f["source"]["quote"], ncols)
            if len(am) == ncols and am[col] != f["value"]:
                warnings.append(f"{f['key']}: {f['value']} is another segment's column; the page's rows are read from column {col + 1} of {ncols}, which prints {am[col]}")
                f["value"], f["period"] = am[col], str(fiscal_year)
    if pages and fiscal_year and (h := _year_column(texts[pages[0] - 1], fiscal_year) or segs.get(pages[0])):  # page-level, not row-anchored: statement-spread fill, no quote to anchor to
        first = _page_rows(texts[pages[0] - 1])
        for sf, f in zip(sfs, fields):  # Volvo: profit before tax answered as "Income for the period * 34,707 50,576", a row the page does not print;
            if "quote_on_page" in f["evidence"] or not (hit := _statement_row(first, sf, h[1])):  # the statement's own "Income after financial items" row is the answer
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
            fix = f and f["value"] is None and _between_rows(sf, fields, sfs, defaults, texts, fiscal_year, sc, pages[0])
            if fix:
                warnings.append(f"{key}: model returned null; {fix[1]!r} sits between the other rows of {c['name']} and closes it in every column")
                f.update(value=fix[0], period=str(fiscal_year), raw_label=fix[2], source={"page": pages[0], "quote": fix[1]},
                         evidence=["quote_on_page", "value_derived" if fix[3] > 1 else "identity_all_columns"])
                values[key] = fix[0]
                filled.add(key)
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
            warnings.append(f"{f['key']}: {f['value']} is printed on none of pages {nearby}; dropped as computed, not read")
            f.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
            values.pop(f["key"], None)
    for sf, f in zip(sfs, fields):  # requires, again: a gross profit dropped just now takes Sectra's "Goods for resale" with it
        req = sf.get("requires")
        if req and f["value"] is not None and by_key[req]["value"] is None and not _label_known(f.get("raw_label"), sf):
            warnings.append(f"{sf['key']}: {f.get('raw_label')!r} {f['value']} dropped: not a known {sf['label'].lower()} label and the statement has no {req}")
            f.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
            values.pop(sf["key"], None)
    _fill_bucket_columns(fields, sfs, schema, texts, pages, fiscal_year, warnings, values, filled)
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
    for sf, field in zip(sfs, fields):
        if field["value"] is not None:
            score_field(field, sf, checks, schema, currency, fiscal_year, statement_pages)

    return {
        "report_id": report_meta.get("report_id"),
        "company": report_meta.get("company"),
        "fiscal_year": fiscal_year,
        "currency": currency,
        "section": schema["name"],
        "fields": fields,
        "checks": checks,
        "warnings": warnings,
    }
