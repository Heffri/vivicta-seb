"""Saved-statement review and comparison. No model calls or document downloads."""
import copy
import math
import re
from . import extract, merge

COMMON = ["entity", "consolidation", "period", "currency", "scale", "source", "restatement"]
DEBT = ["debt_basis", "leases", "bucket_mapping"]
CHOICES = {"consolidation": {"Group", "Parent"}, "scale": {"Units", "Thousands", "Millions", "Billions"}, "restatement": {"As reported", "Restated (explain in note)"}, "debt_basis": {"Carrying amounts", "Contractual undiscounted cash flows"}, "leases": {"Included", "Excluded"}}
SUBSTITUTES = {"value_derived", "stated_zero", "printed_nil"}  # exactly one may stand in for value_in_quote (docs/CONFIDENCE.md)

def required(section):
    return COMMON + (DEBT if section == "debt_maturity" else [])

def _field_ok(f):
    """Same bar decorate() uses to close a field's queue issue: a human confirmed or corrected it, or
    every automatic trust signal is present -- quote on page, value in quote (or exactly one SUBSTITUTE
    standing in for it), label/period/unit checked, right statement page, and a source at all."""
    review = f.get("human_review", {})
    evidence = set(f.get("evidence", []))
    matched = "value_in_quote" in evidence or len(evidence & SUBSTITUTES) == 1
    return review.get("decision") in ("confirmed", "corrected") or (matched and {"quote_on_page", "label_known", "period_ok", "page_is_statement", "unit_ok"} <= evidence and bool(f.get("source")))

def _basis_confirmed(x):
    """Same bar compare() uses for a usable basis: a reviewer, and every required() field filled in,
    with a confirmed period that actually names the saved fiscal year."""
    basis = x.get("basis") or {}
    values = basis.get("values", {})
    if not basis.get("reviewer") or any(not values.get(k, "").strip() for k in required(x.get("section"))):
        return False
    return not values.get("period") or str(x.get("fiscal_year")) in values["period"]

def _unit_basis(unit):
    """'MSEK' -> ('SEK', 'Millions'), 'SEK thousand' -> ('SEK', 'Thousands'), 'kr' -> ('SEK', 'Units'); '' where unreadable --
    a bare currency code ('SEK') names no scale: the analyst fills it."""
    u = re.sub(r"[\s.'‘’]+", " ", str(unit or "").translate(extract._SYMBOLS)).strip()
    s, ccy = u.casefold(), extract._ccy(u)
    scale = ("Billions" if re.search(r"\bbn\b|billion|\bmdr?kr\b", s) else
             "Millions" if re.search(r"\bmn?\b|million|miljoner|\bmn?kr\b|\bm[a-z]{3}\b|\b[a-z]{3}m\b", s) else
             "Thousands" if re.search(r"\b[kt]\b|thousand|tusen|\b0{3}\b|\b[kt][a-z]{3}\b", s) else
             "Units" if s == "kr" else "")
    return (ccy if re.fullmatch(r"[A-Z]{3}", ccy) else ""), scale

def suggested_basis(x):
    """Prefill for the basis form, read off what the extraction already knows. Only a human saves a basis."""
    ccy, scale = _unit_basis(x.get("currency"))
    out = {"entity": x.get("company") or "", "consolidation": "Group", "period": str(x.get("fiscal_year") or ""), "currency": ccy, "scale": scale, "source": "Annual report", "restatement": "As reported"}
    if x["section"] == "debt_maturity":
        out.update(debt_basis={"carrying": "Carrying amounts", "undiscounted": "Contractual undiscounted cash flows"}.get(x.get("maturity_basis"), ""),
                   leases="", bucket_mapping="")  # nothing extracted says whether leases are in: the analyst answers
    return out

def checks(x, schema):
    fields = {f["key"]: f for f in x["fields"]}
    defaults = {f["key"]: f["default"] for f in schema["fields"] if "default" in f}  # a row the report may not print (discontinued ops) counts as its default, as in extract
    out = []
    for rule in schema.get("checks", []):
        keys = [f["key"] for f in schema["fields"] if re.search(r"\b" + re.escape(f["key"]) + r"\b", rule["expr"])]
        # v165: a bucket the maturity table prints no column for (evidence "absent_in_table", the header
        # row its source) is the report's explicit absence: it joins the reconciliation as 0 -- the same
        # participation extract._check gives it under require_explicit_values -- instead of holding the
        # check "unavailable" on a value the report never prints. Its missing unit/period are implied by
        # the table it was not printed in, not an unresolved question about a read figure.
        absent = {k for k in keys if rule.get("require_explicit_values") and fields.get(k, {}).get("value") is None
                  and "absent_in_table" in (fields.get(k, {}).get("evidence") or [])}
        values = {k: fields.get(k, {}).get("value") for k in keys}
        values.update({k: defaults[k] for k in keys if k in defaults and values[k] is None})  # a row the report may not print (discontinued ops) counts as its default
        values.update({k: 0 for k in absent})
        operands = [fields[k] for k in keys if fields.get(k, {}).get("value") is not None]
        missing = [k for k, v in values.items() if not isinstance(v, (float, int)) or not math.isfinite(v)]
        units = {str(f.get("unit") or "").strip().casefold() for f in operands}
        periods = {str(f.get("period") or "").strip().casefold() for f in operands}
        reason = "Missing explicit values: " + ", ".join(missing) if missing else ""
        if not reason and (len(units) != 1 or "" in units or len(periods) != 1 or "" in periods):
            reason = "Cannot reconcile missing or incompatible units/periods."
        if reason:
            out.append({"name": rule["name"], "passed": False, "status": "unavailable", "detail": reason})
        else:
            result = extract._check(dict(rule, null_as_zero=[]), values)
            out.append(dict(result, status="passed" if result["passed"] else "failed"))
    return out

