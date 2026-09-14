# eval
Scores the extraction API against hand-labelled ground truth — the accuracy number we show SEB.

## Adding labels (Sara — edit `labels.csv` in Excel)
Columns: `report_file,section,key,expected_value,expected_page,notes`.
1. Open the PDF, find the field (e.g. Revenue in the income statement).
2. `expected_value` = number as printed, as plain digits: `152 340` -> `152340`, `–7 010` -> `-7010`.
3. `expected_page` = the 1-based page it appears on.
4. `section`/`key` come from the schema files, see `docs/API.md`.
5. Save as CSV (Excel will prompt — say yes, keep UTF-8).

## Running
- `python eval/run.py --dry-run` — no backend needed, scores against the fixture (sanity check).
- `python eval/run.py` — uploads each report in `data/reports/` and runs real extractions.
- Flags: `--api URL`, `--reports-dir DIR`, `--labels CSV`, `--no-fail` (don't exit 1 on misses).

## Reading output
Per-row ✓/✗ for value and page match plus confidence, then value accuracy %, page hit-rate %,
and mean confidence of correct vs. incorrect rows (a calibration hint).
