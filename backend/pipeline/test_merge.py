"""Self-check: the two-run merge behind EXTRACT_MERGE_RUNS and its /extract route wiring. The rule
under test: with the same identity-check state, agreeing values are one answer, while a conflict
has no signal and publishes null. Synthetic extract()-shaped runs only -- no model calls, isolated
KB_DIR, no data/kb reads.
Run: python -m pipeline.test_merge"""
import copy
import json
import os
import tempfile
from contextlib import contextmanager


@contextmanager
def _env(**vals):
    """Temporarily set/unset env vars (None = unset); restores whatever was there before."""
    saved = {k: os.environ.get(k) for k in vals}
    for k, v in vals.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


IS_CHECKS = [{"name": "gross_profit_arith", "passed": True, "detail": ""},
             {"name": "net_profit_arith", "passed": True, "detail": ""},
             {"name": "margin_sanity", "passed": True, "detail": ""}]


def _run(values, conf=None, check_passed=True, warnings=None):
    """An extract()-shaped income_statement result: value None -> source None / confidence 0."""
    fields = []
    for k, v in values.items():
        has = v is not None
        fields.append({"key": k, "label": k, "value": v, "unit": "MSEK" if has else None,
                       "period": "2025" if has else None, "raw_label": k if has else None,
                       "source": {"page": 1, "quote": f"{k} {v}"} if has else None,
                       "confidence": (conf or {}).get(k, 0.9 if has else 0.0),
                       "evidence": ["quote_on_page", "value_in_quote"] if has else []})
    return {"report_id": "lib-acme_2025", "company": "Acme", "fiscal_year": 2025, "currency": "MSEK",
            "section": "income_statement", "maturity_basis": "carrying", "fields": fields,
            "checks": [dict(c, passed=check_passed) for c in IS_CHECKS], "warnings": list(warnings or [])}


def _value(result, key):
    return next(f["value"] for f in result["fields"] if f["key"] == key)


def _full_income_values(**overrides):
    """All shipped income-statement keys non-null unless a route-trigger test changes one."""
    values = {"revenue": 100, "cost_of_sales": -60, "gross_profit": 40, "operating_profit": 30,
              "profit_before_tax": 25, "income_tax": -5, "profit_discontinued": 0, "net_profit": 20,
              "eps_basic": 2}
    return values | overrides


# ---- mode() ---------------------------------------------------------------------------------

def test_mode_env():
    from . import merge
    with _env(EXTRACT_MERGE_RUNS=None):
        assert merge.mode() == "off", "default must be off"
    with _env(EXTRACT_MERGE_RUNS="off"):
        assert merge.mode() == "off"
    with _env(EXTRACT_MERGE_RUNS="UNION "):  # case/space tolerant
        assert merge.mode() == "union"
    with _env(EXTRACT_MERGE_RUNS="majority"):
        assert merge.mode() == "majority"
    with _env(EXTRACT_MERGE_RUNS="consensus"):  # a typo must never turn the second run on
        assert merge.mode() == "off"
    print("merge mode env ok")


# ---- union (fresh runs; no stored vote) ------------------------------------------------------

def test_union_lone_value():
    """academedia-shaped field: only run1 answered -> union takes it; both null stays null."""
    from . import merge
    r1, r2 = _run({"revenue": 12103}, check_passed=False), _run({"revenue": None}, check_passed=False)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "revenue") == 12103 and decisions["revenue"] == "run1 (union: only non-null)"
    assert merged["fields"][0]["source"] == {"page": 1, "quote": "revenue 12103"}  # the winner's full field
    merged, decisions = merge.merge_runs(_run({"revenue": None}), _run({"revenue": None}), None, "union")
    assert _value(merged, "revenue") is None and decisions["revenue"] == "null (union: both null)"
    print("merge union lone value ok")


def test_union_conflict_check_then_agree_conf():
    """Two non-null answers: the run whose identity check passed wins even against higher confidence;
    with the same check state, agreeing values (one answer within the band) still pick their copy by
    confidence; a conflict has no signal left (the fold of tie->null and the 0/4
    higher-confidence branch) and publishes null."""
    from . import merge
    r1 = _run({"total_debt": 3821}, conf={"total_debt": 0.8}, check_passed=True)
    r2 = _run({"total_debt": 1659}, conf={"total_debt": 1.0}, check_passed=False)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") == 3821 and decisions["total_debt"] == "run1 (conflict: union: check passed)"
    r1 = _run({"total_debt": 3821}, conf={"total_debt": 1.0}, check_passed=True)  # agree: conf still picks the copy
    r2 = _run({"total_debt": 3820}, conf={"total_debt": 0.8}, check_passed=True)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") == 3821 and decisions["total_debt"] == "run1 (agree: union: higher conf)"
    merged, decisions = merge.merge_runs(r2, r1, None, "union")  # swapped: higher confidence wins wherever it sits
    assert _value(merged, "total_debt") == 3821 and decisions["total_debt"] == "run2 (agree: union: higher conf)"
    r1 = _run({"total_debt": 3821}, conf={"total_debt": 1.0}, check_passed=True)  # cellavision: conflict, conf differs...
    r2 = _run({"total_debt": 1659}, conf={"total_debt": 0.5}, check_passed=True)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") is None  # ...and conf is no signal for a conflict
    f = merged["fields"][0]
    assert f["source"] is None and f["confidence"] == 0.0 and f["evidence"] == []  # extract()'s dropped-field shape
    assert decisions["total_debt"] == "null (union: conflict, no signal -> null)"
    print("merge union conflict order ok")


