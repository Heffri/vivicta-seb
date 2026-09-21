# v185 — held-out wrong-value attribution

## Scope, method, and measurement

This is an offline attribution of the frozen held-out snapshots, not a re-extraction
or tuning exercise. I read the held-out labels, the two saved output groups, their
page text and warnings, then recomputed `locate.candidate_pages` from the saved page
text. No model, API, network, PDF download, label, pipeline, or data write occurred.
No UAW code was copied: this lane changes documentation only.

The default-off snapshot reproduces **26/40 (65.0%)** values and **8/17 (47.1%)**
cited pages: **9 non-empty wrong values**, **5 empty misses**, and one additional
right-value/wrong-page result (INQ `due_within_1_year`). The non-default `majority`
snapshot is **27/40** and **8/17**; the sole value change is Sedana Medical's false
`4,697` becoming null because both of its new raw runs answered null.

## Non-empty wrong values (9)

`p.` is a report page. “Existing guard” names the guard that covers the failure
family, even where its input boundary prevents it from firing.

| Company / field | Label | Default-off read | Attribution: row/column versus label | Existing guard or absence | Similar stored-library precedent |
| --- | --- | --- | --- | --- | --- |
| Balco Group / `due_within_1_year` | `21,295` (p.90, `Total current borrowings`) | `28,157` (p.101, `Borrowings 7,039 21,118 56,314 482,039 0`) | It sums the first two columns (7,039 + 21,118) of the **Parent Company** table; the Group row on p.90 is a different carrying/current total. | `_scope_reason` / parent guard (v111) should refuse it, but the actual `THE PARENT COMPANY'S NOTES` heading ends on p.100; the same-page upward walk on p.101 returns `unknown`. | **v111** fixed Momentum parent-table buckets; same entity-scope family. |
| Balco Group / `due_1_to_5_years` | `null` (no carrying bucket label) | `538,353` (p.101, same row) | It sums the parent table's 1–2 and 2–5 columns (56,314 + 482,039), inventing a Group bucket. | Same missed parent guard. | **v111**. |
| Balco Group / `due_after_5_years` | `null` | `0` (p.101, same row) | It takes the parent table's `More than 5 years` zero. | Same missed parent guard. | **v111**. |
| G5 Entertainment / `total_debt` | `0` (p.94, `G5 does not have any loan financing`) | `1,282` (p.92, `Total 1,282 1,803`) | The number is the total of a lease-liability maturity schedule immediately following the leased-premises roll-forward, not a Group borrowing total. | Existing wrong-table scope family (v103) does not fire: final citation classification is `unknown`, because the titleless/torn local context supplies no accepted scope marker. | **v103** rejected named undiscounted lease/all-liability tables (Smartcraft, BioInvent); this is the unmarked variant. |
| G5 Entertainment / `due_within_1_year` | `null` | `384` (p.92, `Within one year 384 685`) | Current column of the same lease schedule. | Same missed scope guard. | **v103**. |
| G5 Entertainment / `due_1_to_5_years` | `null` | `897` (p.92, `Between 1 and 5 years ... 897 0`) | 1–5-year column of the same lease schedule. | Same missed scope guard. | **v103**. |
| G5 Entertainment / `due_after_5_years` | `null` | `0` (p.92, same row) | >5-year column of the same lease schedule. | Same missed scope guard. | **v103**. |
| Keo Capital / `total_debt` | `15,596` (p.82, `Loan payable Co-investor - KEO`) | `0` (p.86, `The Company is now a bank debt free company.`) | A Company-level bank-debt sentence overrides the Group/co-investor payable; p.86 itself also says that Maha entered a Keo loan agreement. This is neither a year nor unit error. | **No Group-versus-Company prose-zero guard.** `_stated_zero` accepts the negation/loan wording, then the citation scope gate deliberately skips a stated zero. | No exact repaired example in the 105 reports. **v134** is adjacent only: it protects a known-label printed dash, not a contradictory Company prose zero. |
| Sedana Medical / `total_debt` | `null` | `4,697` (p.57, `Total 4,697 5,917`) | Generic total in Note 24 **Leases**: current lease liabilities 2,812 + non-current lease liabilities 1,885. `bs_tie` corroborates those same lease rows but cannot establish that a lease-only note is the requested borrowing total. | **No standalone generic-total/lease-note scope guard.** The wrong-table guard needs a table classification; the balance-sheet tie is intentionally evidence, not a scope decision. | No like-for-like rejection. **v166** is the boundary: it found 11 lease-inclusive balance-sheet ties that are legitimate, so a broad “lease = reject” rule would regress. |

### Wrong-value category totals and smallest guards

