# Offline stored-KB eval breakdown

Source: `data\kb`. The script imports `eval/run.py` for the value and page predicates; no API, network, PDF download, or model call is made.

## Per-section hit rates

| section | labels | value | page | unscored value |
| --- | ---: | --- | --- | ---: |
| `debt_maturity` | 271 | 215/271 (79.3%) | 158/219 (72.1%) | 0 |

## Miss buckets

A = stored null / not read; B = value mismatch; C = value right, page wrong; D = label candidate (expected value absent from stored text).

| bucket | rows | companies | companies |
| --- | ---: | ---: | --- |
| A | 38 | 27 | acast_2025, arctic_paper_2025, bico_2025, bioinvent_international_2025, byggmastare_a_j_ahlstrom_h_2025, cavotec_2025, ctt_systems_2025, dustin_2025, elanders_2025, flerie_2025, fm_mattsson_2025, green_landscaping_2025, hansa_biopharma_2025, hexatronic_2025, kabe_2025, modern_times_2025, momentum_2025, oresund_2025, ovzon_2025, ratos_2025, rvrc_holding_2025, salix_2025, smartcraft_2025, svolder_2025, tangen_industrikapital_2025, viva_wine_2025, xvivo_perfusion_2025 |
| B | 9 | 8 | academedia_2025, bergman_beving_2025, better_collective_2025, dustin_2025, dynavox_2025, modern_times_2025, net_insight_2025, tangen_industrikapital_2025 |
| C | 10 | 9 | attendo_2025, boozt_2025, ework_2025, flat_capital_2025, fm_mattsson_2025, humana_2025, ncab_2025, powercell_sweden_2025, scandi_standard_2025 |
| D | 9 | 8 | byggmastare_a_j_ahlstrom_h_2025, green_landscaping_2025, mildef_2025, proact_it_2025, sdiptech_2025, stillfront_2025, tangen_industrikapital_2025, volati_2025 |

## ✗ rows

### `ncab_2025` / `total_debt` — C

- Label: value `1090075`, page `101`; stored: value `1090075`, page `93`.
- Reason: label scope: value is printed on both pages (v132 A).
- Locator: label page is a candidate; expected value appears on stored text page(s): `87, 93, 99, 101, 103, 110, 116`.
- Page shape (label / stored): numeric-lines=39, multi-year=2028/2030, group-marker, schema-synonym / numeric-lines=43, multi-year=2024/2025, group-marker, schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, label_known, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `ework_2025` / `total_debt` — C

- Label: value `156410`, page `70`; stored: value `156410`, page `71`.
- Reason: label scope: value is printed on both pages (v132 A).
- Locator: label page is a candidate; expected value appears on stored text page(s): `49, 53, 68, 69, 70, 71, 73`.
- Page shape (label / stored): numeric-lines=33, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / numeric-lines=27, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `flat_capital_2025` / `total_debt` — C

- Label: value `0`, page `33`; stored: value `0`, page `18`.
- Reason: other page difference; inspect page semantics (v132 D).
- Locator: label page is a candidate; expected value appears on stored text page(s): `2, 6, 14, 15, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 31, 32, 34, 35, 36`.
- Page shape (label / stored): numeric-lines=34, multi-year=2024/2025, no-schema-synonym / numeric-lines=20, group-marker, parent-marker, no-schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `svolder_2025` / `total_debt` — A

- Label: value `0`, page `18`; stored: value `-`, page `-`.
- Reason: not read; label value is not literal on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `2, 5, 11, 12, 13, 14, 15, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 43, 44, 46, 47, 50, 53, 57, 60, 63, 65, 66, 68, 73, 74, 75, 76, 77, 80, 87`.
- Page shape (label / stored): numeric-lines=4, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `ratos_2025` / `total_debt` — A

- Label: value `4126`, page `131`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `31, 121, 131`.
- Page shape (label / stored): numeric-lines=33, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `ovzon_2025` / `total_debt` — A

- Label: value `423`, page `61`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `56, 61`.
- Page shape (label / stored): numeric-lines=69, multi-year=2027/2028, group-marker, parent-marker, schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `ovzon_2025` / `due_within_1_year` — A

