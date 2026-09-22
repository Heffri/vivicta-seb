"""Merge two independent extraction runs of the same section into one answer.

The rules were scored offline over 89 stems x 2 rerun answers (docs/acrylic/evidence/v129.md):
per-field union for fresh runs, the stored answer as a third majority vote when a
pipeline-generated `extractions/<section>.json` exists, and an exact skip trigger -- run1
value-identical to stored field by field makes the second run provably a no-op under the majority
merge. Wired into app.py's /extract behind `EXTRACT_MERGE_RUNS=off|union|majority` (default off:
the route is byte-identical); the two raw runs land in `extractions/<section>.run<n>.json` beside
the merged section file.

Pure functions: no model calls, no disk. Labels never enter a rule -- the merge sees only what each
run reports (value/confidence/evidence/source) and whether the run's identity check passed; the
caller recomputes the merged checks with extract's own checker (`recheck`), which is the one part
that needs the schema and the page texts. Parameter notes: a value "matches" another within +/-2
absolute (eval/run.py's relative values_match is for scoring, not a rule input). When the two
runs' identity checks agree, agreeing values are one answer (the copy choice goes to confidence, a
confidence tie to run2), and a *conflict* has no signal to side with: the measured tie-conflicts
were run1 right 1 -- academedia 12103 -- vs run2 right 2 -- net_insight 39415/8305 -- and siding
with the higher-confidence branch instead scored 0/4 on the same conflicts. So any same-check-state
conflict publishes null: never publish a coin flip.

Before values are compared, a vote must be the same *financial question*
(docs/acrylic/evidence/v168.md). Comparing bare numbers let two answers printed on different unit
scales (100 MSEK vs 100 TSEK) or different year columns vouch for each other, and let the stored
third vote count even when it had been read on another fiscal year or maturity basis (re-running
after a carrying/undiscounted switch). Field agreement therefore also compares unit/period
whenever both sides carry them -- units by currency + magnitude, so MSEK, "SEK m" and
"SEK million" stay one answer while KSEK and TSEK do not (a unit known on one side only is not
proof of sameness either); the stored vote must match run1 on report, section, fiscal_year and
maturity_basis, and one missing that metadata sits out with the reason recorded in the merge
block ("not eligible: ..."). run1's `prior_year`/`buckets_by_year` attachments are deterministic
reads of run1's own rows: they ride along only while every field they cover still carries run1's
answer -- another run's copy of that same answer counts (agreeing ties flip no verdict) --
and are dropped with a warning once it does not.
"""
import copy
import os
import re

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


# Unit scales -- the word forms first, then the bare-letter prefix (MSEK/KSEK/TSEK put the
# magnitude first, "SEK m" carries it as its own word), then "SEKm"-style suffixes glued onto a
# known currency, then the thousands notation many reports print ("SEK '000").
_SCALE_WORDS = (("billion", "bn"), ("billions", "bn"), ("million", "m"), ("millions", "m"),
                ("miljoner", "m"), ("miljon", "m"), ("mn", "m"),
                ("thousand", "k"), ("thousands", "k"), ("tusen", "k"))
_SCALE_PREFIX = {"m": "m", "k": "k", "t": "k"}
_SCALE_WORD = re.compile(r"(?i)\b(bn|m|k|t)\b")  # the magnitudes that travel as their own word ("SEK m")
_GLUED_CCY = {"sek", "eur", "usd", "gbp", "nok", "dkk", "chf", "jpy", "cad", "aud", "kr"}
_CCY_STRIP = re.compile(r"(?i)\b(billions?|bn|millions?|miljoner?|mn|thousands?|tusen|of|in|per|m|k|t)\b")
_CCY_ALIAS = {"KRONOR": "SEK", "EURO": "EUR", "KR": "SEK"}  # currency names where the ISO code belongs