def test_union_conflict_null_rule():
    """With the same identity-check state, agreeing values are one answer and keep a copy (conf
    decides, a conf tie -> run2), while a conflict has no distinguishing signal -- the
    tie-conflicts score run1 right 1 (academedia 12103) / run2 right 2 (net_insight 39415, 8305) /
    both wrong 0, and the higher-confidence branch scored 0/4 on the measured conflicts
    (bergman_beving, viva_wine and storytel's wrong side against bonava's one hit) -- so any
    same-state conflict publishes null in extract()'s own dropped-field shape. Check-state
    differences still decide (alligo), and the majority voting path never sees this (third vote)."""
    from . import merge
    r1 = _run({"total_debt": 12103}, conf={"total_debt": 0.9}, check_passed=False)  # academedia's shape
    r2 = _run({"total_debt": 12114}, conf={"total_debt": 0.9}, check_passed=False)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") is None and decisions["total_debt"] == "null (union: conflict, no signal -> null)"
    assert merged["fields"][0]["label"] == "total_debt" and merged["fields"][0]["key"] == "total_debt"
    r1 = _run({"total_debt": 81489}, check_passed=True)  # net_insight's shape: both checks pass, conf tie
    r2 = _run({"total_debt": 39415}, check_passed=True)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") is None and decisions["total_debt"] == "null (union: conflict, no signal -> null)"
    r1 = _run({"total_debt": 1002}, conf={"total_debt": 0.9}, check_passed=False)  # viva_wine's shape: conf differs
    r2 = _run({"total_debt": 1203}, conf={"total_debt": 0.85}, check_passed=False)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") is None and decisions["total_debt"] == "null (union: conflict, no signal -> null)"
    r1 = _run({"revenue": 100}, conf={"revenue": 0.9}, check_passed=True)  # agreeing tie: one answer, run2's copy
    r2 = _run({"revenue": 101.5}, conf={"revenue": 0.9}, check_passed=True)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "revenue") == 101.5 and decisions["revenue"] == "run2 (agree: union: tie -> run2)"
    r1 = _run({"revenue": 32703}, conf={"revenue": 1.0}, check_passed=True)  # ericsson: agree, higher conf keeps its copy
    r2 = _run({"revenue": 32703}, conf={"revenue": 0.95}, check_passed=True)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "revenue") == 32703 and decisions["revenue"] == "run1 (agree: union: higher conf)"
    r1 = _run({"total_debt": 3629}, conf={"total_debt": 0.9}, check_passed=False)  # not this branch: checks decide (alligo)
    r2 = _run({"total_debt": 3630}, conf={"total_debt": 0.9}, check_passed=True)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") == 3630 and decisions["total_debt"] == "run2 (agree: union: check passed)"
    print("merge union conflict null rule ok")


def test_union_conflict_balance_sheet_tie():
    """Net Insight's real same-state conflict becomes decidable when exactly one run ties to BS."""
    from . import merge
    r1 = _run({"total_debt": 81489}, check_passed=True)
    r2 = _run({"total_debt": 39415}, check_passed=True)
    r2["fields"][0]["evidence"].append("bs_tie")
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") == 39415
    assert decisions["total_debt"] == "run2 (conflict: union: balance-sheet tie)"
    print("merge balance-sheet tie conflict rule ok")


def test_union_agree_band():
    """Values within +/-2 are one answer; the winner among agreeing runs still goes by check, then
    confidence, then the tie rule (agree -> run2)."""
    from . import merge
    r1 = _run({"revenue": 100}, conf={"revenue": 1.0}, check_passed=False)
    r2 = _run({"revenue": 101.5}, conf={"revenue": 0.9}, check_passed=True)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "revenue") == 101.5 and decisions["revenue"] == "run2 (agree: union: check passed)"
    r2 = _run({"revenue": 101.5}, conf={"revenue": 1.0}, check_passed=False)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")  # both fail the check, conf tie, agree -> run2
    assert _value(merged, "revenue") == 101.5 and decisions["revenue"] == "run2 (agree: union: tie -> run2)"
    print("merge union agree band ok")


# ---- majority (stored answer as the third vote) ----------------------------------------------