- Label: value `40`, page `61`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `3, 21, 45, 47, 61, 62, 63, 66`.
- Page shape (label / stored): numeric-lines=69, multi-year=2027/2028, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `better_collective_2025` / `total_debt` — B

- Label: value `259691`, page `161`; stored: value `259946`, page `161`.
- Reason: same-table prior-year/other-column or wrong-row candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `127, 161, 162, 169, 184, 185`.
- Page shape (label / stored): numeric-lines=27, multi-year=2024/2025, group-marker, no-schema-synonym / numeric-lines=27, multi-year=2024/2025, group-marker, no-schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `boozt_2025` / `total_debt` — C

- Label: value `441`, page `108`; stored: value `441`, page `122`.
- Reason: label scope: value is printed on both pages (v132 A).
- Locator: label page is a candidate; expected value appears on stored text page(s): `48, 108, 121, 122`.
- Page shape (label / stored): numeric-lines=27, multi-year=2025/2026, group-marker, no-schema-synonym / numeric-lines=26, multi-year=2024/2025, group-marker, no-schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `boozt_2025` / `due_within_1_year` — C

- Label: value `104`, page `108`; stored: value `104`, page `121`.
- Reason: derived/translated citation: value is not printed on source page (v132 B by-design).
- Locator: label page is a candidate; expected value appears on stored text page(s): `7, 32, 45, 47, 48, 79, 98, 104, 108, 110`.
- Page shape (label / stored): numeric-lines=27, multi-year=2025/2026, group-marker, schema-synonym / numeric-lines=30, multi-year=2024/2025, group-marker, no-schema-synonym.
- Mechanism: `warning (unmapped)`; evidence: `arith_ok, label_known, page_is_statement, period_ok, quote_on_page, unit_ok, value_derived`; relevant warning(s): due_within_1_year: 104 is printed on none of pages [121, 122]; dropped as computed, not read.

### `humana_2025` / `total_debt` — C

- Label: value `4401`, page `148`; stored: value `4401`, page `149`.
- Reason: adjacent table continuation/off-by-one candidate (v132 C).
- Locator: label page is a candidate; expected value appears on stored text page(s): `149, 150`.
- Page shape (label / stored): numeric-lines=70, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / numeric-lines=33, multi-year=2024/2025, group-marker, parent-marker, schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok`; relevant warning(s): -.

### `academedia_2025` / `total_debt` — B

- Label: value `12103`, page `87`; stored: value `12114`, page `87`.
- Reason: same-table prior-year/other-column or wrong-row candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `87`.
- Page shape (label / stored): numeric-lines=47, multi-year=2024/2025, group-marker, no-schema-synonym / numeric-lines=47, multi-year=2024/2025, group-marker, no-schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `bergman_beving_2025` / `total_debt` — B

- Label: value `2390`, page `120`; stored: value `2038`, page `119`.
- Reason: row label is not schema-recognised (synonym gap candidate).
- Locator: label page is a candidate; expected value appears on stored text page(s): `120`.
- Page shape (label / stored): numeric-lines=44, multi-year=2026/2029, group-marker, parent-marker, schema-synonym / numeric-lines=63, multi-year=2025/2026, group-marker, parent-marker, no-schema-synonym.
- Mechanism: `model`; evidence: `page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `bergman_beving_2025` / `due_within_1_year` — B

- Label: value `424`, page `120`; stored: value `354`, page `119`.
- Reason: row label is not schema-recognised (synonym gap candidate).
- Locator: label page is a candidate; expected value appears on stored text page(s): `90, 110, 120`.
- Page shape (label / stored): numeric-lines=44, multi-year=2026/2029, group-marker, parent-marker, schema-synonym / numeric-lines=63, multi-year=2025/2026, group-marker, parent-marker, schema-synonym.
- Mechanism: `model`; evidence: `page_is_statement, period_ok, quote_on_page, unit_ok`; relevant warning(s): -.

### `ctt_systems_2025` / `due_within_1_year` — A

- Label: value `35.5`, page `52`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `33, 34, 36, 51, 52`.
- Page shape (label / stored): numeric-lines=60, multi-year=2024/2025, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `fm_mattsson_2025` / `total_debt` — C

