"""Merge two independent extraction runs of the same section into one answer (v133).

v129 (docs/acrylic/evidence/v129.md) scored the offline rules over 89 stems x 2 rerun answers:
per-field union for fresh runs (R2), the stored answer as a third majority vote when a
pipeline-generated `extractions/<section>.json` exists (R5), and an exact skip trigger -- run1
value-identical to stored field by field makes the second run provably a no-op under the majority
merge. Wired into app.py's /extract behind `EXTRACT_MERGE_RUNS=off|union|majority` (default off:
the route is byte-identical); the two raw runs land in `extractions/<section>.run<n>.json` beside
the merged section file.

Pure functions: no model calls, no disk. Labels never enter a rule -- the merge sees only what each
run reports (value/confidence/evidence/source) and whether the run's identity check passed; the
caller recomputes the merged checks with extract's own checker (`recheck`), which is the one part
that needs the schema and the page texts. Parameter notes: a value "matches" another within +/-2
absolute (the work order's band; eval/run.py's relative values_match is for scoring, not a rule
input). When the two runs' identity checks agree, agreeing values are one answer (the copy choice
goes to confidence, a confidence tie to run2), and a *conflict* has no signal to side with: v145
measured the tie-conflicts in the v129/v136/v141 datasets at run1 right 1 -- academedia 12103 --
vs run2 right 2 -- net_insight 39415/8305 -- and the v145-b ruling folded the higher-confidence
branch in after it scored 0/4 on the same datasets' conflicts, so any same-check-state conflict
publishes null (v129 R3's spirit: never publish a coin flip) where v133 had pinned run2.
"""
import copy
import os

from . import extract

TIE_BAND = 2  # +/-2: two values this close are one answer for voting and for the skip trigger


def mode() -> str:
    """EXTRACT_MERGE_RUNS, "off" unless it says exactly union|majority -- off is the byte-identical
    default, so a typo can never silently turn the second run on."""
    value = os.getenv("EXTRACT_MERGE_RUNS", "").strip().lower()
    return value if value in ("union", "majority") else "off"