def test_majority_votes():
    """>=2 votes on a value wins (null votes as null); the field comes from the winning value's own
    run, run1 before run2 before stored. kabe-shaped: two nulls beat run1's lone 22. bonava-shaped:
    run2 + stored outvote run1's null. A ±2 near-miss still counts as agreement."""
    from . import merge
    stored = _run({"due_within_1_year": None})
    merged, decisions = merge.merge_runs(_run({"due_within_1_year": 22}), _run({"due_within_1_year": None}), stored, "majority")
    assert _value(merged, "due_within_1_year") is None and decisions["due_within_1_year"] == "run2 (majority: run2+stored)"
    stored = _run({"due_within_1_year": 804})
    merged, decisions = merge.merge_runs(_run({"due_within_1_year": None}), _run({"due_within_1_year": 804}), stored, "majority")
    assert _value(merged, "due_within_1_year") == 804 and decisions["due_within_1_year"] == "run2 (majority: run2+stored)"
    stored = _run({"due_within_1_year": 104})
    merged, decisions = merge.merge_runs(_run({"due_within_1_year": 104}), _run({"due_within_1_year": 108}), stored, "majority")
    assert _value(merged, "due_within_1_year") == 104 and decisions["due_within_1_year"] == "run1 (majority: run1+stored)"
    stored = _run({"revenue": 101.5})
    merged, decisions = merge.merge_runs(_run({"revenue": 100}), _run({"revenue": 100}), stored, "majority")
    assert _value(merged, "revenue") == 100 and decisions["revenue"] == "run1 (majority: unanimous)"
    print("merge majority votes ok")


def test_majority_three_way_splits_back_to_union():
    """Three mutually distinct answers (stored null, or a third value) fall back to union over the
    two runs -- including the conflict rule. academedia's real field shape (12103 vs 12114, both
    checks failing, stored null: no third vote to break it) publishes null."""
    from . import merge
    r1, r2 = _run({"total_debt": 12103}, check_passed=False), _run({"total_debt": 12114}, check_passed=False)
    merged, decisions = merge.merge_runs(r1, r2, _run({"total_debt": None}), "majority")
    assert _value(merged, "total_debt") is None
    assert decisions["total_debt"] == "null (3-way split -> union: conflict, no signal -> null)"
    r2 = _run({"total_debt": 12114}, check_passed=True)  # agreeing runs can never reach the fallback (2 votes), so the
    third = _run({"total_debt": 99999}, check_passed=False)  # decided fallback branches are check-state and null only
    merged, decisions = merge.merge_runs(r1, r2, third, "majority")  # no 2-vote value -> union over the runs
    assert _value(merged, "total_debt") == 12114 and decisions["total_debt"] == "run2 (conflict: 3-way split -> union: check passed)"
    print("merge majority 3-way fallback ok")


def test_majority_without_stored_is_union():
    """mode=majority with no stored answer (fresh extraction, or a reviewed one filtered by the
    route) must decide exactly like union."""
    from . import merge
    cases = [(_run({"revenue": None}), _run({"revenue": 5})),
             (_run({"revenue": 22}), _run({"revenue": None})),
             (_run({"revenue": 7}, check_passed=True), _run({"revenue": 9}, check_passed=False))]
    for r1, r2 in cases:
        _, maj = merge.merge_runs(r1, r2, None, "majority")
        _, uni = merge.merge_runs(r1, r2, None, "union")
        assert maj == uni, (maj, uni)
    print("merge majority degenerates to union ok")


# ---- exact skip trigger -----------------------------------------------------------------------

def test_matches_stored_trigger():
    """The exact skip trigger: run1 value-identical to stored on every field (+/-2, null == null)."""
    from . import merge
    values = {"revenue": 100, "cost_of_sales": -60, "gross_profit": 40, "operating_profit": None}
    assert merge.matches_stored(_run(values), _run(values)) is True
    stored = _run({**values, "revenue": 101.5})  # within the band: still identical
    assert merge.matches_stored(_run(values), stored) is True
    for drift in ({"revenue": 103}, {"operating_profit": 1}, {"gross_profit": None}):
        assert merge.matches_stored(_run(values), _run({**values, **drift})) is False, drift
    print("merge exact trigger ok")


def test_merge_is_pure_and_shapes_the_record():
    """merge_runs must not touch its inputs; warnings are prefixed per run and closed by one merge
    summary; the top-level merge block carries mode/runs/decisions."""
    from . import merge
    r1 = _run({"revenue": 100, "gross_profit": 40}, warnings=["revenue: filled from page 1"])
    r2 = _run({"revenue": 103, "gross_profit": None}, warnings=["llm: timeout (pages [1, 2])"])
    snap1, snap2 = copy.deepcopy(r1), copy.deepcopy(r2)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert r1 == snap1 and r2 == snap2, "merge_runs mutated an input"
    assert _value(merged, "revenue") is None  # 100 vs 103: |d| = 3 is outside the band, conf tie -> null
    assert merged["warnings"][0] == "run1: revenue: filled from page 1"
    assert merged["warnings"][1] == "run2: llm: timeout (pages [1, 2])"
    assert merged["warnings"][-1].startswith("merge: union, per-field: ")
    assert "revenue=null (union: conflict, no signal -> null)" in merged["warnings"][-1]
    assert merged["merge"] == {"mode": "union", "runs": 2, "decisions": decisions}
    assert merged["section"] == "income_statement" and merged["fiscal_year"] == 2025  # run1's shell
    assert merged["checks"] == r1["checks"]  # stale on purpose: recheck() replaces them
    print("merge purity + record shape ok")


# ---- a vote must be the same financial question ------------------------------------------------

