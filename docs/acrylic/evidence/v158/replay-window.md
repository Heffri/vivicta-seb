mechanism_only: sections ['debt_maturity'], pages window, variants ['mechanism', 'total']; extract() with the model's values nulled, zero model calls
  kb: C:\Users\<owner>\.ao\data\worktrees\vivicta-glm\vivicta-glm-91\data\kb
  labels: 271 rows over due_1_to_5_years 43, due_after_5_years 39, due_within_1_year 84, total_debt 105
  kb/academedia_2025  shape=total-only  window=[87, 88]  labels=1
    stored     total_debt=12103 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=12103 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
  kb/acast_2025  shape=bucket-column  window=[65, 66]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: column reading of 'Lease liabilities 141,152 32,511 32,692 32,404 32,404 45,414' rejected -- due_within_1_year 141152, due_1_to_5_years 130011 exceed its own total 45414; model's own values kept
             ! total_debt: column reading of 'Total 555,370 446,990 32,692 32,404 32,404 45,414' rejected -- due_within_1_year 555370, due_1_to_5_years 544490 exceed its own total 45414; model's own values kept
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: column reading of 'Lease liabilities 141,152 32,511 32,692 32,404 32,404 45,414' rejected -- due_within_1_year 141152, due_1_to_5_years 130011 exceed its own total 45414; model's own values kept
             ! total_debt: column reading of 'Total 555,370 446,990 32,692 32,404 32,404 45,414' rejected -- due_within_1_year 555370, due_1_to_5_years 544490 exceed its own total 45414; model's own values kept
  kb/alligo_2025  shape=total-only  window=[143]  labels=2
    stored     total_debt=3629 due_within_1_year=473 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=3629 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/ambea_2025  shape=total-only  window=[119, 120]  labels=2
    stored     total_debt=12643 due_within_1_year=2308 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=12643 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=statement-spread fill
             ! total_debt: model returned null, filled from page 119 row 'Total interest-bearing liabilities 12,643 10,757'
    total      total_debt=12643 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/apotea_2025  shape=total-only  window=[113]  labels=4
    stored     total_debt=21.6 due_within_1_year=21.6 due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
    total      total_debt=21.6 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 1
  kb/arctic_paper_2025  shape=bucket-rows  window=[66, 67]  labels=2
    stored     total_debt=None due_within_1_year=219487 due_1_to_5_years=31722 due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/arjo_2025  shape=total-only  window=[109, 110]  labels=4
    stored     total_debt=5387 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
    total      total_debt=5387 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
  kb/attendo_2025  shape=total-only  window=[103, 104]  labels=1
    stored     total_debt=2978 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=2978 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
  kb/avarda_bank_2025  shape=total-only  window=[80, 81]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
  kb/bergman_beving_2025  shape=bucket-rows  window=[119, 120]  labels=2
    stored     total_debt=2038 due_within_1_year=354 due_1_to_5_years=1920 due_after_5_years=0   labels 0/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=2038 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 1
  kb/better_collective_2025  shape=total-only  window=[160, 161]  labels=1
    stored     total_debt=259946 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
             ! total_debt: 2 candidate debt rows for the bucket table ('Lease liabilities', 'Lease liabilities') -- ambiguous, none used
    total      total_debt=259946 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 1
             writers: total_debt=warning (unmapped)
             ! total_debt: 2 candidate debt rows for the bucket table ('Lease liabilities', 'Lease liabilities') -- ambiguous, none used
  kb/bhg_2025  shape=total-only  window=[131, 132]  labels=1
    stored     total_debt=1297.4 due_within_1_year=None due_1_to_5_years=None due_after_5_years=0   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=1297.4 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
  kb/bico_2025  shape=total-only  window=[111, 112]  labels=2
    stored     total_debt=1286.8 due_within_1_year=1068.5 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=1286.8 due_within_1_year=1068.5 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: model returned null; the note's two section subtotals on page 111 sum to 1286.8 (218.3 + 1068.5), each closing on its own rows; no printed or model total corroborates -- the two closures alone prove it
             ! due_within_1_year: model returned null; 1068.5 is printed in the note's current-section Summa row on page 111 ('Total 1,068.5 93.9 1,001.5 -'); no printed or model total corroborates -- the two closures alone prove it
    total      total_debt=1286.8 due_within_1_year=1068.5 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: page 111 is headed 2021, not 2025; period set to 2021
             ! total_debt: 1286.8 is printed on none of pages [111, 112]; dropped as computed, not read
             ! total_debt: model returned null; the note's two section subtotals on page 111 sum to 1286.8 (218.3 + 1068.5), each closing on its own rows; no printed or model total corroborates -- the two closures alone prove it
             ! due_within_1_year: model returned null; 1068.5 is printed in the note's current-section Summa row on page 111 ('Total 1,068.5 93.9 1,001.5 -'); no printed or model total corroborates -- the two closures alone prove it
  kb/biogaia_2025  shape=total-only  window=[153, 154]  labels=1
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
             writers: total_debt=warning (unmapped)
             ! total_debt: quote not found on page 153
  kb/bioinvent_international_2025  shape=total-only  window=[65, 66]  labels=4
    stored     total_debt=8527 due_within_1_year=7370 due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
    total      total_debt=8527 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 1
  kb/bonava_2025  shape=total-only  window=[156, 157]  labels=2
    stored     total_debt=3639 due_within_1_year=804 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=3639 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/boozt_2025  shape=bucket-rows  window=[121, 122]  labels=4
    stored     total_debt=441 due_within_1_year=104 due_1_to_5_years=273 due_after_5_years=63   labels 4/4  non-null 4
    mechanism  total_debt=441 due_within_1_year=104 due_1_to_5_years=273 due_after_5_years=63   labels 4/4  non-null 4
             writers: total_debt=_fill_bucket_columns, due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_fill_bucket_columns, due_after_5_years=_fill_bucket_columns
             ! total_debt: model returned null; 441 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
             ! due_within_1_year: model returned null; 104 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
             ! due_1_to_5_years: model returned null; 273 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
             ! due_after_5_years: model returned null; 63 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
    total      total_debt=441 due_within_1_year=104 due_1_to_5_years=273 due_after_5_years=63   labels 4/4  non-null 4
             writers: due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_fill_bucket_columns, due_after_5_years=_fill_bucket_columns
             ! due_within_1_year: model returned null; 104 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
             ! due_1_to_5_years: model returned null; 273 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
             ! due_after_5_years: model returned null; 63 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
  kb/bts_2025  shape=bucket-rows  window=[92, 93]  labels=3
    stored     total_debt=579797 due_within_1_year=77141 due_1_to_5_years=502656 due_after_5_years=None   labels 3/3  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/3  non-null 0
    total      total_debt=579797 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/3  non-null 1
  kb/byggmastare_a_j_ahlstrom_h_2025  shape=total-only  window=[54, 55]  labels=4
    stored     total_debt=2873 due_within_1_year=962 due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    total      total_debt=2873 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 1
  kb/byggmax_2025  shape=total-only  window=[99, 100]  labels=2
    stored     total_debt=2021 due_within_1_year=779 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=2021 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/catella_2025  shape=total-only  window=[107, 108]  labels=4
    stored     total_debt=1474 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
    total      total_debt=1474 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
  kb/cavotec_2025  shape=total-only  window=[71, 72]  labels=2
    stored     total_debt=23702 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: 'Lease liabilities 3,805 8,756 4,621 2,689' names fiscal year 2024, not 2025; not this year's bucket row
             ! total_debt: 'Total 39,403 23,112 4,621 2,689' is a Total*/Summa* row with no total column in its own header (due_within_1_year, due_after_5_years, due_within_1_year, due_after_5_years); its own total cannot be checked, left for another path
    total      total_debt=23702 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=warning (unmapped)
             ! total_debt: 'Lease liabilities 3,805 8,756 4,621 2,689' names fiscal year 2024, not 2025; not this year's bucket row
             ! total_debt: 'Total 39,403 23,112 4,621 2,689' is a Total*/Summa* row with no total column in its own header (due_within_1_year, due_after_5_years, due_within_1_year, due_after_5_years); its own total cannot be checked, left for another path
  kb/cellavision_2025  shape=bucket-rows  window=[92, 93]  labels=4
    stored     total_debt=25651 due_within_1_year=13680 due_1_to_5_years=8768 due_after_5_years=3203   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
             ! total_debt: 'Total 969 969 2,268 2,268' is a Total*/Summa* row with no total column in its own header (due_within_1_year, due_after_5_years, due_within_1_year); its own total cannot be checked, left for another path
    total      total_debt=25651 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 1
             writers: total_debt=warning (unmapped)
             ! total_debt: 'Total 969 969 2,268 2,268' is a Total*/Summa* row with no total column in its own header (due_within_1_year, due_after_5_years, due_within_1_year); its own total cannot be checked, left for another path
  kb/cloetta_2025  shape=bucket-column  window=[169, 170]  labels=4
    stored     total_debt=1605 due_within_1_year=197 due_1_to_5_years=1399 due_after_5_years=9   labels 4/4  non-null 4
    mechanism  total_debt=1605 due_within_1_year=197 due_1_to_5_years=1399 due_after_5_years=9   labels 4/4  non-null 4
             writers: total_debt=_fill_bucket_columns, due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_fill_bucket_columns, due_after_5_years=_fill_bucket_columns
             ! total_debt: model returned null; 1605 read from 'Total 197 22 1,377 9 1,605' by its column order
             ! due_within_1_year: model returned null; 197 read from 'Total 197 22 1,377 9 1,605' by its column order
             ! due_1_to_5_years: model returned null; 1399 read from 'Total 197 22 1,377 9 1,605' by its column order
             ! due_after_5_years: model returned null; 9 read from 'Total 197 22 1,377 9 1,605' by its column order
    total      total_debt=1605 due_within_1_year=197 due_1_to_5_years=1399 due_after_5_years=9   labels 4/4  non-null 4
             writers: due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_fill_bucket_columns, due_after_5_years=_fill_bucket_columns
             ! due_within_1_year: model returned null; 197 read from 'Total 197 22 1,377 9 1,605' by its column order
             ! due_1_to_5_years: model returned null; 1399 read from 'Total 197 22 1,377 9 1,605' by its column order
             ! due_after_5_years: model returned null; 9 read from 'Total 197 22 1,377 9 1,605' by its column order
  kb/coor_service_management_hold_2025  shape=total-only  window=[157, 158]  labels=4
    stored     total_debt=2727 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
    total      total_debt=2727 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
  kb/creades_2025  shape=prose-zero  window=[61, 62]  labels=4
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
    total      total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
             writers: total_debt=_stated_zero
             ! total_debt: 0 is printed on none of pages [61, 62]; kept on the report's own words, page 61: 'Investmentföretaget har varken räntebärande skulder eller kundfordringar.'
             ! total_debt: quote not found on page 61
  kb/ctt_systems_2025  shape=bucket-rows  window=[52, 53]  labels=4
    stored     total_debt=35.5 due_within_1_year=35.5 due_1_to_5_years=0 due_after_5_years=0   labels 4/4  non-null 4
    mechanism  total_debt=35.5 due_within_1_year=35.5 due_1_to_5_years=0 due_after_5_years=0   labels 4/4  non-null 4
             writers: total_debt=_fill_bucket_columns, due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_model_zero_on_dash_row, due_after_5_years=_model_zero_on_dash_row
             ! total_debt: model returned null; 35.5 read from 'Interest-bearing liabilities to credit institutions 35.5 - - - - - 35.5' by its column order
             ! due_within_1_year: model returned null; 35.5 read from 'Interest-bearing liabilities to credit institutions 35.5 - - - - - 35.5' by its column order
             ! due_1_to_5_years: model returned null; a dash is printed in the row's own column for it ('Interest-bearing liabilities to credit institutions 35.5 - - - - - 35.5') -- no debt due in that window, the report's explicit 0
             ! due_after_5_years: model returned null; a dash is printed in the row's own column for it ('Interest-bearing liabilities to credit institutions 35.5 - - - - - 35.5') -- no debt due in that window, the report's explicit 0
    total      total_debt=35.5 due_within_1_year=35.5 due_1_to_5_years=0 due_after_5_years=0   labels 4/4  non-null 4
             writers: total_debt=warning (unmapped), due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_model_zero_on_dash_row, due_after_5_years=_model_zero_on_dash_row
             ! total_debt: quote not found on page 52
             ! due_within_1_year: model returned null; 35.5 read from 'Interest-bearing liabilities to credit institutions 35.5 - - - - - 35.5' by its column order
             ! due_1_to_5_years: model returned null; a dash is printed in the row's own column for it ('Interest-bearing liabilities to credit institutions 35.5 - - - - - 35.5') -- no debt due in that window, the report's explicit 0
             ! due_after_5_years: model returned null; a dash is printed in the row's own column for it ('Interest-bearing liabilities to credit institutions 35.5 - - - - - 35.5') -- no debt due in that window, the report's explicit 0
  kb/duni_2025  shape=total-only  window=[181, 182]  labels=2
    stored     total_debt=1498 due_within_1_year=0 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=1498 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/dustin_2025  shape=total-only  window=[116, 117]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/dynavox_2025  shape=total-only  window=[134, 135]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/egetis_therapeutics_2025  shape=total-only  window=[74, 75]  labels=2
    stored     total_debt=76.5 due_within_1_year=31.5 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=76.5 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/elanders_2025  shape=total-only  window=[141, 142]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/enea_2025  shape=bucket-rows  window=[76, 77]  labels=4
    stored     total_debt=305555 due_within_1_year=136403 due_1_to_5_years=169152 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=305555 due_within_1_year=136403 due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: model returned null; the note's two section subtotals on page 76 sum to 305555 (169152 + 136403), each closing on its own rows; no printed or model total corroborates -- the two closures alone prove it
             ! due_within_1_year: model returned null; 136403 is printed in the note's current-section Summa row on page 76 ('Total current liabilities, interest-bearing 136,403 51,314 136,403 51,314'); no printed or model total corroborates -- the two closures alone prove it
    total      total_debt=136403 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 1
             writers: total_debt=warning (unmapped)
             ! total_debt: 305555 is another segment's column; the page's rows are read from column 1 of 4, which prints 136403
  kb/enity_holding_2025  shape=total-only  window=[81, 82]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
  kb/ependion_2025  shape=bucket-column  window=[155, 156]  labels=4
    stored     total_debt=583531 due_within_1_year=167546 due_1_to_5_years=415984 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=583531 due_within_1_year=167546 due_1_to_5_years=415984 due_after_5_years=None   labels 4/4  non-null 3
             writers: total_debt=_fill_bucket_columns, due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_fill_bucket_columns
             ! total_debt: model returned null; 583531 read from 'Borrowing 167,546 35,636 380,348 583,531' by its column order
             ! due_within_1_year: model returned null; 167546 read from 'Borrowing 167,546 35,636 380,348 583,531' by its column order
             ! due_1_to_5_years: model returned null; 415984 read from 'Borrowing 167,546 35,636 380,348 583,531' by its column order
    total      total_debt=583531 due_within_1_year=167546 due_1_to_5_years=415984 due_after_5_years=None   labels 4/4  non-null 3
             writers: due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_fill_bucket_columns
             ! due_within_1_year: model returned null; 167546 read from 'Borrowing 167,546 35,636 380,348 583,531' by its column order
             ! due_1_to_5_years: model returned null; 415984 read from 'Borrowing 167,546 35,636 380,348 583,531' by its column order
  kb/ericsson_2025  shape=total-only  window=[65, 66]  labels=2
    stored     total_debt=32703 due_within_1_year=3538 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=32703 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=statement-spread fill
             ! total_debt: model returned null, filled from page 65 row 'Total interest-bearing liabilities 32,703 38,041'
    total      total_debt=32703 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=warning (unmapped)
             ! total_debt: quoted 'Revaluation due to changes in credit risk'; the 'Total interest-bearing liabilities' row prints 32703
  kb/ework_2025  shape=bucket-column  window=[70, 71]  labels=3
    stored     total_debt=156410 due_within_1_year=156409 due_1_to_5_years=0 due_after_5_years=0   labels 3/3  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/3  non-null 0
    total      total_debt=156410 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/3  non-null 1
  kb/fagerhult_2025  shape=bucket-rows  window=[140, 141]  labels=4
    stored     total_debt=3449.5 due_within_1_year=56 due_1_to_5_years=3390 due_after_5_years=3.5   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    total      total_debt=6.3 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 1
             writers: total_debt=warning (unmapped)
             ! total_debt: 3449.5 is another segment's column; the page's rows are read from column 1 of 4, which prints 6.3
  kb/fasadgruppen_2025  shape=bucket-rows  window=[136, 137]  labels=4
    stored     total_debt=2194 due_within_1_year=159.5 due_1_to_5_years=2034.5 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
    total      total_debt=2194 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 1
  kb/flat_capital_2025  shape=total-only  window=[18, 19]  labels=4
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
    total      total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
  kb/flerie_2025  shape=total-only  window=[86, 87]  labels=2
    stored     total_debt=2.1 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=2.1 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/fm_mattsson_2025  shape=total-only  window=[123, 124]  labels=2
    stored     total_debt=89532 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=89532 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/gentoo_media_2025  shape=total-only  window=[88, 89]  labels=4
    stored     total_debt=111798 due_within_1_year=111798 due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
    total      total_debt=111798 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 1
  kb/green_landscaping_2025  shape=total-only  window=[99, 100]  labels=4
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/gruvaktiebolaget_viscaria_2025  shape=total-only  window=[110, 111]  labels=2
    stored     total_debt=677.8 due_within_1_year=661.8 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=677.8 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/hansa_biopharma_2025  shape=total-only  window=[65, 66]  labels=2
    stored     total_debt=927403 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=927403 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=warning (unmapped)
             ! currency: the model says IN THOUSANDS OF SEK, but the statement names only EUR/GBP/SEK/USD and the report mostly SEK; SEK it is
  kb/hanza_2025  shape=bucket-rows  window=[132, 133]  labels=4
    stored     total_debt=1444 due_within_1_year=60 due_1_to_5_years=1382 due_after_5_years=2   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    total      total_debt=1444 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 1
  kb/hexatronic_2025  shape=bucket-rows  window=[160, 161]  labels=4
    stored     total_debt=2243 due_within_1_year=62 due_1_to_5_years=2181 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
    total      total_debt=2243 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 1
  kb/hoist_finance_2025  shape=total-only  window=[126, 127]  labels=1
    stored     total_debt=52680 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=52680 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
  kb/humana_2025  shape=total-only  window=[148, 149]  labels=2
    stored     total_debt=4401 due_within_1_year=543 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=4401 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=warning (unmapped)
             ! total_debt: quote not found on page 149
  kb/humble_2025  shape=total-only  window=[90, 91]  labels=1
    stored     total_debt=1668 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=1668 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
  kb/instalco_2025  shape=total-only  window=[127, 128]  labels=1
    stored     total_debt=3122 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
             ! total_debt: column reading of 'Liabilities to credit institutions – – 3,209 – 3,209 3,122' rejected -- due_1_to_5_years 3209 exceeds its own total 3122; model's own values kept
    total      total_debt=3122 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
             writers: total_debt=_fill_bucket_columns
             ! total_debt: column reading of 'Liabilities to credit institutions – – 3,209 – 3,209 3,122' rejected -- due_1_to_5_years 3209 exceeds its own total 3122; model's own values kept
  kb/intrum_2025  shape=bucket-rows  window=[123, 124]  labels=4
    stored     total_debt=43384 due_within_1_year=271 due_1_to_5_years=43113 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
    total      total_debt=43384 due_within_1_year=271 due_1_to_5_years=43113 due_after_5_years=None   labels 4/4  non-null 3
             writers: due_within_1_year=statement-spread fill, due_1_to_5_years=warning (unmapped)
             ! due_within_1_year: model returned null; filled from page 123 row 'Total borrowings in current liabilities1 271 13,839 - 13,839'
             ! due_1_to_5_years: derived as the sum of 4 rows inside its window on page 123 ('Between 1 and 2 years' … 'Between 4 and 5 years'); closes on 43384
  kb/inwido_2025  shape=total-only  window=[166, 167]  labels=1
    stored     total_debt=1796 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=1796 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
  kb/itab_2025  shape=total-only  window=[125, 126]  labels=1
    stored     total_debt=3369 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=3369 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
  kb/kabe_2025  shape=total-only  window=[92, 93]  labels=2
    stored     total_debt=50 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=50 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/karnell_2025  shape=bucket-rows  window=[106, 107]  labels=4
    stored     total_debt=397.2 due_within_1_year=43.5 due_1_to_5_years=353.7 due_after_5_years=0   labels 4/4  non-null 4
    mechanism  total_debt=397.2 due_within_1_year=43.5 due_1_to_5_years=353.7 due_after_5_years=0   labels 4/4  non-null 4
             writers: total_debt=_fill_bucket_columns, due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_fill_bucket_columns, due_after_5_years=_fill_bucket_columns
             ! total_debt: model returned null; 397.2 read from 'Liabilities to credit institutions 43.5 353.7 - 397.2' by its column order
             ! due_within_1_year: model returned null; 43.5 read from 'Liabilities to credit institutions 43.5 353.7 - 397.2' by its column order
             ! due_1_to_5_years: model returned null; 353.7 read from 'Liabilities to credit institutions 43.5 353.7 - 397.2' by its column order
             ! due_after_5_years: model returned null; no debt due in that window -- the row prints a dash in its '>3 years' column ('Liabilities to credit institutions 43.5 353.7 - 397.2'), which spans it whole
    total      total_debt=397.2 due_within_1_year=43.5 due_1_to_5_years=353.7 due_after_5_years=0   labels 4/4  non-null 4
             writers: due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_fill_bucket_columns, due_after_5_years=_fill_bucket_columns
             ! due_within_1_year: model returned null; 43.5 read from 'Liabilities to credit institutions 43.5 353.7 - 397.2' by its column order
             ! due_1_to_5_years: model returned null; 353.7 read from 'Liabilities to credit institutions 43.5 353.7 - 397.2' by its column order
             ! due_after_5_years: model returned null; no debt due in that window -- the row prints a dash in its '>3 years' column ('Liabilities to credit institutions 43.5 353.7 - 397.2'), which spans it whole
  kb/karnov_2025  shape=total-only  window=[135, 136]  labels=2
    stored     total_debt=1965 due_within_1_year=135.2 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=1965 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/knowit_2025  shape=total-only  window=[152, 153]  labels=4
    stored     total_debt=758938 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
    total      total_debt=758938 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
  kb/lime_technologies_2025  shape=subtotal-pair/refused-scope  window=[91, 92]  labels=2
    stored     total_debt=211300 due_within_1_year=80786 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=211300 due_within_1_year=80786 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: model returned null; the note's two section subtotals on page 91 sum to 211300 (130514 + 80786), each closing on its own rows; no printed or model total corroborates -- the two closures alone prove it
             ! due_within_1_year: model returned null; 80786 is printed in the note's current-section Summa row on page 91 ('Total 80,786 79,521 18,896 51,367'); no printed or model total corroborates -- the two closures alone prove it
    total      total_debt=211300 due_within_1_year=80786 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: 211300 is printed on none of pages [91, 92]; dropped as computed, not read
             ! total_debt: model returned null; the note's two section subtotals on page 91 sum to 211300 (130514 + 80786), each closing on its own rows; no printed or model total corroborates -- the two closures alone prove it
             ! due_within_1_year: model returned null; 80786 is printed in the note's current-section Summa row on page 91 ('Total 80,786 79,521 18,896 51,367'); no printed or model total corroborates -- the two closures alone prove it
  kb/linc_2025  shape=total-only  window=[100, 101]  labels=1
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
             writers: total_debt=_model_zero_on_dash_row
             ! total_debt: 0 kept -- 'Räntebärande skulder – –' prints a dash in the fiscal-year column under a known label (printed nil)
  kb/medcap_2025  shape=bucket-rows  window=[101, 102]  labels=4
    stored     total_debt=718.7 due_within_1_year=102.3 due_1_to_5_years=616.5 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
    total      total_debt=718.7 due_within_1_year=102.3 due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 2
             writers: due_within_1_year=warning (unmapped)
             ! due_within_1_year: model returned null; the rows above the total (6 månader eller mindre + 6 – 12 månader) sum to 102.3 in the 2025 column, closing maturity_sums_to_total
  kb/meko_2025  shape=total-only  window=[102, 103]  labels=4
    stored     total_debt=6558 due_within_1_year=768 due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
    total      total_debt=6558 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 1
  kb/meren_energy_2025  shape=total-only  window=[73, 74]  labels=2
    stored     total_debt=333.8 due_within_1_year=68.6 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=333.8 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/mildef_2025  shape=total-only  window=[112, 113]  labels=2
    stored     total_debt=772.9 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=772.9 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=statement-spread fill
             ! total_debt: model returned null, filled from page 112 row 'Total borrowing 772.9 220.4'
    total      total_debt=772.9 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/modern_times_2025  shape=bucket-column  window=[142, 143]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: column reading of 'Lease liabilities 155 37 33 85 151' declined -- gross-value maturity block is headed 2024, not 2025
             ! total_debt: column reading of 'Total 3,322 2,281 890 151 3,123' declined -- gross-value maturity block is headed 2024, not 2025
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: column reading of 'Lease liabilities 155 37 33 85 151' declined -- gross-value maturity block is headed 2024, not 2025
             ! total_debt: column reading of 'Total 3,322 2,281 890 151 3,123' declined -- gross-value maturity block is headed 2024, not 2025
  kb/momentum_2025  shape=refused-scope  window=[111, 112]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! due_within_1_year: model returned null, fill from page 111 row 'Within 1 year 2 2' refused -- the Parent Company section 'Parent Company' holds this table
             ! due_1_to_5_years: model returned null, fill from page 111 row 'Between 1 and 5 years 2 1' refused -- the Parent Company section 'Parent Company' holds this table
             ! due_after_5_years: model returned null, fill from page 111 row 'Later than 5 years – –' refused -- the Parent Company section 'Parent Company' holds this table
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! due_within_1_year: model returned null, fill from page 111 row 'Within 1 year 2 2' refused -- the Parent Company section 'Parent Company' holds this table
             ! due_1_to_5_years: model returned null, fill from page 111 row 'Between 1 and 5 years 2 1' refused -- the Parent Company section 'Parent Company' holds this table
             ! due_after_5_years: model returned null, fill from page 111 row 'Later than 5 years – –' refused -- the Parent Company section 'Parent Company' holds this table
  kb/morrow_bank_2025  shape=total-only  window=[74, 75]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
  kb/ncab_2025  shape=total-only  window=[117, 118]  labels=4
    stored     total_debt=1090075 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
    total      total_debt=1090075 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
  kb/nederman_holding_2025  shape=total-only  window=[150, 151]  labels=2
    stored     total_debt=2475.3 due_within_1_year=117.3 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=2475.3 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/nelly_2025  shape=total-only  window=[89, 90]  labels=2
    stored     total_debt=287.1 due_within_1_year=36.2 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=287.1 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/net_insight_2025  shape=bucket-rows  window=[91, 92]  labels=4
    stored     total_debt=39415 due_within_1_year=8305 due_1_to_5_years=31110 due_after_5_years=0   labels 3/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
    total      total_debt=39415 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 1
  kb/nobia_2025  shape=bucket-rows  window=[131, 132]  labels=4
    stored     total_debt=2983 due_within_1_year=0 due_1_to_5_years=2983 due_after_5_years=0   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    total      total_debt=2983 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 1
  kb/norion_bank_2025  shape=total-only  window=[70, 71]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
  kb/note_2025  shape=subtotal-pair  window=[107, 108]  labels=2
    stored     total_debt=824281 due_within_1_year=595420 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=824281 due_within_1_year=595420 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: model returned null; the note's two section subtotals on page 107 sum to 824281 (228861 + 595420), each closing on its own rows; no printed or model total corroborates -- the two closures alone prove it
             ! due_within_1_year: model returned null; 595420 is printed in the note's current-section Summa row on page 107 ('Summa 595 420 380 108'); no printed or model total corroborates -- the two closures alone prove it
    total      total_debt=824281 due_within_1_year=595420 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: 824281 is printed on none of pages [107, 108]; dropped as computed, not read
             ! total_debt: model returned null; the note's two section subtotals on page 107 sum to 824281 (228861 + 595420), each closing on its own rows; no printed or model total corroborates -- the two closures alone prove it
             ! due_within_1_year: model returned null; 595420 is printed in the note's current-section Summa row on page 107 ('Summa 595 420 380 108'); no printed or model total corroborates -- the two closures alone prove it
  kb/orron_energy_2025  shape=total-only  window=[67, 68]  labels=2
    stored     total_debt=106.4 due_within_1_year=0 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=106.4 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/ovzon_2025  shape=total-only  window=[62, 63]  labels=4
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
  kb/powercell_sweden_2025  shape=total-only  window=[44, 45]  labels=1
    stored     total_debt=19055 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=19055 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
             writers: total_debt=statement-spread fill
             ! total_debt: model returned null, filled from page 44 row 'Total borrowings (Note 27) 19,055 73,819'
    total      total_debt=19055 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
  kb/proact_it_2025  shape=bucket-rows  window=[103, 104]  labels=4
    stored     total_debt=478611 due_within_1_year=0 due_1_to_5_years=166153 due_after_5_years=None   labels 3/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
    total      total_debt=478611 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 1
  kb/ratos_2025  shape=total-only  window=[131, 132]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/raysearch_laboratories_2025  shape=total-only  window=[72, 73]  labels=2
    stored     total_debt=394.9 due_within_1_year=77.5 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=394.9 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/rejlers_2025  shape=bucket-rows  window=[105, 106]  labels=3
    stored     total_debt=400.3 due_within_1_year=400.3 due_1_to_5_years=0 due_after_5_years=None   labels 3/3  non-null 3
    mechanism  total_debt=None due_within_1_year=400.3 due_1_to_5_years=None due_after_5_years=None   labels 1/3  non-null 1
             writers: due_within_1_year=statement-spread fill
             ! due_within_1_year: model returned null, filled from page 105 row 'Within one year 400.3 349.5'
    total      total_debt=400.3 due_within_1_year=400.3 due_1_to_5_years=None due_after_5_years=None   labels 2/3  non-null 2
             writers: due_within_1_year=statement-spread fill
             ! due_within_1_year: model returned null, filled from page 105 row 'Within one year 400.3 349.5'
  kb/rusta_2025  shape=finer-rows  window=[115, 116]  labels=4
    stored     total_debt=6624 due_within_1_year=1039 due_1_to_5_years=3153 due_after_5_years=2431   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
             ! due_within_1_year: model returned null, fill from page 115 row 'Within one year 607 590' refused -- the Parent Company section 'Parent Company' holds this table
             ! due_after_5_years: model returned null, fill from page 115 row 'Later than 5 years 2,016 2,231' refused -- the Parent Company section 'Parent Company' holds this table
    total      total_debt=6624 due_within_1_year=1039 due_1_to_5_years=3153 due_after_5_years=None   labels 3/4  non-null 3
             writers: due_within_1_year=warning (unmapped), due_1_to_5_years=warning (unmapped)
             ! due_within_1_year: model returned null, fill from page 115 row 'Within one year 607 590' refused -- the Parent Company section 'Parent Company' holds this table
             ! due_after_5_years: model returned null, fill from page 115 row 'Later than 5 years 2,016 2,231' refused -- the Parent Company section 'Parent Company' holds this table
             ! due_within_1_year: model returned null; the rows above the total (0–6 months + 7–12 months) sum to 1039 in the 2025 column, closing maturity_sums_to_total
             ! due_1_to_5_years: model returned null; the rows above the total (1–2 years + 2–5 years) sum to 3153 in the 2025 column, closing maturity_sums_to_total
  kb/rvrc_holding_2025  shape=bucket-column  window=[109, 110]  labels=2
    stored     total_debt=12 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: column reading of 'Total 210 3 7 0 0 220' declined -- table 'Maturity analysis regarding non-discounted liabilities' is undiscounted; refused under the carrying basis
             ! total_debt: column reading of 'Total 225 2 8 1 0 235' declined -- table 'Maturity analysis regarding non-discounted liabilities' is undiscounted; refused under the carrying basis
    total      total_debt=12 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=_fill_bucket_columns
             ! total_debt: column reading of 'Total 210 3 7 0 0 220' declined -- table 'Maturity analysis regarding non-discounted liabilities' is undiscounted; refused under the carrying basis
             ! total_debt: column reading of 'Total 225 2 8 1 0 235' declined -- table 'Maturity analysis regarding non-discounted liabilities' is undiscounted; refused under the carrying basis
  kb/salix_2025  shape=refused-scope  window=[177, 178]  labels=2
    stored     total_debt=3246 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! due_within_1_year: model returned null, fill from page 177 row 'Within 1 year 87 87 1' refused -- table 'Timing of revenue recognition, contract liabilities' is a non-debt subject table
    total      total_debt=3246 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             ! due_within_1_year: model returned null, fill from page 177 row 'Within 1 year 87 87 1' refused -- table 'Timing of revenue recognition, contract liabilities' is a non-debt subject table
  kb/scandi_standard_2025  shape=bucket-column  window=[127, 128]  labels=2
    stored     total_debt=2307 due_within_1_year=70 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: column reading of 'Total 547 44 – – –12' rejected -- due_within_1_year 547, due_1_to_5_years 44 exceed its own total -12; model's own values kept
    total      total_debt=2307 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=_fill_bucket_columns
             ! total_debt: column reading of 'Total 547 44 – – –12' rejected -- due_within_1_year 547, due_1_to_5_years 44 exceed its own total -12; model's own values kept
  kb/sdiptech_2025  shape=total-only  window=[110, 111]  labels=2
    stored     total_debt=4495 due_within_1_year=446 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=4495 due_within_1_year=446 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: model returned null; the note's two section subtotals on page 110 sum to 4495 (4049 + 446), each closing on its own rows; no printed or model total corroborates -- the two closures alone prove it
             ! due_within_1_year: model returned null; 446 is printed in the note's current-section Summa row on page 110 ('Total 446 537'); no printed or model total corroborates -- the two closures alone prove it
    total      total_debt=4495 due_within_1_year=446 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: 4495 is printed on none of pages [110, 111]; dropped as computed, not read
             ! total_debt: model returned null; the note's two section subtotals on page 110 sum to 4495 (4049 + 446), each closing on its own rows; no printed or model total corroborates -- the two closures alone prove it
             ! due_within_1_year: model returned null; 446 is printed in the note's current-section Summa row on page 110 ('Total 446 537'); no printed or model total corroborates -- the two closures alone prove it
  kb/smartcraft_2025  shape=lease-refused  window=[59, 60]  labels=4
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
             ! due_within_1_year: model returned null, fill from page 59 row 'Less than 1 year 13 825 13 825' refused -- table 'Total undiscounted lease liabilities' is undiscounted
             ! due_after_5_years: model returned null, fill from page 59 row 'More than 5 years - -' refused -- table 'Total undiscounted lease liabilities' is undiscounted
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
             ! due_within_1_year: model returned null, fill from page 59 row 'Less than 1 year 13 825 13 825' refused -- table 'Total undiscounted lease liabilities' is undiscounted
             ! due_after_5_years: model returned null, fill from page 59 row 'More than 5 years - -' refused -- table 'Total undiscounted lease liabilities' is undiscounted
  kb/stillfront_2025  shape=bucket-rows  window=[109, 110]  labels=4
    stored     total_debt=5887 due_within_1_year=None due_1_to_5_years=5152 due_after_5_years=4   labels 3/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    total      total_debt=5887 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 1
  kb/storytel_2025  shape=total-only  window=[114]  labels=4
    stored     total_debt=550 due_within_1_year=550 due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
    total      total_debt=550 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 1
  kb/svedbergs_2025  shape=bucket-rows  window=[132, 133]  labels=4
    stored     total_debt=496405 due_within_1_year=51440 due_1_to_5_years=435842 due_after_5_years=9124   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    total      total_debt=496405 due_within_1_year=51440 due_1_to_5_years=435842 due_after_5_years=None   labels 3/4  non-null 3
             writers: due_within_1_year=_finer_split_rows, due_1_to_5_years=warning (unmapped)
             ! due_within_1_year: model returned null; filled from page 132 row 'Kortfristiga räntebärande skulder 2025 2024 2025 2024'
             ! due_within_1_year: 2025 reads one finer-split row and misses its siblings; the rows above the total (3 månader eller mindre + Mellan 3 månader och 1 år) sum to 51440 in the 2025 column, closing maturity_sums_to_total
             ! due_1_to_5_years: model returned null; the rows above the total (Mellan 1 år och 2 år + Mellan 2 år och 5 år) sum to 435842 in the 2025 column, closing maturity_sums_to_total
  kb/svolder_2025  shape=total-only  window=[18, 19]  labels=4
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
  kb/synsam_2025  shape=bucket-rows  window=[121, 122]  labels=3
    stored     total_debt=2718 due_within_1_year=0 due_1_to_5_years=2718 due_after_5_years=None   labels 3/3  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/3  non-null 0
    total      total_debt=2718 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/3  non-null 1
  kb/tangen_industrikapital_2025  shape=total-only  window=[63, 64]  labels=4
    stored     total_debt=915454 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    total      total_debt=915454 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 1
  kb/traction_2025  shape=prose-zero  window=[32, 33]  labels=1
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
             writers: total_debt=warning (unmapped)
             ! total_debt: quote not found on page 32
  kb/vbg_2025  shape=total-only  window=[133, 134]  labels=1
    stored     total_debt=1504774 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=1504774 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
  kb/vef_2025  shape=total-only  window=[20, 21]  labels=2
    stored     total_debt=25721 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 0
    total      total_debt=25721 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 1
  kb/viaplay_2025  shape=bucket-rows  window=[113, 114]  labels=4
    stored     total_debt=6422 due_within_1_year=920 due_1_to_5_years=5502 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
    total      total_debt=6422 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 1
  kb/vicore_pharma_holding_2025  shape=total-only  window=[46, 47]  labels=1
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    total      total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
             writers: total_debt=warning (unmapped)
             ! total_debt: quote not found on page 46
  kb/viva_wine_2025  shape=total-only  window=[105]  labels=2
    stored     total_debt=1203 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=1203 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
  kb/vnv_global_2025  shape=total-only  window=[37, 38]  labels=2
    stored     total_debt=46246 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 0
    total      total_debt=46246 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 1
  kb/volati_2025  shape=refused-scope  window=[177, 178]  labels=2
    stored     total_debt=3246 due_within_1_year=192 due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! due_within_1_year: model returned null, fill from page 177 row 'Within 1 year 87 87 1' refused -- table 'Timing of revenue recognition, contract liabilities' is a non-debt subject table
    total      total_debt=3246 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 1
             ! due_within_1_year: model returned null, fill from page 177 row 'Within 1 year 87 87 1' refused -- table 'Timing of revenue recognition, contract liabilities' is a non-debt subject table
  kb/xano_industri_2025  shape=bucket-column  window=[84, 85]  labels=4
    stored     total_debt=904522 due_within_1_year=51075 due_1_to_5_years=802669 due_after_5_years=50778   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    total      total_debt=904522 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 1
  kb/xvivo_perfusion_2025  shape=total-only  window=[93, 94]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    total      total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0

