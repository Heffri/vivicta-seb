"""Candidate pages -> Extraction dict: one LLM call, then provenance check + arithmetic checks.

Next for a teammate: (1) two-pass -- first ask the model *which* candidate page is the
statement, then extract from that page alone (less context, fewer hallucinations);
(2) on "quote not found" retry once with the warnings fed back into the prompt;
(3) pick the period column explicitly (current vs prior year) instead of trusting
the model's "leftmost number" habit; (4) tune SYSTEM_PROMPT_TEMPLATE against eval/.
"""
import json
import os
import re
from collections import Counter

from openai import OpenAI

from . import kb, locate
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
    client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.getenv("LLM_API_KEY") or "none",
                    timeout=float(os.getenv("LLM_TIMEOUT", "300")), max_retries=0)  # a local 8b model that thinks for 5 min is stuck
    resp = client.chat.completions.create(
        model=os.environ["LLM_MODEL"],
        temperature=0,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    )
    content = resp.choices[0].message.content or ""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)  # qwen3 & co
    content = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content)  # fenced anyway? strip
    return json.loads(content)


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


def _check(check: dict, values: dict) -> dict:
    out = {"name": check["name"], "passed": False, "detail": ""}
    try:
        result = eval(check["expr"], {"__builtins__": {}, **_SAFE_BUILTINS}, values)  # ponytail: our own schema files, not user input
    except NameError as e:
        out["detail"] = f"missing: {e.name}"
        return out
    except Exception as e:
        out["detail"] = f"{type(e).__name__}: {e}"
        return out
    substituted = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: str(values.get(m.group(), m.group())), check["expr"])
    out.update(passed=bool(result), detail=f"{check.get('detail', '')} | {substituted}".strip(" |"))
    return out


WEIGHTS = {"quote_on_page": 0.35, "value_in_quote": 0.20, "arith_ok": 0.20, "label_known": 0.10,
           "period_ok": 0.05, "page_is_statement": 0.05, "unit_ok": 0.05,  # docs/CONFIDENCE.md; sums to 1.0
           "value_derived": 0.20}  # stands in for value_in_quote when the printed number is unreadable, never both


_DASHES = str.maketrans({"–": "-", "−": "-", " ": " "})
_SPACE_GROUPS = re.compile(r"(?<![\d,.])\d{1,3}(?:[  ]\d{3})+(?![,.'\d])")  # Swedish thousands; "7 176,658" (note ref + number) and "1,051 969" (two columns) stay apart
_AMOUNT = re.compile(r"[-(]?(\d{1,3}(?:[ ,.']\d{3})*|\d+)(?:([.,])(\d{1,2}))?\)?")


def _year_column(text: str, fiscal_year) -> tuple[int, int] | None:
    """(position of the fiscal year, number of year columns) from the table's year header ("Note 2024 2025" -> (1, 2)).
    None without a header or when the fiscal year is not in it."""
    head, year = " ".join(text[:600].split()), re.compile(r"\b20\d\d\b")  # the header is at the top of the page
    for m in year.finditer(head):
        run, end = [m.group()], m.end()
        while (n := year.search(head, end)) and n.start() - end <= 12 and not re.search(r"\d", head[end:n.start()]):
            run.append(n.group())  # "2025 2024" or Telia's "2025 Jan-Dec 2024": one word between years is still the header
            end = n.end()
        if len(run) >= 2:
            return (run.index(str(fiscal_year)), len(run)) if str(fiscal_year) in run else None
    return None


def _row_amounts(quote: str, ncols: int | None = None) -> list:
    """Numbers after the row label, parsed; note references ("6, 7", "G2") dropped.
    With the column count known, Swedish space-grouped rows are split by it: "Total sales 6, 10 155 113 161 921"
    is a note reference plus two 6-digit amounts, which no regex can tell from five small numbers."""
    q = quote.translate(_DASHES)
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
    out = []
    for t in toks[last_alpha + 1:]:
        t = t.rstrip(",;")
        m = _AMOUNT.fullmatch(t)
        if not m or (len(re.sub(r"\D", "", t)) < 3 and not m.group(3)):  # "6" / "12" alone is a note reference
            continue
        v = int(re.sub(r"\D", "", m.group(1))) + (float(f"0.{m.group(3)}") if m.group(3) else 0)  # ponytail: "1,234" is read as a thousand, not a Swedish decimal
        v = -v if t[0] in "-(" else v
        out.append(int(v) if float(v).is_integer() else round(v, 2))
    return out


def _page_rows(text: str) -> list[str]:
    """The page as table rows: a line with a word starts a row, the number/note lines after it belong to it
    (pymupdf prints "Gross income\\n14,753\\n14,480" as three lines). Lossy for column-major layouts."""
    rows: list[str] = []
    for line in text.splitlines():
        wrapped = rows and not re.search(r"\d", rows[-1]) and re.match(r"\s*[a-zåäöé]", line)  # "...before items affecting" / "comparability (SEK)1 3 11.55"
        if re.search(r"[^\W\d_]{2,}", line) and not wrapped:  # "G2, G3" is a note reference, not a label
            rows.append(line.strip())
        elif rows and line.strip():
            rows[-1] += " " + line.strip()
    return rows