def _with_field(run, key, **kw):
    """A copy of `run` whose field `key` gained the given keys (unit/period overrides, ...)."""
    r = copy.deepcopy(run)
    next(f for f in r["fields"] if f["key"] == key).update(kw)
    return r


def test_same_question_unit_scale():
    """Two answers agreeing numerically but printed on different unit scales are NOT one answer --
    100 MSEK vs 100 TSEK conflicts and publishes null (the no-signal rule). Equal scale+currency
    under different spellings stays one answer (SEK M == MSEK, KSEK == TSEK, KUSD == 'USD
    thousands', MSEK == 'SEK million'), a currency difference still conflicts (MSEK vs MEUR)."""
    from . import merge
    r1 = _run({"total_debt": 100}, conf={"total_debt": 0.9}, check_passed=True)
    r2 = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.9}, check_passed=True),
                     "total_debt", unit="TSEK")
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") is None, "100 MSEK vs 100 TSEK must not vote together"
    assert decisions["total_debt"] == "null (union: conflict, no signal -> null)"
    for same_unit in ("SEK M", "SEK million"):
        other = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.8}, check_passed=True),
                            "total_debt", unit=same_unit)
        merged, decisions = merge.merge_runs(r1, other, None, "union")
        assert _value(merged, "total_debt") == 100 and "agree" in decisions["total_debt"], same_unit
    r1k = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.9}, check_passed=True),
                      "total_debt", unit="KSEK")
    r2t = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.8}, check_passed=True),
                      "total_debt", unit="TSEK")
    merged, decisions = merge.merge_runs(r1k, r2t, None, "union")
    assert _value(merged, "total_debt") == 100 and "agree" in decisions["total_debt"], "KSEK == TSEK"
    r2u = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.8}, check_passed=True),
                      "total_debt", unit="USD thousands")
    r1u = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.9}, check_passed=True),
                      "total_debt", unit="KUSD")
    merged, decisions = merge.merge_runs(r1u, r2u, None, "union")
    assert _value(merged, "total_debt") == 100 and "agree" in decisions["total_debt"], "KUSD == USD thousands"
    r2e = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.9}, check_passed=True),
                      "total_debt", unit="MEUR")
    merged, decisions = merge.merge_runs(r1, r2e, None, "union")
    assert _value(merged, "total_debt") is None, "MSEK vs MEUR is not the same answer"
    print("merge same-question unit scale ok")


def test_same_question_period_and_unknown_metadata():
    """Same value but a different period is not one answer (2025 column vs 2024 column); a
    unit/period present on one side only does not count as the same (unknown is not proof); two
    sides neither of which printed it keep agreeing (nothing contradicts); null == null is the
    null agreement regardless of metadata."""
    from . import merge
    r1 = _run({"total_debt": 100}, conf={"total_debt": 0.9}, check_passed=True)
    r2 = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.9}, check_passed=True),
                     "total_debt", period="2024")
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") is None, "2025 vs 2024 column is not the same question"
    r2 = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.9}, check_passed=True),
                     "total_debt", unit=None)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") is None, "a known vs an unknown unit is not a confirmed match"
    r2 = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.8}, check_passed=True),
                     "total_debt", unit=None, period=None)
    r1 = _with_field(r1, "total_debt", unit=None, period=None)
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert _value(merged, "total_debt") == 100, "nothing printed on either side: the values still agree"
    merged, decisions = merge.merge_runs(_run({"total_debt": None}), _run({"total_debt": None}), None, "union")
    assert _value(merged, "total_debt") is None and decisions["total_debt"] == "null (union: both null)"
    print("merge same-question period/unknown ok")


def test_matches_stored_same_question():
    """The exact skip trigger is a same-question comparison too -- different unit scale or
    period, or a stored answer from another financial year/basis/report, never skips run 2; equal
    scale under different spellings still matches."""
    from . import merge
    run1 = _run({"revenue": 100, "gross_profit": 40})
    assert merge.matches_stored(run1, _run({"revenue": 100, "gross_profit": 40})) is True
    stored = _with_field(_run({"revenue": 100, "gross_profit": 40}), "revenue", unit="TSEK")
    assert merge.matches_stored(run1, stored) is False, "100 MSEK vs 100 TSEK must not skip run 2"
    stored = _with_field(_run({"revenue": 100, "gross_profit": 40}), "revenue", unit="SEK million")
    assert merge.matches_stored(run1, stored) is True, "MSEK == SEK million: same question"
    stored = _with_field(_run({"revenue": 100, "gross_profit": 40}), "revenue", period="2024")
    assert merge.matches_stored(run1, stored) is False
    stored = _run({"revenue": 100, "gross_profit": 40}) | {"fiscal_year": 2024}
    assert merge.matches_stored(run1, stored) is False, "stored from another fiscal year must not skip"
    stored = _run({"revenue": 100, "gross_profit": 40}) | {"maturity_basis": "undiscounted"}
    assert merge.matches_stored(run1, stored) is False, "stored on another basis must not skip"
    stored = _run({"revenue": 100, "gross_profit": 40}) | {"report_id": "lib-someone_else_2025"}
    assert merge.matches_stored(run1, stored) is False, "another report's answer must not skip"
    stored = _run({"revenue": 100, "gross_profit": 40}) | {"maturity_basis": None}
    assert merge.matches_stored(run1, stored) is False, "metadata unknown on the stored side: no skip"
    print("merge matches-stored same-question ok")


