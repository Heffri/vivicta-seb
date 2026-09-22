# Accuracy — the honest version

How well the parser reads the `debt_maturity` note, measured several different ways. The README
carries the headline; this is the full picture, including what the numbers do *not* mean.

**Stored-library scores and first-extraction scores are two different claims.** They are kept
separate here, and the error *nature* is separate again.

**1) The stored library (curated).** `data/kb/` holds 105 stored `debt_maturity` extractions,
republished after every pipeline change under a "nothing loses on the hand-verified labels" gate.
That gate is exactly why this number is *not* a first-pass rate:

```bash
python eval/run.py --stored-kb data/kb --no-fail   # zero model calls, offline, reproducible
```

- Values **328/368 (89.1%)** — 272 scored `debt_maturity` rows (of 276 hand-verified across 106
  companies: the Mid Cap hardening universe plus the large-cap originals), plus 96
  `income_statement` rows (income alone: 96/96 values, 92/92 cited pages)
- Cited pages **263/313 (84.0%)** (scored only where a value is cited)
- Debt section alone: values **232/272 (85.3%)**, pages **171/221 (77.4%)** — the headline number
  is pulled up by the income section; the debt number is the honest one for the scoped section
- Offline labelled-page coverage (all 276 debt rows with a page): locator candidates **263/276
  (95.3%)** → candidates plus the deterministic full-text field sweep **268/276 (97.1%)**
  (see [`docs/acrylic/evidence/w198.md`](acrylic/evidence/w198.md), which reached 264/276, and
  [`docs/acrylic/evidence/w203.md`](acrylic/evidence/w203.md), whose wordlist fixes took it to
  268/276 — the remaining 8 are named structural table-layout gaps, not missing synonyms)

Per-section figures come from `python scripts/eval_breakdown.py --stored-kb data/kb --section debt_maturity`.

**2) First extraction (no labels at run time).** Three measured batches where the pipeline ran
without label access and was scored afterwards:

- 24 companies the locator had just made reachable: **9 → 14** fully-labelled companies
  ([`docs/acrylic/evidence/v124.md`](acrylic/evidence/v124.md))
- 18 newly-labelled stems: stored 16/40 → **19/40** label fields after that round's publish set —
  the raw fresh runs scored 14/40 ([`docs/acrylic/evidence/v136.md`](acrylic/evidence/v136.md))
- 28 remaining value-miss stems: 23/69 → **31/69** fields, pages 17/62 → 23/62
  ([`docs/acrylic/evidence/v160.md`](acrylic/evidence/v160.md))

**3) What the errors are.** Of the 40 debt value misses in the stored library: **33 are empty**
(the field was not read, or was honestly declined) and **7 are non-empty but wrong**
(`python scripts/eval_breakdown.py --stored-kb data\kb --section debt_maturity`: A 28 + D 5 stored
nulls vs B 5 + D 2 — dynavox 896.3 joined the wrong side after v166's republish). An audit of
the disputed label candidates found **0 label errors**, **2 report-internal disagreements** (the
report itself prints two inconsistent totals — Green Landscaping, Volati) and **7 hard cases**
where the label is right and a named, bounded mechanism gap blocked the read
([`docs/acrylic/evidence/v154.md`](acrylic/evidence/v154.md)). Scope calls that depend on
Kristian's definitions (carrying vs undiscounted, leases in/out) are disclosed per company, not
silently resolved.

**4) Held-out first extraction (Small Cap, blind labels).** There are two separate ten-report
FY2025 samples, each labelled before its outputs were opened. **Round 1** (`seed=1`) scored
**26/40 (65.0%)** values and **8/17 (47.1%)** cited pages at the shipped default (5 empty, 9
non-empty-wrong); it was subsequently used to develop guard/tuning work and is no longer the
current held-out benchmark. **Round 2** (`seed=2`, excluding round 1's extracted-or-skipped
companies) is the current held-out benchmark: shipped-default `off` scored **36/40 (90.0%)** values
and **14/17 (82.4%)** cited pages (**1 empty**, **3 non-empty-wrong**), and the same frozen labels
under non-default `majority` scored the same 36/40 and 14/17. A later decision run with the bounded
`EXTRACT_SECOND_PASS=1` scored **29/40** values and **12/17** pages (**3 empty**, **8
non-empty-wrong**) at an average **+2.5 calls / +18.4 model seconds per report**, so that switch
remains off by default. Neither n=10 measurement is a market-accuracy claim, and neither is
extrapolated into one; see [`docs/acrylic/evidence/v178.md`](acrylic/evidence/v178.md),
[`docs/acrylic/evidence/v190.md`](acrylic/evidence/v190.md), and
[`docs/acrylic/evidence/w211.md`](acrylic/evidence/w211.md).

**5) The boundary.** The 106 labelled companies have been used repeatedly to debug and tune this
pipeline — none of the numbers above is an out-of-the-box market-accuracy claim, and we do not
present them as one.

**6) What we've tried and ruled out.** Two alternatives were benchmarked: **Laya** (zero-shot
classifier) scored **79.6%** at its default threshold — below the **80.6%** always-applicable naive
baseline — and **69.9%** after train-calibrated thresholding; a zero-shot miss, not a verdict on a
fine-tuned model. **Docling**'s PDF conversion took **1710 s** for a 163-page report against **6.3 s**
for this parser (**~271× slower**); no accuracy comparison was run, so the only supported conclusion
is speed. Detail: [`docs/acrylic/evidence/m02.md`](acrylic/evidence/m02.md), and the runnable
benchmarks in [`experiments/`](../experiments).

Other checks:

```bash
python eval/run.py --dry-run       # scores the fixture, no backend needed
python eval/run.py                 # runs the real pipeline over data/reports + eval/labels.csv
python scripts/random_check.py --n 10 --seed 1   # fetches 10 untuned Large Cap reports; how many parse at full confidence
```