- Label: value `89532`, page `141`; stored: value `89532`, page `124`.
- Reason: label scope: value is printed on both pages (v132 A).
- Locator: label page is a candidate; expected value appears on stored text page(s): `124, 141`.
- Page shape (label / stored): numeric-lines=43, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / numeric-lines=38, multi-year=2025/2026, group-marker, parent-marker, schema-synonym.
- Mechanism: `warning (unmapped)`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): total_debt: -89532 printed with a liabilities-negative sign convention; recorded as 89532.

### `fm_mattsson_2025` / `due_within_1_year` — A

- Label: value `30610`, page `110`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `110, 136, 140`.
- Page shape (label / stored): numeric-lines=22, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `smartcraft_2025` / `total_debt` — A

- Label: value `28248`, page `58`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is outside candidates.
- Locator: label page is outside candidates; expected value appears on stored text page(s): `58`.
- Page shape (label / stored): numeric-lines=25, multi-year=2024/2025, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `smartcraft_2025` / `due_within_1_year` — A

- Label: value `13439`, page `58`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is outside candidates.
- Locator: label page is outside candidates; expected value appears on stored text page(s): `22, 58, 64`.
- Page shape (label / stored): numeric-lines=25, multi-year=2024/2025, no-schema-synonym / page text unavailable.
- Mechanism: `warning (unmapped)`; evidence: `-`; relevant warning(s): due_within_1_year: model returned null, fill from page 59 row 'Less than 1 year 13 825 13 825' refused -- table 'Total undiscounted lease liabilities' is undiscounted.

### `smartcraft_2025` / `due_1_to_5_years` — A

- Label: value `14809`, page `58`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is outside candidates.
- Locator: label page is outside candidates; expected value appears on stored text page(s): `22, 58`.
- Page shape (label / stored): numeric-lines=25, multi-year=2024/2025, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `xvivo_perfusion_2025` / `total_debt` — A

- Label: value `124721`, page `92`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `92, 96`.
- Page shape (label / stored): numeric-lines=21, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `xvivo_perfusion_2025` / `due_within_1_year` — A

- Label: value `11556`, page `65`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `65, 95`.
- Page shape (label / stored): numeric-lines=42, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `net_insight_2025` / `due_after_5_years` — B

- Label: value `null`, page `91`; stored: value `0`, page `91`.
- Reason: row label is not schema-recognised (synonym gap candidate).
- Locator: label page is a candidate; expected value appears on stored text page(s): `none`.
- Page shape (label / stored): numeric-lines=26, multi-year=2025/2030, group-marker, no-schema-synonym / numeric-lines=26, multi-year=2025/2030, group-marker, no-schema-synonym.
- Mechanism: `warning (unmapped)`; evidence: `arith_ok, page_is_statement, period_ok, unit_ok`; relevant warning(s): due_after_5_years: quote not found on page 91.

### `proact_it_2025` / `due_within_1_year` — D

- Label: value `312458`, page `103`; stored: value `0`, page `103`.
- Reason: label candidate: expected value is absent from all stored report text.
- Locator: label page is a candidate; expected value appears on stored text page(s): `none`.
- Page shape (label / stored): numeric-lines=73, multi-year=2029/2030, group-marker, parent-marker, no-schema-synonym / numeric-lines=73, multi-year=2029/2030, group-marker, parent-marker, no-schema-synonym.
- Mechanism: `warning (unmapped)`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok`; relevant warning(s): due_within_1_year: 312458 is another segment's column; the page's rows are read from column 1 of 3, which prints 0.

### `scandi_standard_2025` / `due_within_1_year` — C

- Label: value `70`, page `102`; stored: value `70`, page `134`.
- Reason: label scope: value is printed on both pages (v132 A).
- Locator: label page is a candidate; expected value appears on stored text page(s): `28, 51, 70, 88, 93, 101, 102, 103, 125, 132, 134, 145, 148, 149`.
- Page shape (label / stored): numeric-lines=46, multi-year=2024/2025, group-marker, no-schema-synonym / numeric-lines=44, multi-year=2024/2025, group-marker, schema-synonym.
- Mechanism: `_fill_bucket_columns`; evidence: `arith_ok, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): total_debt: column reading of 'Total 547 44 – – –12' rejected -- due_within_1_year 547, due_1_to_5_years 44 exceed its own total -12; model's own values kept \| due_within_1_year: -70 printed with a liabilities-negative sign convention; recorded as 70.