def test_stored_vote_must_be_same_question():
    """The stored third vote only counts when it is the same financial question -- same
    report, section, fiscal_year, maturity_basis. A stored answer missing the metadata or read on
    another one sits out, and the merge block says why ('not eligible: <reason>')."""
    from . import merge
    r1, r2 = _run({"revenue": 100, "gross_profit": 40}), _run({"revenue": 250, "gross_profit": None})
    stored = _run({"revenue": 250, "gross_profit": 39}) | {"fiscal_year": 2024}
    merged, decisions = merge.merge_runs(r1, r2, stored, "majority")
    assert merged["merge"]["stored_vote"].startswith("not eligible: "), merged["merge"]
    assert "fiscal_year" in merged["merge"]["stored_vote"]
    assert _value(merged, "revenue") is None, "without the stored vote the conflict has no signal"
    stored = _run({"revenue": 250, "gross_profit": 39}) | {"maturity_basis": "undiscounted"}
    merged, decisions = merge.merge_runs(r1, r2, stored, "majority")
    assert "maturity_basis" in merged["merge"]["stored_vote"]
    assert _value(merged, "revenue") is None
    stored = _run({"revenue": 250, "gross_profit": 39}) | {"maturity_basis": None}
    merged, decisions = merge.merge_runs(r1, r2, stored, "majority")
    assert "no maturity_basis" in merged["merge"]["stored_vote"], "missing metadata: not eligible"
    assert _value(merged, "revenue") is None
    stored = _run({"revenue": 250, "gross_profit": 39}) | {"section": "debt_maturity"}
    merged, decisions = merge.merge_runs(r1, r2, stored, "majority")
    assert "section" in merged["merge"]["stored_vote"]
    stored = _run({"revenue": 250, "gross_profit": 39}) | {"report_id": "lib-other_2025"}
    merged, decisions = merge.merge_runs(r1, r2, stored, "majority")
    assert "report" in merged["merge"]["stored_vote"]
    eligible = _run({"revenue": 250, "gross_profit": 39})
    merged, decisions = merge.merge_runs(r1, r2, eligible, "majority")
    assert "stored_vote" not in merged["merge"], "an eligible stored vote needs no note"
    assert _value(merged, "revenue") == 250 and decisions["revenue"] == "run2 (majority: run2+stored)"
    print("merge stored-vote eligibility ok")


def test_majority_scale_mismatch_does_not_stack():
    """With the unit scales differing, the two 100s are different answers and never give a
    2-vote majority together; only the same-scale pair votes as one."""
    from . import merge
    r1 = _run({"total_debt": 100}, conf={"total_debt": 0.9}, check_passed=True)
    r2 = _with_field(_run({"total_debt": 100}, conf={"total_debt": 0.9}, check_passed=True),
                     "total_debt", unit="TSEK")
    stored = _run({"total_debt": 100})
    merged, decisions = merge.merge_runs(r1, r2, stored, "majority")
    assert _value(merged, "total_debt") == 100 and decisions["total_debt"] == "run1 (majority: run1+stored)", \
        "MSEK pair votes, the TSEK answer does not join it"
    stored = _with_field(_run({"total_debt": 100}), "total_debt", unit="TSEK")
    merged, decisions = merge.merge_runs(r1, r2, stored, "majority")
    assert _value(merged, "total_debt") == 100 and decisions["total_debt"] == "run2 (majority: run2+stored)", \
        "now the TSEK pair votes and the MSEK answer does not join it"
    print("merge majority scale mismatch ok")


