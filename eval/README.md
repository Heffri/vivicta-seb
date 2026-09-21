# eval
Scores the extraction API against hand-labelled ground truth — the accuracy number we show SEB.

## Adding labels (Sara — edit `labels.csv` in Excel)
Columns: `report_file,section,key,expected_value,expected_page,notes`.
1. Open the PDF, find the field (e.g. Revenue in the income statement).
2. `expected_value` = number as printed, as plain digits: `152 340` -> `152340`, `–7 010` -> `-7010`.
3. `expected_page` = the 1-based page it appears on.
4. `section`/`key` come from the schema files, see `docs/API.md`.
5. Save as CSV (Excel will prompt — say yes, keep UTF-8).

## Held-out labels
`heldout-smallcap-2025.csv` is a frozen, blind held-out measurement set. It must never be copied
or merged into `labels.csv`, used in prompts or few-shot examples, or used to tune extraction or
shipping decisions; score it only through its explicit `--labels` path against an isolated stored-KB
snapshot after the first extraction has completed.

## Running
- `python eval/run.py --dry-run` — no backend needed, scores against the fixture (sanity check).
- `python eval/run.py` — uploads each report in `data/reports/` and runs real extractions.
- Flags: `--api URL`, `--reports-dir DIR`, `--labels CSV`, `--no-fail` (don't exit 1 on misses).
- `python eval/run.py --stored-kb DIR` — zero API/model calls: scores each label row against an
  already-stored `<DIR>/<stem>/extractions/<section>.json` (the shape `GET /api/kb/<stem>/<section>`
  returns) using the same comparison/printing as the modes above. Repeatable (`--stored-kb dir1
  --stored-kb dir2 ...`) — one report is printed per directory, so the same `report_file` scored
  against several snapshots (e.g. one per hardening seed) shows up once per snapshot, not merged. A
  label row whose `(report_file, section)` has no stored extraction file at all scores `-` (not
  counted as a miss) rather than a value mismatch. `--stored-kb data/kb` now covers the Mid Cap
  `debt_maturity` labels too: the 72 hardening-seed entries published by `scripts/publish_kb.py`
  (v093) live there beside the 102 Large Cap entries. `labels.csv` itself now holds 231 hand-verified
  `debt_maturity` rows across 87 companies (v057's seeds-1–4 set, v094's seeds-5–8 rows, v099's
  seed-9 + Financials rows and v105's seed-10 rows) — 327 scored rows with the 96 income rows (the 3
  `nordic_industrials` example rows have no KB stem and never score).

## Reading output
Per-row ✓/✗ for value and page match plus confidence, then value accuracy %, page hit-rate %,
and mean confidence of correct vs. incorrect rows (a calibration hint).