def _unit_key(unit: str) -> tuple[str, str] | None:
    """(magnitude, currency) of a printed unit -- "MSEK"/"SEK m"/"SEKm"/"SEK million" -> ("m",
    "SEK"), "KSEK"/"TSEK"/"SEK '000"/"THOUSANDS OF SEK" -> ("k", "SEK"). None when no currency
    survives parsing, so two unparcable units are never declared the same by a guess; identical
    spellings never reach this (`_unit_same` compares them first). Bare "SEK" stays ("", "SEK"):
    the glued-letter rule only fires for a known currency, so SEK/NOK never read as thousands."""
    text = unit.strip().lower()
    scale = next((s for w, s in _SCALE_WORDS if w in text), "") or \
        next((_SCALE_PREFIX[w.lower()] for w in _SCALE_WORD.findall(text)), "")
    bare = _CCY_STRIP.sub(" ", text)  # word-form magnitudes and connectors off
    if not scale and "000" in text:
        scale = "k"  # "SEK '000": the thousands notation many reports print
    if not scale:
        toks = [t for t in re.split(r"[^a-z]+", bare) if t]
        # the glued-letter rules only fire when what remains is a known currency, so "MSEK"/"Mkr"
        # read their leading magnitude while "Miljoner ..." keeps its m and stays unparcable-scale
        if text[:1] in _SCALE_PREFIX and toks and toks[0][1:] in _GLUED_CCY:
            scale, bare = _SCALE_PREFIX[text[:1]], text[1:]  # "MSEK"/"Mkr": the leading magnitude letter off
        else:  # "SEKm"/"EURk": a magnitude letter glued onto a known currency
            tail = next((t for t in toks if len(t) > 3 and t[-1] in _SCALE_PREFIX and t[:-1] in _GLUED_CCY), None)
            if tail:
                scale, bare = _SCALE_PREFIX[tail[-1]], text[:-1]  # the trailing magnitude letter off
    ccy = re.sub(r"[^A-Z]", "", bare.upper())
    ccy = _CCY_ALIAS.get(ccy, ccy)
    return (scale or "", ccy) if ccy else None


def _unit_same(a: str, b: str) -> bool:
    """Two printed units name the same magnitude of the same currency: identical spellings, or
    scale-equivalent ones ("SEK M" == "MSEK", "KSEK" == "TSEK", "KUSD" == "USD thousands").
    100 MSEK and 100 TSEK are a 1000x apart and never compare equal."""
    if a == b:
        return True
    ka, kb = _unit_key(a), _unit_key(b)
    return ka is not None and kb is not None and ka == kb


def _same_field(a: dict, b: dict) -> bool:
    """Same answer to the same financial question: the values agree (`_same`) and -- when both
    sides carry a figure -- so do the unit (by magnitude+currency) and the period. A unit/period
    printed on one side only does not count as the same (unknown is not proof); two sides that
    neither printed one have nothing contradicting. Metadata of a null answer qualifies nothing:
    null == null stays the null agreement it always was."""
    if not _same(a.get("value"), b.get("value")):
        return False
    if a.get("value") is None:  # _same made one side a number otherwise
        return True
    for key in ("unit", "period"):
        x, y = a.get(key), b.get(key)
        if x is None and y is None:
            continue
        if x is None or y is None:
            return False
        if key == "unit" and not _unit_same(str(x), str(y)):
            return False
        if key == "period" and str(x) != str(y):
            return False
    return True