def test_prior_year_and_buckets_follow_run1():
    """Run1's prior_year/buckets_by_year attachments are deterministic reads of run1's own
    rows, so they ride along only while every field they cover still carries run1's answer -- a
    value within the band on the same unit/period, whoever's copy of it won (an agreeing tie
    flips no verdict). Once a covered field is no longer that answer (a conflict-null, another
    run's different value, a different unit scale) the attachment is dropped, with a warning."""
    from . import merge
    r1 = _run({"total_debt": 100, "due_within_1_year": 40}, warnings=[])
    r1["prior_year"] = {"total_debt": 90, "due_within_1_year": 35}
    r1["buckets_by_year"] = {"2026": 30, "2027-2030": 50, "later": 20}
    r2 = _run({"total_debt": 100, "due_within_1_year": 41})
    merged, decisions = merge.merge_runs(r1, r2, None, "union")
    assert "prior_year" in merged and "buckets_by_year" in merged, "agreeing copies: still run1's answer"
    assert not any(w.startswith("merge: prior_year") or w.startswith("merge: buckets_by_year")
                   for w in merged["warnings"])
    r1f = _with_field(_run({"total_debt": 100, "due_within_1_year": 40}, check_passed=False), "total_debt")
    r1f["prior_year"] = {"total_debt": 90, "due_within_1_year": 35}
    r1f["buckets_by_year"] = {"2026": 30, "2027-2030": 50, "later": 20}
    r2 = _run({"total_debt": 200, "due_within_1_year": 40}, check_passed=True)  # check passed: 200 wins
    merged, decisions = merge.merge_runs(r1f, r2, None, "union")
    assert _value(merged, "total_debt") == 200 and decisions["total_debt"] == "run2 (conflict: union: check passed)"
    assert "prior_year" not in merged, "the attachment closed on run1's 100, the answer published is 200"
    assert "buckets_by_year" not in merged, "its gate closes on total_debt, which is no longer run1's"
    assert any(w == "merge: prior_year dropped -- total_debt is no longer run1's answer" for w in merged["warnings"])
    assert any(w == "merge: buckets_by_year dropped -- total_debt is no longer run1's answer" for w in merged["warnings"])
    r1f["prior_year"] = {"due_within_1_year": 35}  # a prior year that only covers an agreeing field stays
    merged, _ = merge.merge_runs(r1f, r2, None, "union")
    assert "prior_year" in merged and merged["prior_year"] == {"due_within_1_year": 35}
    assert any(w.startswith("merge: buckets_by_year dropped") for w in merged["warnings"])
    r1n = _run({"total_debt": 12103, "due_within_1_year": 40}, check_passed=False)
    r1n["prior_year"] = {"total_debt": 90}
    r2n = _run({"total_debt": 12114, "due_within_1_year": None}, check_passed=False)
    merged, _ = merge.merge_runs(r1n, r2n, None, "union")
    assert "prior_year" not in merged, "a nulled field is not run1's answer either: the attachment goes"
    r1f["prior_year"] = {"total_debt": 90}
    r2s = _with_field(_run({"total_debt": 100, "due_within_1_year": 40}, check_passed=True), "total_debt", unit="TSEK")
    r2s = _with_field(r2s, "total_debt", value=100)  # same number, different scale: check passed wins it
    merged, _ = merge.merge_runs(r1f, r2s, None, "union")
    assert _value(merged, "total_debt") == 100
    assert "prior_year" not in merged, "100 TSEK is not the answer run1's attachment closed on"
    print("merge prior_year/buckets follow run1 ok")


# ---- kb: per-run records that are not sections ------------------------------------------------

def _seed_kb(kb):
    stem = "acme_2025"
    meta = {"company": "Acme", "fiscal_year": 2025, "language": "en", "source_url": None,
            "pages": 2, "sha256": "beef", "filename": "acme.pdf"}
    kb.save_report(stem, meta, ["revenue 100\ngross_profit 40", "second page"])
    kb.save_extraction(stem, "income_statement", _run({"revenue": 100, "gross_profit": 40}))
    return stem


def test_save_run_records_are_not_sections():
    from . import kb
    with tempfile.TemporaryDirectory() as tmp, _env(KB_DIR=tmp):
        kb._pages_cache.clear(), kb._bm25_cache.clear(), kb._vecs.clear()
        stem = _seed_kb(kb)
        kb.save_run(stem, "income_statement", 1, _run({"revenue": 111, "gross_profit": 44}))
        kb.save_run(stem, "income_statement", 2, _run({"revenue": 222, "gross_profit": 55}))
        d = kb.kb_dir() / stem / "extractions"
        assert json.loads((d / "income_statement.run1.json").read_text(encoding="utf-8"))["fields"][0]["value"] == 111
        assert (d / "income_statement.run2.json").is_file()
        entry = next(e for e in kb.entries() if e["stem"] == stem)
        assert entry["sections"] == ["income_statement"], f"run records leaked into sections: {entry['sections']}"
        facts = [c for c in kb.chunks(stem) if c["start"] == -1]
        assert len(facts) == 2, f"run records doubled the fact chunks: {len(facts)}"
        assert {c["text"] for c in facts} and all("111" not in c["text"] and "222" not in c["text"] for c in facts)
    print("kb save_run records not sections ok")


# ---- /extract route wiring ---------------------------------------------------------------------

def _setup_route(tmp):
    os.environ["KB_DIR"] = tmp
    import app as app_mod
    from fastapi.testclient import TestClient
    app_mod.reports["lib-acme_2025"] = {"report_id": "lib-acme_2025", "filename": "acme.pdf", "pages": 3,
                                        "company": "Acme", "fiscal_year": 2025, "stem": "acme_2025"}
    return app_mod, TestClient(app_mod.app)


def _stub_model(app_mod, results):
    """Stub the model boundary: extract_mod.extract pops `results` in order (an extra call fails the
    test), _llm_configured/report_texts/candidate_pages stand in for the configured-provider path."""
    calls = []

    def fake_extract(texts, pages, schema, report, page_select_hints=None):
        calls.append({"texts": texts, "pages": pages, "page_select_hints": page_select_hints})
        assert len(calls) <= len(results), f"extract called {len(calls)}x, expected <= {len(results)}"
        return copy.deepcopy(results[len(calls) - 1])

    orig = (app_mod.extract_mod.extract, app_mod._llm_configured, app_mod.report_texts, app_mod.locate.candidate_pages)
    app_mod.extract_mod.extract = fake_extract
    app_mod._llm_configured = lambda: True
    app_mod.report_texts = lambda rid: ["revenue page text", "page two", "page three"]
    app_mod.locate.candidate_pages = lambda texts, schema, **kw: [1, 2]  # kw: the caller passes fiscal_year
    return calls, orig


