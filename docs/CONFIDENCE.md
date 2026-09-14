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
  synonym match (Yubico, engcon, AFRY); `Operating result`, `Result before tax` as `... profit` (SSAB, Stora Enso).
- a bank prints no `Profit before tax` row: when none of a field's synonyms appears on the statement page, its
  `fallback_synonyms` apply (`Operating profit` is the pre-tax line, `Total operating income` the top line; NOBA, Nordnet).
  An industrial keeps them apart because the primary row exists.
- a field with `requires` (cost of sales requires gross profit) is dropped when the statement has no such row and the model's
  label is not a known synonym (`Materials and services` in Stora Enso's by-nature statement is not cost of sales).
- a row whose label is excluded and for which the statement prints no alternative is dropped (`Net operating surplus` is not
  operating profit; Catena, a property company, presents none).
- a value printed nowhere that is the sum of the 2-8 rows ending at the quote (`Current tax -56` + `Deferred tax -367` = -423,
  Catena; the four rows under IPC's `Cost of sales` heading) gets `value_derived` when the identity check that ties the field
  to its neighbours holds with those sums in **every** column; a coincidence in one year is not a proof. Only checks flagged
  `identity` in the schema count (margin sanity would accept anything). The identity also establishes the concept, so
  `label_known` is granted; the heading (or the joined row labels) becomes the label.
- an `expense` field printed unsigned (SEB: `Income tax expense 7,835`) is stored negative when that, and only that, makes
  the identity check pass.
- a row on the statement page returned without a unit takes the statement's unit from the page header (`SEK m`, `MSEK`,
  `USD Thousands`); the header also serves when the model answered nothing at all (SEB: both calls timed out, the page rows
  filled every field).
- a model call that times out on the statement spread is retried once on the statement page alone (IPC: two pages hang,
  one answers in a minute); a hung single page ends the attempts and the page rows fill what they can.
- component rows (IPC): the model quotes the first row under a "Cost of sales" heading. The identity check fails, and the run of rows starting at (or ending at) the quote whose sums make the identity hold in *every* column becomes the value and the quote, labelled by the heading. `value_derived`, not `value_in_quote`.
- twin rows (Lundbergs): the same printed row offered for two keys ("Rörelseresultat" as gross profit and as operating profit) belongs to the key whose label it is; the other is dropped, and a row that `requires` it follows.
- the statement row (SEB): when a variant row is replaced or a null is filled from the page, the row whose label is exactly a synonym wins over a prefix match ("Operating profit", not "Operating profit before items affecting comparability").
- a quote on the neighbouring row (Lundbergs: every label paired with the row below it): when the model's label is a known one and the page prints a row with exactly that label, that row is the quote and its figure the value.
- an unknown label whose identity holds in every column (Addnode: "Purchases of goods and services" between net sales and gross profit, both years) earns `label_known`; one column is one equation and proves nothing.
- segments printed side by side (Volvo: "2025 2024" four times, Industrial Operations to Volvo Group): every row on the page is read from the same fiscal-year column, the one most of the fields already sit in (the model took income taxes from the first pair and the rest from the last). A lone dash in a row is nil, so the columns stay aligned; a footnote marker glued to a number ("-297,0421)", Volvo Cars) is dropped.
- a printed label counts as a known synonym only when it *starts with* one: "Net income" is not a discontinued-operations row just because "net income from discontinued operations" is. Volvo Cars: the null fill had taken it, the identity then failed, and net profit was "repaired" to a wrong sum at full confidence.
- a property company's `Net operating surplus` is its gross profit (rental income - property expenses); operating profit it is not.
- a null between two known rows (Addnode: the model returned no income tax after two timeouts, the page fill then took an OCI row): when an identity is missing one operand and exactly one row sits between the other operands' rows and closes the identity in *every* column, that row is the value. A row whose label matches another field's `exclude_labels` (`Tax attributable to items that may be reclassified`) is never taken for it.
- a column-major text layer (Arion Bank: the PDF's text order is all numbers, then all labels): when a page has 12 or more consecutive letterless lines, its text is rebuilt from word positions (baseline grouping, left to right) so `Net interest income 7 52,542 46,302` is one line again. `PARSER_VERSION` is stamped in the knowledge base and a cached report is re-parsed when the version changes.
- a currency token inside the label (Castellum: `Earnings, SEK per share before and after dilution`, `Rental and service income`) is stripped before the synonym match; `(SEK)` no longer hides the printed label from `exclude_labels`, so `basic and diluted` is guarded explicitly.
- an optional operand with an unknown label (NCC: `Result from sales of Group companies 20` offered as discontinued operations) is dropped when the identity fails with it and holds with its default (0): profit before tax + tax already equals net profit.
- a small amount in parentheses or with a minus sign (`Discontinued operations held for sale, net of income tax 18 (19) (37)`, Arion Bank) is an amount, not a note reference: only bare one- and two-digit tokens are note references. The null fill then finds the row.
- trailing small numbers are columns, not notes (Vitrolife: `Net sales 4, 5 3,440 3,609 15 25` — the parent company's 15 and 25): note references sit between the label and the first amount, so only leading one- and two-digit tokens are dropped when the column count is known.
- the printed label wins over the model's paraphrase (Castellum: `Income` offered for the row printed `Rental and service income`): when the model's label is not a known synonym and the row's own is, the field adopts the printed one and earns `label_known`.
- a page headed by another year (Pandox: `Not C1, forts. KONCERNEN 2024`, the segment note for the prior year, no year header): a field the model stamped with the fiscal year is re-stamped with the year in the page heading and capped at 0.50 as wrong-year. The locator also no longer lets a leading "koncernen" excuse a segment page — only the parent-company exclusions defer to a preceding "group".
- the fetcher checks the issuer, not just the name's first word (Lundin Gold's search returned Lundin Mining's report): the two identifying tokens of the company name must appear in the first 20 pages, and MFN/Nasdaq hits must carry both.
- alphanumeric note references (Pandox: `Kostnader Hyresavtal C1, C4, C6, C7, G5 –519 –568`) may sit between the quote's tokens like numeric ones, so a two-row quote such as `Kostnader Hyresavtal –519 –568 Kostnader Egen drift –2 728 –2 713` verifies and the field then goes through the derived-sum proof (`value_derived`).
- a property company has no operating profit row: `Resultat före värdeförändringar` / `förvaltningsresultat` / `income from property management` sit after net financial items and are excluded labels, so the field is dropped (null) rather than reported at 0.9 under the wrong name.
- a broken fiscal year (Sectra: `2025/2026 2024/2025`) is one column per pair, named by its first year, in the locator's multi-year test and in the year header; a model period `2025/2026` is read as 2025.
- the locator reads the page heading's years from the raw text as well as the boilerplate-stripped one (Medicover: the "5-year financial summary" title and its bare `2025` / `2024` lines repeat on enough pages to be stripped, which hid the five-year table).
- the derived-sum proof also tries the rows just above the quote (IPC: the model quoted the `Gross profit` subtotal for the four rows under the `Cost of sales` heading; they sum to it in both columns).
- units: `€m` / `$m` and `Mkr` / `Mdkr` are recognised as EUR / USD / SEK scales (Medicover, Clas Ohlson).
- a known row's printed figure beats the model's reading (Pandox without chain-of-thought: `Bruttoresultat 4 222 3 855` returned as 3622): when the verified row carries the field's own label and one amount per year column, the fiscal-year amount is the value. A value off by a factor of 1000 is a unit mix-up and is left for the rescale rule.
- a number printed nowhere on the cited page or the statement spread is dropped, whether or not its quote verifies (Sectra, Beijer Ref: net sales minus goods for resale offered as gross profit in a by-nature statement, quoting the `Total income` row): computed, not read, and the prompt's rule is null then. This runs after the derived-sum pass, so a provable sum of rows (Catena's two tax rows) survives and an unprovable one does not; a cost of sales left without a gross profit goes with it.
- speed: the model is called through Ollama's native API with `think=false` — qwen3:8b answers in 25–50 s instead of 100–170 s, and the backend's repairs above catch the arithmetic slips the chain of thought used to avoid. `LLM_THINK=1` turns it back on; any other `LLM_BASE_URL` uses the OpenAI-compatible path unchanged.
- a three-year statement is not a summary (Essity prints 2025 2024 2023): the locator's multi-year penalty starts at four distinct years in the heading, or five year tokens.
- a note reference on its own line between a label and its figures joins the label's row (Atrium Ljungberg: `Net sales` / `IE.3` / `3,446`), and trailing note refs (`IE.3`, `B1, B2`) are not part of a label when labels are compared.
- the printed-figure rule above does not fire when the model's value is printed in the row (Beijer Alma `Rörelseresultat 9 952 1 091`: note 9 and 952, which the column parser reads as 9952) — and when the value is the fiscal-year figure of another row whose label is exactly a synonym, that row is the quote (Atrium: 3446 quoted as the `Net sales, project and construction work` sub-row).
- a zero the model made up stands for null: 0 quoting a row that prints no 0 is dropped (Wihlborgs: `Operating surplus 3,107 2,996` as operating profit; a real zero is printed, `Other income 0 3`).
- a label written as `<known part>: <other field's row>` quoting the other field's row is re-pointed to the row printed with the known part (Nordea: `Operating profit: Net profit for the year` 4840 → `Operating profit 6,316`, the bank's profit before tax).
- a derived sum may not use another field's row as an addend (Nordea: tax row + net profit row offered as net profit restates the identity and proves nothing; the wrong operand was profit before tax).
- synonyms: `operating surplus` / `driftsöverskott` (gross profit, property companies; excluded for operating profit — Corem), `pre-tax profit`, `profit after financial income and expense`, `net profit, discontinued operations` and kin (Tele2: the model answered null, the row fills the identity: 5,678 − 1,099 + 7 = 4,587).

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
- **Printed currency beats the model's habit.** The statement's currency is the majority of the model's field units, unless that currency is printed nowhere on the statement spread while the report's most-used currency code is: Evolution (a Swedish issuer reporting in EUR thousands) got `SEK` on five rows and `EUR` on EPS, which cost EPS its `unit_ok`; the units are swapped to the printed one and a warning says so.
- **Group | Parent Company pairs.** When the year header repeats and the page names both the group and the parent, the group pair is on the side named first, whatever column the model happened to read (Vitrolife: the model mixed the 2024 group column with the 2025 parent column; every row is re-read from column 1 of 4).
- **A broken fiscal year printed as a month range.** `Apr 25-Mar 26` is the fiscal-2025 column (named by its first year, as `2025/26`), and a figure that sits in the fiscal-year column gets that period whatever year the model stamped (Asmodee wrote 2026; without this every field was capped at 0.50 as wrong-year).
- **Ligatures and four-decimal figures.** Labels are NFKC-normalised before matching (Ericsson prints `ﬁnancial`), and amounts may carry up to four decimals (Asmodee `0.1186`).
- **Opposite sign convention.** A row printed positive for an expense the field carries negative (Swedbank `Total expenses 24 532`) still counts as that row when the identity is checked column by column, so `Total expenses` / `Profit before impairment...` earn `identity_all_columns` from `gross_profit_arith` holding in both years.