### `bioinvent_international_2025` / `due_1_to_5_years` — A

- Label: value `1157`, page `66`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `45, 66`.
- Page shape (label / stored): numeric-lines=35, multi-year=2025/2026, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `stillfront_2025` / `due_within_1_year` — D

- Label: value `710`, page `109`; stored: value `-`, page `-`.
- Reason: label candidate: expected value is absent from all stored report text.
- Locator: label page is a candidate; expected value appears on stored text page(s): `none`.
- Page shape (label / stored): numeric-lines=46, multi-year=2025/2026, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `warning (unmapped)`; evidence: `-`; relevant warning(s): due_within_1_year: 732 is printed on none of pages [109, 110]; dropped as computed, not read.

### `sdiptech_2025` / `total_debt` — D

- Label: value `4495`, page `110`; stored: value `-`, page `-`.
- Reason: label candidate: expected value is absent from all stored report text.
- Locator: label page is a candidate; expected value appears on stored text page(s): `none`.
- Page shape (label / stored): numeric-lines=60, multi-year=2030/2031, group-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `kabe_2025` / `due_within_1_year` — A

- Label: value `30`, page `79`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `2, 4, 5, 26, 28, 30, 31, 32, 38, 76, 79, 83, 91, 95, 97, 100, 103`.
- Page shape (label / stored): numeric-lines=41, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `oresund_2025` / `total_debt` — A

- Label: value `13425`, page `47`; stored: value `-`, page `-`.
- Reason: not read; label value is not literal on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `36`.
- Page shape (label / stored): numeric-lines=27, multi-year=2031/2032, group-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `oresund_2025` / `due_within_1_year` — A

- Label: value `4002`, page `47`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `36, 47`.
- Page shape (label / stored): numeric-lines=27, multi-year=2031/2032, group-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `salix_2025` / `due_within_1_year` — A

- Label: value `192`, page `177`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `13, 177, 193`.
- Page shape (label / stored): numeric-lines=40, multi-year=2024/2025, group-marker, schema-synonym / page text unavailable.
- Mechanism: `warning (unmapped)`; evidence: `-`; relevant warning(s): due_within_1_year: model returned null, fill from page 177 row 'Within 1 year 87 87 1' refused -- table 'Timing of revenue recognition, contract liabilities' is a non-debt subject table.

### `tangen_industrikapital_2025` / `total_debt` — B

- Label: value `588199`, page `62`; stored: value `915454`, page `57`.
- Reason: other value mismatch (row/column needs inspection).
- Locator: label page is outside candidates; expected value appears on stored text page(s): `59, 62`.
- Page shape (label / stored): numeric-lines=31, multi-year=2024/2025, group-marker, no-schema-synonym / numeric-lines=31, multi-year=2025/2026, group-marker, schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, label_known, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `tangen_industrikapital_2025` / `due_within_1_year` — A

- Label: value `141734`, page `62`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is outside candidates.
- Locator: label page is outside candidates; expected value appears on stored text page(s): `37, 62`.
- Page shape (label / stored): numeric-lines=31, multi-year=2024/2025, group-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `tangen_industrikapital_2025` / `due_1_to_5_years` — D

- Label: value `388979`, page `62`; stored: value `-`, page `-`.
- Reason: label candidate: expected value is absent from all stored report text.
- Locator: label page is outside candidates; expected value appears on stored text page(s): `none`.
- Page shape (label / stored): numeric-lines=31, multi-year=2024/2025, group-marker, schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `tangen_industrikapital_2025` / `due_after_5_years` — A

- Label: value `57486`, page `62`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is outside candidates.
- Locator: label page is outside candidates; expected value appears on stored text page(s): `62`.
- Page shape (label / stored): numeric-lines=31, multi-year=2024/2025, group-marker, schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `hexatronic_2025` / `due_within_1_year` — A

- Label: value `62`, page `114`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `3, 50, 51, 64, 72, 75, 114, 119, 150, 159, 162, 175`.
- Page shape (label / stored): numeric-lines=26, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `hexatronic_2025` / `due_1_to_5_years` — A

- Label: value `2181`, page `160`; stored: value `-`, page `-`.
- Reason: not read; label value is not literal on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `114, 159, 162, 175`.
- Page shape (label / stored): numeric-lines=21, multi-year=2025/2028, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `dynavox_2025` / `total_debt` — B