def _teardown_route(app_mod, orig):
    app_mod.extract_mod.extract, app_mod._llm_configured, app_mod.report_texts, app_mod.locate.candidate_pages = orig
    app_mod.reports.pop("lib-acme_2025", None)


def _post(client):
    return client.post("/api/reports/lib-acme_2025/extract", json={"section": "income_statement"})


def _run_files():
    from . import kb
    d = kb.kb_dir() / "acme_2025" / "extractions"
    return sorted(p.name for p in d.glob("*.run*.json")) if d.is_dir() else []


def test_route_off_is_the_old_route():
    """EXTRACT_MERGE_RUNS off (default): one model call, no run records, no merge key -- the route
    is byte-identical to the pre-merge route."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp, _env(EXTRACT_MERGE_RUNS=None):
        app_mod, client = _setup_route(tmp)
        runs = [_run({"revenue": 100, "gross_profit": 40}), _run({"revenue": 999, "gross_profit": 1})]
        calls, orig = _stub_model(app_mod, runs)
        try:
            r = _post(client)
            assert r.status_code == 200, r.text
            x = r.json()
            assert len(calls) == 1, f"off mode must not run the second extraction ({len(calls)} calls)"
            assert "merge" not in x, x.get("merge")
            assert _value(x, "revenue") == 100 and _value(x, "gross_profit") == 40
            assert _run_files() == [], _run_files()
            assert not (kb.kb_dir() / "acme_2025" / "extractions" / "income_statement.json").exists() or \
                "merge" not in json.loads((kb.kb_dir() / "acme_2025" / "extractions" / "income_statement.json").read_text(encoding="utf-8"))
            assert "issues" in x  # decorate ran, as before
        finally:
            _teardown_route(app_mod, orig)
    print("route off unchanged ok")


def test_route_union_two_runs_two_records():
    """union: two extractions, both raw answers on disk, merged per the rules, merge block + summary
    warning on the merged result and in the saved section file."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp, _env(EXTRACT_MERGE_RUNS="union"):
        app_mod, client = _setup_route(tmp)
        runs = [_run({"revenue": 100, "gross_profit": 40}, warnings=["revenue: filled from page 1"]),
                _run({"revenue": 250, "cost_of_sales": -60}, warnings=["llm: slow (pages [1, 2])"])]
        calls, orig = _stub_model(app_mod, runs)
        try:
            r = _post(client)
            assert r.status_code == 200, r.text
            x = r.json()
            assert len(calls) == 2, f"union must run the extraction twice ({len(calls)} calls)"
            assert calls[0]["pages"] == calls[1]["pages"] == [1, 2]  # same window both runs
            assert _value(x, "revenue") is None  # conflict (100 vs 250), checks pass -> no signal, null
            assert _value(x, "gross_profit") == 40  # only run1 answered
            assert _value(x, "cost_of_sales") == -60  # only run2 answered
            assert x["merge"]["mode"] == "union" and x["merge"]["runs"] == 2
            assert x["merge"]["decisions"]["revenue"] == "null (union: conflict, no signal -> null)"
            assert x["warnings"][0] == "run1: revenue: filled from page 1"
            assert x["warnings"][1] == "run2: llm: slow (pages [1, 2])"
            assert x["warnings"][-1].startswith("merge: union, per-field: ")
            assert _run_files() == ["income_statement.run1.json", "income_statement.run2.json"], _run_files()
            saved = json.loads((kb.kb_dir() / "acme_2025" / "extractions" / "income_statement.json").read_text(encoding="utf-8"))
            assert saved["merge"]["runs"] == 2 and _value(saved, "revenue") is None
            assert saved["checks"] and all("name" in c for c in saved["checks"])  # recheck() filled them
            assert "issues" in saved  # decorate ran on the merged result
        finally:
            _teardown_route(app_mod, orig)
    print("route union two runs ok")


