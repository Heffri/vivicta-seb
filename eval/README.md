# eval
Scores the extraction API against hand-labelled ground truth — the accuracy number we show SEB.

## Adding labels (edit `labels.csv` in a spreadsheet)
Columns: `report_file,section,key,expected_value,expected_page,notes`.
1. Open the PDF, find the field (e.g. Revenue in the income statement).
2. `expected_value` = number as printed, as plain digits: `152 340` -> `152340`, `–7 010` -> `-7010`.
3. `expected_page` = the 1-based page it appears on.
4. `section`/`key` come from the schema files, see `docs/API.md`.
5. Save as CSV (Excel will prompt — say yes, keep UTF-8).

## Held-out labels
`heldout-smallcap-2025.csv` (round 1) and `heldout-smallcap-2025-r2.csv` (round 2) are frozen,
blind measurement sets. Neither may be copied or merged into `labels.csv` or used in prompts or
few-shot examples; score each only through its explicit `--labels` path against an isolated
stored-KB snapshot after first extraction. Round 1 was subsequently used for guard/tuning work and
is historical but remains frozen; round 2 is the current held-out set and must not be used to tune
extraction or shipping decisions.

## Running
- `python eval/run.py --dry-run` — no backend needed, scores against the fixture (sanity check).
- `python eval/run.py` — uploads each report in `data/reports/` and runs real extractions.
- Flags: `--api URL`, `--reports-dir DIR`, `--labels CSV`, `--no-fail` (don't exit 1 on misses).
- `python eval/run.py --stored-kb DIR` — zero API/model calls: scores each label row against an
  already-stored `<DIR>/<stem>/extractions/<section>.json` (the shape `GET /api/kb/<stem>/<section>`
  returns) using the same comparison/printing as the modes above. Repeatable (`--stored-kb dir1
  --stored-kb dir2 ...`) — one report is printed per directory, so the same `report_file` scored
  against several snapshots shows up once per snapshot, not merged. A label row whose
  `(report_file, section)` has no stored extraction file at all scores `-` (not counted as a miss)
  rather than a value mismatch. `labels.csv` holds 375 hand-verified rows — 276 `debt_maturity`
  and 99 `income_statement` — across 118 reports. Against `data/kb` (105 stored `debt_maturity`
  and 102 stored `income_statement` extractions) 368 of those rows score. The other 7 have no
  stored extraction for their section and never score: the 3 `nordic_industrials` example rows,
  which have no KB stem, and 4 `abb_2025` `debt_maturity` rows.

## Reading output
Per-row ✓/✗ for value and page match plus confidence, then value accuracy %, page hit-rate %,
and mean confidence of correct vs. incorrect rows (a calibration hint).
