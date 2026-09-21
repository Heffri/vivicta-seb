"""Debt tables need component sums, not the income statement's year-column repairs."""
import math
import re
import time

from .parse import normalize_ws

PROMPT = """Read consolidated GROUP borrowings and their maturity from this annual report.
Use CARRYING AMOUNTS for the requested fiscal year. Never mix carrying amounts with
undiscounted cash flows, future interest, nominal amounts or fair values.
Exclude trade payables, derivatives and unused credit facilities. Use the issuer's
reported borrowing scope and describe explicitly whether leases are included.
A lease-only table is NOT the group's debt maturity. Parent-company debt is NOT group debt.
If the consolidated note has only total and current debt, return those and leave
1-5 and >5 years empty. Non-current does NOT mean 1-5 years. Missing does NOT mean zero.
For each field return components: the printed amount(s) which belong to that field,
each with a verbatim contiguous quote and its PAGE marker. Do NOT compute any sum.
Return exactly ONE field entry per requested key, with ALL its rows in components.
Every field's period is the balance-sheet fiscal year (e.g. "2025"), NOT the maturity
year or range. Maturity years belong in raw_label and quotes only.
For calendar year Y: within 1 year = Y+1, 1-5 years = Y+2 through Y+5,
after 5 years = Y+6 and later. Include ALL rows for a bucket, not a partial subtotal.
If a maturity interval crosses a bucket boundary, leave that bucket empty.
Read the requested year's CARRYING AMOUNT column, never the fixed/floating subcolumns.
Quotes for year-labelled rows must contain the year and the amount. Copy full rows
including other columns if needed. Preserve signs and thousands separators.
Total may be a printed total or the complete list of borrowing components, excluding
non-debt liabilities. Never use a total of all financial liabilities as total borrowings.
No overlapping subtotals and detail rows in one field. No duplicate component.
Use scope=group only for a consolidated borrowing note (not lease-only or parent-only).
context_source must quote a SHORT contiguous note title exactly as printed (e.g.
"Borrowings and trade payables"). Do not paraphrase or join separate sentences.
For each missing field explain why in warnings. Prefer null/empty to guessing.
Output exactly the requested JSON schema. Do not use tools.
"""


def response_schema():
    from .extract import _FIELD
    source = _FIELD["properties"]["source"]
    def obj(props):
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    component = obj({"value": {"type": "number"}, "source": source})
    field = obj({"key": {"type": "string"}, "unit": {"type": ["string", "null"]},
                 "period": {"type": ["string", "null"]}, "raw_label": {"type": ["string", "null"]},
                 "components": {"type": "array", "items": component}})
    return obj({"scope": {"type": "string", "enum": ["group", "parent", "lease_only", "unknown"]},
                "basis": {"type": "string", "enum": ["carrying_amount", "contractual_cash_flows", "unknown"]},
                "debt_scope": {"type": "string"}, "context_source": source,
                "fields": {"type": "array", "items": field},
                "warnings": {"type": "array", "items": {"type": "string"}}})


def verified_source(source, texts, pages):
    if not isinstance(source, dict):
        return False
    p, q = source.get("page"), source.get("quote")
    # Exact contiguous evidence only. Numeric-only year rows are legitimate here.
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    return (type(p) is int and p in pages and 1 <= p <= len(texts) and isinstance(q, str)
            and bool(q.strip()) and re.search(r"(?<!\w)" + re.escape(norm(q)) + r"(?!\w)", norm(texts[p - 1])) is not None)