- Label: value `896.2`, page `133`; stored: value `893.8`, page `135`.
- Reason: row label is not schema-recognised (synonym gap candidate).
- Locator: label page is outside candidates; expected value appears on stored text page(s): `133, 134, 146`.
- Page shape (label / stored): numeric-lines=27, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / numeric-lines=27, multi-year=2026/2027, group-marker, parent-marker, no-schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `flerie_2025` / `due_within_1_year` — A

- Label: value `0.5`, page `57`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `57, 59, 60, 72, 76, 77, 78, 82, 83, 85, 86, 88`.
- Page shape (label / stored): numeric-lines=32, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `warning (unmapped)`; evidence: `-`; relevant warning(s): merge: union, per-field: total_debt=run1 (only non-null), due_within_1_year=null (both null), due_1_to_5_years=null (both null), due_after_5_years=null (both null).

### `attendo_2025` / `total_debt` — C

- Label: value `2978`, page `101`; stored: value `2978`, page `103`.
- Reason: label scope: value is printed on both pages (v132 A).
- Locator: label page is a candidate; expected value appears on stored text page(s): `84, 101, 102, 103`.
- Page shape (label / stored): numeric-lines=62, multi-year=2025/2026, group-marker, no-schema-synonym / numeric-lines=47, multi-year=2024/2025, group-marker, no-schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `powercell_sweden_2025` / `total_debt` — C

- Label: value `19055`, page `50`; stored: value `19055`, page `44`.
- Reason: label scope: value is printed on both pages (v132 A).
- Locator: label page is a candidate; expected value appears on stored text page(s): `44, 49, 50, 52`.
- Page shape (label / stored): numeric-lines=62, multi-year=2027/2030, group-marker, parent-marker, schema-synonym / numeric-lines=60, multi-year=2024/2025, group-marker, schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, label_known, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `rvrc_holding_2025` / `due_within_1_year` — A

- Label: value `5`, page `95`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is outside candidates.
- Locator: label page is outside candidates; expected value appears on stored text page(s): `2, 3, 5, 6, 8, 10, 12, 15, 17, 19, 26, 31, 40, 41, 42, 43, 47, 49, 51, 57, 61, 66, 68, 69, 70, 71, 72, 75, 76, 77, 81, 82, 85, 87, 89, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 106, 107, 108, 109, 110, 114, 117, 119, 120, 122`.
- Page shape (label / stored): numeric-lines=42, multi-year=2024/2025, group-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `byggmastare_a_j_ahlstrom_h_2025` / `due_1_to_5_years` — D

- Label: value `1911`, page `54`; stored: value `-`, page `-`.
- Reason: label candidate: expected value is absent from all stored report text.
- Locator: label page is a candidate; expected value appears on stored text page(s): `none`.
- Page shape (label / stored): numeric-lines=34, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `warning (unmapped)`; evidence: `-`; relevant warning(s): due_1_to_5_years: 1911 is printed on none of pages [53, 54]; dropped as computed, not read.

### `byggmastare_a_j_ahlstrom_h_2025` / `due_after_5_years` — A

- Label: value `0`, page `54`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `8, 9, 14, 20, 21, 22, 23, 24, 25, 27, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60`.
- Page shape (label / stored): numeric-lines=34, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `acast_2025` / `total_debt` — A

- Label: value `135382`, page `67`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is outside candidates.
- Locator: label page is outside candidates; expected value appears on stored text page(s): `60, 65, 67`.
- Page shape (label / stored): numeric-lines=34, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `_fill_bucket_columns`; evidence: `-`; relevant warning(s): total_debt: column reading of 'Lease liabilities 141,152 32,511 32,692 32,404 32,404 45,414' rejected -- due_within_1_year 141152, due_1_to_5_years 130011 exceed its own total 45414; model's own values kept \| total_debt: column reading of 'Total 555,370 446,990 32,692 32,404 32,404 45,414' rejected -- due_within_1_year 555370, due_1_to_5_years 544490 exceed its own total 45414; model's own values kept.

### `acast_2025` / `due_within_1_year` — A

