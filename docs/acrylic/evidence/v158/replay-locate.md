mechanism_only: sections ['debt_maturity'], pages locate, variants ['mechanism']; extract() with the model's values nulled, zero model calls
  kb: C:\Users\xingyi chen\.ao\data\worktrees\vivicta-glm\vivicta-glm-91\data\kb
  labels: 271 rows over due_1_to_5_years 43, due_after_5_years 39, due_within_1_year 84, total_debt 105
  kb/academedia_2025  shape=total-only  window=[97, 98]  labels=1
    stored     total_debt=12103 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/acast_2025  shape=bucket-column  window=[65, 66]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: column reading of 'Lease liabilities 141,152 32,511 32,692 32,404 32,404 45,414' rejected -- due_within_1_year 141152, due_1_to_5_years 130011 exceed its own total 45414; model's own values kept
             ! total_debt: column reading of 'Total 555,370 446,990 32,692 32,404 32,404 45,414' rejected -- due_within_1_year 555370, due_1_to_5_years 544490 exceed its own total 45414; model's own values kept
  kb/alligo_2025  shape=total-only  window=[142, 143]  labels=2
    stored     total_debt=3629 due_within_1_year=473 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/ambea_2025  shape=total-only  window=[119, 120]  labels=2
    stored     total_debt=12643 due_within_1_year=2308 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=12643 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=statement-spread fill
             ! total_debt: model returned null, filled from page 119 row 'Total interest-bearing liabilities 12,643 10,757'
  kb/apotea_2025  shape=total-only  window=[113, 114]  labels=4
    stored     total_debt=21.6 due_within_1_year=21.6 due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
  kb/arctic_paper_2025  shape=bucket-rows  window=[75, 76]  labels=2
    stored     total_debt=None due_within_1_year=219487 due_1_to_5_years=31722 due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/arjo_2025  shape=total-only  window=[109, 110]  labels=4
    stored     total_debt=5387 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
  kb/attendo_2025  shape=total-only  window=[103, 104]  labels=1
    stored     total_debt=2978 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/avarda_bank_2025  shape=total-only  window=[81, 82]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
  kb/bergman_beving_2025  shape=bucket-rows  window=[119, 120]  labels=2
    stored     total_debt=2038 due_within_1_year=354 due_1_to_5_years=1920 due_after_5_years=0   labels 0/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/better_collective_2025  shape=total-only  window=[129, 130]  labels=1
    stored     total_debt=259946 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/bhg_2025  shape=total-only  window=[150, 151]  labels=1
    stored     total_debt=1297.4 due_within_1_year=None due_1_to_5_years=None due_after_5_years=0   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/bico_2025  shape=total-only  window=[86, 87]  labels=2
    stored     total_debt=1286.8 due_within_1_year=1068.5 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/biogaia_2025  shape=total-only  window=[148, 149]  labels=1
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/bioinvent_international_2025  shape=total-only  window=[65, 66]  labels=4
    stored     total_debt=8527 due_within_1_year=7370 due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
  kb/bonava_2025  shape=total-only  window=[152, 153]  labels=2
    stored     total_debt=3639 due_within_1_year=804 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=3639 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=statement-spread fill
             ! total_debt: model returned null, filled from page 152 row 'Total interest-bearing liabilities 3,639 4,310'
  kb/boozt_2025  shape=bucket-rows  window=[121, 122]  labels=4
    stored     total_debt=441 due_within_1_year=104 due_1_to_5_years=273 due_after_5_years=63   labels 4/4  non-null 4
    mechanism  total_debt=441 due_within_1_year=104 due_1_to_5_years=273 due_after_5_years=63   labels 4/4  non-null 4
             writers: total_debt=_fill_bucket_columns, due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_fill_bucket_columns, due_after_5_years=_fill_bucket_columns
             ! total_debt: model returned null; 441 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
             ! due_within_1_year: model returned null; 104 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
             ! due_1_to_5_years: model returned null; 273 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
             ! due_after_5_years: model returned null; 63 read from 'Lease liabilities 441 26 78 273 63 -' by its column order
  kb/bts_2025  shape=bucket-rows  window=[93, 94]  labels=3
    stored     total_debt=579797 due_within_1_year=77141 due_1_to_5_years=502656 due_after_5_years=None   labels 3/3  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/3  non-null 0
             ! total_debt: 'Total –112,982 –88,736' is a Total*/Summa* row with no total column in its own header (due_within_1_year, due_1_to_5_years); its own total cannot be checked, left for another path
  kb/byggmastare_a_j_ahlstrom_h_2025  shape=total-only  window=[53, 54]  labels=4
    stored     total_debt=2873 due_within_1_year=962 due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 2
    mechanism  total_debt=None due_within_1_year=922 due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 1
             writers: due_within_1_year=statement-spread fill
             ! due_within_1_year: model returned null, filled from page 53 row 'Kortfristiga räntebärande skulder 922 853'
  kb/byggmax_2025  shape=total-only  window=[85, 86]  labels=2
    stored     total_debt=2021 due_within_1_year=779 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/catella_2025  shape=total-only  window=[107, 108]  labels=4
    stored     total_debt=1474 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
  kb/cavotec_2025  shape=total-only  window=[71, 72]  labels=2
    stored     total_debt=23702 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: 'Lease liabilities 3,805 8,756 4,621 2,689' names fiscal year 2024, not 2025; not this year's bucket row
             ! total_debt: 'Total 39,403 23,112 4,621 2,689' is a Total*/Summa* row with no total column in its own header (due_within_1_year, due_after_5_years, due_within_1_year, due_after_5_years); its own total cannot be checked, left for another path
  kb/cellavision_2025  shape=bucket-rows  window=[77, 78]  labels=4
    stored     total_debt=25651 due_within_1_year=13680 due_1_to_5_years=8768 due_after_5_years=3203   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/cloetta_2025  shape=bucket-column  window=[39, 40]  labels=4
    stored     total_debt=1605 due_within_1_year=197 due_1_to_5_years=1399 due_after_5_years=9   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/coor_service_management_hold_2025  shape=total-only  window=[159, 160]  labels=4
    stored     total_debt=2727 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
  kb/creades_2025  shape=prose-zero  window=[61, 62]  labels=4
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
  kb/ctt_systems_2025  shape=bucket-rows  window=[41, 42]  labels=4
    stored     total_debt=35.5 due_within_1_year=35.5 due_1_to_5_years=0 due_after_5_years=0   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/duni_2025  shape=total-only  window=[176, 177]  labels=2
    stored     total_debt=1498 due_within_1_year=0 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/dustin_2025  shape=total-only  window=[116, 117]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/dynavox_2025  shape=total-only  window=[134, 135]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/egetis_therapeutics_2025  shape=total-only  window=[72, 73]  labels=2
    stored     total_debt=76.5 due_within_1_year=31.5 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/elanders_2025  shape=total-only  window=[144, 145]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/enea_2025  shape=bucket-rows  window=[76, 77]  labels=4
    stored     total_debt=305555 due_within_1_year=136403 due_1_to_5_years=169152 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=305555 due_within_1_year=136403 due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: model returned null; the note's two section subtotals on page 76 sum to 305555 (169152 + 136403), each closing on its own rows; corroborated by page 75 prose
             ! due_within_1_year: model returned null; 136403 is printed in the note's current-section Summa row on page 76 ('Total current liabilities, interest-bearing 136,403 51,314 136,403 51,314'); corroborated by page 75 prose
  kb/enity_holding_2025  shape=total-only  window=[95, 96]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
  kb/ependion_2025  shape=bucket-column  window=[154, 155]  labels=4
    stored     total_debt=583531 due_within_1_year=167546 due_1_to_5_years=415984 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=583531 due_within_1_year=167546 due_1_to_5_years=415984 due_after_5_years=None   labels 4/4  non-null 3
             writers: total_debt=_fill_bucket_columns, due_within_1_year=_fill_bucket_columns, due_1_to_5_years=_fill_bucket_columns
             ! total_debt: model returned null; 583531 read from 'Borrowing 167,546 35,636 380,348 583,531' by its column order
             ! due_within_1_year: model returned null; 167546 read from 'Borrowing 167,546 35,636 380,348 583,531' by its column order
             ! due_1_to_5_years: model returned null; 415984 read from 'Borrowing 167,546 35,636 380,348 583,531' by its column order
  kb/ericsson_2025  shape=total-only  window=[65, 66]  labels=2
    stored     total_debt=32703 due_within_1_year=3538 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=32703 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
             writers: total_debt=statement-spread fill
             ! total_debt: model returned null, filled from page 65 row 'Total interest-bearing liabilities 32,703 38,041'
  kb/ework_2025  shape=bucket-column  window=[70, 71]  labels=3
    stored     total_debt=156410 due_within_1_year=156409 due_1_to_5_years=0 due_after_5_years=0   labels 3/3  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/3  non-null 0
  kb/fagerhult_2025  shape=bucket-rows  window=[140, 141]  labels=4
    stored     total_debt=3449.5 due_within_1_year=56 due_1_to_5_years=3390 due_after_5_years=3.5   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/fasadgruppen_2025  shape=bucket-rows  window=[136, 137]  labels=4
    stored     total_debt=2194 due_within_1_year=159.5 due_1_to_5_years=2034.5 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
  kb/flat_capital_2025  shape=total-only  window=[18, 19]  labels=4
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
  kb/flerie_2025  shape=total-only  window=[86, 87]  labels=2
    stored     total_debt=2.1 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/fm_mattsson_2025  shape=total-only  window=[123, 124]  labels=2
    stored     total_debt=89532 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/gentoo_media_2025  shape=total-only  window=[92, 93]  labels=4
    stored     total_debt=111798 due_within_1_year=111798 due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
  kb/green_landscaping_2025  shape=total-only  window=[99, 100]  labels=4
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/gruvaktiebolaget_viscaria_2025  shape=total-only  window=[111, 112]  labels=2
    stored     total_debt=677.8 due_within_1_year=661.8 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/hansa_biopharma_2025  shape=total-only  window=[65, 66]  labels=2
    stored     total_debt=927403 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/hanza_2025  shape=bucket-rows  window=[133, 134]  labels=4
    stored     total_debt=1444 due_within_1_year=60 due_1_to_5_years=1382 due_after_5_years=2   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/hexatronic_2025  shape=bucket-rows  window=[160, 161]  labels=4
    stored     total_debt=2243 due_within_1_year=62 due_1_to_5_years=2181 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
  kb/hoist_finance_2025  shape=total-only  window=[127, 128]  labels=1
    stored     total_debt=52680 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/humana_2025  shape=total-only  window=[149, 150]  labels=2
    stored     total_debt=4401 due_within_1_year=543 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/humble_2025  shape=total-only  window=[127, 128]  labels=1
    stored     total_debt=1668 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/instalco_2025  shape=total-only  window=[122, 123]  labels=1
    stored     total_debt=3122 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/intrum_2025  shape=bucket-rows  window=[123, 124]  labels=4
    stored     total_debt=43384 due_within_1_year=271 due_1_to_5_years=43113 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
  kb/inwido_2025  shape=total-only  window=[143, 144]  labels=1
    stored     total_debt=1796 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/itab_2025  shape=total-only  window=[125, 126]  labels=1
    stored     total_debt=3369 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/kabe_2025  shape=total-only  window=[29, 30]  labels=2
    stored     total_debt=50 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/karnell_2025  shape=bucket-rows  window=[91, 92]  labels=4
    stored     total_debt=397.2 due_within_1_year=43.5 due_1_to_5_years=353.7 due_after_5_years=0   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/karnov_2025  shape=total-only  window=[135, 136]  labels=2
    stored     total_debt=1965 due_within_1_year=135.2 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/knowit_2025  shape=total-only  window=[152, 153]  labels=4
    stored     total_debt=758938 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
  kb/lime_technologies_2025  shape=subtotal-pair/refused-scope  window=[72, 73]  labels=2
    stored     total_debt=211300 due_within_1_year=80786 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: column reading of 'Borrowing (incl. overdraft) 15,000 51,396 60,000 25,000' declined -- table 'Liquidity risk - Group' is undiscounted; refused under the carrying basis
  kb/linc_2025  shape=total-only  window=[67, 68]  labels=1
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/medcap_2025  shape=bucket-rows  window=[101, 102]  labels=4
    stored     total_debt=718.7 due_within_1_year=102.3 due_1_to_5_years=616.5 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
  kb/meko_2025  shape=total-only  window=[98, 99]  labels=4
    stored     total_debt=6558 due_within_1_year=768 due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
  kb/meren_energy_2025  shape=total-only  window=[32, 33]  labels=2
    stored     total_debt=333.8 due_within_1_year=68.6 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/mildef_2025  shape=total-only  window=[95, 96]  labels=2
    stored     total_debt=772.9 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/modern_times_2025  shape=bucket-column  window=[149, 150]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! due_1_to_5_years: model returned null, fill from page 149 row 'One to five years 207 118' refused -- table 'Maturity analysis – Contractual undiscounted cash flow' is undiscounted
             ! due_after_5_years: model returned null, fill from page 149 row 'More than five years 16 0' refused -- table 'Maturity analysis – Contractual undiscounted cash flow' is undiscounted
  kb/momentum_2025  shape=refused-scope  window=[116, 117]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/morrow_bank_2025  shape=total-only  window=[43, 44]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
  kb/ncab_2025  shape=total-only  window=[101, 102]  labels=4
    stored     total_debt=1090075 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
  kb/nederman_holding_2025  shape=total-only  window=[150, 151]  labels=2
    stored     total_debt=2475.3 due_within_1_year=117.3 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/nelly_2025  shape=total-only  window=[88, 89]  labels=2
    stored     total_debt=287.1 due_within_1_year=36.2 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/net_insight_2025  shape=bucket-rows  window=[79, 80]  labels=4
    stored     total_debt=39415 due_within_1_year=8305 due_1_to_5_years=31110 due_after_5_years=0   labels 3/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
  kb/nobia_2025  shape=bucket-rows  window=[131, 132]  labels=4
    stored     total_debt=2983 due_within_1_year=0 due_1_to_5_years=2983 due_after_5_years=0   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/norion_bank_2025  shape=total-only  window=[70, 71]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 0
  kb/note_2025  shape=subtotal-pair  window=[107, 108]  labels=2
    stored     total_debt=824281 due_within_1_year=595420 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=824281 due_within_1_year=595420 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: model returned null; the note's two section subtotals on page 107 sum to 824281 (228861 + 595420), each closing on its own rows; corroborated by page 109 prose
             ! due_within_1_year: model returned null; 595420 is printed in the note's current-section Summa row on page 107 ('Summa 595 420 380 108'); corroborated by page 109 prose
  kb/oresund_2025  shape=total-only  window=[47, 48]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/orron_energy_2025  shape=total-only  window=[64, 65]  labels=2
    stored     total_debt=106.4 due_within_1_year=0 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/ovzon_2025  shape=total-only  window=[62, 63]  labels=4
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
  kb/powercell_sweden_2025  shape=total-only  window=[44, 45]  labels=1
    stored     total_debt=19055 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=19055 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
             writers: total_debt=statement-spread fill
             ! total_debt: model returned null, filled from page 44 row 'Total borrowings (Note 27) 19,055 73,819'
  kb/proact_it_2025  shape=bucket-rows  window=[104, 105]  labels=4
    stored     total_debt=478611 due_within_1_year=0 due_1_to_5_years=166153 due_after_5_years=None   labels 3/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
  kb/ratos_2025  shape=total-only  window=[131, 132]  labels=1
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/raysearch_laboratories_2025  shape=total-only  window=[72, 73]  labels=2
    stored     total_debt=394.9 due_within_1_year=77.5 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/rejlers_2025  shape=bucket-rows  window=[105, 106]  labels=3
    stored     total_debt=400.3 due_within_1_year=400.3 due_1_to_5_years=0 due_after_5_years=None   labels 3/3  non-null 3
    mechanism  total_debt=None due_within_1_year=400.3 due_1_to_5_years=None due_after_5_years=None   labels 1/3  non-null 1
             writers: due_within_1_year=statement-spread fill
             ! due_within_1_year: model returned null, filled from page 105 row 'Within one year 400.3 349.5'
  kb/rusta_2025  shape=finer-rows  window=[132, 133]  labels=4
    stored     total_debt=6624 due_within_1_year=1039 due_1_to_5_years=3153 due_after_5_years=2431   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/rvrc_holding_2025  shape=bucket-column  window=[110, 111]  labels=2
    stored     total_debt=12 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: column reading of 'Total 210 3 7 0 0 220' declined -- table 'Maturity analysis regarding non-discounted liabilities' is undiscounted; refused under the carrying basis
             ! total_debt: column reading of 'Total 225 2 8 1 0 235' declined -- table 'Maturity analysis regarding non-discounted liabilities' is undiscounted; refused under the carrying basis
  kb/salix_2025  shape=refused-scope  window=[177, 178]  labels=2
    stored     total_debt=3246 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! due_within_1_year: model returned null, fill from page 177 row 'Within 1 year 87 87 1' refused -- table 'Timing of revenue recognition, contract liabilities' is a non-debt subject table
  kb/scandi_standard_2025  shape=bucket-column  window=[127, 128]  labels=2
    stored     total_debt=2307 due_within_1_year=70 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! total_debt: column reading of 'Total 547 44 – – –12' rejected -- due_within_1_year 547, due_1_to_5_years 44 exceed its own total -12; model's own values kept
  kb/sdiptech_2025  shape=total-only  window=[110, 111]  labels=2
    stored     total_debt=4495 due_within_1_year=446 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
    mechanism  total_debt=4495 due_within_1_year=446 due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 2
             writers: total_debt=_subtotal_pair_fill, due_within_1_year=_subtotal_pair_fill
             ! total_debt: model returned null; the note's two section subtotals on page 110 sum to 4495 (4049 + 446), each closing on its own rows; corroborated by page 80 prose
             ! due_within_1_year: model returned null; 446 is printed in the note's current-section Summa row on page 110 ('Total 446 537'); corroborated by page 80 prose
  kb/smartcraft_2025  shape=lease-refused  window=[59, 60]  labels=4
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
             ! due_within_1_year: model returned null, fill from page 59 row 'Less than 1 year 13 825 13 825' refused -- table 'Total undiscounted lease liabilities' is undiscounted
             ! due_after_5_years: model returned null, fill from page 59 row 'More than 5 years - -' refused -- table 'Total undiscounted lease liabilities' is undiscounted
  kb/stillfront_2025  shape=bucket-rows  window=[109, 110]  labels=4
    stored     total_debt=5887 due_within_1_year=None due_1_to_5_years=5152 due_after_5_years=4   labels 3/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/storytel_2025  shape=total-only  window=[114, 115]  labels=4
    stored     total_debt=550 due_within_1_year=550 due_1_to_5_years=None due_after_5_years=None   labels 4/4  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/4  non-null 0
  kb/svedbergs_2025  shape=bucket-rows  window=[132, 133]  labels=4
    stored     total_debt=496405 due_within_1_year=51440 due_1_to_5_years=435842 due_after_5_years=9124   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/svolder_2025  shape=total-only  window=[77, 78]  labels=4
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 3/4  non-null 0
  kb/synsam_2025  shape=bucket-rows  window=[123, 124]  labels=3
    stored     total_debt=2718 due_within_1_year=0 due_1_to_5_years=2718 due_after_5_years=None   labels 3/3  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/3  non-null 0
  kb/tangen_industrikapital_2025  shape=total-only  window=[63, 64]  labels=4
    stored     total_debt=915454 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/traction_2025  shape=prose-zero  window=[19, 20]  labels=1
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/vbg_2025  shape=total-only  window=[133, 134]  labels=1
    stored     total_debt=1504774 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/vef_2025  shape=total-only  window=[20, 21]  labels=2
    stored     total_debt=25721 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 0
  kb/viaplay_2025  shape=bucket-rows  window=[17, 18]  labels=4
    stored     total_debt=6422 due_within_1_year=920 due_1_to_5_years=5502 due_after_5_years=None   labels 4/4  non-null 3
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/4  non-null 0
  kb/vicore_pharma_holding_2025  shape=total-only  window=[46, 47]  labels=1
    stored     total_debt=0 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/1  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/1  non-null 0
  kb/viva_wine_2025  shape=total-only  window=[112, 113]  labels=2
    stored     total_debt=1203 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
  kb/vnv_global_2025  shape=total-only  window=[37, 38]  labels=2
    stored     total_debt=46246 due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 2/2  non-null 1
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 0
  kb/volati_2025  shape=refused-scope  window=[177, 178]  labels=2
    stored     total_debt=3246 due_within_1_year=192 due_1_to_5_years=None due_after_5_years=None   labels 1/2  non-null 2
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
             ! due_within_1_year: model returned null, fill from page 177 row 'Within 1 year 87 87 1' refused -- table 'Timing of revenue recognition, contract liabilities' is a non-debt subject table
  kb/xano_industri_2025  shape=bucket-column  window=[84, 85]  labels=4
    stored     total_debt=904522 due_within_1_year=51075 due_1_to_5_years=802669 due_after_5_years=50778   labels 4/4  non-null 4
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/4  non-null 0
  kb/xvivo_perfusion_2025  shape=total-only  window=[93, 94]  labels=2
    stored     total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0
    mechanism  total_debt=None due_within_1_year=None due_1_to_5_years=None due_after_5_years=None   labels 0/2  non-null 0