def decorate(x, schema, audit=None):
    old = copy.deepcopy(x.get("checks", []))
    x["checks"] = checks(x, schema)
    if audit and old != x["checks"]:
        x.setdefault("check_history", []).append(dict(audit, previous=old))
    basis = x.get("basis") or {}
    values = basis.get("values", {})
    # Basis definitions are a form to confirm, not a review task: they live beside the queue and never block ready.
    basis_issues = [{"kind": "basis", "key": k, "detail": "Confirm " + k.replace("_", " ")} for k in required(x["section"]) if not basis.get("reviewer") or not values.get(k, "").strip()]
    if values.get("period") and str(x.get("fiscal_year")) not in values["period"]:
        basis_issues.append({"kind": "basis", "key": "period", "detail": "Confirmed period must identify the saved fiscal year"})
    optional = {f["key"] for f in schema["fields"] if f.get("optional")}  # a line the report may simply not print
    # optional lines sharing an identity (cost of sales + gross profit) are printed together or not at all:
    # one present and the other null is a miss, not "not reported"
    by_key = {f["key"]: f for f in x["fields"]}
    peers = {k: {o for c in schema.get("checks", []) if c.get("identity") and re.search(rf"\b{k}\b", c["expr"]) for o in optional if re.search(rf"\b{o}\b", c["expr"])} for k in optional}
    sfs = {f["key"]: f for f in schema["fields"]}
    issues, not_reported = [], []
    for f in x["fields"]:
        review = f.get("human_review", {})
        evidence = set(f.get("evidence", []))
        # v165: a null bucket the report's own maturity table prints no column for is not an open
        # question -- the header row in its source is the proof it is not printed; nothing to review.
        # A reviewer actively marking it unresolved re-opens it below like any other field.
        if f.get("value") is None and "absent_in_table" in evidence and review.get("decision") != "unresolved":
            continue
        sf = sfs.get(f["key"], {})  # saved fields scored before extract widened label_known to row_synonyms + label: same vocabulary here, no re-extraction
        if extract._label_known(f.get("raw_label"), {**sf, "synonyms": sf.get("synonyms", []) + sf.get("row_synonyms", []) + [sf.get("label", "")]}):
            evidence.add("label_known")
        matched = "value_in_quote" in evidence or len(evidence & SUBSTITUTES) == 1
        resolved = review.get("decision") in ("confirmed", "corrected") or (matched and {"quote_on_page", "label_known", "period_ok", "page_is_statement", "unit_ok"} <= evidence and bool(f.get("source")))
        if f.get("value") is None and f["key"] in optional and review.get("decision") != "unresolved" and all(by_key.get(o, {}).get("value") is None for o in peers[f["key"]]):
            not_reported.append(f["key"])
        elif f.get("value") is None or not f.get("unit") or not f.get("period") or review.get("decision") == "unresolved" or not resolved or (values.get("period") and str(f.get("period")) != values["period"]):
            issues.append({"kind": "field", "key": f["key"], "detail": f.get("label", f["key"]) + (": missing value (not zero)" if f.get("value") is None else ": verify value, unit, period and source")})
    issues += [{"kind": "check", "key": c["name"], "detail": c["name"] + ": " + c["detail"]} for c in x["checks"] if c["status"] == "failed"]  # "unavailable" is a missing operand, already a field issue or not reported
    x.update(issues=issues, basis_issues=basis_issues, basis_suggested=suggested_basis(x), not_reported=not_reported, ready=not issues)
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


# v174: upcoming-maturities list over a whole saved collection -- consult-gpt6 #8 / consult-fable #2.
# Deterministic (no model, no FX): total debt, the amount due within a year, and their share, for every
# debt_maturity extraction handed in (kb_export_extractions' decorated output). No pairwise comparison --
# each row judges only its own basis/evidence/units, so the share stays visible even when "comparable" is
# false (an analyst can still read an unconfirmed number; the flag says not to rank on it yet).
_SCALE_MULTIPLIER = {"": 1.0, "k": 1e3, "m": 1e6, "bn": 1e9}
_SCALE_UNIT = {1.0: "", 1e3: "T", 1e6: "M", 1e9: "B"}
# merge._unit_key parses any alphabetic leftover as a "currency" (fine for its own job: are these two
# specific strings the same magnitude+currency). We additionally require the code be one we recognise,
# so a genuinely unparseable unit ("doubloons") reads as unknown here rather than a confident code.
_KNOWN_CCY = {"SEK", "EUR", "USD", "GBP", "NOK", "DKK", "CHF", "JPY", "CAD", "AUD", "PLN", "CNY"}