def stored_ineligible(run1: dict, stored: dict) -> str | None:
    """Why the stored answer may not vote (None = it may): a vote must be the same financial
    question -- same report, section, fiscal_year and maturity_basis (the gpt6 P0-4 ruling; the
    route only ever reads this stem's own file, the rest is compared here). A stored answer
    missing that metadata cannot prove sameness, so it sits out too; merge_runs records the
    reason in the merge block as "not eligible: <reason>". run1's own metadata is the live one
    (it was just extracted): comparing against it is comparing against now."""
    if not isinstance(stored, dict):
        return "stored is not an extraction record"
    reasons = []
    for key, label in (("report_id", "report"), ("section", "section"), ("fiscal_year", "fiscal_year"),
                       ("maturity_basis", "maturity_basis")):
        mine, its = run1.get(key), stored.get(key)
        if its is None:
            reasons.append(f"stored has no {label}")
        elif mine is None:
            reasons.append(f"this run has no {label}")
        elif its != mine:
            reasons.append(f"stored {label} {its!r} != {mine!r}")
    return "; ".join(reasons) or None


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
    confidence tie to run2. A same-state conflict is normally signal-free (measured split:
    run1 right 1 -- academedia 12103 -- vs run2 right 2 -- net_insight 39415/8305 -- both wrong 0;
    siding with the higher-confidence branch instead scored 0/4 on the same conflicts), except
    when exactly one total carries extract.py's independent `bs_tie` evidence; that field wins.
    Otherwise the null rule keeps the conflict in extract()'s own dropped-field shape.
    Agree vs conflict is a same-financial-question comparison
    (`_same_field`) -- two answers printed on different unit scales or year columns are a conflict
    even when the bare numbers match."""
    kind = "agree" if _same_field(a, b) else "conflict"
    if ia and not ib:
        return a, "run1", "check passed", kind
    if ib and not ia:
        return b, "run2", "check passed", kind
    if _same_field(a, b):
        if (a.get("confidence") or 0.0) > (b.get("confidence") or 0.0):
            return a, "run1", "higher conf", "agree"
        if (b.get("confidence") or 0.0) > (a.get("confidence") or 0.0):
            return b, "run2", "higher conf", "agree"
        return b, "run2", "tie -> run2", "agree"
    a_ties, b_ties = "bs_tie" in a.get("evidence", []), "bs_tie" in b.get("evidence", [])
    if a_ties != b_ties:
        return (a, "run1", "balance-sheet tie", "conflict") if a_ties else (b, "run2", "balance-sheet tie", "conflict")
    null = copy.deepcopy(a)
    null.update(value=None, unit=None, period=None, raw_label=None, source=None, confidence=0.0, evidence=[])
    return null, "null", "conflict, no signal -> null", None


def _union(a: dict, b: dict, ia, ib) -> tuple[dict, str]:
    """Union per field: the non-null side wins; two answers go to the
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
    """Majority per field: the three votes {run1, run2, stored} decide by value (null votes as
    null), >=2 votes win, and the field comes from the winning value's own run -- run1 before
    run2 before stored. Three mutually distinct answers fall back to union over the two fresh
    runs: the stored answer may not smuggle in a value no fresh run supports. By construction the
    fallback only ever sees agreeing runs when both are null -- two agreeing values are already a
    2-vote majority -- so with both runs non-null it decides on the check state or, same state,
    publishes null. Agreement is `_same_field`'s -- two votes on the same bare
    number but different unit scales or periods are different answers, not a majority."""
    votes = {"run1": a, "run2": b, "stored": s}
    for name in votes:
        agree = [n for n, f in votes.items() if _same_field(votes[name], f)]
        if len(agree) >= 2:
            how = "unanimous" if len(agree) == 3 else "+".join(agree)
            return votes[name], f"{name} (majority: {how})"
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
    stored_note = None
    if majority:  # an old answer on a different financial question does not vote
        stored_note = stored_ineligible(run1, stored)
        if stored_note:
            stored, majority = None, False
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
    by_key = {f["key"]: f for f in fields}  # these attachments are deterministic reads of
    r1f = {f["key"]: f for f in run1["fields"]}  # run1's own rows and gate on run1's own values --
    for extra, gate in (("prior_year", None), ("buckets_by_year", ("total_debt",))):  # they stay while
        if extra not in merged:                                                       # every covered field
            continue                                                                  # still carries run1's
        keys = gate if gate is not None else [k for k in merged[extra] if k in by_key]  # answer (another
        off = [k for k in keys if not (k in by_key and k in r1f                       # run's copy of that same
                                       and _same_field(by_key[k], r1f[k]))]           # answer counts;
        if off:                                                                       # agreeing ties flip no
            merged.pop(extra)                                                         # verdict) -- and go once
            merged["warnings"].append(f"merge: {extra} dropped -- {'/'.join(off)} is no longer run1's answer")
    merged["merge"] = {"mode": mode, "runs": 2, "decisions": decisions}
    if stored_note:
        merged["merge"]["stored_vote"] = f"not eligible: {stored_note}"
    return merged, decisions


def matches_stored(run1: dict, stored: dict) -> bool:
    """The exact skip trigger: run1 is value-identical to the stored answer on every one of
    run1's fields (+/-2, null == null; unit/period compared too whenever both sides carry
    them). Under the majority merge every field then already has two agreeing votes or two nulls,
    so the second run is provably a no-op and the call buys nothing. Fresh runs have no stored
    answer and always pay both. An answer from another financial question never skips the
    second run -- a stored record on a different report, section, fiscal_year or maturity_basis,
    or one missing that metadata, is ineligible (`stored_ineligible`) and reads False here."""
    if stored_ineligible(run1, stored):
        return False
    stored_fields = {f["key"]: f for f in stored.get("fields", [])}
    return all(_same_field(f, stored_fields.get(f["key"]) or {"value": None}) for f in run1.get("fields", []))


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