def _clean_label(label) -> str:
    label = re.sub(r"\s*[/(]\s*\(?loss\)?|/förlust", "", normalize_ws(str(label or "")), flags=re.I)  # "Profit/loss before tax", "Profit (loss)"
    return re.sub(r"[\s\d,.:;*)(]+$", "", label).lower()  # drop trailing note refs


def _label_known(label, sf: dict) -> bool:
    """The printed label is one of the field's synonyms (prefix match) and none of its exclude_labels patterns
    (an adjusted / diluted / continuing-operations variant of the row is not the row)."""
    rl = _clean_label(label)
    if not rl or any(re.search(p, rl) for p in sf.get("exclude_labels", [])):
        return False
    return any(rl.startswith(s.lower()) or s.lower().startswith(rl) for s in sf.get("synonyms", []))


def _row_label(row: str) -> str:
    """'Gross income 14,753 14,480' -> 'Gross income'."""
    return re.split(r"\s+(?=[-(–−]?\d)", row.strip(), 1)[0].rstrip(" ,.:;*")


def _ccy(unit) -> str:
    """'MSEK' / 'SEKm' / 'USD m' / 'SEK million' -> 'SEK' / 'USD': the currency without the scale."""
    c = re.sub(r"(?i)\b(m|mn|mkr|million|millions|thousand|thousands|bn|billion|k|cent|cents|öre)\b|[^A-Za-z]", "", str(unit or "")).upper()
    c = {"EURO": "EUR", "KR": "SEK", "KRONOR": "SEK"}.get(c, c)  # Hexagon prints EPS in "Euro cent"
    if len(c) == 4 and c[0] == "M":
        c = c[1:]
    if len(c) == 4 and c[-1] == "M":
        c = c[:-1]
    return c


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
    return pat is not None and re.search(pat, quote) is not None


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


