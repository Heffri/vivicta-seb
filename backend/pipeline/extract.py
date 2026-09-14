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
import unicodedata
import urllib.request
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
    base, timeout = os.environ["LLM_BASE_URL"], float(os.getenv("LLM_TIMEOUT", "120"))  # a local 8b model that answers in 30-40 s and is still going after two minutes is stuck
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if re.search(r":11434/v1/?$", base):
        # Ollama's native API: think=false makes qwen3 answer in ~35 s instead of ~100 s. Its OpenAI-compatible /v1 ignores
        # both the think option and the "/no_think" soft switch, and the model then reasons for a minute before the JSON.
        body = {"model": os.environ["LLM_MODEL"], "stream": False, "think": os.getenv("LLM_THINK", "0") == "1", "format": schema,
                "options": {"temperature": 0, "num_ctx": int(os.getenv("LLM_NUM_CTX", "16384"))}, "messages": messages}
        req = urllib.request.Request(base.rsplit("/v1", 1)[0] + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = json.loads(r.read())["message"]["content"]
    else:  # any OpenAI-compatible endpoint (Azure, OpenAI, a hosted model for the demo)
        client = OpenAI(base_url=base, api_key=os.getenv("LLM_API_KEY") or "none", timeout=timeout, max_retries=0)
        resp = client.chat.completions.create(model=os.environ["LLM_MODEL"], temperature=0, messages=messages,
                                              response_format={"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}})
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
           "value_derived": 0.20,  # stands in for value_in_quote when the printed number is unreadable, never both
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


def _row_amounts(quote: str, ncols: int | None = None) -> list:
    """Numbers after the row label, parsed; note references ("6, 7", "G2") dropped; a lone dash is nil (0), so columns stay aligned.
    With the column count known, Swedish space-grouped rows are split by it: "Total sales 6, 10 155 113 161 921"
    is a note reference plus two 6-digit amounts, which no regex can tell from five small numbers."""
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
            out.append(0)
            noteish.append(False)
            continue
        m = _AMOUNT.fullmatch(t)
        if not m:
            continue
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
    label = re.sub(r"(?i)\bresult\b", "profit", unicodedata.normalize("NFKC", str(label or "")))  # Ericsson prints "ﬁnancial" with a ligature  # SSAB / Elekta / Stora Enso: "Operating result", "Result before tax", "Result for the year"
    label = re.sub(r"\s*[/(]\s*\(?loss\)?|/förlust", "", normalize_ws(label), flags=re.I)  # "Profit/loss before tax", "Profit (loss)"; normalize_ws glues digits to the word before
    label = re.sub(r",?\s*\(?\b(?:SEK|EUR|USD|NOK|DKK|ISK|GBP|CHF|kr)\b\)?", "", label, flags=re.I)  # Castellum "Earnings, SEK per share before and after dilution"; "Resultat per aktie (SEK)"
    label = re.sub(r"(?:\s+[A-Z]{1,3}\.?\d{1,2}(?:[-–]\d{1,2})?,?)+$", "", label)  # "Net sales IE.3", "Net sales B1, B2"
    return re.sub(r"[\s\d,.:;*)(]+$", "", label).lower()  # drop trailing note refs


def _label_known(label, sf: dict) -> bool:
    """The printed label is one of the field's synonyms (prefix match) and none of its exclude_labels patterns
    (an adjusted / diluted / continuing-operations variant of the row is not the row)."""
    rl = _clean_label(label)
    if not rl or any(re.search(p, rl) for p in sf.get("exclude_labels", [])):
        return False
    return any(rl.startswith(s.lower()) for s in sf.get("synonyms", []))


def _row_label(row: str) -> str:
    """'Gross income 14,753 14,480' -> 'Gross income'."""
    return re.split(r"\s+(?=[-(–−]?\d)", row.strip(), 1)[0].rstrip(" ,.:;*")


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


def _signed(amounts: list, col: int, value) -> list:
    """Swedbank prints expenses positive, the field carries them negative: the whole row flips with the fiscal-year figure."""
    return [-a for a in amounts] if col < len(amounts) and amounts[col] == -value and value else amounts


def _column_values(field: dict, fields: list[dict], defaults: dict, texts: list[str], fiscal_year) -> list[dict] | None:
    """Per table column, the other fields' printed figures ({key: amount}), for fields whose verified quote is a full row
    of the same table layout. Lets a check be evaluated in the comparative column too."""
    src = field.get("source") or {}
    header = _year_column(texts[src["page"] - 1], fiscal_year) if src.get("page") else None
    if not header:
        return None
    col, ncols = header
    cols = [dict(defaults) for _ in range(ncols)]
    for g in fields:
        gs = g.get("source") or {}
        if g is field or g["value"] is None or not gs.get("page") or "quote_on_page" not in g["evidence"]:
            continue
        if _year_column(texts[gs["page"] - 1], fiscal_year) != header:
            continue
        am = _signed(_row_amounts(gs["quote"], ncols), col, g["value"])
        if len(am) == ncols and am[col] == g["value"]:
            for c in range(ncols):
                cols[c][g["key"]] = am[c]
    return cols


def _derived_value(field: dict, texts: list[str], fiscal_year, check: dict | None = None, others: list[dict] | None = None, taken: set | None = None):
    """(value, quote, label) when the field's figure is proven by the rows around its quote, column by column:
    (a) the quote is a total row whose fiscal-year figure is unreadable: the 2..6 rows above sum to the row in every other
        column (Röko's text layer prints "Profit before tax 1,01 923"; 1,051 + 49 - 90 = 1,010 while 969 + 66 - 112 = 923);
    (b) the value is printed nowhere: it is the sum of the 2..8 rows ending at the quote (Catena "Current tax -56" +
        "Deferred tax -367" = -423; IPC's four rows under the "Cost of sales" heading), and the check that ties the field
        to its neighbours holds with those sums in every column, not just the fiscal year's.
    The quote becomes those rows; in (b) the label becomes the heading above them, or the rows' labels joined. No addend may be
    another field's row (`taken`): a sum over the identity's other operands restates the identity and proves nothing."""
    src = field.get("source") or {}
    text = texts[src["page"] - 1] if src.get("page") else ""
    header, rows = _year_column(text, fiscal_year), _page_rows(text)
    if not header or src.get("quote") not in rows:
        return None
    col, ncols = header
    i, own = rows.index(src["quote"]), _row_amounts(src["quote"], ncols)
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
    "Current tax -157 -154", "Deferred tax 27 20", "Profit for the year 384 402"; no total tax row exists). None of the rows may
    carry another field's label. (value, quote, label, number of rows) or None."""
    text = texts[page - 1]
    header, rows = _year_column(text, fiscal_year), _page_rows(text)
    if not header or header[1] < 2:
        return None
    col, ncols = header
    idx = [rows.index(g["source"]["quote"]) for g in fields if g["value"] is not None and (g.get("source") or {}).get("page") == page
           and g["source"]["quote"] in rows and re.search(rf"\b{re.escape(g['key'])}\b", check["expr"])]
    if len(idx) < 2:
        return None
    between = [r for r in rows[min(idx) + 1:max(idx)] if len(_row_amounts(r, ncols)) == ncols]
    if not between or any(_label_known(_row_label(r), gs) for r in between for gs in sfs if gs is not sf):
        return None
    parts = [_row_amounts(r, ncols) for r in between]
    sums = [round(sum(a[c] for a in parts), 2) for c in range(ncols)]
    others, quote = _column_values({"source": {"page": page}}, fields, defaults, texts, fiscal_year), " ".join(between)
    if others and all(_check(check, {**others[c], sf["key"]: sums[c]})["passed"] for c in range(ncols)) and quote_on_page(quote, text):
        return sums[col], quote, " + ".join(_row_label(r) for r in between), len(between)
    return None


def _statement_row(rows: list[str], sf: dict, ncols: int) -> str | None:
    """The field's row on a statement page: the full row whose label is exactly a synonym ("Operating profit" for a bank's
    profit before tax), else the one full row with a known, unexcluded label prefix. None when ambiguous."""
    full = [r for r in rows if len(_row_amounts(r, ncols)) == ncols]
    syn = {s.lower() for s in sf.get("synonyms", [])}
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

    fields, filled, sfs = [], set(), []
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
            h = _year_column(first, fiscal_year)
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
                    # Sectra: "Net sales" minus "Goods for resale" offered as gross profit with a quote that is not on the page. A number
                    # printed nowhere on the cited page or the statement spread was computed or invented, and the rules say null then.
                    warnings.append(f"{sf['key']}: {field['value']} is printed on none of pages {nearby}; dropped as computed, not read")
                    field.update(value=None, unit=None, period=None, raw_label=None, source=None, evidence=[])
                    fields.append(field)
                    continue
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
    if pages and fiscal_year and (h := _year_column(texts[pages[0] - 1], fiscal_year) or segs.get(pages[0])):
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
    checks = [_check(c, {**defaults, **values}) for c in schema.get("checks", [])]
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
                c.update(_check(sc, {**defaults, **values}))
                break
    for c, sc in zip(checks, schema.get("checks", [])):
        if c["passed"] or c["detail"].startswith("missing:") or not sc.get("identity"):
            continue
        for sf, f in zip(sfs, fields):  # SEB prints "Income tax expense 7,835": expenses unsigned; the check decides the sign
            if sf.get("expense") and isinstance(f["value"], (int, float)) and f["value"] > 0 and re.search(rf"\b{re.escape(f['key'])}\b", sc["expr"]) \
                    and "quote_on_page" in f["evidence"] and _check(sc, {**defaults, **values, f["key"]: -f["value"]})["passed"]:
                warnings.append(f"{f['key']}: printed unsigned as {f['value']}; stored as {-f['value']} (an expense), which makes {c['name']} pass")
                f["value"] = values[f["key"]] = -f["value"]
                c.update(_check(sc, {**defaults, **values}))
                break
    for c, sc in zip(checks, schema.get("checks", [])):
        if sc.get("identity") and c["detail"].startswith("missing: ") and pages and fiscal_year:
            key = c["detail"].split(": ", 1)[1]  # Addnode after two LLM timeouts: no tax answer, and the statement prints no total tax row
            sf, f = next(((s, g) for s, g in zip(sfs, fields) if g["key"] == key), (None, None))
            fix = f and f["value"] is None and _between_rows(sf, fields, sfs, defaults, texts, fiscal_year, sc, pages[0])
            if fix:
                warnings.append(f"{key}: model returned null; {fix[1]!r} sits between the other rows of {c['name']} and closes it in every column")
                f.update(value=fix[0], period=str(fiscal_year), raw_label=fix[2], source={"page": pages[0], "quote": fix[1]},
                         evidence=["quote_on_page", "value_derived" if fix[3] > 1 else "identity_all_columns"])
                values[key] = fix[0]
                filled.add(key)
                c.update(_check(sc, {**defaults, **values}))
        if c["detail"].startswith("missing:") or not sc.get("identity"):  # only an equality proves a sum of rows; margin_sanity would accept anything
            continue
        for f, sf in zip(fields, sfs):  # an operand whose figure is proven by the rows around its quote: Röko "1,01", Catena's two tax rows
            if f["value"] is None or not re.search(rf"\b{re.escape(f['key'])}\b", sc["expr"]) or "quote_on_page" not in f["evidence"] \
                    or "value_derived" in f["evidence"] or (c["passed"] and _value_in_quote(f["value"], f["source"]["quote"])):
                continue
            taken = {g["source"]["quote"] for g in fields if g is not f and g["value"] is not None and g.get("source")}  # Nordea: tax row + net profit row offered as net profit
            own_row = _value_in_quote(f["value"], f["source"]["quote"]) and _clean_label(_row_label(f["source"]["quote"])) in {x.lower() for x in sf.get("synonyms", [])}                 and _clean_label(f.get("raw_label")) == _clean_label(_row_label(f["source"]["quote"]))  # IPC: "Cost of sales" heading over a "Production costs" row is not the row
            # Sagax: "Profit before tax 4,485" is the row; it may be corrected by the rows above it summing differently (Röko), never extended
            # by a neighbour ("Profit before tax + Deferred tax") -- the failing identity is the tax row's problem (current tax only)
            fix = _derived_value(f, texts, fiscal_year, None if own_row else sc, _column_values(f, fields, defaults, texts, fiscal_year), taken)
            if fix and _check(sc, {**defaults, **values, f["key"]: fix[0]})["passed"]:
                if fix[0] != f["value"]:
                    warnings.append(f"{f['key']}: {f['value']} fails {c['name']}; {fix[1]!r} sums to {fix[0]} in every column, which passes")
                else:
                    warnings.append(f"{f['key']}: {f['value']} is not printed; it is the sum of {fix[1]!r}, and {c['name']} holds with those rows in every column")
                f["value"], f["source"]["quote"], f["raw_label"], values[f["key"]] = fix[0], fix[1], fix[2], fix[0]
                f["evidence"].append("value_derived")
                c.update(_check(sc, {**defaults, **values}))
                break
    for f, sf in zip(fields, sfs):  # Sectra (by nature): net sales minus goods for resale offered as gross profit, quoting "Total income 3,689,793"
        src = f["source"] or {}
        if f["value"] is None or "value_derived" in f["evidence"] or not src.get("page") or _value_in_quote(f["value"], src.get("quote", "")):
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
    checks = [_check(c, {**defaults, **values}) for c in schema.get("checks", [])]
    for c, sc in zip(checks, schema.get("checks", [])):
        if not c["passed"] or not sc.get("identity"):
            continue
        for f, sf in zip(fields, sfs):  # Addnode: "Purchases of goods and services" sits between net sales and gross profit and closes the identity in both years
            src = f["source"] or {}
            if f["value"] is None or _label_known(f.get("raw_label"), sf) or "quote_on_page" not in f["evidence"] or not re.search(rf"\b{re.escape(f['key'])}\b", sc["expr"]):
                continue
            header, others = _year_column(texts[src["page"] - 1], fiscal_year), _column_values(f, fields, defaults, texts, fiscal_year)
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