def test_route_majority_skips_on_exact_match():
    """majority + a pipeline-generated stored answer identical to run1 field by field: one call, no
    run records, merged == run1 with the skip sentence."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp, _env(EXTRACT_MERGE_RUNS="majority"):
        app_mod, client = _setup_route(tmp)
        kb.save_extraction("acme_2025", "income_statement", _run({"revenue": 100, "gross_profit": 40}))
        runs = [_run({"revenue": 100, "gross_profit": 40}), _run({"revenue": 999, "gross_profit": 1})]
        calls, orig = _stub_model(app_mod, runs)
        try:
            r = _post(client)
            assert r.status_code == 200, r.text
            x = r.json()
            assert len(calls) == 1, f"exact trigger must skip the second run ({len(calls)} calls)"
            assert _value(x, "revenue") == 100
            assert x["merge"] == {"mode": "majority", "runs": 1,
                                  "decisions": {f["key"]: "run1 (matches stored)" for f in x["fields"]}}
            assert "merge: run1 matches the stored answer field by field; second run skipped" in x["warnings"]
            assert _run_files() == [], _run_files()
        finally:
            _teardown_route(app_mod, orig)
    print("route majority skip ok")


def test_route_majority_stored_votes_when_pipeline_generated():
    """majority with a usable stored answer: it votes. Stored + run2 agree on 804, run1 answered
    null -> 804 wins with run2's field. The exact trigger does not fire (run1 differs)."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp, _env(EXTRACT_MERGE_RUNS="majority"):
        app_mod, client = _setup_route(tmp)
        kb.save_extraction("acme_2025", "income_statement", _run({"revenue": 804, "gross_profit": None}))
        runs = [_run({"revenue": None, "gross_profit": 40}),
                _run({"revenue": 804, "gross_profit": 39})]
        calls, orig = _stub_model(app_mod, runs)
        try:
            r = _post(client)
            assert r.status_code == 200, r.text
            x = r.json()
            assert len(calls) == 2, "run1 != stored -> the second run must happen"
            assert _value(x, "revenue") == 804 and x["merge"]["decisions"]["revenue"] == "run2 (majority: run2+stored)"
            assert _value(x, "gross_profit") == 40 and x["merge"]["decisions"]["gross_profit"] == "run1 (majority: run1+run2)"  # 40 vs 39: within the band
            assert x["merge"]["runs"] == 2
            assert _run_files() == ["income_statement.run1.json", "income_statement.run2.json"]
        finally:
            _teardown_route(app_mod, orig)
    print("route majority stored vote ok")


def test_route_retry_hints_only_on_failed_or_null_first_run():
    """PAGE_SELECT_HINTS=retry keeps run 1 ordinary and gives run 2 markers only after the
    first identity check fails or a schema field is null; the merge records that provenance."""
    with tempfile.TemporaryDirectory() as tmp, _env(EXTRACT_MERGE_RUNS="majority", PAGE_SELECT_HINTS="retry"):
        app_mod, client = _setup_route(tmp)
        runs = [_run(_full_income_values(), check_passed=False),
                _run(_full_income_values(), check_passed=True)]
        calls, orig = _stub_model(app_mod, runs)
        try:
            r = _post(client)
            assert r.status_code == 200, r.text
            x = r.json()
            assert [call["page_select_hints"] for call in calls] == [False, True], calls
            assert x["merge"]["hints"] == "run2", x["merge"]
        finally:
            _teardown_route(app_mod, orig)
    print("route retry hints on failed first run ok")


def test_route_retry_hints_on_null_first_run():
    """A passed first identity check still retries with markers when a schema field is null."""
    with tempfile.TemporaryDirectory() as tmp, _env(EXTRACT_MERGE_RUNS="majority", PAGE_SELECT_HINTS="retry"):
        app_mod, client = _setup_route(tmp)
        runs = [_run(_full_income_values(profit_discontinued=None), check_passed=True),
                _run(_full_income_values(), check_passed=True)]
        calls, orig = _stub_model(app_mod, runs)
        try:
            r = _post(client)
            assert r.status_code == 200, r.text
            assert [call["page_select_hints"] for call in calls] == [False, True], calls
        finally:
            _teardown_route(app_mod, orig)
    print("route retry hints on null first run ok")


def test_route_retry_hints_preserves_majority_exact_skip():
    """The existing majority exact-match trigger still wins before retry eligibility: one
    unhinted first run, no raw records, and no fabricated hints marker."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp, _env(EXTRACT_MERGE_RUNS="majority", PAGE_SELECT_HINTS="retry"):
        app_mod, client = _setup_route(tmp)
        stored = _run(_full_income_values())
        kb.save_extraction("acme_2025", "income_statement", stored)
        calls, orig = _stub_model(app_mod, [copy.deepcopy(stored)])
        try:
            r = _post(client)
            assert r.status_code == 200, r.text
            x = r.json()
            assert [call["page_select_hints"] for call in calls] == [False], calls
            assert x["merge"]["runs"] == 1 and "hints" not in x["merge"], x["merge"]
        finally:
            _teardown_route(app_mod, orig)
    print("route retry hints preserves exact skip ok")


if __name__ == "__main__":
    test_mode_env()
    test_union_lone_value()
    test_union_conflict_check_then_agree_conf()
    test_union_conflict_null_rule()
    test_union_conflict_balance_sheet_tie()
    test_union_agree_band()
    test_majority_votes()
    test_majority_three_way_splits_back_to_union()
    test_majority_without_stored_is_union()
    test_matches_stored_trigger()
    test_same_question_unit_scale()
    test_same_question_period_and_unknown_metadata()
    test_matches_stored_same_question()
    test_stored_vote_must_be_same_question()
    test_majority_scale_mismatch_does_not_stack()
    test_prior_year_and_buckets_follow_run1()
    test_merge_is_pure_and_shapes_the_record()
    test_save_run_records_are_not_sections()
    test_route_off_is_the_old_route()
    test_route_union_two_runs_two_records()
    test_route_majority_skips_on_exact_match()
    test_route_majority_stored_votes_when_pipeline_generated()
    test_route_retry_hints_only_on_failed_or_null_first_run()
    test_route_retry_hints_on_null_first_run()
    test_route_retry_hints_preserves_majority_exact_skip()
    print("merge self-check ok")