- Label: value `32052`, page `67`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is outside candidates.
- Locator: label page is outside candidates; expected value appears on stored text page(s): `67`.
- Page shape (label / stored): numeric-lines=34, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `_fill_bucket_columns`; evidence: `-`; relevant warning(s): total_debt: column reading of 'Lease liabilities 141,152 32,511 32,692 32,404 32,404 45,414' rejected -- due_within_1_year 141152, due_1_to_5_years 130011 exceed its own total 45414; model's own values kept \| total_debt: column reading of 'Total 555,370 446,990 32,692 32,404 32,404 45,414' rejected -- due_within_1_year 555370, due_1_to_5_years 544490 exceed its own total 45414; model's own values kept.

### `arctic_paper_2025` / `total_debt` — A

- Label: value `251209`, page `71`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `71, 75`.
- Page shape (label / stored): numeric-lines=31, multi-year=2024/2025, group-marker, no-schema-synonym / page text unavailable.
- Mechanism: `warning (unmapped)`; evidence: `-`; relevant warning(s): merge: union, per-field: total_debt=null (both null), due_within_1_year=run2 (agree: confidence tie -> run2), due_1_to_5_years=run2 (only non-null), due_after_5_years=null (both null).

### `bico_2025` / `total_debt` — A

- Label: value `1286.8`, page `111`; stored: value `-`, page `-`.
- Reason: not read; label value is not literal on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `120`.
- Page shape (label / stored): numeric-lines=56, multi-year=2025/2026, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `warning (unmapped)`; evidence: `-`; relevant warning(s): merge: union, per-field: total_debt=null (both null), due_within_1_year=run2 (agree: confidence tie -> run2), due_1_to_5_years=null (both null), due_after_5_years=null (both null).

### `cavotec_2025` / `due_within_1_year` — A

- Label: value `3324`, page `59`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `59, 78`.
- Page shape (label / stored): numeric-lines=41, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `warning (unmapped)`; evidence: `-`; relevant warning(s): total_debt: 'Total 39,403 23,112 4,621 2,689' is a Total*/Summa* row with no total column in its own header (due_within_1_year, due_after_5_years, due_within_1_year, due_after_5_years); its own total cannot be checked, left for another path.

### `dustin_2025` / `total_debt` — B

- Label: value `2538`, page `115`; stored: value `3055`, page `117`.
- Reason: parent-company column/page candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `79, 115, 117, 136`.
- Page shape (label / stored): numeric-lines=41, multi-year=2024/2025, group-marker, no-schema-synonym / numeric-lines=44, multi-year=2025/2027, group-marker, parent-marker, no-schema-synonym.
- Mechanism: `model`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): -.

### `dustin_2025` / `due_within_1_year` — A

- Label: value `63`, page `100`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `42, 54, 61, 63, 67, 73, 75, 100, 108, 112, 116`.
- Page shape (label / stored): numeric-lines=67, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `elanders_2025` / `total_debt` — A

- Label: value `4620`, page `143`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is outside candidates.
- Locator: label page is outside candidates; expected value appears on stored text page(s): `143`.
- Page shape (label / stored): numeric-lines=20, multi-year=2025/2026, group-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `elanders_2025` / `due_within_1_year` — A

- Label: value `228`, page `117`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `117`.
- Page shape (label / stored): numeric-lines=24, multi-year=2024/2025, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `green_landscaping_2025` / `total_debt` — D

- Label: value `2495`, page `76`; stored: value `-`, page `-`.
- Reason: label candidate: expected value is absent from all stored report text.
- Locator: label page is a candidate; expected value appears on stored text page(s): `none`.
- Page shape (label / stored): numeric-lines=25, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `green_landscaping_2025` / `due_within_1_year` — A

- Label: value `87`, page `76`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `12, 17, 75, 76, 87, 90, 97, 99, 100, 102, 112`.
- Page shape (label / stored): numeric-lines=25, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `green_landscaping_2025` / `due_1_to_5_years` — D

- Label: value `2398`, page `102`; stored: value `-`, page `-`.
- Reason: label candidate: expected value is absent from all stored report text.
- Locator: label page is a candidate; expected value appears on stored text page(s): `none`.
- Page shape (label / stored): numeric-lines=50, multi-year=2025/2028, group-marker, schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `green_landscaping_2025` / `due_after_5_years` — A

