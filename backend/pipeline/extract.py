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

from .parse import normalize_ws

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
- Use the current fiscal year column (normally the first number after the row label).
- value: drop thousands separators (152 340 -> 152340), "." as decimal separator, sign as printed (costs negative).
- Never invent numbers. Prefer null over a guess.
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


def system_prompt(schema: dict) -> str:
    lines = "\n".join(
        f"- {f['key']} | {f['label']} | {f.get('description', '')} | {f.get('unit_hint', '')}" for f in schema["fields"]
    )
    return SYSTEM_PROMPT_TEMPLATE.format(
        title=schema.get("title", schema["name"]),
        description=schema.get("description", ""),
        value_convention=schema.get("value_convention", ""),
        exclude=", ".join(schema.get("exclude_keywords", [])) or "-",
        field_lines=lines,
    )


def call_llm(system: str, user: str) -> dict:
    client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.getenv("LLM_API_KEY") or "none")
    resp = client.chat.completions.create(
        model=os.environ["LLM_MODEL"],
        temperature=0,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": "extraction", "strict": True, "schema": RESPONSE_SCHEMA}},
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


def extract(texts: list[str], pages: list[int], schema: dict, report_meta: dict) -> dict:
    user = "\n\n".join(f"=== PAGE {n} ===\n{texts[n - 1]}" for n in pages)
    warnings: list[str] = []
    try:
        raw = call_llm(system_prompt(schema), user).get("fields", [])
    except Exception as e:  # ponytail: no retry; teammates add one with the error fed back to the model
        raw, warnings = [], [f"llm: {type(e).__name__}: {e}"]
    by_key = {f.get("key"): f for f in raw if isinstance(f, dict)}

    fields = []
    for sf in schema["fields"]:
        f = by_key.get(sf["key"]) or {}
        field = {
            "key": sf["key"], "label": sf["label"], "value": _num(f.get("value")),
            "unit": f.get("unit"), "period": f.get("period"), "raw_label": f.get("raw_label"),
            "source": f.get("source") or None, "confidence": float(f.get("confidence") or 0),
        }
        src = field["source"]
        if field["value"] is not None and not src:  # contract: no source, no value
            warnings.append(f"{sf['key']}: value without source dropped")
            field["value"], field["confidence"] = None, 0.0
        elif src:
            page, quote = src.get("page"), src.get("quote") or ""
            if not (isinstance(page, int) and 1 <= page <= len(texts)):
                warnings.append(f"{sf['key']}: source page {page} out of range")
                field["confidence"] *= 0.5
            elif normalize_ws(quote) not in normalize_ws(texts[page - 1]):
                warnings.append(f"{sf['key']}: quote not found on page {page}")
                field["confidence"] *= 0.5
        field["confidence"] = round(min(max(field["confidence"], 0), 1), 3)
        fields.append(field)

    values = {f["key"]: f["value"] for f in fields if isinstance(f["value"], (int, float))}
    units = Counter(f["unit"] for f in fields if f["unit"])
    periods = Counter(f["period"] for f in fields if re.fullmatch(r"\d{4}", str(f["period"])))
    return {
        "report_id": report_meta.get("report_id"),
        "company": report_meta.get("company"),
        "fiscal_year": report_meta.get("fiscal_year") or (int(periods.most_common(1)[0][0]) if periods else None),
        "currency": units.most_common(1)[0][0] if units else None,
        "section": schema["name"],
        "fields": fields,
        "checks": [_check(c, values) for c in schema.get("checks", [])],
        "warnings": warnings,
    }