summary (scored against labels; fields = labeled field instances, companies = all labeled keys right)
  stored     fields 221/271  companies 73/105  non-null 183/420
  mechanism  fields 69/271  companies 9/105  non-null 19/420

field classes per labeled field instance (variant vs the stored record)
  mechanism: ok-both 68  stored-only 153  mech-only 1  both-wrong 49

companies the mechanism variant turns right over a wrong stored record: none
field instances the mechanism variant reads right over a wrong stored record: 1
  kb/net_insight_2025 due_after_5_years: mechanism None (label null, stored 0)
field instances the stored record reads right that the mechanism variant would lose: 152 null + 1 wrong
  kb/byggmastare_a_j_ahlstrom_h_2025 due_within_1_year: stored 962 (label 962), variant 922

hit rate by stored shape (primary class; mechanism variant vs stored)
  shape           stems | fields stored | fields mech | companies stored | companies mech
  total-only         66 |    112/144    |     44/144  |        46/66     |        6/66
  bucket-rows        22 |     75/81     |     15/81   |        17/22     |        1/22
  bucket-column       8 |     18/23     |      4/23   |         5/8      |        1/8
  refused-scope       3 |      2/6      |      0/6    |         0/3      |        0/3
  prose-zero          2 |      5/5      |      3/5    |         2/2      |        0/2
  subtotal-pair       2 |      4/4      |      2/4    |         2/2      |        1/2
  finer-rows          1 |      4/4      |      0/4    |         1/1      |        0/1
  lease-refused       1 |      1/4      |      1/4    |         0/1      |        0/1
