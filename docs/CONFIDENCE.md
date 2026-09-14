# What `confidence` means

Until 2026-09-14 `confidence` was the model's self-assessment — qwen3 says 1.0 for everything, so it meant nothing.
From now on it is **computed by the backend from evidence the backend can verify itself**. The model's opinion is not an input.

`confidence = 1.0` means: *every piece of evidence below is present*. Anything less names what is missing.

## Evidence, per field

| Code | Evidence | Weight | Checked how |
|---|---|---|---|
| `quote_on_page` | `source.quote` (or its longest suffix that still holds a label word and a number — the model likes to prepend the section header) occurs on `source.page`: verbatim (whitespace-normalised), or every token in order with only a note reference (`6, 7`) between label and number. The quote is replaced by the part that was verified. A bare number or a bare label never counts | 0.35 | `parse.quote_on_page` |
| `value_in_quote` | the printed number is inside that verified quote (`168 343`, `168,343`, `168343`, `-7 246`, `(7 246)` all count) | 0.20 | regex over digit groups |
| `value_derived` | *instead of* `value_in_quote`, never both: the printed number is unreadable (Röko's text layer says `Profit before tax 1,01 923`) and a schema check failed, but the 2–6 rows printed right above sum to the value in the fiscal-year column **and** to the printed figures in every other column, and the check passes with it. The quote becomes those addend rows | 0.20 | `extract._derived_value` |
| `arith_ok` | no schema check that references this key failed; a check with a missing operand (`gross_profit` in a by-nature statement) is n/a, not a failure. Optional rows (`profit_discontinued`, schema `default: 0`) count as 0 | 0.20 | `checks[]` |
| `label_known` | `raw_label` matches one of the field's `synonyms` (sv + en, case-insensitive, prefix match) and none of its `exclude_labels` patterns (an adjusted / diluted / continuing-operations variant of the row is not the row); a sub-row under a known heading counts as `heading: sub-row` | 0.10 | `synonyms` + `exclude_labels` per schema field |
| `period_ok` | `period` equals the report's fiscal year | 0.05 | `Report.fiscal_year` (curated for library reports) |
| `page_is_statement` | `source.page` is the locator's best page or the one after it (statements span two pages; the locator scores heading keywords, field-synonym coverage and digit density, and penalises multi-year / quarterly / parent-company headings) | 0.05 | `locate.candidate_pages` |
| `unit_ok` | `unit` equals the section currency; for per-share fields the currency without scale must match (`SEK` vs `MSEK` / `SEKm` / `SEK million`) | 0.05 | string compare |

Score = sum of weights of satisfied evidence. Hard caps override the sum:

- `quote_on_page` missing → **cap 0.25** (the value has no verifiable provenance; the row is red)
- `value_in_quote` missing although the quote was verified → **cap 0.50** (the row is on the page, this number is not in it — a computed or invented figure)
- a check referencing the key **failed** → **cap 0.50** (the number contradicts its neighbours)
- `period` is a year other than the report's fiscal year → **cap 0.50** (another year's figure)

The verified quote is then widened to the **printed row** it belongs to (the page is split into rows: a line with a word
starts one, the number and note lines after it belong to it), so `source.quote` shows every column, not the one number the
model copied. Deterministic **repairs** run on that row before scoring, each leaving a warning:

- a value that is not printed in its verified quote but whose /10, /100 or /1000 is (`1177` -> `11.77`, `5424600` -> `5424.6`,
  `230` -> `23.0`) is replaced by the printed number;
- a value that is another year's column of the row (the page's year header says `2024 2025` for Sandvik; Skanska's model quote
  `Gross income 14,480` was the 2024 column of `Gross income 14,753 14,480`) is replaced by the fiscal-year column;
- a row that the statement sums into a `Total <same label>` row with a known synonym label (`Sales 155 054` + `Sales, acquired
  business` = `Total sales 155 113`, Securitas) is replaced by the total;
- a quote whose label the model renamed (`Profit before tax 3,145` for the printed `Profit after financial items 3,145`, Getinge)
  or whose page is a note rather than the statement (Sandvik cited the tax note for `Income tax -4,767`) is replaced by the row
  on the cited page or the statement spread that holds the number under a known synonym label; `raw_label` and `page` follow;
- a row that is the sum of the two rows above it, one of them in the field's `excludes` list (`Revenue 23,447` = `Net sales 20,427`
  + `Other operating income 3,020`, SCA), is unwound to the addend with a known label;
- a row whose label matches one of the field's `exclude_labels` (`Earnings per share ... before items affecting comparability
  11.55`, Securitas; `efter utspädning`, Saab) is replaced by the page row with a known, unexcluded label;
- a field the model left null although the statement page prints a row whose label *is* one of the field's synonyms
  (`Income after financial items 7,300`, Telia) is filled from that row and then verified like any model answer;
- a sub-row label under a known heading (`Basic earnings per share` / `Net income 2.59`, ABB) is reported as `heading: sub-row`
  so `label_known` sees the printed context.
- `Profit/loss before tax`, `Profit (loss) for the year` are read as `Profit before tax`, `Profit for the year` before the
  synonym match (Yubico, engcon, AFRY).

Swedish space-grouped rows are split by the column count from the year header (`155 054 161 900` is two amounts; no regex can
tell that from four small numbers), so the repairs only run on pages where that header was found.

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