def _parse_unit(unit):
    """(currency, scale-multiplier) from a free-text unit ('MSEK', 'SEK million', 'TSEK', 'EUR'000',
    'Mkr' ...) -- reuses merge._unit_key (v168's tested magnitude/currency parser, already exercised
    against real saved units) instead of a second copy of the same regexes. currency is None when no
    recognised code survives parsing, so callers must treat the figure as not safely combinable with
    another field, never guess one."""
    if not unit or not str(unit).strip():
        return None, None
    key = merge._unit_key(str(unit))
    if key is None or key[1] not in _KNOWN_CCY:
        return None, None
    scale, ccy = key
    return ccy, _SCALE_MULTIPLIER[scale]

def _maturity_row(x):
    fields = {f["key"]: f for f in x.get("fields", [])}
    total, w1y = fields.get("total_debt", {}), fields.get("due_within_1_year", {})
    basis_ok = _basis_confirmed(x)
    reasons = [] if basis_ok else ["Basis not confirmed: entity level, period, debt basis and lease scope must be reviewed first."]
    for field, label in ((total, "total debt"), (w1y, "amount due within 1 year")):
        if field.get("value") is None:
            reasons.append(f"Missing {label}.")
        elif not _field_ok(field):
            reasons.append(f"{label[0].upper()}{label[1:]} is not yet verified (no confirmed source).")
    total_ccy, total_scale = _parse_unit(total.get("unit"))
    w1y_ccy, w1y_scale = _parse_unit(w1y.get("unit"))
    share, note = None, ""
    display_total, display_w1y = {"value": total.get("value"), "unit": total.get("unit")}, {"value": w1y.get("value"), "unit": w1y.get("unit")}
    # Share is arithmetic on whatever numbers exist -- it stays visible even when basis/evidence make the
    # row not "comparable" yet (an analyst can still read an unconfirmed number). Only a missing value, an
    # unrecognised/mismatched currency, or a zero denominator actually block computing it.
    if total.get("value") is not None and w1y.get("value") is not None:
        if not total_ccy or not w1y_ccy or total_ccy != w1y_ccy:
            reasons.append("Total and the <1y bucket are not in a recognised, matching currency; no FX conversion is applied.")
        elif total["value"] == 0:
            note = "No debt outstanding."
        else:
            share = (w1y["value"] * w1y_scale) / (total["value"] * total_scale)
            if total_scale != w1y_scale:
                # Same currency (checked above), different printed scale (e.g. MSEK vs TSEK): normalise
                # both to the coarser scale so the pair reads consistently -- never a currency guess.
                target = max(total_scale, w1y_scale)
                unit = f"{_SCALE_UNIT.get(target, '')}{total_ccy}"
                display_total = {"value": round(total["value"] * total_scale / target, 3), "unit": unit}
                display_w1y = {"value": round(w1y["value"] * w1y_scale / target, 3), "unit": unit}
    decisions = {(f.get("human_review") or {}).get("decision") for f in (total, w1y) if (f.get("human_review") or {}).get("decision")}
    values = (x.get("basis") or {}).get("values", {})
    return {
        "stem": x.get("stem"), "report_id": x.get("report_id"), "company": x.get("company"), "fiscal_year": x.get("fiscal_year"),
        "total": display_total,
        "due_within_1_year": display_w1y,
        "share": round(share, 4) if share is not None else None,
        "basis_confirmed": basis_ok,
        "consolidation": values.get("consolidation") or None, "debt_basis": values.get("debt_basis") or None, "leases": values.get("leases") or None,
        "review_status": "unresolved" if "unresolved" in decisions else (", ".join(sorted(decisions)) if decisions else "unreviewed"),
        "comparable": not reasons,
        "reason": "; ".join(reasons) if reasons else note,
    }

def maturity_wall(extractions):
    """{rows, coverage} over a list of decorated debt_maturity extractions (kb_export_extractions'
    output) -- deterministic total/<1y/share per company, comparable only when basis, period, debt
    basis, lease scope and both fields' evidence all hold and the two amounts share a recognised
    currency (no FX). Rows sort comparable-first, by share descending; non-comparable rows sort last
    but stay in the list -- coverage counts, not silence, explain what isn't ready."""
    rows = [_maturity_row(x) for x in extractions if x.get("section") == "debt_maturity"]
    rows.sort(key=lambda r: (not r["comparable"], r["share"] is None, -(r["share"] or 0)))
    coverage = {
        "total": len(rows),
        "comparable": sum(1 for r in rows if r["comparable"]),
        "missing_total": sum(1 for r in rows if r["total"]["value"] is None),
        "missing_w1y": sum(1 for r in rows if r["due_within_1_year"]["value"] is None),
        "basis_unconfirmed": sum(1 for r in rows if not r["basis_confirmed"]),
    }
    return {"rows": rows, "coverage": coverage}