- Label: value `10`, page `102`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `2, 6, 8, 10, 11, 15, 26, 28, 29, 34, 55, 60, 61, 62, 63, 64, 67, 70, 74, 77, 78, 79, 80, 81, 90, 91, 92, 93, 94, 98, 99, 100, 101, 102, 104, 105, 106, 112`.
- Page shape (label / stored): numeric-lines=50, multi-year=2025/2028, group-marker, schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `hansa_biopharma_2025` / `due_within_1_year` — A

- Label: value `136869`, page `40`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `40, 64, 69`.
- Page shape (label / stored): numeric-lines=41, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `warning (unmapped)`; evidence: `-`; relevant warning(s): currency: the model says in thousands of SEK, but the statement names only EUR<local-path> and the report mostly SEK; SEK it is.

### `mildef_2025` / `due_within_1_year` — D

- Label: value `137.7`, page `112`; stored: value `-`, page `-`.
- Reason: label candidate: expected value is absent from all stored report text.
- Locator: label page is a candidate; expected value appears on stored text page(s): `none`.
- Page shape (label / stored): numeric-lines=30, multi-year=2025/2028, group-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `modern_times_2025` / `total_debt` — A

- Label: value `3741`, page `118`; stored: value `-`, page `-`.
- Reason: not read; label value is not literal on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `148`.
- Page shape (label / stored): numeric-lines=34, multi-year=2024/2025, group-marker, parent-marker, schema-synonym / page text unavailable.
- Mechanism: `_fill_bucket_columns`; evidence: `-`; relevant warning(s): total_debt: 3487 disagrees with the maturity table; 85151 read from 'Lease liabilities 155 37 33 85 151' by its column order.

### `modern_times_2025` / `due_within_1_year` — B

- Label: value `418`, page `118`; stored: value `155`, page `142`.
- Reason: row label is not schema-recognised (synonym gap candidate).
- Locator: label page is a candidate; expected value appears on stored text page(s): `118`.
- Page shape (label / stored): numeric-lines=34, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / numeric-lines=23, multi-year=2027/2028, group-marker, no-schema-synonym.
- Mechanism: `_fill_bucket_columns`; evidence: `page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): due_within_1_year: 582 disagrees with the maturity table; 155 read from 'Lease liabilities 155 37 33 85 151' by its column order.

### `momentum_2025` / `total_debt` — A

- Label: value `395`, page `116`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `78, 116, 117, 131`.
- Page shape (label / stored): numeric-lines=37, multi-year=2024/2025, group-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `momentum_2025` / `due_within_1_year` — A

- Label: value `67`, page `94`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `67, 85, 87, 94, 98, 105, 115, 117, 119`.
- Page shape (label / stored): numeric-lines=40, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `warning (unmapped)`; evidence: `-`; relevant warning(s): due_within_1_year: model returned null, fill from page 111 row 'Within 1 year 2 2' refused -- the Parent Company section 'Parent Company' holds this table.

### `viva_wine_2025` / `due_within_1_year` — A

- Label: value `310`, page `79`; stored: value `-`, page `-`.
- Reason: not read; label value is printed on label page; label page is a candidate.
- Locator: label page is a candidate; expected value appears on stored text page(s): `79`.
- Page shape (label / stored): numeric-lines=45, multi-year=2024/2025, group-marker, parent-marker, no-schema-synonym / page text unavailable.
- Mechanism: `model`; evidence: `-`; relevant warning(s): -.

### `volati_2025` / `total_debt` — D

- Label: value `3245`, page `177`; stored: value `3246`, page `177`.
- Reason: label candidate: expected value is absent from all stored report text.
- Locator: label page is a candidate; expected value appears on stored text page(s): `none`.
- Page shape (label / stored): numeric-lines=40, multi-year=2024/2025, group-marker, no-schema-synonym / numeric-lines=40, multi-year=2024/2025, group-marker, no-schema-synonym.
- Mechanism: `warning (unmapped)`; evidence: `arith_ok, page_is_statement, period_ok, quote_on_page, unit_ok, value_in_quote`; relevant warning(s): merge: union, per-field: total_debt=run2 (agree: confidence tie -> run2), due_within_1_year=run2 (agree: confidence tie -> run2), due_1_to_5_years=null (both null), due_after_5_years=null (both null).