def _derived_value(field: dict, texts: list[str], fiscal_year):
    """(value, quote) when the field's row is the exact column-wise sum of the 2..6 rows printed right above it: every
    other column of the row agrees with that sum, only the fiscal-year column does not. Röko's text layer prints
    "Profit before tax 1,01 923" (a digit lost); Operating profit 1,051 + Financial income 49 + Financial expenses -90
    = 1,010 while 969 + 66 - 112 = 923 as printed. The quote becomes those rows, the sum the value."""
    src = field.get("source") or {}
    text = texts[src["page"] - 1] if src.get("page") else ""
    header, rows = _year_column(text, fiscal_year), _page_rows(text)
    if not header or src.get("quote") not in rows:
        return None
    col, ncols = header
    i, own = rows.index(src["quote"]), _row_amounts(src["quote"], ncols)
    if len(own) != ncols:
        return None
    for k in range(2, 7):
        parts = [_row_amounts(r, ncols) for r in rows[max(i - k, 0):i]]
        if len(parts) < k or any(len(a) != ncols for a in parts):
            return None  # a heading or a row without amounts ends the run of addends
        sums = [round(sum(a[c] for a in parts), 2) for c in range(ncols)]
        quote = " ".join(rows[i - k:i])
        if all(sums[c] == own[c] for c in range(ncols) if c != col) and sums[col] != field["value"] and quote_on_page(quote, text):
            return sums[col], quote
    return None


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
    if _label_known(field.get("raw_label"), sf):
        ev.append("label_known")
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
    for attempt in (pages[:4], pages[:2]):  # SCA: the model timed out thinking over six pages; the statement spread alone is a quick call
        user = (f"Fiscal year to extract: {fiscal_year}\n\n" if fiscal_year else "") + \
            "\n\n".join(f"=== PAGE {n} ===\n{texts[n - 1]}" for n in attempt)
        try:
            raw = call_llm(system, user).get("fields", [])
            break
        except Exception as e:  # ponytail: one retry on fewer pages; teammates feed the error back to the model
            warnings.append(f"llm: {type(e).__name__}: {e} (pages {attempt})")
    by_key = {f.get("key"): f for f in raw if isinstance(f, dict)}

    fields, filled, sfs = [], set(), []
    for sf in schema["fields"]:
        if sf.get("fallback_synonyms") and pages and not any(_label_known(_row_label(r), sf) for r in _page_rows(texts[pages[0] - 1])):
            # a bank prints no "profit before tax" row: its "Operating profit" is the line before tax (NOBA); its top line is "Total operating income"
            sf = {**sf, "synonyms": sf["synonyms"] + sf["fallback_synonyms"]}
        sfs.append(sf)
        f = by_key.get(sf["key"]) or {}
        field = {
            "key": sf["key"], "label": sf["label"], "value": _num(f.get("value")),
            "unit": f.get("unit"), "period": f.get("period"), "raw_label": f.get("raw_label"),
            "source": f.get("source") or None, "confidence": 0.0, "evidence": [],  # the model's own confidence is ignored, see docs/CONFIDENCE.md
        }
        if field["value"] is None and not field["source"] and pages and fiscal_year:
            # Telia: the model answered null although "Income after financial items 7,300 6,234" is printed on the statement
            # page under a synonym label. Fill it from the page; everything below then verifies it like a model answer.
            first = texts[pages[0] - 1]
            hit = next((r for r in _page_rows(first) if _clean_label(_row_label(r)) in {s.lower() for s in sf.get("synonyms", [])}), None)
            if hit and (h := _year_column(first, fiscal_year)) and len(am := _row_amounts(hit, h[1])) == h[1]:
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
                warnings.append(f"{sf['key']}: quote not found on page {page}")
            else:
                field["evidence"].append("quote_on_page")
                src["quote"] = verified  # the row that is actually on the page (model may prepend a section header)
                fixed = repair_value(field["value"], verified)
                if fixed is not None:
                    warnings.append(f"{sf['key']}: value {field['value']} rescaled to {fixed} as printed in the quote")
                    field["value"] = fixed
                header = _year_column(texts[page - 1], fiscal_year) if fiscal_year else None
                ncols = header and header[1]
                row = src["quote"] = next((r for r in rows if quote_on_page(verified, r)), verified)  # the full printed row, all columns
                amounts = _row_amounts(row, ncols)
                if header and len(amounts) == ncols and field["value"] in amounts and amounts[header[0]] != field["value"]:
                    warnings.append(f"{sf['key']}: {field['value']} is not the {fiscal_year} column, {amounts[header[0]]} is")  # Sandvik prints 2024 first
                    field["value"], field["period"] = amounts[header[0]], str(fiscal_year)
                if header and any(re.search(p, _clean_label(_row_label(row))) for p in sf.get("exclude_labels", [])):
                    # Securitas: "...before and after dilution and before items affecting comparability 11.55" is the adjusted
                    # EPS; Saab: "efter utspädning" is diluted. The statement row with a known, unexcluded label wins.
                    alt = next((r for r in rows if _label_known(_row_label(r), sf) and len(_row_amounts(r, ncols)) == ncols), None)
                    if alt:
                        amounts = _row_amounts(alt, ncols)
                        warnings.append(f"{sf['key']}: {_row_label(row)!r} {field['value']} is a variant row; {_row_label(alt)!r} {amounts[header[0]]} is the statement row")
                        row = src["quote"] = alt
                        field["value"], field["raw_label"], field["period"] = amounts[header[0]], _row_label(alt), str(fiscal_year)
                label, i = _row_label(row), rows.index(row) if row in rows else -1
                if not _label_known(field.get("raw_label"), sf) and i >= 0:
                    # ABB: "Basic earnings per share" is a heading, the figure sits on the sub-row "Net income 2.59 2.13"
                    heading = next((h for h in rows[max(i - 4, 0):i][::-1] if _label_known(_row_label(h), sf)), None)
                    if heading:
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

    values = {f["key"]: f["value"] for f in fields if isinstance(f["value"], (int, float))}
    units = Counter(f["unit"] for f in fields if f["unit"])
    periods = Counter(f["period"] for f in fields if re.fullmatch(r"\d{4}", str(f["period"])))
    defaults = {sf["key"]: sf["default"] for sf in schema["fields"] if "default" in sf}  # optional rows (discontinued ops) count as 0
    checks = [_check(c, {**defaults, **values}) for c in schema.get("checks", [])]
    for c, sc in zip(checks, schema.get("checks", [])):
        if c["passed"] or c["detail"].startswith("missing:"):
            continue
        for f in fields:  # one operand of a failed check is a row whose addends above prove another value: Röko "1,01"
            if f["value"] is None or not re.search(rf"\b{re.escape(f['key'])}\b", sc["expr"]) or "quote_on_page" not in f["evidence"]:
                continue
            fix = _derived_value(f, texts, fiscal_year)
            if fix and _check(sc, {**defaults, **values, f["key"]: fix[0]})["passed"]:
                warnings.append(f"{f['key']}: {f['value']} fails {c['name']}; the rows above {f['source']['quote']!r} sum to {fix[0]} in every column, which passes")
                f["value"], f["source"]["quote"], values[f["key"]] = fix[0], fix[1], fix[0]
                f["evidence"].append("value_derived")
                break
    checks = [_check(c, {**defaults, **values}) for c in schema.get("checks", [])]
    currency = units.most_common(1)[0][0] if units else None
    for f, sf in zip(fields, sfs):
        if f["key"] in filled and currency:  # a row filled from the page has the statement's unit
            f["unit"] = _ccy(currency) if sf.get("unit_hint") == "currency_per_share" else currency
    fiscal_year = fiscal_year or (int(periods.most_common(1)[0][0]) if periods else None)
    statement_pages = set(pages[:2])  # the locator's statement spread: best page + the one after it
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