def validate(raw, texts, pages, schema, meta):
    from .extract import _check, _value_in_quote
    if not isinstance(raw, dict) or not isinstance(raw.get("fields"), list):
        raise ValueError("Debt response must contain a fields array")
    warnings = [w for w in raw.get("warnings", []) if isinstance(w, str)]
    context = raw.get("context_source")
    scope_ok = raw.get("scope") == "group" and raw.get("basis") == "carrying_amount" and verified_source(context, texts, pages)
    if not scope_ok:
        warnings.append("Debt scope/basis not verified: require consolidated borrowings at carrying amount.")
    by_key = {}
    for f in raw["fields"]:
        if not isinstance(f, dict):
            raise ValueError("Debt fields must be objects")
        key = f.get("key")
        if key not in by_key:
            by_key[key] = dict(f)
        else:
            previous = by_key[key]
            if any(previous.get(k) != f.get(k) for k in ("unit", "period")):
                raise ValueError("Conflicting units/periods for repeated debt field")
            previous["components"] = previous.get("components", []) + f.get("components", [])
            previous["raw_label"] = "; ".join(filter(None, [previous.get("raw_label"), f.get("raw_label")]))
    fields = []
    for sf in schema["fields"]:
        f = by_key.get(sf["key"], {})
        components = f.get("components", [])
        valid = scope_ok and isinstance(components, list) and bool(components)
        seen = set()
        for c in components if isinstance(components, list) else []:
            if not isinstance(c, dict):
                valid = False
                break
            v, src = c.get("value"), c.get("source")
            if (type(v) not in (int, float) or not math.isfinite(v) or v < 0
                    or not verified_source(src, texts, pages) or not _value_in_quote(v, src["quote"])):
                valid = False
                break
            identity = (src["page"], normalize_ws(src["quote"]), v)
            if identity in seen:
                valid = False
            seen.add(identity)
            year = re.match(r"\s*(20\d{2})(?:\s|$)", src["quote"])
            if year and sf["key"] != "total_debt" and meta.get("fiscal_year"):
                offset = int(year[1]) - int(meta["fiscal_year"])
                bucket = "due_within_1_year" if offset == 1 else "due_1_to_5_years" if 2 <= offset <= 5 else "due_after_5_years" if offset > 5 else None
                if bucket != sf["key"]:
                    valid = False
        if str(f.get("period")) != str(meta.get("fiscal_year")) or not f.get("unit"):
            valid = False
        if not valid:
            if components:
                warnings.append(f"{sf['key']}: unverified component, duplicate, period or scope; value withheld")
            fields.append(dict(key=sf["key"], label=sf["label"], value=None, unit=f.get("unit"), period=f.get("period"),
                               raw_label=f.get("raw_label"), source=None, confidence=0, evidence=[]))
            continue
        value = sum(c["value"] for c in components)
        evidence = ["quote_on_page", "value_derived" if len(components) > 1 else "value_in_quote", "period_ok"]
        fields.append(dict(key=sf["key"], label=sf["label"], value=value, unit=f["unit"], period=f["period"],
                           raw_label=f.get("raw_label"), source=components[0]["source"], components=components,
                           calculation=" + ".join(str(c["value"]) for c in components) + f" = {value}" if len(components) > 1 else None,
                           confidence=0.6, evidence=evidence))
    units = {f["unit"] for f in fields if f["value"] is not None}
    if len(units) > 1:
        warnings.append("Mixed units: debt values withheld rather than summed across units.")
        for f in fields:
            f.update(value=None, source=None, components=[], calculation=None, confidence=0, evidence=[])
    values = {f["key"]: f["value"] for f in fields if f["value"] is not None}
    checks = [_check(c, values) for c in schema.get("checks", [])]
    if any(not c["passed"] and not c["detail"].startswith("missing:") for c in checks):
        warnings.append("Maturity buckets do not reconcile to total debt and have been withheld. Review completeness, scope and column selection before use.")
        for f in fields:
            if f["key"] != "total_debt":
                f.update(value=None, source=None, components=[], calculation=None, confidence=0, evidence=[])
    for f in fields:
        if f["value"] is not None and checks and all(c["passed"] for c in checks):
            f["evidence"].append("arith_ok")
            f["confidence"] = 0.8  # arithmetic and provenance do not prove scope/column interpretation
    return dict(report_id=meta.get("report_id"), company=meta.get("company"), fiscal_year=meta.get("fiscal_year"),
                currency=next(iter(units)) if len(units) == 1 else None, section=schema["name"], fields=fields,
                checks=checks, warnings=warnings, debt_scope=raw.get("debt_scope"), context_source=context if scope_ok else None)


def extract_maturity(texts, pages, schema, meta, prompt):
    from .extract import call_llm
    started = time.perf_counter()
    used = pages[:4]
    user = f"Fiscal year: {meta.get('fiscal_year')}\n" + "\n".join(f"=== PAGE {p} ===\n{texts[p-1]}" for p in used)
    raw = call_llm(prompt, user, response_schema(), "debt_maturity")
    elapsed = time.perf_counter() - started
    result = validate(raw, texts, used, schema, meta)
    result["timings"] = {"model": round(elapsed, 3), "validate": round(time.perf_counter() - started - elapsed, 3), "attempts": 1}
    return result
