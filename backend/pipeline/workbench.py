"""Saved-statement review and comparison. No model calls or document downloads."""
import copy
import math
import re
from . import extract

COMMON = ["entity", "consolidation", "period", "currency", "scale", "source", "restatement"]
DEBT = ["debt_basis", "leases", "bucket_mapping"]
CHOICES = {"consolidation": {"Group", "Parent"}, "scale": {"Units", "Thousands", "Millions", "Billions"}, "restatement": {"As reported", "Restated (explain in note)"}, "debt_basis": {"Carrying amounts", "Contractual undiscounted cash flows"}, "leases": {"Included", "Excluded"}}

def required(section):
    return COMMON + (DEBT if section == "debt_maturity" else [])

def checks(x, schema):
    fields = {f["key"]: f for f in x["fields"]}
    out = []
    for rule in schema.get("checks", []):
        keys = [f["key"] for f in schema["fields"] if re.search(r"\b" + re.escape(f["key"]) + r"\b", rule["expr"])]
        operands = [fields.get(k, {}) for k in keys]
        missing = [k for k in keys if not isinstance(fields.get(k, {}).get("value"), (float, int)) or not math.isfinite(fields[k]["value"])]
        units = {str(f.get("unit") or "").strip().casefold() for f in operands}
        periods = {str(f.get("period") or "").strip().casefold() for f in operands}
        reason = "Missing explicit values: " + ", ".join(missing) if missing else ""
        if not reason and (len(units) != 1 or "" in units or len(periods) != 1 or "" in periods):
            reason = "Cannot reconcile missing or incompatible units/periods."
        if reason:
            out.append({"name": rule["name"], "passed": False, "status": "unavailable", "detail": reason})
        else:
            result = extract._check(dict(rule, null_as_zero=[]), {k: fields[k]["value"] for k in keys})
            out.append(dict(result, status="passed" if result["passed"] else "failed"))
    return out

def decorate(x, schema, audit=None):
    old = copy.deepcopy(x.get("checks", []))
    x["checks"] = checks(x, schema)
    if audit and old != x["checks"]:
        x.setdefault("check_history", []).append(dict(audit, previous=old))
    basis = x.get("basis") or {}
    values = basis.get("values", {})
    issues = [{"kind": "basis", "key": k, "detail": "Confirm " + k.replace("_", " ")} for k in required(x["section"]) if not basis.get("reviewer") or not values.get(k, "").strip()]
    if values.get("period") and str(x.get("fiscal_year")) not in values["period"]:
        issues.append({"kind": "basis", "key": "period", "detail": "Confirmed period must identify the saved fiscal year"})
    for f in x["fields"]:
        review = f.get("human_review", {})
        evidence = set(f.get("evidence", []))
        resolved = review.get("decision") in ("confirmed", "corrected") or ({"quote_on_page", "value_in_quote", "label_known", "period_ok", "page_is_statement", "unit_ok"} <= evidence and bool(f.get("source")))
        if f.get("value") is None or not f.get("unit") or not f.get("period") or review.get("decision") == "unresolved" or not resolved or (values.get("period") and str(f.get("period")) != values["period"]):
            issues.append({"kind": "field", "key": f["key"], "detail": f.get("label", f["key"]) + (": missing value (not zero)" if f.get("value") is None else ": verify value, unit, period and source")})
    issues += [{"kind": "check", "key": c["name"], "detail": c["name"] + ": " + c["detail"]} for c in x["checks"] if not c["passed"]]
    x.update(issues=issues, ready=not issues)
    return x

def compare(current, previous):
    reasons = []
    a, b = current.get("basis", {}), previous.get("basis", {})
    av, bv = a.get("values", {}), b.get("values", {})
    for x, basis in ((current, a), (previous, b)):
        if not basis.get("reviewer") or any(not basis.get("values", {}).get(k, "").strip() for k in required(x["section"])):
            reasons.append(f"{x.get('fiscal_year')}: confirm the basis of figures first.")
    for k in ["entity", "consolidation", "currency", "scale"] + (DEBT if current["section"] == "debt_maturity" else []):
        if str(av.get(k, "")).strip().casefold() != str(bv.get(k, "")).strip().casefold():
            reasons.append("Incompatible " + k.replace("_", " ") + ".")
    for x, v in ((current, av), (previous, bv)):
        if str(x.get("fiscal_year")) not in v.get("period", ""):
            reasons.append("Confirmed period must identify the saved fiscal year.")
    if av.get("period", "").replace(str(current.get("fiscal_year")), "YEAR") != bv.get("period", "").replace(str(previous.get("fiscal_year")), "YEAR"):
        reasons.append("Incompatible reporting periods.")
    rows = []
    old = {f["key"]: f for f in previous["fields"]}
    for f in current["fields"]:
        g = old.get(f["key"], {})
        v, p = f.get("value"), g.get("value")
        reason = "; ".join(reasons)
        if not reason and (not isinstance(v, (int, float)) or not isinstance(p, (int, float))): reason = "Missing numeric value."
        if not reason and (not f.get("unit") or f.get("unit", "").casefold() != (g.get("unit") or "").casefold()): reason = "Incompatible or missing units."
        if not reason and (str(f.get("period")) != av.get("period") or str(g.get("period")) != bv.get("period")): reason = "Field period differs from the confirmed basis."
        delta = None if reason else v - p
        rows.append({"key": f["key"], "label": f["label"], "current": v, "previous": p, "delta": delta,
                     "percent": delta / abs(p) * 100 if delta is not None and p else None,
                     "sign_change": bool(delta is not None and v * p < 0), "reason": reason or ("Percentage unavailable: previous value is zero." if p == 0 else ""),
                     "current_source": f.get("source"), "previous_source": g.get("source"), "current_review": f.get("human_review"), "previous_review": g.get("human_review")})
    return {"previous_stem": previous.get("stem"), "current_year": current.get("fiscal_year"), "previous_year": previous.get("fiscal_year"),
            "previous_basis": b, "restatement": {"current": av.get("restatement", "unknown"), "previous": bv.get("restatement", "unknown")}, "reasons": reasons, "rows": rows}