summary (scored against labels; fields = labeled field instances, companies = all labeled keys right)
  stored     fields 221/269  companies 73/104  non-null 183/416
  mechanism  fields 85/269  companies 14/104  non-null 34/416
  total      fields 158/269  companies 37/104  non-null 113/416

field classes per labeled field instance (variant vs the stored record)
  mechanism: ok-both 84  stored-only 137  mech-only 1  both-wrong 47
  total: ok-both 157  stored-only 64  mech-only 1  both-wrong 47

companies the mechanism variant turns right over a wrong stored record: none
field instances the mechanism variant reads right over a wrong stored record: 1
  kb/net_insight_2025 due_after_5_years: mechanism None (label null, stored 0)
field instances the stored record reads right that the mechanism variant would lose: 137 null + 0 wrong
companies the total variant turns right over a wrong stored record: none
field instances the total variant reads right over a wrong stored record: 1
  kb/net_insight_2025 due_after_5_years: mechanism None (label null, stored 0)
field instances the stored record reads right that the total variant would lose: 62 null + 2 wrong
  kb/enea_2025 total_debt: stored 305555 (label 305555), variant 136403
  kb/fagerhult_2025 total_debt: stored 3449.5 (label 3449.5), variant 6.3

hit rate by stored shape (primary class; mechanism variant vs stored)
  shape           stems | fields stored | fields mech | companies stored | companies mech
  total-only         65 |    112/142    |     46/142  |        46/65     |        7/65
  bucket-rows        22 |     75/81     |     23/81   |        17/22     |        3/22
  bucket-column       8 |     18/23     |      8/23   |         5/8      |        2/8
  refused-scope       3 |      2/6      |      0/6    |         0/3      |        0/3
  prose-zero          2 |      5/5      |      3/5    |         2/2      |        0/2
  subtotal-pair       2 |      4/4      |      4/4    |         2/2      |        2/2
  finer-rows          1 |      4/4      |      0/4    |         1/1      |        0/1
  lease-refused       1 |      1/4      |      1/4    |         0/1      |        0/1
not replayable:
  kb/oresund_2025: no candidate pages derivable
