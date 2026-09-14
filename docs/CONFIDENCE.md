# What `confidence` means

Until 2026-09-14 `confidence` was the model's self-assessment — qwen3 says 1.0 for everything, so it meant nothing.
From now on it is **computed by the backend from evidence the backend can verify itself**. The model's opinion is not an input.

`confidence = 1.0` means: *every piece of evidence below is present*. Anything less names what is missing.

## Evidence, per field

| Code | Evidence | Weight | Checked how |
|---|---|---|---|
| `quote_on_page` | `source.quote` occurs verbatim (whitespace-normalised) in the text of `source.page` | 0.35 | `parse.normalize_ws`, already done |
| `value_in_quote` | the printed number is inside that verified quote (`168 343`, `168,343`, `168343`, `-7 246`, `(7 246)` all count) | 0.20 | regex over digit groups |
| `arith_ok` | every schema check that references this key passed | 0.20 | `checks[]` |
| `label_known` | `raw_label` matches one of the field's `synonyms` (sv + en, case-insensitive, prefix match) | 0.10 | new `synonyms` list per schema field |
| `period_ok` | `period` equals the report's fiscal year | 0.05 | `Report.fiscal_year` (curated for library reports) |
| `page_is_statement` | `source.page` is among the locator's top 3 **and** a schema keyword is in that page's heading | 0.05 | `locate.candidate_pages` |
| `unit_ok` | `unit` equals the section currency (or the field's `unit_hint`, e.g. SEK for EPS) | 0.05 | string compare |

Score = sum of weights of satisfied evidence. Two hard caps override the sum:

- `quote_on_page` missing → **cap 0.25** (the value has no verifiable provenance; the row is red)
- a check referencing the key **failed** → **cap 0.50** (the number contradicts its neighbours)

The response carries the evidence, not just the number:

```ts
type Field = { ...; confidence: number; evidence: string[] }  // e.g. ["quote_on_page","value_in_quote","arith_ok","label_known","period_ok","unit_ok"] — page_is_statement missing => 0.95
```

The UI shows the missing codes in the confidence badge's tooltip. `eval/run.py` prints mean confidence next to accuracy.

## What it does *not* mean

Confidence 1.0 does **not** mean the value is right. Saab SV extracted the *parent-company* statement with every quote verified and every check passing — wrong entity, perfect evidence. Only hand labels (`eval/labels.csv`) catch that. Hence the standing target for the parser:

> **10 randomly drawn companies, all fields match the hand labels, all fields at confidence 1.0.**

Random draw 2026-09-14 (seed 20260914, Nasdaq Stockholm large caps excluding banks/investment companies — those need their own schema): Hexagon, Telia, SCA, Husqvarna, Skanska, Getinge, Sandvik, ABB, Trelleborg, Securitas. Plus the five already labelled (Atlas Copco, Saab SV, SKF, Investor*, SEB*). `*` = expected mismatch, kept as negative controls.

## Upgrades when the caps are hit

- Wrong-entity detection: require a `group` keyword (koncernen / consolidated) in the page heading for `page_is_statement`; penalise `moderbolaget` / `parent company` (already in `exclude_keywords`).
- Second opinion: re-run the extraction with a different page window or model and add `agrees_with_second_pass` (weight taken from `label_known`).
- ESEF/iXBRL: for the primary statements the tagged XHTML is ground truth; when present, `matches_esef` should be worth 0.5 on its own.