| Category | Wrong values | Smallest viable guard | Replay estimate |
| --- | ---: | --- | --- |
| Parent-note continuation across a page break (Balco) | 3 | Extend the v111 parent-section walk across **only** a terminal `Parent Company Notes` continuation header, and stop at a new Group/Consolidated heading. | Do not use a plain previous-page word scan: it also sees parent-company prose before four correct Cloetta fields. The exact terminal-heading version is narrower but needs a full replay before a zero-regression claim. |
| Unmarked lease maturity schedule (G5) | 4 | Before accepting a generic maturity row, require either a debt/carrying signal or reject a local lease-only roll-forward/table context with no debt row. | Medium risk. v103's marker-based form had zero regressions, but v166 documents legitimate lease-inclusive debt totals; the new contextual predicate needs replay and counterexamples. |
| Company-scoped stated zero despite a Group/co-investor payable (Keo) | 1 | Reject a Company-level prose zero only when the same page also gives a nonzero loan-payable/Keo-loan contradiction; do not require the word “Group” globally. | Low for that exact predicate: the current 105 reports contain seven stored zero totals and none combines a Company-scoped zero quote with a nonzero `Loan payable` row. Still replay it. |
| Generic lease-note total supported by `bs_tie` (Sedana) | 1 | For an otherwise generic `Total`, refuse it when the local heading is lease-only and its balance-sheet proof consists solely of lease rows; retain named `total interest-bearing`/borrowings rows. | Promising but must be narrow. In the current 105, no stored `Total`-style `bs_tie` has only lease components; RaySearch is excluded because its source is explicitly `Total interest-bearing liabilities`. |

Thus **7/9** wrong values fall in an existing scope-guard family that should have
refused the read (3 parent continuation + 4 lease schedule), and **2/9** expose a
missing direct guard (Company prose zero; generic lease-note total).

## Empty misses (5)

The snapshots predate v181, so they contain no `missing_reason` attachment. Under
v181's current final-null code table, each receives `not_found`: none has an
`absent_in_table`, off-grid, straddle, non-current-only, lease-table-only, or
parent-only event. The code is therefore honest but not diagnostic enough to
separate model silence from a dropped candidate read.

| Company / field | Label | `locate.candidate_pages` result | Why no value was retained | v181 code |
| --- | --- | --- | --- | --- |
| Annehem Fastigheter / `due_within_1_year` | `498.1` (p.85, `varav kortfristiga räntebärande skulder 498,1`) | p.85 is rank **1** (candidate hit) | The ordinary window includes p.85 and there are no warnings: the model simply left the printed current-debt row empty. | `not_found` |
| INQ Group / `total_debt` | `27,889` (p.41, `Total interest bearing liabilities`) | p.41 is rank **6** (candidate hit) | Default one-pass reads only its first two pages, p.23–24; p.41 is ranked but never shown in that full-text window, and there is no warning. | `not_found` |
| INQ Group / `due_1_to_5_years` | `25,532` (p.42, financing reconciliation) | p.42 is rank **3** (candidate hit) | p.42 is outside the default p.23–24 window. The model nevertheless found `25,532` in p.23's `Borrowings` row, but the same-row guard dropped it because that row labels the total borrowings, not the 1–5 field; the bucket-header reader did not map the `0–3 months` header. | `not_found` |
| Keo Capital / `due_within_1_year` | `0` (p.86, dash in `Loan payable`) | p.86 is rank **1** (candidate hit) | No field was retained. The column attempt on the p.86 all-liabilities/undiscounted total was rejected by the over-valve after negative values compared as greater than the negative total (`-1,089`, `-15,596` versus `-16,685`). | `not_found` |
| Keo Capital / `due_1_to_5_years` | `15,596` (p.86, `Loan payable`) | p.86 is rank **1** (candidate hit) | Same rejected signed all-liabilities column attempt; no named v181 scope event was recorded. | `not_found` |

Candidate-page coverage is therefore **5/5**. Three source pages are inside the
default full-text window (Annehem and both Keo fields), while INQ's two label pages
are candidates but outside that two-page window. The warning trail distinguishes
one INQ field collision and the two Keo over-valve rejections; it contains no
warning for Annehem or INQ total.

## Majority comparison and conclusion

The comparison changes **one company only**: Sedana Medical `total_debt` is `4,697`
in default-off, while both `majority` raw runs are null and the merged value stays
null. Balco, G5, Keo, and all five empty fields are unchanged. Majority is therefore
a useful abstention observation, not a root-cause repair.

Recommended next lane: first write offline red tests for the Balco page-break parent
scope and the G5/Sedana lease-context distinctions, then implement only predicates
that pass the full stored-library replay; keep the Keo prose-zero issue separately
scoped because its exact guard is different.

## Verification and delivery checks

- Re-ran `eval/run.py` and `eval_breakdown.py` against both sealed snapshots: default
  **26/40**, majority **27/40**; default buckets A=5, B=9, C=1, D=0.
- Recomputed all listed candidate ranks with `locate.candidate_pages`; no model or
  network call is involved.
- Red observation: the frozen default-off outcome above. No green behavior is claimed:
  this lane deliberately changes no implementation, labels, or data. The second
  snapshot independently confirms the one Sedana abstention only.
- Changed path: `docs/acrylic/evidence/v185.md` only.