def _same(a, b) -> bool:
    """Value-identical for merging: both null, or both plain numbers within TIE_BAND; anything
    non-numeric compares exactly."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return a == b
    return abs(a - b) <= TIE_BAND


def _identity_ok(run: dict) -> bool | None:
    """Whether the run's identity check passed: `maturity_sums_to_total` when the section carries
    it, else the first check (both shipped schemas put an identity check first -- debt_maturity's
    maturity_sums_to_total, income_statement's gross_profit_arith). None = no checks at all, which
    counts as "did not pass" in the tiebreak below."""
    checks = run.get("checks") or []
    check = next((c for c in checks if c.get("name") == "maturity_sums_to_total"), checks[0] if checks else None)
    return None if check is None else bool(check.get("passed"))


def _pick(a: dict, b: dict, ia, ib) -> tuple[dict, str, str, str | None]:
    """(field, run name, reason, kind) between two non-null answers; kind is None when field is a
    synthesized null whose reason already carries the wording. The run whose identity check passed
    wins. With the same check state, agreeing values (+/-2) are one answer -- both sides carry the
    same verdict on every agreeing instance measured -- so the copy choice goes to confidence, a
    confidence tie to run2. A conflict has no signal to side with: v145 measured the tie-conflicts
    across the v129/v136/v141 datasets at run1 right 1 / run2 right 2 / both wrong 0, and v145-b
    folded the higher-confidence branch in after it scored 0/4 on the same datasets' conflicts --
    so any same-state conflict publishes null in extract()'s own dropped-field shape."""
    kind = "agree" if _same(a.get("value"), b.get("value")) else "conflict"
    if ia and not ib:
        return a, "run1", "check passed", kind
    if ib and not ia:
        return b, "run2", "check passed", kind
    if _same(a.get("value"), b.get("value")):
        if (a.get("confidence") or 0.0) > (b.get("confidence") or 0.0):
            return a, "run1", "higher conf", "agree"
        if (b.get("confidence") or 0.0) > (a.get("confidence") or 0.0):
            return b, "run2", "higher conf", "agree"
        return b, "run2", "tie -> run2", "agree"
    null = copy.deepcopy(a)
    null.update(value=None, unit=None, period=None, raw_label=None, source=None, confidence=0.0, evidence=[])
    return null, "null", "conflict, no signal -> null", None


def _union(a: dict, b: dict, ia, ib) -> tuple[dict, str]:
    """v129 R2 per field with v145-b's conflict rule: the non-null side wins; two answers go to the
    check, then -- only if the values agree within the band -- to confidence and the run2 tie; a
    conflict publishes null. Whether they agree within the band or conflict changes which branch
    decides, and the recorded reason names it."""
    if a.get("value") is None and b.get("value") is None:
        return a, "null (union: both null)"
    if a.get("value") is None:
        return b, "run2 (union: only non-null)"
    if b.get("value") is None:
        return a, "run1 (union: only non-null)"
    field, name, reason, kind = _pick(a, b, ia, ib)
    return field, f"{name} (union: {reason})" if kind is None else f"{name} ({kind}: union: {reason})"


def _majority(a: dict, b: dict, s: dict, ia, ib) -> tuple[dict, str]:
    """v129 R5 per field: the three votes {run1, run2, stored} decide by value (null votes as
    null), >=2 votes win, and the field comes from the winning value's own run -- run1 before
    run2 before stored. Three mutually distinct answers fall back to union over the two fresh
    runs: the stored answer may not smuggle in a value no fresh run supports. By construction the
    fallback only ever sees agreeing runs when both are null -- two agreeing values are already a
    2-vote majority -- so with both runs non-null it decides on the check state or, same state,
    publishes null (v145-b)."""
    votes = {"run1": a.get("value"), "run2": b.get("value"), "stored": s.get("value")}
    for name, field in (("run1", a), ("run2", b), ("stored", s)):
        agree = [n for n, v in votes.items() if _same(votes[name], v)]
        if len(agree) >= 2:
            how = "unanimous" if len(agree) == 3 else "+".join(agree)
            return field, f"{name} (majority: {how})"
    if a.get("value") is None and b.get("value") is None:
        return a, "null (3-way split -> union: both null)"
    if a.get("value") is None:
        return b, "run2 (3-way split -> union: only non-null)"
    if b.get("value") is None:
        return a, "run1 (3-way split -> union: only non-null)"
    field, name, reason, kind = _pick(a, b, ia, ib)  # the fallback has no third vote either, so union's rule governs it
    return field, (f"{name} (3-way split -> union: {reason})" if kind is None
                   else f"{name} ({kind}: 3-way split -> union: {reason})")


def merge_runs(run1: dict, run2: dict, stored: dict | None, mode: str) -> tuple[dict, dict]:
    """(merged, decisions) from two raw extract() returns (+ the stored answer under majority).
    merged is run1's shell -- report_id/company/fiscal_year/currency/section and run1's extras such
    as prior_year -- with per-field winner fields, per-run-prefixed warnings closed by one merge
    summary line, and the top-level merge block. `checks` stays run1's stale set on purpose: the
    winner's checks would misdescribe a field mix, and recomputing needs the schema and page texts,
    which a pure function does not have -- the caller runs recheck(). stored=None (a fresh run, or
    one the route filtered out because it carries human reviews) makes majority decide exactly like
    union."""
    if mode not in ("union", "majority"):
        raise ValueError(f"merge mode must be union|majority, not {mode!r}")
    majority = mode == "majority" and stored is not None
    f2 = {f["key"]: f for f in run2["fields"]}
    fs = {f["key"]: f for f in stored.get("fields", [])} if majority else {}
    ia, ib = _identity_ok(run1), _identity_ok(run2)
    merged = copy.deepcopy(run1)
    fields, decisions = [], {}

    def _merge(a, b, s):
        field, how = _majority(a, b, s, ia, ib) if majority else _union(a, b, ia, ib)
        fields.append(copy.deepcopy(field))
        decisions[field["key"]] = how

    for a in run1["fields"]:  # real extract() emits one field per schema key, so this covers everything;
        _merge(a, f2.get(a["key"]) or {"value": None}, fs.get(a["key"]) or {"value": None})
    for b in run2["fields"]:  # a key only run2 answered (schema drift, a stub) must not be silently dropped
        if b["key"] not in decisions:
            _merge({"key": b["key"], "value": None}, b, fs.get(b["key"]) or {"value": None})
    merged["fields"] = fields
    merged["warnings"] = [f"run1: {w}" for w in run1.get("warnings", [])] \
        + [f"run2: {w}" for w in run2.get("warnings", [])] \
        + [f"merge: {mode}, per-field: " + ", ".join(f"{k}={decisions[k]}" for k in decisions)]
    merged["merge"] = {"mode": mode, "runs": 2, "decisions": decisions}
    return merged, decisions


def matches_stored(run1: dict, stored: dict) -> bool:
    """v129 R5's exact skip trigger: run1 is value-identical to the stored answer on every one of
    run1's fields (+/-2, null == null). Under the majority merge every field then already has two
    agreeing votes or two nulls, so the second run is provably a no-op and the call buys nothing.
    Fresh runs have no stored answer and always pay both."""
    stored_values = {f["key"]: f.get("value") for f in stored.get("fields", [])}
    return all(_same(f.get("value"), stored_values.get(f["key"])) for f in run1.get("fields", []))


def recheck(merged: dict, schema: dict, texts: list[str], pages: list[int]) -> None:
    """Recompute merged["checks"] over the merged values with extract's own checker (extract._check,
    the same private function workbench.checks already calls -- extract exposes no public alias).
    stated_zeros rebuilt from the merged fields' evidence the way extract() builds it, defaults from
    the schema: the same inputs as extract()'s final check pass."""
    fields = merged["fields"]
    values = {f["key"]: f["value"] for f in fields if isinstance(f["value"], (int, float))}
    defaults = {sf["key"]: sf["default"] for sf in schema["fields"] if "default" in sf}
    stated = {f["key"] for f in fields if "stated_zero" in f.get("evidence", [])}
    merged["checks"] = [extract._check(c, {**defaults, **values}, texts=texts, pages=pages,
                                       fields=fields, schema=schema, stated_zeros=stated)
                        for c in schema.get("checks", [])]
