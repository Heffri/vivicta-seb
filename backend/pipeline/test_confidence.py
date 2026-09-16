"""Self-check for evidence scoring (docs/CONFIDENCE.md). Run: python -m pipeline.test_confidence"""
from . import extract as x


def demo():
    schema = {"keywords": ["income statement"], "checks": [{"name": "gp", "expr": "abs((revenue + cost_of_sales) - gross_profit) <= 2", "identity": True}],
              "fields": [{"key": "revenue", "synonyms": ["revenue", "net sales"], "unit_hint": "currency_millions"},
                         {"key": "eps_basic", "synonyms": ["earnings per share"], "unit_hint": "currency_per_share"}]}
    checks = [{"name": "gp", "passed": True, "detail": ""}]
    f = {"key": "revenue", "value": 168343, "unit": "MSEK", "period": "2025", "raw_label": "Revenues 3",
         "source": {"page": 106, "quote": "Revenues 3 168 343 176 771"}, "confidence": 0, "evidence": ["quote_on_page"]}
    x.score_field(f, schema["fields"][0], checks, schema, "MSEK", 2025, {106})
    assert f["confidence"] == 1.0 and len(f["evidence"]) == 7, f
    f = {"key": "eps_basic", "value": 5.43, "unit": "SEK", "period": "2025", "raw_label": "Basic earnings per share",
         "source": {"page": 106, "quote": "Basic earnings per share, SEK 5.43 5.66"}, "confidence": 0, "evidence": ["quote_on_page"]}
    x.score_field(f, schema["fields"][1], checks, schema, "MSEK", 2025, {106})
    assert "unit_ok" in f["evidence"] and "value_in_quote" in f["evidence"] and "label_known" not in f["evidence"], f  # "Basic earnings..." is not a prefix of a synonym
    f = {"key": "revenue", "value": 138494, "unit": "MSEK", "period": "2025", "raw_label": "Net sales",
         "source": {"page": 189, "quote": "made up"}, "confidence": 0, "evidence": []}
    x.score_field(f, schema["fields"][0], checks, schema, "MSEK", 2025, set())
    assert f["confidence"] == 0.25 and "quote_on_page" not in f["evidence"], f  # cap: no provenance
    f = {"key": "revenue", "value": 100, "unit": "MSEK", "period": "2025", "raw_label": "Net sales",
         "source": {"page": 1, "quote": "Net sales 100"}, "confidence": 0, "evidence": ["quote_on_page"]}
    x.score_field(f, schema["fields"][0], [{"name": "gp", "passed": False, "detail": ""}], schema, "MSEK", 2025, {1})
    assert f["confidence"] == 0.5 and "arith_ok" not in f["evidence"], f  # cap: failed check
    assert x._value_in_quote(-7246, "Income tax (7,246) (6,910)") and x._value_in_quote(4.56, "4,56 kr") and not x._value_in_quote(1683, "3 168 343")
    assert not x._value_in_quote(1171, "Earnings per share 11.71 10.02") and x._value_in_quote(11.71, "11.71") and x._value_in_quote(168343, "168.343")
    assert x.repair_value(1171, "Basic earnings per share, SEK 11.71") == 11.71 and x.repair_value(5424600, "Net sales 5,424.6 5,401.1") == 5424.6
    assert x.repair_value(168343, "Revenues 3 168 343 176 771") is None and x.repair_value(309, "EPS 3.09") == 3.09
    from .parse import quote_on_page
    page = "Revenue\n6,7\n176,658\n176,481\nCost of sales"
    assert quote_on_page("Revenue 176,658", page)  # note refs between label and number
    assert quote_on_page("Försäljningsintäkter 79 146", "Försäljningsintäkter\n4\n79 146\n63 751")
    assert quote_on_page("Kostnad för sålda varor -61 978", "Kostnad för sålda varor\n5\n–61 978\n–50 088")  # en dash
    assert not quote_on_page("Revenue 176", page) and not quote_on_page("Revenue 999", page)
    assert not quote_on_page("176,658", "Revenue 176,658") and not quote_on_page("Revenue", "Revenue 176,658")  # bare number / bare label
    telia = "Continuing operations \nRevenue\n C5, C6\n80,982\n80,965\nGoods and services purchased\nC7\n-28,277\nOperating income\nC5\n10,426\n10,834"
    assert quote_on_page("Continuing operations Operating income C5 10,426 10,834", telia) == "Operating income C5 10,426 10,834"  # header prepended
    assert quote_on_page("Earnings per share\n1\nGroup\n15.76\n15.73", "EARNINGS PER SHARE 1\nsek\n2025\n2024\nGroup, excluding items 17.09 16.74\nGroup\n15.76\n15.73") == "Group 15.76 15.73"
    # column repair: Sandvik prints 2024 before 2025
    assert x._year_column("Consolidated income statement\nMSEK\nNote\n2024\n2025\nRevenue\nG2, G3\n122,878\n120,680", 2025) == (1, 2)
    assert x._year_column("Income Statements\nYear ended December 31 ($ in millions)\n2025\n2024\nSales", 2025) == (0, 2)
    assert x._year_column("Consolidated income statement for the year ended december 31 msek note revenues 168 343", 2025) is None
    assert x._year_column("Industrial Operations Financial Services Eliminations Volvo Group\n2025 2024 2025 2024 2025 2024 2025 2024\nNet sales", 2025) is None  # segments side by side
    assert x._row_amounts("Revenue\nG2, G3\n122,878\n120,680") == [122878, 120680] and x._row_amounts("Revenue 6, 7 176,658 176,481") == [176658, 176481]
    assert x._row_amounts("Försäljningsintäkter 4 79 146 63 751") == [79146, 63751] and x._row_amounts("Cost of goods sold 6,12 -1,827.9 -1,791.4") == [-1827.9, -1791.4]
    assert x._row_amounts("Income tax (7,246) (6,910)") == [-7246, -6910] and x._row_amounts("Resultat per aktie (SEK) 11,77 9,02") == [11.77, 9.02]
    assert x._row_amounts("Discontinued operations held for sale, net of income tax 18 (19) (37)", 2) == [-19, -37]  # Arion: a two-digit amount in parentheses is not a note reference
    assert x._row_amounts("Earnings per share, Euro cent 23.0 38.1") == [23, 38.1] and x._row_amounts("Net sales 3,5,24 5,424.6 5,401.1") == [5424.6, 5401.1]
    assert x.repair_value(230, "Earnings per share, Euro cent 23.0 38.1") == 23 and x.repair_value(50, "Note 5 Revenue") is None
    assert x._value_in_quote(0.9, "total C20 0.90 1.80") and x._value_in_quote(11.7, "(SEK) 14 11,70 7,74") and not x._value_in_quote(11.7, "11.75")
    # Swedish space-grouped rows need the column count: "155 054 161 900" is two amounts, not one
    assert x._row_amounts("Sales 155 054 161 900", 2) == [155054, 161900] and x._row_amounts("Total sales 6, 10 155 113 161 921", 2) == [155113, 161921]
    assert x._row_amounts("Innehav utan bestämmande inflytande 42 39", 2) == [42, 39] and x._row_amounts("Production expenses 11, 12, 13 -121 972 -127 935", 2) == [-121972, -127935]
    assert x._row_amounts("Operating income 9 073 9 296", 2) == [9073, 9296]
    assert x._year_column("Consolidated income statement\nSEK million\nNote\n2025\nJan-Dec\n2024\nRevenue", 2025) == (0, 2)  # Telia
    # page rows: the printed row behind a truncated quote, and the number under a synonym label the model renamed
    page = "Consolidated income statement\nSEK M\nNote\n2025\n2024\nRevenue\n6, 7\n176,658\n176,481\nCost of sales\n8, 9, 10, 33, 38\n-161,906\n-162,001\nGross income\n14,753\n14,480\nProfit after financial items\n3,145\n2,282\nEarnings per share, SEK1\n17\n8.29\n6.01"
    rows = x._page_rows(page)
    assert "Gross income 14,753 14,480" in rows and "Revenue 6, 7 176,658 176,481" in rows and "Cost of sales 8, 9, 10, 33, 38 -161,906 -162,001" in rows, rows
    assert x._row_label("Gross income 14,753 14,480") == "Gross income" and x._row_label("Earnings per share, SEK1 17 8.29 6.01") == "Earnings per share, SEK1"
    assert x._row_label("Production expenses 11, 12, 13 -121 972 -127 935") == "Production expenses"
    row = next(r for r in rows if quote_on_page("Gross income 14,480", r))
    assert x._row_amounts(row, 2) == [14753, 14480]
    pbt = {"key": "profit_before_tax", "synonyms": ["profit before tax", "profit after financial items"]}
    hit = next(r for r in rows if x._label_known(x._row_label(r), pbt) and x._value_in_quote(3145, r))
    assert x._label_known("Profit/loss before tax", pbt) and x._label_known("Profit (loss) before tax 9", pbt)  # Yubico
    assert x._clean_label("Result before Tax") == "profit before tax" and x._clean_label("Operating result 2.1") == "operating profit"  # SSAB, Stora Enso
    assert x._ccy("KSEK") == x._ccy("TSEK") == x._ccy("SEK thousand") == "SEK" and x._ccy("TEUR") == "EUR"  # Paradox reports in KSEK
    assert hit == "Profit after financial items 3,145 2,282", hit
    assert quote_on_page("Cost of sales -161,906", page), "long note-reference gap"
    assert x._ccy("MSEK") == x._ccy("SEKm") == x._ccy("SEK million") == "SEK" and x._ccy("USD m") == "USD" and x._ccy("MEUR") == x._ccy("Euro cent") == "EUR" and x._ccy("kr") == "SEK"
    # a check whose operand is missing is n/a, not failed; another year's figure is capped at 0.5
    f = {"key": "revenue", "value": 100, "unit": "MSEK", "period": "2025", "raw_label": "Net sales",
         "source": {"page": 1, "quote": "Net sales 100"}, "confidence": 0, "evidence": ["quote_on_page"]}
    x.score_field(f, schema["fields"][0], [{"name": "gp", "passed": False, "detail": "missing: gross_profit"}], schema, "MSEK", 2025, {1})
    assert f["confidence"] == 1.0, f
    f = {"key": "revenue", "value": 122878, "unit": "MSEK", "period": "2024", "raw_label": "Revenue",
         "source": {"page": 1, "quote": "Revenue 122,878 120,680"}, "confidence": 0, "evidence": ["quote_on_page"]}
    x.score_field(f, schema["fields"][0], checks, schema, "MSEK", 2025, {1})
    assert f["confidence"] == 0.5 and "period_ok" not in f["evidence"], f
    f = {"key": "revenue", "value": 4578, "unit": "MSEK", "period": "2025", "raw_label": "EBITDA",
         "source": {"page": 1, "quote": "EBITDA 6,564 7,143"}, "confidence": 0, "evidence": ["quote_on_page"]}
    x.score_field(f, schema["fields"][0], checks, schema, "MSEK", 2025, {1})
    assert f["confidence"] == 0.5 and "value_in_quote" not in f["evidence"], f  # number not in its own quote
    # end to end on a by-nature statement: a revenue subtotal is unwound, a null the model gave is filled from the page
    sca = ("Consolidated income statement\nSEKm\nNote\n2025\n2024\nNet sales\nB1\n20,427\n20,232\nOther operating income\nB1, B2\n3,020\n3,395\n"
           "Revenue\n23,447\n23,627\nOperating profit\n4,432\n5,027\nProfit before tax\n3,999\n4,521\nIncome taxes\nB5\n–794\n–882")
    full = {"name": "is", "keywords": ["income statement"], "checks": [], "fields": [
        {"key": "revenue", "label": "Revenue", "synonyms": ["revenue", "net sales"], "unit_hint": "currency_millions", "excludes": ["other operating income"]},
        {"key": "profit_before_tax", "label": "PBT", "synonyms": ["profit before tax"], "unit_hint": "currency_millions"},
        {"key": "income_tax", "label": "Tax", "synonyms": ["income taxes"], "unit_hint": "currency_millions"}]}
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "revenue", "value": 23447, "unit": "SEKm", "period": "2025", "raw_label": "Revenue", "source": {"page": 1, "quote": "Revenue 23,447 23,627"}},
        {"key": "profit_before_tax", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "income_tax", "value": -794, "unit": "SEKm", "period": "2025", "raw_label": "Income taxes", "source": {"page": 2, "quote": "Income taxes -794"}}]}
    out = x.extract([sca, "Note B5 Taxes\nblah"], [1, 2], full, {"fiscal_year": 2025})
    got = {f["key"]: (f["value"], f["confidence"], f["source"]["page"]) for f in out["fields"]}
    assert got == {"revenue": (20427, 1.0, 1), "profit_before_tax": (3999, 1.0, 1), "income_tax": (-794, 1.0, 1)}, (got, out["warnings"])
    assert out["fields"][1]["unit"] == "SEKm" and out["fields"][1]["source"]["quote"] == "Profit before tax 3,999 4,521", out["fields"][1]
    # variant rows: an adjusted / diluted EPS label is not the field, the plain statement row replaces it
    import json, pathlib
    eps = next(f for f in json.loads((pathlib.Path(__file__).parents[1] / "schemas" / "income_statement.json").read_text("utf-8"))["fields"] if f["key"] == "eps_basic")
    assert x._label_known("Earnings per share before and after dilution (SEK)", eps) and x._label_known("Earnings per share (SEK), basic and diluted, total C20", eps)
    assert not x._label_known("Earnings per share before and after dilution and before items affecting comparability (SEK)1", eps)
    assert not x._label_known("Resultat per aktie efter utspädning (SEK)", eps) and x._label_known("Resultat per aktie före utspädning (SEK)", eps)
    sec = "Consolidated statement of income\nNote\n2025\n2024\nNet income for the year\n5 144\n5 172\nEarnings per share before and after dilution (SEK)\n3\n8.93\n9.01\nEarnings per share before and after dilution and before items affecting \ncomparability (SEK)1\n3\n11.55\n10.81"
    x.call_llm = lambda *a, **k: {"fields": [{"key": "eps_basic", "value": 11.55, "unit": "SEK", "period": "2025", "raw_label": "Earnings per share before and after dilution and before items affecting comparability (SEK)",
                                             "source": {"page": 1, "quote": "comparability (SEK)1 3 11.55 10.81"}}]}
    out = x.extract([sec], [1], {"name": "is", "keywords": [], "checks": [], "fields": [eps]}, {"fiscal_year": 2025})
    f = out["fields"][0]
    assert (f["value"], f["confidence"], f["source"]["quote"]) == (8.93, 1.0, "Earnings per share before and after dilution (SEK) 3 8.93 9.01"), (f, out["warnings"])
    # Röko: the text layer prints "Profit before tax 1,01 923" (a digit lost); the three rows above sum to 1,010 / 923
    roko = ("Consolidated income statement\nMSEK\nNote\n2025\n2024\nOperating profit\n8, 9, 10, 11, 12\n1,051\n969\nFinancial income\n7, 13\n49\n66\n"
            "Financial expenses\n7, 12, 13\n-90\n-112\nProfit before tax\n1,01\n923\nTax on net profit for the year\n14\n-254\n-221\nNet profit for the year1\n755\n702\n")
    sch = {"name": "is", "keywords": [], "fields": [{"key": k, "label": k, "synonyms": [syn], "unit_hint": "currency_millions"} for k, syn in
           (("profit_before_tax", "profit before tax"), ("income_tax", "tax on net profit for the year"), ("net_profit", "net profit for the year"))],
           "checks": [{"name": "net_profit_arith", "expr": "abs((profit_before_tax + income_tax) - net_profit) <= 2", "identity": True}]}
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "profit_before_tax", "value": 923, "unit": "MSEK", "period": "2025", "raw_label": "Profit before tax", "source": {"page": 1, "quote": "Profit before tax 1,01 923"}},
        {"key": "income_tax", "value": -254, "unit": "MSEK", "period": "2025", "raw_label": "Tax on net profit for the year", "source": {"page": 1, "quote": "Tax on net profit for the year 14 -254 -221"}},
        {"key": "net_profit", "value": 755, "unit": "MSEK", "period": "2025", "raw_label": "Net profit for the year1", "source": {"page": 1, "quote": "Net profit for the year1 755 702"}}]}
    out = x.extract([roko], [1], sch, {"fiscal_year": 2025})
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(1010, 1.0), (-254, 1.0), (755, 1.0)], (out["fields"], out["warnings"])
    assert out["checks"][0]["passed"] and "value_derived" in out["fields"][0]["evidence"] and out["fields"][0]["source"]["quote"].startswith("Operating profit"), out
    # NOBA (a bank): no "profit before tax" row, so PBT's fallback synonym "operating profit" applies; "before credit losses" is excluded
    real = {f["key"]: f for f in json.load(open(pathlib.Path(__file__).parent.parent / "schemas" / "income_statement.json", encoding="utf-8"))["fields"]}
    bank = ("INCOME STATEMENT, CONSOLIDATED\nSEKm\nNOTE\nJAN-DEC \n2025\nJAN-DEC \n2024\nTotal operating income\n11,276\n9,884\nProfit before credit losses\n8,519\n7,161\n"
            "Net credit losses\n14\n-3,780\n-4,149\nOperating profit before amortisation of transaction surplus values\n4,739\n3,012\nAmortisation of surplus values from transactions\n12\n-128\n-134\n"
            "Operating profit \n6\n4,610\n2,878\nTax on profit for the year\n15\n-999\n-676\nNet profit for the year\n3,611\n2,202\n")
    sch = {"name": "is", "keywords": [], "fields": [real[k] for k in ("revenue", "profit_before_tax", "income_tax", "net_profit")],
           "checks": [{"name": "net_profit_arith", "expr": "abs((profit_before_tax + income_tax) - net_profit) <= 2", "identity": True}]}
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "revenue", "value": 11276, "unit": "SEKm", "period": "2025", "raw_label": "Total operating income", "source": {"page": 1, "quote": "Total operating income 11,276 9,884"}},
        {"key": "profit_before_tax", "value": 8519, "unit": "SEKm", "period": "2025", "raw_label": "Profit before credit losses", "source": {"page": 1, "quote": "Profit before credit losses 8,519 7,161"}},
        {"key": "income_tax", "value": -999, "unit": "SEKm", "period": "2025", "raw_label": "Tax on profit for the year", "source": {"page": 1, "quote": "Tax on profit for the year 15 -999 -676"}},
        {"key": "net_profit", "value": 3611, "unit": "SEKm", "period": "2025", "raw_label": "Net profit for the year", "source": {"page": 1, "quote": "Net profit for the year 3,611 2,202"}}]}
    out = x.extract([bank], [1], sch, {"fiscal_year": 2025})
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(11276, 1.0), (4610, 1.0), (-999, 1.0), (3611, 1.0)], (out["fields"], out["warnings"])
    assert out["fields"][1]["raw_label"] == "Operating profit" and out["checks"][0]["passed"], out
    # an industrial keeps "Operating profit" and "Profit before tax" apart: the fallback never switches on when the primary row exists
    ind = "Income statement\nMSEK\n2025\n2024\nOperating profit\n1,051\n969\nProfit before tax\n1,010\n923\nTax\n-254\n-221\nNet profit for the year\n755\n702\n"
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "profit_before_tax", "value": 1051, "unit": "MSEK", "period": "2025", "raw_label": "Operating profit", "source": {"page": 1, "quote": "Operating profit 1,051 969"}},
        {"key": "income_tax", "value": -254, "unit": "MSEK", "period": "2025", "raw_label": "Tax", "source": {"page": 1, "quote": "Tax -254 -221"}},
        {"key": "net_profit", "value": 755, "unit": "MSEK", "period": "2025", "raw_label": "Net profit for the year", "source": {"page": 1, "quote": "Net profit for the year 755 702"}}]}
    out = x.extract([ind], [1], {**sch, "fields": sch["fields"][1:]}, {"fiscal_year": 2025})
    assert (out["fields"][0]["value"], out["fields"][0]["confidence"]) == (1051, 0.5) and "label_known" not in out["fields"][0]["evidence"], out["fields"][0]
    # NCC: EPS "before items affecting comparability" is the adjusted figure; "after items affecting comparability" is the IFRS one
    ncc = ("Consolidated income statement\nSEK M\nNote\n2025\n2024\nNet profit for the year\n142\n1,571\nEarnings per share before and after dilution\n26\n"
           "Earnings per share, SEK, before items affecting comparability\n13.89 \n16.08 \nEarnings per share, SEK, after items affecting comparability\n1.45 \n16.08 \n")
    x.call_llm = lambda *a, **k: {"fields": [{"key": "eps_basic", "value": 13.89, "unit": "SEK", "period": "2025", "raw_label": "Earnings per share, SEK, before items affecting comparability",
                                             "source": {"page": 1, "quote": "Earnings per share, SEK, before items affecting comparability 13.89 16.08"}}]}
    out = x.extract([ncc], [1], {"name": "is", "keywords": [], "checks": [], "fields": [real["eps_basic"]]}, {"fiscal_year": 2025})
    assert (out["fields"][0]["value"], out["fields"][0]["confidence"]) == (1.45, 1.0), (out["fields"][0], out["warnings"])
    # Stora Enso: "Materials and services" is not cost of sales, and a by-nature statement has no gross profit to check it against
    x.call_llm = lambda *a, **k: {"fields": [{"key": "cost_of_sales", "value": -7020, "unit": "EUR million", "period": "2025", "raw_label": "Materials and services",
                                             "source": {"page": 1, "quote": "Materials and services1 2.2 -7,020 -6,738"}}]}
    out = x.extract(["Consolidated income statement\nEUR million\n2025\n2024\nSales\n8,999\n9,050\nMaterials and services1\n2.2\n-7,020\n-6,738\n"], [1],
                    {"name": "is", "keywords": [], "checks": [], "fields": [real["cost_of_sales"], real["gross_profit"]]}, {"fiscal_year": 2025})
    assert out["fields"][0]["value"] is None and "dropped" in out["warnings"][-1], (out["fields"], out["warnings"])
    # Catena: no total tax row; "Current tax" + "Deferred tax" = the model's -423, and PBT + tax = net profit holds in both columns
    cat = ("Consolidated statement of comprehensive income\nSEK M\nNote 3 01/01/2025 -31/12/2025 01/01/2024 -31/12/2024\nProfit before tax\n2,067\n1,344\n"
           "Current tax\n-56\n-53\nDeferred tax\n10\n-367\n-211\nNet profit for the year\n19\n1,644\n1,080\n")
    assert x._year_column(cat, 2025) == (0, 2)
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "profit_before_tax", "value": 2067, "unit": "SEK M", "period": "2025", "raw_label": "Profit before tax", "source": {"page": 1, "quote": "Profit before tax 2,067 1,344"}},
        {"key": "income_tax", "value": -423, "unit": "SEK M", "period": "2025", "raw_label": "Current tax\nDeferred tax", "source": {"page": 1, "quote": "Deferred tax 10 -367 -211"}},
        {"key": "net_profit", "value": 1644, "unit": "SEK M", "period": "2025", "raw_label": "Net profit for the year", "source": {"page": 1, "quote": "Net profit for the year 19 1,644 1,080"}}]}
    sch = {"name": "is", "keywords": [], "fields": [real[k] for k in ("profit_before_tax", "income_tax", "net_profit")],
           "checks": [{"name": "net_profit_arith", "expr": "abs((profit_before_tax + income_tax) - net_profit) <= 2", "identity": True}]}
    out = x.extract([cat], [1], sch, {"fiscal_year": 2025})
    tax = out["fields"][1]
    assert (tax["value"], tax["confidence"], tax["raw_label"]) == (-423, 1.0, "Current tax + Deferred tax") and "value_derived" in tax["evidence"], (tax, out["warnings"])
    # ... but not when the comparative column disagrees (a coincidence in the fiscal year is not a proof): then -423 is printed nowhere and is dropped
    out = x.extract([cat.replace("-53", "-99")], [1], sch, {"fiscal_year": 2025})
    assert out["fields"][1]["value"] is None and any("printed on none of pages" in w for w in out["warnings"]), (out["fields"][1], out["warnings"])
    # ... and "Net operating surplus" is not operating profit; with no operating profit row on the page the value is dropped
    x.call_llm = lambda *a, **k: {"fields": [{"key": "operating_profit", "value": 2198, "unit": "SEK M", "period": "2025", "raw_label": "Net operating surplus",
                                             "source": {"page": 1, "quote": "Net operating surplus 2,198 1,789"}}]}
    out = x.extract([cat.replace("Profit before tax", "Net operating surplus\n2,198\n1,789\nProfit before tax")], [1],
                    {"name": "is", "keywords": [], "checks": [], "fields": [real["operating_profit"]]}, {"fiscal_year": 2025})
    assert out["fields"][0]["value"] is None and "dropped" in out["warnings"][-1], (out["fields"], out["warnings"])
    # SEB: the model timed out, rows are filled from the page; "Income tax expense 7,835" is printed unsigned; unit from the header
    seb = ("Income statement\nSEB GROUP\nSEK m\nNote\n2025\n2024\nTotal operating income\n76,939\n81,887\nOperating profit before items affecting comparability\n39,314\n46,043\n"
           "Operating profit\n38,898\n46,043\nIncome tax expense\n14\n7,835\n10,178\nNET PROFIT\n31,063\n35,865\nBasic earnings per share, SEK\n15\n15.60\n17.51\n"
           "Diluted earnings per share, SEK\n15\n15.43\n17.33\n")
    def boom(*a, **k):
        raise TimeoutError("stuck")
    x.call_llm = boom
    sch = {"name": "is", "keywords": [], "fields": [real[k] for k in ("revenue", "operating_profit", "profit_before_tax", "income_tax", "net_profit", "eps_basic")],
           "checks": [{"name": "net_profit_arith", "expr": "abs((profit_before_tax + income_tax) - net_profit) <= 2", "identity": True}]}
    out = x.extract([seb, ""], [1, 2], sch, {"fiscal_year": 2025})
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(76939, 1.0), (38898, 1.0), (38898, 1.0), (-7835, 1.0), (31063, 1.0), (15.6, 1.0)], (out["fields"], out["warnings"])
    assert out["currency"] == "SEK m" and sum("llm:" in w for w in out["warnings"]) == 2, out  # the spread and the single page; not the four-page window
    assert x._page_unit("Consolidated Statement of Operations\nUSD Thousands\nNote 2025 2024") == "USD Thousands" and x._page_unit("SEK M\nNote 2025") == "SEK M"
    assert not x._label_known("Earnings per share fully diluted - USD1", real["eps_basic"]) and x._label_known("Earnings per share - USD1", real["eps_basic"])  # IPC
    # SEB, model answered: profit before tax offered as "Profit before credit losses..." (a variant); the statement row is the
    # exact synonym "Operating profit", not the prefix match "Operating profit before items affecting comparability"
    seb2 = seb.replace("Operating profit\n38,898", "Profit before credit losses and imposed levies\n44,342\n51,000\nOperating profit\n38,898")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "profit_before_tax", "value": 44342, "unit": "SEK m", "period": "2025", "raw_label": "Profit before credit losses and imposed levies", "source": {"page": 1, "quote": "Profit before credit losses and imposed levies 44,342"}},
        {"key": "income_tax", "value": 7835, "unit": "SEK m", "period": "2025", "raw_label": "Income tax expense", "source": {"page": 1, "quote": "Income tax expense 14 7,835"}},
        {"key": "net_profit", "value": 31063, "unit": "SEK m", "period": "2025", "raw_label": "NET PROFIT", "source": {"page": 1, "quote": "NET PROFIT 31,063"}}]}
    out = x.extract([seb2], [1], {**sch, "fields": [real[k] for k in ("profit_before_tax", "income_tax", "net_profit")]}, {"fiscal_year": 2025})
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(38898, 1.0), (-7835, 1.0), (31063, 1.0)], (out["fields"], out["warnings"])
    # IPC: the model quoted the first row under the "Cost of sales" heading; the four rows sum to revenue - gross profit in both columns
    ipc = ("Consolidated Statement of Operations\nUSD Thousands\nNote 2025 2024\nRevenue 3 685,888 797,783\nCost of sales\nProduction costs 4 (427,623) (448,218)\n"
           "Depletion and decommissioning costs 3,9 (122,749) (128,392)\nDepreciation of other tangible fixed assets 3,9 (5,597) (8,933)\n"
           "Exploration and business development costs 3 (1,799) (2,069)\nGross profit 3 128,120 210,171\nOther income / (expense) 751 1,137\n")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "revenue", "value": 685888, "unit": "USD Thousands", "period": "2025", "raw_label": "Revenue", "source": {"page": 1, "quote": "Revenue 3 685,888"}},
        {"key": "cost_of_sales", "value": -427623, "unit": "USD Thousands", "period": "2025", "raw_label": "Cost of sales", "source": {"page": 1, "quote": "Production costs 4 (427,623)"}},
        {"key": "gross_profit", "value": 128120, "unit": "USD Thousands", "period": "2025", "raw_label": "Gross profit", "source": {"page": 1, "quote": "Gross profit 3 128,120"}}]}
    gp = {"name": "gross_profit_arith", "expr": "abs((revenue + cost_of_sales) - gross_profit) <= 2", "identity": True}
    out = x.extract([ipc], [1], {"name": "is", "keywords": [], "checks": [gp], "fields": [real[k] for k in ("revenue", "cost_of_sales", "gross_profit")]}, {"fiscal_year": 2025})
    cos = out["fields"][1]
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(685888, 1.0), (-557768, 1.0), (128120, 1.0)], (out["fields"], out["warnings"])
    assert cos["raw_label"] == "Cost of sales" and cos["source"]["quote"].startswith("Production costs") and "value_derived" in cos["evidence"], cos
    # Lundbergs (by nature, no gross profit): "Rörelseresultat" offered as gross profit as well as operating profit -> the twin without the label goes,
    # then the cost row it required
    lb = ("Resultaträkning\nKONCERNEN, mnkr\nNot 2025 2024\nNettoomsättning m m 3 28 781 29 311\nRåvaror, förnödenheter samt kostnad sålda lageraktier -12 455 -13 494\n"
          "Personalkostnader 5 -4 038 -3 996\nRörelseresultat 11 16 077 10 334\n")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "revenue", "value": 28781, "unit": "mnkr", "period": "2025", "raw_label": "Nettoomsättning m m", "source": {"page": 1, "quote": "Nettoomsättning m m 3 28 781"}},
        {"key": "cost_of_sales", "value": -12455, "unit": "mnkr", "period": "2025", "raw_label": "Råvaror, förnödenheter samt kostnad sålda lageraktier", "source": {"page": 1, "quote": "Råvaror, förnödenheter samt kostnad sålda lageraktier -12 455"}},
        {"key": "gross_profit", "value": 16077, "unit": "mnkr", "period": "2025", "raw_label": "Rörelseresultat", "source": {"page": 1, "quote": "Rörelseresultat 11 16 077"}},
        {"key": "operating_profit", "value": 16077, "unit": "mnkr", "period": "2025", "raw_label": "Rörelseresultat", "source": {"page": 1, "quote": "Rörelseresultat 11 16 077"}}]}
    out = x.extract([lb], [1], {"name": "is", "keywords": [], "checks": [gp], "fields": [real[k] for k in ("revenue", "cost_of_sales", "gross_profit", "operating_profit")]}, {"fiscal_year": 2025})
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(28781, 1.0), (None, 0.0), (None, 0.0), (16077, 1.0)], (out["fields"], out["warnings"])
    assert x._page_unit(lb) == "mnkr", x._page_unit(lb)
    # Lundbergs, second run: the model paired every label with the row below it ("Rörelseresultat" 16077 quoted as "Resultat efter
    # finansiella poster 15 465"), and "Nettoomsättning" with the 30 615 subtotal on the "Övriga intäkter" row
    lb2 = ("Resultaträkning\nKONCERNEN, mnkr\nNot 2025 2024\nNettoomsättning m m 3 28 781 29 311\nÖvriga intäkter m m 4 1 834 2 385 30 615 31 696\n"
           "Rörelseresultat 11 16 077 10 334\nFinansiella intäkter 12 58 79\nResultat efter finansiella poster 15 465 9 808\nSkatt 13 -1 044 -1 425\nÅrets resultat 14 421 8 383\n")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "revenue", "value": 30615, "unit": "mnkr", "period": "2025", "raw_label": "Nettoomsättning m m", "source": {"page": 1, "quote": "Övriga intäkter m m 4 1 834 2 385 30 615"}},
        {"key": "operating_profit", "value": 16077, "unit": "mnkr", "period": "2025", "raw_label": "Rörelseresultat", "source": {"page": 1, "quote": "Resultat efter finansiella poster 15 465"}},
        {"key": "profit_before_tax", "value": 15465, "unit": "mnkr", "period": "2025", "raw_label": "Resultat efter finansiella poster", "source": {"page": 1, "quote": "Skatt 13 -1 044"}},
        {"key": "income_tax", "value": -1044, "unit": "mnkr", "period": "2025", "raw_label": "Skatt", "source": {"page": 1, "quote": "Årets resultat 14 421"}},
        {"key": "net_profit", "value": 14421, "unit": "mnkr", "period": "2025", "raw_label": "Årets resultat", "source": {"page": 1, "quote": "Årets resultat 14 421"}}]}
    out = x.extract([lb2], [1], {**sch, "fields": [real[k] for k in ("revenue", "operating_profit", "profit_before_tax", "income_tax", "net_profit")]}, {"fiscal_year": 2025})
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(28781, 1.0), (16077, 1.0), (15465, 1.0), (-1044, 1.0), (14421, 1.0)], (out["fields"], out["warnings"])
    assert out["fields"][1]["source"]["quote"] == "Rörelseresultat 11 16 077 10 334" and sum("row prints" in w for w in out["warnings"]) == 4, out["warnings"]
    # Catena (property company): rental income - property expenses = net operating surplus is the gross profit
    assert x._label_known("Net operating surplus", real["gross_profit"]) and x._label_known("Property expenses", real["cost_of_sales"]) and not x._label_known("Net operating surplus", real["operating_profit"])
    # Addnode: "Purchases of goods and services" is not a cost of sales label, but net sales + it = gross profit in both years
    an = "Consolidated income statement\nSEK m\nNote 2025 2024\nNet sales 2, 3, 38 5,793 7,757\nPurchases of goods and services 38 -1,350 -3,559\nGross profit 4,443 4,198\n"
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "revenue", "value": 5793, "unit": "SEK m", "period": "2025", "raw_label": "Net sales", "source": {"page": 1, "quote": "Net sales 2, 3, 38 5,793"}},
        {"key": "cost_of_sales", "value": -1350, "unit": "SEK m", "period": "2025", "raw_label": "Purchases of goods and services", "source": {"page": 1, "quote": "Purchases of goods and services 38 -1,350"}},
        {"key": "gross_profit", "value": 4443, "unit": "SEK m", "period": "2025", "raw_label": "Gross profit", "source": {"page": 1, "quote": "Gross profit 4,443"}}]}
    out = x.extract([an], [1], {"name": "is", "keywords": [], "checks": [gp], "fields": [real[k] for k in ("revenue", "cost_of_sales", "gross_profit")]}, {"fiscal_year": 2025})
    assert [f["confidence"] for f in out["fields"]] == [1.0, 1.0, 1.0] and "identity_all_columns" in out["fields"][1]["evidence"], (out["fields"], out["warnings"])
    out = x.extract([an.replace("-3,559", "-3,000")], [1], {"name": "is", "keywords": [], "checks": [gp], "fields": [real[k] for k in ("revenue", "cost_of_sales", "gross_profit")]}, {"fiscal_year": 2025})
    assert out["fields"][1]["confidence"] == 0.9, out["fields"][1]  # only one year adds up: the label stays unknown
    # Volvo: "2025 2024" per segment; the model took income taxes from Industrial Operations and the rest from Volvo Group
    vo = ("Consolidated income statement\nIndustrial Operations Financial Services Eliminations Volvo Group\nSEK M Note 2025 2024 2025 2024 2025 2024 2025 2024\n"
          "Net sales 6, 7 457,509 504,975 26,469 26,982 -4,795 -5,140 479,183 526,816\nIncome after financial items 43,522 63,168 3,869 4,042 – – 47,391 67,210\n"
          "Income taxes 10 -11,669 -15,542 -1,016 -1,092 – – -12,685 -16,634\nIncome for the period * 31,853 47,626 2,853 2,949 – – 34,707 50,576\n")
    assert x._row_amounts("Income taxes 10 -11,669 -15,542 -1,016 -1,092 – – -12,685 -16,634", 8) == [-11669, -15542, -1016, -1092, 0, 0, -12685, -16634]
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "revenue", "value": 479183, "unit": "SEK M", "period": "2025", "raw_label": "Net sales", "source": {"page": 1, "quote": "Net sales 6, 7 457,509 504,975 26,469 26,982 -4,795 -5,140 479,183 526,816"}},
        {"key": "profit_before_tax", "value": 47391, "unit": "SEK M", "period": "2025", "raw_label": "Income after financial items", "source": {"page": 1, "quote": "Income after financial items 43,522 63,168 3,869 4,042 – – 47,391 67,210"}},
        {"key": "income_tax", "value": -11669, "unit": "SEK M", "period": "2025", "raw_label": "Income taxes", "source": {"page": 1, "quote": "Income taxes 10 -11,669 -15,542 -1,016 -1,092 – – -12,685 -16,634"}},
        {"key": "net_profit", "value": 34707, "unit": "SEK M", "period": "2025", "raw_label": "Income for the period", "source": {"page": 1, "quote": "Income for the period * 31,853 47,626 2,853 2,949 – – 34,707 50,576"}}]}
    out = x.extract([vo], [1], {**sch, "fields": [real[k] for k in ("revenue", "profit_before_tax", "income_tax", "net_profit")]}, {"fiscal_year": 2025})
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(479183, 1.0), (47391, 1.0), (-12685, 1.0), (34707, 1.0)], (out["fields"], out["warnings"])
    assert sum("segment" in w for w in out["warnings"]) == 1, out["warnings"]
    vo_fields = x.call_llm()["fields"]  # second run: profit before tax answered as the net income row with a quote the page does not print
    x.call_llm = lambda *a, **k: {"fields": [dict(f, value=34707, raw_label="Income for the period *", source={"page": 1, "quote": "Income for the period * 34,707 50,576"}) if f["key"] == "profit_before_tax" else f for f in vo_fields]}
    out = x.extract([vo], [1], {**sch, "fields": [real[k] for k in ("revenue", "profit_before_tax", "income_tax", "net_profit")]}, {"fiscal_year": 2025})
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(479183, 1.0), (47391, 1.0), (-12685, 1.0), (34707, 1.0)], (out["fields"], out["warnings"])
    assert any("not printed on the statement" in w for w in out["warnings"]) and out["fields"][1]["raw_label"] == "Income after financial items", out["warnings"]
    assert x._row_amounts("Cost of sales 3 –297,0421) –320,821", 2) == [-297042, -320821] and x._value_in_quote(-297042, "Cost of sales 3 –297,0421) –320,821")  # Volvo Cars footnote marker
    # Volvo Cars: "Net income" is a prefix of "net income from discontinued operations", not a discontinued-operations row (the null fill took it, then "repaired" net profit)
    assert not x._label_known("Net income", real["profit_discontinued"]) and x._label_known("Income before tax", real["profit_before_tax"]) and x._label_known("Net income", real["net_profit"])
    # Addnode after two LLM timeouts: nothing answered; the statement rows fill the fields, tax = current + deferred between profit after financial items and profit for the year
    an2 = an + "Operating profit 2, 7 607 598\nProfit after financial items 514 536\nCurrent tax 11, 12 -157 -154\nDeferred tax 11, 12 27 20\nProfit for the year 384 402\nTax attributable to items that may be reclassified -11 14\n"
    x.call_llm = lambda *a, **k: {"fields": []}
    npa = {"name": "net_profit_arith", "expr": "abs((profit_before_tax + income_tax + profit_discontinued) - net_profit) <= 2", "identity": True}
    out = x.extract([an2], [1], {"name": "is", "keywords": [], "checks": [gp, npa], "fields": [real[k] for k in ("revenue", "cost_of_sales", "gross_profit", "profit_before_tax", "income_tax", "profit_discontinued", "net_profit")]}, {"fiscal_year": 2025})
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(5793, 1.0), (-1350, 1.0), (4443, 1.0), (514, 1.0), (-130, 1.0), (None, 0.0), (384, 1.0)], (out["fields"], out["warnings"])
    assert out["fields"][4]["raw_label"] == "Current tax + Deferred tax" and "value_derived" in out["fields"][4]["evidence"] and "identity_all_columns" in out["fields"][1]["evidence"], out["fields"]
    assert not x._label_known("Tax attributable to items that may be reclassified", real["income_tax"])
    # Arion Bank: a column-major text layer (every figure, then every label); lines rebuilt from word coordinates
    import pymupdf
    from . import parse
    pg = pymupdf.open().new_page()
    for y, (lab, a, b) in enumerate([("Interest income", "129,777", "132,259"), ("Net earnings", "32,507", "26,112")]):
        pg.insert_text((40, 100 + 14 * y), lab + " " + "." * 40), pg.insert_text((400, 100 + 14 * y), a), pg.insert_text((470, 100 + 14 * y), b)
    assert parse._lines_from_words(pg).splitlines() == ["Interest income 129,777 132,259", "Net earnings 32,507 26,112"], parse._lines_from_words(pg)
    assert parse._numeric_run("Notes" + "".join(f"{chr(10)}{i}" for i in range(12)) + f"{chr(10)}Label") == 12 and parse._numeric_run(f"Gross income{chr(10)}14,753{chr(10)}14,480") == 2
    from . import locate
    assert locate.strip_boilerplate(["Financial statements Group and Parent company_ _____124\nNotes ......... 136\nConsolidated income statement\nNet sales 26 46,021 45,052"])[0] == "Consolidated income statement\nNet sales 26 46,021 45,052"  # AAK nav bar
    # NCC: "Result from sales of Group companies 20" offered as discontinued operations; the identity holds without it
    ncc2 = ("Consolidated income statement\nSEK M\nNote\n2025\n2024\nResult from sales of Group companies\n8\n20\n3\n"
            "Profit after financial items\n630\n1,863\nTax on profit for the year\n23, 39\n–489\n–292\nNet profit for the year\n142\n1,571\n")
    sch = {"name": "is", "keywords": [], "fields": [real[k] for k in ("profit_before_tax", "income_tax", "profit_discontinued", "net_profit")],
           "checks": [{"name": "net_profit_arith", "expr": "abs((profit_before_tax + income_tax + profit_discontinued) - net_profit) <= 2", "identity": True}]}
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "profit_before_tax", "value": 630, "unit": "SEK M", "period": "2025", "raw_label": "Profit after financial items", "source": {"page": 1, "quote": "Profit after financial items 630 1,863"}},
        {"key": "income_tax", "value": -489, "unit": "SEK M", "period": "2025", "raw_label": "Tax on profit for the year", "source": {"page": 1, "quote": "Tax on profit for the year 23, 39 –489 –292"}},
        {"key": "profit_discontinued", "value": 20, "unit": "SEK M", "period": "2025", "raw_label": "Result from sales of Group companies", "source": {"page": 1, "quote": "Result from sales of Group companies 8 20 3"}},
        {"key": "net_profit", "value": 142, "unit": "SEK M", "period": "2025", "raw_label": "Net profit for the year", "source": {"page": 1, "quote": "Net profit for the year 142 1,571"}}]}
    out = x.extract([ncc2], [1], sch, {"fiscal_year": 2025})
    assert out["fields"][2]["value"] is None and out["checks"][0]["passed"] and all(f["confidence"] == 1.0 for f in out["fields"] if f["value"] is not None), (out["fields"], out["warnings"])
    # Ericsson (debt maturity): the note has no >5y row, so due_after_5_years is null — a correct extraction, not a failure.
    # A check's null_as_zero lists the operands that count as 0 while they are null, as long as at least one of them is real;
    # when every listed operand is null the sum proves nothing and the check stays missing (never 0 == total).
    dmc = {"name": "maturity_sums_to_total", "expr": "abs((due_within_1_year + due_1_to_5_years + due_after_5_years) - total_debt) <= 2",
           "detail": "due_within_1_year + due_1_to_5_years + due_after_5_years == total_debt (±2 rounding)", "identity": True,
           "null_as_zero": ["due_within_1_year", "due_1_to_5_years", "due_after_5_years"]}
    c = x._check(dmc, {"due_within_1_year": 3538, "due_1_to_5_years": 29165, "total_debt": 32703})
    assert c["passed"] and "due_after_5_years null" in c["detail"], c  # the detail names the bucket counted as 0
    c = x._check(dmc, {"total_debt": 32703})  # no bucket printed at all
    assert not c["passed"] and c["detail"].startswith("missing:"), c
    c = x._check({k: v for k, v in dmc.items() if k != "null_as_zero"}, {"due_within_1_year": 3538, "due_1_to_5_years": 29165, "total_debt": 32703})
    assert not c["passed"] and c["detail"] == "missing: due_after_5_years", c  # without the flag: the old behaviour
    # ... end to end: the identity passes with the null bucket as 0, and total_debt keeps arith_ok at full confidence
    dm = json.loads((pathlib.Path(__file__).parents[1] / "schemas" / "debt_maturity.json").read_text("utf-8"))
    ericsson = "Note 20 Borrowings\nMSEK\n2025\nTotal borrowings 32,703\nWithin 1 year 3,538\n1-5 years 29,165\n"
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 32703, "unit": "MSEK", "period": "2025", "raw_label": "Total borrowings", "source": {"page": 1, "quote": "Total borrowings 32,703"}},
        {"key": "due_within_1_year", "value": 3538, "unit": "MSEK", "period": "2025", "raw_label": "Within 1 year", "source": {"page": 1, "quote": "Within 1 year 3,538"}},
        {"key": "due_1_to_5_years", "value": 29165, "unit": "MSEK", "period": "2025", "raw_label": "1-5 years", "source": {"page": 1, "quote": "1-5 years 29,165"}},
        {"key": "due_after_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None}]}
    out = x.extract([ericsson], [1], dm, {"fiscal_year": 2025})
    c = out["checks"][0]
    assert c["passed"] and "due_after_5_years null" in c["detail"], (c, out["warnings"])
    total = next(f for f in out["fields"] if f["key"] == "total_debt")
    assert total["confidence"] == 1.0 and "arith_ok" in total["evidence"], total
    # v011b: a printed bucket label is a known synonym — _clean_label glues digits ("Within 1 year" -> within1year), so
    # _label_known must run the synonym through the same cleaning before the prefix match (en dash, ">", space variants).
    dmf = {f["key"]: f for f in dm["fields"]}
    assert x._label_known("Within 1 year", dmf["due_within_1_year"]) and x._label_known("Inom 1 år", dmf["due_within_1_year"]) and x._label_known("< 1 år", dmf["due_within_1_year"])
    assert x._label_known("1-5 years", dmf["due_1_to_5_years"]) and x._label_known("1–5 years", dmf["due_1_to_5_years"]) and x._label_known("1–5 år", dmf["due_1_to_5_years"])
    assert x._label_known("After 5 years", dmf["due_after_5_years"]) and x._label_known("> 5 år", dmf["due_after_5_years"]) and x._label_known("Later than 5 years", dmf["due_after_5_years"])
    assert not x._label_known("1-5 years", dmf["due_after_5_years"]) and not x._label_known("Total borrowings", dmf["due_1_to_5_years"])  # prefix match, not substring
    # ... so the Ericsson fixture's buckets read perfectly at full confidence too
    out = x.extract([ericsson], [1], dm, {"fiscal_year": 2025})
    assert [(f["value"], f["confidence"]) for f in out["fields"]] == [(32703, 1.0), (3538, 1.0), (29165, 1.0), (None, 0.0)], (out["fields"], out["warnings"])
    # v012: _statement_row finds the printed bucket rows. Two defects, both in its direct helpers: the exact-match set
    # held the synonyms verbatim (v011b fixed the prefix match only), and _row_label cut the label at the first
    # space-digit, so "Within 1 year 3 538 4 100" matched as "Within" and "Inom 1 år …" as "Inom".
    assert x._row_label("Within 1 year 3 538 4 100") == "Within 1 year" and x._row_label("Inom 1 år 3 538 4 100") == "Inom 1 år" \
        and x._row_label("< 1 år 3 538 4 100") == "< 1 år"  # a number with label words after it is part of the label
    assert x._row_label("1–5 years 29 165 30 000") == "1–5 years" and x._row_label("Total sales 6, 10 155 113 161 921") == "Total sales"  # amounts still start where the label ends
    amb = ["Total borrowings 32 703 34 500", "Within 1 year 3 538 4 100", "1-5 years 29 165 30 000", "1-5 years, of which fixed rate 10 000 9 000"]
    assert x._statement_row(amb, dmf["due_1_to_5_years"], 2) == "1-5 years 29 165 30 000", amb  # the exact row, not the sub-row under it
    assert x._statement_row(amb, dmf["due_within_1_year"], 2) == "Within 1 year 3 538 4 100"
    assert x._statement_row(["Summa räntebärande skulder 32 703 34 500", "Inom 1 år 3 538 4 100", "Inom 1 år, varav konvertibler 500 400"],
                            dmf["due_within_1_year"], 2) == "Inom 1 år 3 538 4 100"
    row = x._statement_row(["Total borrowings 32 703 34 500", "1–5 years 29 165 30 000"], dmf["due_1_to_5_years"], 2)  # en dash
    assert x._row_amounts(row, 2) == [29165, 30000], row  # the "1" and "5" are the label's, not amounts
    # ... end to end: the model answers nothing, the note's own printed rows fill every bucket it prints, and the identity closes
    x.call_llm = lambda *a, **k: {"fields": []}
    out = x.extract(["Note 20 Borrowings\nMSEK\n2025 2024\nTotal borrowings 32 703 34 500\nWithin 1 year 3 538 4 100\n"
                     "1-5 years 29 165 30 000\n1-5 years, of which fixed rate 10 000 9 000\n"], [1], dm, {"fiscal_year": 2025})
    assert [(f["key"], f["value"], f["confidence"]) for f in out["fields"]] == [
        ("total_debt", 32703, 1.0), ("due_within_1_year", 3538, 1.0), ("due_1_to_5_years", 29165, 1.0),
        ("due_after_5_years", None, 0.0)], (out["fields"], out["warnings"])
    assert out["checks"][0]["passed"] and "due_after_5_years null" in out["checks"][0]["detail"], out["checks"]
    # v014: the sum-repair's own_syns (extract(), the _derived_value call) held the synonyms verbatim while the
    # rows' labels go through _clean_label -- a part row named by a digit-bearing synonym ("Within 1 year" is
    # within1year) could never join the field's own row, so the Essity-style join silently died for digit labels.
    # "cost total" (digit-free) names the quote's own row, so own_row itself is true on both sides of the change;
    # the digit synonym names the part row that must be allowed to join.
    gp14 = {"name": "gp14", "expr": "abs((revenue + special_cost) - gross_profit) <= 2", "identity": True}
    syn14 = {"name": "is", "keywords": [], "fields": [
        {"key": "revenue", "label": "Revenue", "synonyms": ["revenue"], "unit_hint": "currency_millions"},
        {"key": "special_cost", "label": "Special cost", "synonyms": ["cost total", "within 1 year"], "unit_hint": "currency_millions"},
        {"key": "gross_profit", "label": "Gross profit", "synonyms": ["gross profit"], "unit_hint": "currency_millions"}],
        "checks": [gp14]}
    p14 = ("Consolidated income statement\nSEKm\nNote\n2025\n2024\nCost of sales\nWithin 1 year items -20 -15\n"
           "Cost total -100 -90\nRevenue 500 450\nGross profit 380 345\n")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "revenue", "value": 500, "unit": "SEKm", "period": "2025", "raw_label": "Revenue", "source": {"page": 1, "quote": "Revenue 500 450"}},
        {"key": "special_cost", "value": -100, "unit": "SEKm", "period": "2025", "raw_label": "Cost total", "source": {"page": 1, "quote": "Cost total -100 -90"}},
        {"key": "gross_profit", "value": 380, "unit": "SEKm", "period": "2025", "raw_label": "Gross profit", "source": {"page": 1, "quote": "Gross profit 380 345"}}]}
    out = x.extract([p14], [1], syn14, {"fiscal_year": 2025})
    cost = out["fields"][1]
    assert (cost["value"], cost["confidence"]) == (-120, 1.0) and "value_derived" in cost["evidence"] \
        and cost["raw_label"] == "Cost of sales" \
        and cost["source"]["quote"] == "Within 1 year items -20 -15 Cost total -100 -90", (cost, out["warnings"])
    assert out["checks"][0]["passed"], out["checks"]
    # v018: a currency/unit token glued to a footnote marker ("SEK1)") defeated both the currency-strip regex (no
    # word boundary between the letter and the digit) and the trailing note-ref regex (the closing ")" sits past
    # the digit, short of the end-of-string anchor) -- so the token survived there while the same currency word
    # without a footnote was fully stripped. Superscript digits ("SEK¹") hit the same gap once NFKC turns them
    # into a plain digit; stripped pre-NFKC so a lowercase unit ("kr") is covered too, not only the uppercase
    # 3-letter codes the note-ref regex happens to rescue by accident.
    assert x._clean_label("EPS, SEK1)") == x._clean_label("EPS, SEK") == "eps"
    assert x._clean_label("Resultat per aktie, kr¹") == x._clean_label("Resultat per aktie, kr") == "resultat per aktie"
    assert x._clean_label("Earnings per share, MSEK2)") == x._clean_label("Earnings per share, MSEK")  # symmetric before v023 too (both kept ", msek"); after v023 both fully strip it instead, see below
    # not a footnote: digits that are part of the label's own meaning are untouched, exactly as before
    assert x._clean_label("1-5 years") == x._clean_label("1–5 years") == "1-5years" and x._clean_label("Within 1 year") == "within1year"
    # v023: a magnitude prefix (k/K/m/M/b/B/t/T -- thousand/million/billion, "t/T" also covering the Swedish
    # "tusen" convention) glued directly ahead of a currency code was never stripped: \bSEK\b has no word boundary
    # between "M" and "S" in "MSEK", so "Revenue, MSEK" kept ", msek" while plain "Revenue" had nothing to strip
    # (the gap v018's Findings flagged and left open). The bare-code strip ("EPS, SEK" -> "eps") and the
    # digit-preserving cases above are unaffected -- this only extends the same currency alternation, still
    # anchored on both sides by \b, to allow one optional magnitude letter immediately before the code.
    assert x._clean_label("Revenue, MSEK") == x._clean_label("Revenue") == "revenue"
    assert x._clean_label("Revenue, TSEK") == x._clean_label("Revenue, KSEK") == x._clean_label("Revenue, kSEK") == "revenue"
    assert x._clean_label("Net sales, MEUR") == x._clean_label("Net sales") == "net sales"
    assert x._clean_label("Net sales (MSEK)") == x._clean_label("Net sales")
    # v036: the dominant failure mode v035 found across a seed of 10 -- a maturity note that prints one row
    # (often "Total") with the buckets as *columns* instead of one row per bucket. _year_column finds no year in
    # a bucket header, so it and everything built on it (_column_values, _derived_value, _between_rows) bail
    # before trying. Cloetta's own Note 21 (real text, trimmed to the header + the one row that matters):
    cloetta = ("Note 21 Borrowings\n31 Dec 2025\nSEKm\nRemaining term\n< 1 year\nRemaining term\nRemaining term\n"
               "1–2 years\nRemaining term\n2–5 years\n> 5 years Total\nLoans from credit institutions - - 1,353 - 1,353\n"
               "Capitalised transaction costs -3 -5 -4 - -12\nCommercial papers 149 - - - 149\nAccrued interest 0 - - - 0\n"
               "Lease liabilities 51 27 28 9 115\nTotal 197 22 1,377 9 1,605\n")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 1605, "unit": "SEKm", "period": "2025", "raw_label": "Total", "source": {"page": 1, "quote": "Total 197 22 1,377 9 1,605"}},
        {"key": "due_within_1_year", "value": 197, "unit": "SEKm", "period": "2025", "raw_label": "Total", "source": {"page": 1, "quote": "Total 197 22 1,377 9 1,605"}},
        {"key": "due_1_to_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},  # the model tried 22+1,377=1,399, correctly dropped: no literal quote for a computed sum
        {"key": "due_after_5_years", "value": 9, "unit": "SEKm", "period": "2025", "raw_label": "Total", "source": {"page": 1, "quote": "Total 197 22 1,377 9 1,605"}}]}
    out = x.extract([cloetta], [1], dm, {"fiscal_year": 2025})
    got = {f["key"]: (f["value"], f["confidence"]) for f in out["fields"]}
    assert got == {"total_debt": (1605, 0.9), "due_within_1_year": (197, 0.9), "due_1_to_5_years": (1399, 1.0), "due_after_5_years": (9, 0.9)}, (got, out["warnings"])
    assert out["checks"][0]["passed"], out["checks"]  # null-filling the one bucket the model couldn't quote closes the identity, lifting the other three off their failed-check 0.5 cap too
    d15 = next(f for f in out["fields"] if f["key"] == "due_1_to_5_years")
    assert d15["source"]["quote"] == "Total 197 22 1,377 9 1,605" and "value_derived" in d15["evidence"] and "value_in_quote" not in d15["evidence"]  # a sum of two columns has no literal quote of its own
    # disagree: the model attributes the "1-2 years" column (22) to due_within_1_year instead of its own "< 1 year" column -- the page's column order wins, same as every other repair in this file
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 1605, "unit": "SEKm", "period": "2025", "raw_label": "Total", "source": {"page": 1, "quote": "Total 197 22 1,377 9 1,605"}},
        {"key": "due_within_1_year", "value": 22, "unit": "SEKm", "period": "2025", "raw_label": "Total", "source": {"page": 1, "quote": "Total 197 22 1,377 9 1,605"}},
        {"key": "due_1_to_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "due_after_5_years", "value": 9, "unit": "SEKm", "period": "2025", "raw_label": "Total", "source": {"page": 1, "quote": "Total 197 22 1,377 9 1,605"}}]}
    out = x.extract([cloetta], [1], dm, {"fiscal_year": 2025})
    within = next(f for f in out["fields"] if f["key"] == "due_within_1_year")
    assert within["value"] == 197 and any("22 disagrees with the maturity table" in w for w in out["warnings"]), (within, out["warnings"])
    # a maturity table whose columns are calendar years rather than named buckets ("2026 2027 2028 Later"), per HANDOFF's "expect these": folded to <1y / 1-5y / >5y off the report's own fiscal year, not the model's
    yr = "Note 20 Borrowings\nMSEK\n2026 2027 2028 Later Total\nTotal borrowings 412 1,286 933 47 2,678\n"
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 2678, "unit": "MSEK", "period": "2025", "raw_label": "Total borrowings", "source": {"page": 1, "quote": "Total borrowings 412 1,286 933 47 2,678"}},
        {"key": "due_within_1_year", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "due_1_to_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "due_after_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None}]}
    out = x.extract([yr], [1], dm, {"fiscal_year": 2025})
    got = {f["key"]: f["value"] for f in out["fields"]}
    assert got == {"total_debt": 2678, "due_within_1_year": 412, "due_1_to_5_years": 2219, "due_after_5_years": 47} and out["checks"][0]["passed"], (got, out["warnings"])  # 2027 + 2028 = 1,286 + 933
    # not every bucket-as-columns table is readable this way, and guessing wrong is worse than not fixing it -- three
    # real shapes from the same seed that stay exactly as they were (v035's own "not fixed" verdicts, unchanged):
    # XANO: the header wraps across two of _page_rows' lines ("Summa" / "inom 1 år"), scrambling column order out of
    # print order; the safety valve is the row's own column count (8) never matching however many bucket keys are found
    xano = ("FINANSIELLA SKULDER Förfallotid\nPER 2025-12-31 –30 dgr 31–90 dgr 91–360 dgr Summa Mellan 1 Mellan 3 Efter 5 år Totalt\n"
            "inom 1 år och 3 år och 5 år\nSumma räntebärande skulder 4 090 8 680 38 305 51 075 768 885 33 784 50 778 904 522\n")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 904522, "unit": "TSEK", "period": "2025", "raw_label": "Summa räntebärande skulder", "source": {"page": 1, "quote": "Summa räntebärande skulder 4 090 8 680 38 305 51 075 768 885 33 784 50 778 904 522"}},
        {"key": "due_within_1_year", "value": 51075, "unit": "TSEK", "period": "2025", "raw_label": "inom 1 år och 3 år och 5 år: Summa räntebärande skulder", "source": {"page": 1, "quote": "Summa räntebärande skulder 4 090 8 680 38 305 51 075 768 885 33 784 50 778 904 522"}},
        {"key": "due_1_to_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "due_after_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None}]}
    out = x.extract([xano], [1], dm, {"fiscal_year": 2025})
    got = {f["key"]: (f["value"], f["confidence"]) for f in out["fields"]}
    # v044: "Efter 5 år" is printed whole on the header line (only "Summa"/"Mellan 1"/"Mellan 3" wrap away), so
    # due_after_5_years is a bucket the table demonstrably has, just one the safety valve correctly declined to
    # read a number for -- the check reads missing: due_after_5_years, not a false failure against a fabricated
    # due_after_5_years=0, and total_debt/due_within_1_year (independently quote- and label-verified) are no
    # longer capped for a sibling bucket's gap. due_1_to_5_years has no matching synonym anywhere on the page
    # (its own header words wrapped into "inom 1 år och 3 år och 5 år", which reads as digit-glued "1"/"3"/"5"
    # tokens, none of which forms "mellan...och..." or a "1-5"/"1-2"/"2-5" run) and stays a confirmed 0.
    assert got == {"total_debt": (904522, 1.0), "due_within_1_year": (51075, 1.0), "due_1_to_5_years": (None, 0.0), "due_after_5_years": (None, 0.0)} \
        and out["checks"][0]["detail"] == "missing: due_after_5_years" and not out["warnings"], (got, out["checks"], out["warnings"])
    # Ework: the table's own finer split (<1 month / 1-3 / 3-12 months) never says "year", and an unexplained
    # 6th numeric column means the header's bucket-key hits never reach the row's own column count (8) either
    ework = ("kSEK Due < 1 month 1-3 months 3-12 months 1-5 years > 5 years Total undis- Carrying\ncounted value amount\n2025\n"
             "Short-term interest-bearing\nliabilities* – 153,761 971 1,677 – – 156,410 156,410\n")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 156410, "unit": "kSEK", "period": "2025", "raw_label": "Interest-bearing liabilities", "source": {"page": 1, "quote": "Short-term interest-bearing liabilities* – 153,761 971 1,677 – – 156,410 156,410"}},
        {"key": "due_within_1_year", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "due_1_to_5_years", "value": 1677, "unit": "kSEK", "period": "2025", "raw_label": "Short-term interest-bearing liabilities*", "source": {"page": 1, "quote": "Short-term interest-bearing liabilities* – 153,761 971 1,677 – – 156,410 156,410"}},
        {"key": "due_after_5_years", "value": 0, "unit": "kSEK", "period": "2025", "raw_label": "Short-term interest-bearing liabilities*", "source": {"page": 1, "quote": "Short-term interest-bearing liabilities* – 153,761 971 1,677 – – 156,410 156,410"}}]}
    out = x.extract([ework], [1], dm, {"fiscal_year": 2025})
    got = {f["key"]: f["value"] for f in out["fields"]}
    assert got == {"total_debt": 156410, "due_within_1_year": None, "due_1_to_5_years": 1677, "due_after_5_years": None}, (got, out["warnings"])  # unchanged from the model's own (repair-dropped) answer
    # Bergman & Beving: the only row that could be "the total" is "Total financial liabilities", which is not a
    # total_debt synonym (no "interest-bearing"/"borrowings") and not bare Total/Summa/Totalt either -- it also
    # includes non-interest-bearing accounts payable, so treating it as one would have been wrong, not just unproven
    assert x._bucket_total_row(x._page_rows("Total financial liabilities 3,111 3,380 778 454 2,116 32\n"), dmf["total_debt"]) == []
    # v040: Acast (seed 2, real Note text) -- two stacked calendar-year maturity tables (this year, then a
    # prior-year comparative), each ending in a bare "Total" row. The current year's own Total row is glued to
    # trailing sidebar prose by the PDF's column layout ("...19,250 approximation of fair value." then "2024"
    # on its own line merges onto the same row), so it never reads as >=2 amounts and drops out as a candidate;
    # only the prior year's row is left. Its own column count (6) still happens to match the *current* year's
    # own header (found first, scanning top-down over the whole page) closely enough to pass the safety valve,
    # producing a due_within_1_year bigger than its own total_debt. A bucket can never exceed the total it is
    # part of, in any report: reject the whole row's column reading when one does, rather than "fix" one field
    # out of a header that was never really aligned to that row to begin with.
    acast = ("SEK thousand Carrying amount 2026 2027 2028 2029 After 2029 The carrying amounts of the Group's finance lease\n"
             "Total 690,785 592,113 34,980 33,467 21,826 19,250 approximation of fair value.\n2024\n"
             "SEK thousand Carrying amount 2025 2026 2027 2028 After 2028\n"
             "Total 555,370 446,990 32,692 32,404 32,404 45,414\n")
    leases = "SEK thousand 31.12.2025 31.12.2024\nLease liabilities\nCurrent 32,052 23,443\nNon-current 103,330 117,709\nTotal lease Liability 135,382 141,152\n"
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 135382, "unit": "SEK thousand", "period": "2025", "raw_label": "Total lease Liability",
         "source": {"page": 1, "quote": "Total lease Liability 135,382 141,152"}},
        {"key": "due_within_1_year", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "due_1_to_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "due_after_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None}]}
    out = x.extract([leases, acast], [1, 2], dm, {"fiscal_year": 2025})
    got = {f["key"]: (f["value"], f["confidence"]) for f in out["fields"]}
    assert got == {"total_debt": (135382, 0.9), "due_within_1_year": (None, 0.0), "due_1_to_5_years": (None, 0.0), "due_after_5_years": (None, 0.0)}, (got, out["warnings"])
    assert any("exceed its own total 45414" in w for w in out["warnings"]), out["warnings"]  # the column reading is rejected outright, not one field silently "fixed"
    # v040: Nelly Group (seed 2, real Note text) -- the model correctly reads due_within_1_year from its own
    # "Kortfristiga" (current) row, but the schema has no bare "kortfristiga" synonym (only the compound
    # "kortfristiga räntebärande skulder"), so the row was never recognised as due_within_1_year's own -- and
    # the neighbour-sum repair, left unrestricted, folded in "Långfristiga" (non-current) too, turning a
    # correct current-portion read into the current+non-current total. A row the model already read and
    # labelled faithfully is its own row whether or not the schema happens to recognise that label as a
    # synonym *yet* -- see own_row in extract().
    nelly = ("Leasingskulder (Miljoner kronor) 2025 2024\nKortfristiga 36,2 35,7\nLångfristiga 250,9 251,5\n"
             "Leasingskulder som ingår i\n\xadrapporten över finansiell ställning 287,1 287,2\n")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 287.1, "unit": "Miljoner kronor", "period": "2025",
         "raw_label": "Leasingskulder som ingår i rapporten över finansiell ställning",
         "source": {"page": 1, "quote": "\xadrapporten över finansiell ställning 287,1 287,2"}},
        {"key": "due_within_1_year", "value": 36.2, "unit": "Miljoner kronor", "period": "2025", "raw_label": "Kortfristiga",
         "source": {"page": 1, "quote": "Kortfristiga 36,2 35,7"}},
        {"key": "due_1_to_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "due_after_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None}]}
    out = x.extract([nelly], [1], dm, {"fiscal_year": 2025})
    got = {f["key"]: (f["value"], f["confidence"]) for f in out["fields"]}
    assert got == {"total_debt": (287.1, 0.5), "due_within_1_year": (36.2, 0.5), "due_1_to_5_years": (None, 0.0), "due_after_5_years": (None, 0.0)}, (got, out["warnings"])
    assert not out["warnings"], out["warnings"]  # no repair fires at all: the model's own, correctly-labelled row stands unmolested
    # v040: a maturity table's own Total row is not immune to the report's usual "-" nil convention either --
    # a dash inside the bucket columns (not just in the instrument rows above the total, which Cloetta's own
    # test above already covers) must not desync col_keys from amounts, trailing or mid-row, and must read as
    # "no debt due in that window" (None), never a fabricated 0.
    header = "Note 21 Borrowings\n31 Dec 2025\nSEKm\nRemaining term\n< 1 year\nRemaining term\nRemaining term\n1–2 years\nRemaining term\n2–5 years\n> 5 years Total\n"
    x.call_llm = lambda *a, **k: {"fields": [{"key": k, "value": None, "unit": None, "period": None, "raw_label": None, "source": None} for k in dmf]}
    out = x.extract([header + "Total 197 22 1,377 - 1,596\n"], [1], dm, {"fiscal_year": 2025})  # trailing dash: no >5y bucket
    got = {f["key"]: (f["value"], f["confidence"]) for f in out["fields"]}
    assert got == {"total_debt": (1596, 0.9), "due_within_1_year": (197, 0.9), "due_1_to_5_years": (1399, 1.0), "due_after_5_years": (None, 0.0)}, (got, out["warnings"])
    assert out["checks"][0]["passed"], out["checks"]
    out = x.extract([header + "Total 197 - 1,377 9 1,583\n"], [1], dm, {"fiscal_year": 2025})  # mid-row dash: no 1-2y bucket, 2-5y and >5y still line up
    got = {f["key"]: (f["value"], f["confidence"]) for f in out["fields"]}
    assert got == {"total_debt": (1583, 0.9), "due_within_1_year": (197, 0.9), "due_1_to_5_years": (1377, 0.9), "due_after_5_years": (9, 0.9)}, (got, out["warnings"])
    assert out["checks"][0]["passed"], out["checks"]
    # v044: null_as_zero, refined -- v041 finding 3 (MedCap, Ependion, same seed): a bucket the model failed to
    # extract reads identically to a bucket the report never prints -- both are null -- but only the second one
    # is really a 0. Before defaulting a null bucket to 0, _check now looks for its own synonym label (the same
    # normalize_ws digit-gluing v012/v014 already use for row labels) on the pages the check's other, real
    # operands were sourced from, or the candidate pages; found -> leave it out of the substitution, so the check
    # reads "missing: <field>" instead of a false failure; not found -> 0, exactly as before. texts/pages/fields/
    # schema are new, optional _check args: every call above this one omits them, so the pre-v044 unconditional
    # zero-fill is unchanged for all of them (the full suite above this block is unmodified except the one XANO
    # case, which hits this exact mechanism too -- see its own updated comment).
    c = x._check(dmc, {"total_debt": 718.7, "due_1_to_5_years": 616.5}, texts=["Totalt 718,7\n1 – 5 år 616,5\n",
                 "MSEK <1 år 1 – 2 år 2 – 4 år 4 – 5 år >5år\n"], pages=[1, 2],
                 fields=[{"key": "total_debt", "source": {"page": 1}}, {"key": "due_1_to_5_years", "source": {"page": 1}}], schema=dm)
    assert not c["passed"] and c["detail"] == "missing: due_within_1_year", c  # "<1 år" sits on the candidate page: not a confirmed 0
    c = x._check(dmc, {"due_within_1_year": 3538, "due_1_to_5_years": 29165, "total_debt": 32703},
                 texts=["Total borrowings 32,703\nWithin 1 year 3,538\n1-5 years 29,165\n"], pages=[1],
                 fields=[{"key": "due_within_1_year", "source": {"page": 1}}, {"key": "due_1_to_5_years", "source": {"page": 1}}], schema=dm)
    assert c["passed"] and "due_after_5_years null" in c["detail"], c  # no "after 5 years"/"efter 5 år" anywhere: still a real 0
    # end to end, MedCap's own page text (seed3-kb, pp.101-102, relabelled 1-2 here): the model reads total_debt
    # and due_1_to_5_years verbatim off the carrying-amount table (p.101); due_within_1_year is null (its true
    # value is the unprinted sum 54.3+48.0=102.3, correctly dropped elsewhere as computed-not-quoted -- not this
    # lane's territory) and due_after_5_years is null too (this table really has no >5y row). Before this lane:
    # due_within_1_year zero-filled, 0+616.5 != 718.7, check FAILED, total_debt/due_1_to_5_years capped at 0.5
    # (docs/acrylic/evidence/v041.md's own recorded outcome for MedCap). due_within_1_year's own bucket boundary
    # ("<1 år") is not on the carrying table but is on the contractual table two pages later (still a candidate
    # page, p.102/page 2 here) -- present, so the check now reads missing, not failed, and the two verified
    # fields are no longer capped for a sibling bucket's gap. (v052 has since closed the gap itself: the same
    # derivation that fills the model's fabricated-quote answer below now also fills this null one -- due_within_1_year
    # comes back 102.3 and the check moves on to the one bucket the carrying table really does not print.)
    medcap101 = ("Förfallotidpunkt för upplåning Koncernen Moderbolaget\nMSEK 2025-12-31 2024-12-31 2025-12-31 2024-12-31\n"
                 "6 månader eller mindre 54,3 41,8 – –\n6 – 12 månader 48,0 19,0 – –\n1 – 5 år 616,5 316,7 – –\nTotalt 718,7 377,6 – –\n")
    medcap102 = ("Koncernen 2025-12-31\nMSEK <1 år 1 – 2 år 2 – 4 år 4 – 5 år >5år\nSkulder till kreditinstitut 59,3 97,5 59,1 – –\n"
                 "Leasingskulder 50,6 100,8 66,4 30,6 142,9\nÖvriga långfristiga skulder 80,9 187,1 – – –\n"
                 "Leverantörs- och övriga skulder 241,0 – – – –\nTotalt 431,8 385,4 125,5 30,6 142,9\n")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 718.7, "unit": "MSEK", "period": "2025", "raw_label": "Totalt", "source": {"page": 1, "quote": "Totalt 718,7 377,6 – –"}},
        {"key": "due_within_1_year", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "due_1_to_5_years", "value": 616.5, "unit": "MSEK", "period": "2025", "raw_label": "1 – 5 år", "source": {"page": 1, "quote": "1 – 5 år 616,5 316,7 – –"}},
        {"key": "due_after_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None}]}
    out = x.extract([medcap101, medcap102], [1, 2], dm, {"fiscal_year": 2025})
    assert not out["checks"][0]["passed"] and out["checks"][0]["detail"] == "missing: due_after_5_years", out["checks"]  # was failed pre-v044, "missing: due_within_1_year" before v052 closed it
    total = next(f for f in out["fields"] if f["key"] == "total_debt")
    bucket15 = next(f for f in out["fields"] if f["key"] == "due_1_to_5_years")
    assert total["confidence"] == 0.9 and "arith_ok" in total["evidence"], total  # was capped at 0.5
    assert bucket15["confidence"] == 1.0 and "arith_ok" in bucket15["evidence"], bucket15  # was capped at 0.5
    # Ependion (same seed, v041 finding 3's other example): stays failed, correctly -- its bucket table (p.155)
    # never prints a digit-form boundary at all ("Between 1 and 2 years" / "Between 2 and 3 years", spelled out,
    # scrambled by a sidebar TOC column glued onto the same lines by parse.py), and the schema has no spelled-out
    # synonym for either bucket (docs/acrylic/evidence/v041.md's own finding: "the spelled-out ... wording
    # doesn't exist in the schema at all yet regardless"). A schema-vocabulary gap, out of this lane's territory
    # (schema untouched) -- not the null-vs-missing conflation this lane fixes. Recorded so a future schema
    # change adding that wording is the one that should flip this case, not a regression in this mechanism.
    ependion155 = ("Contracted terms\nSEK 000 31 Dec. 2025 31 Dec. 2024\nBetween Between\nWithin 12 1 and 2 and\n"
                   "months 2 years 3 years Total\nBorrowing 167,546 35,636 380,348 583,531\n")
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 583531, "unit": "SEK 000", "period": "2025", "raw_label": "Borrowing", "source": {"page": 1, "quote": "Borrowing 167,546 35,636 380,348 583,531"}},
        {"key": "due_within_1_year", "value": 167546, "unit": "SEK 000", "period": "2025", "raw_label": "Borrowing", "source": {"page": 1, "quote": "Borrowing 167,546 35,636 380,348 583,531"}},
        {"key": "due_1_to_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None},
        {"key": "due_after_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None}]}
    out = x.extract([ependion155], [1], dm, {"fiscal_year": 2025})
    assert not out["checks"][0]["passed"] and not out["checks"][0]["detail"].startswith("missing:"), out["checks"]
    within = next(f for f in out["fields"] if f["key"] == "due_within_1_year")
    assert within["confidence"] == 0.5, within  # still capped: neither sibling bucket's label is anywhere on the page
    # v052: a note page can stack a second table above the one the field's row sits in (MedCap p.101: a
    # receivables-ageing table over the maturity table), and the maturity header itself repeats the year across
    # Koncernen | Moderbolaget pairs. Row derivations now anchor the year header to the quoted row -- the nearest
    # year run above it (_row_year_column) -- and, when the fiscal year appears twice in that run, take the Group
    # side when Group is named before Parent on the run's row or the one above it, the last pair when reversed.
    # The page-level _year_column default is untouched: still the page's first run, still None on repeats.
    assert x._year_column(medcap101, 2025) is None  # the page-level default still declines a repeated year, as before
    age101 = ("MSEK 2025-12-31 2024-12-31\nEj förfallet 241,6 180,5\nMindre än 3 månader 25,0 29,1\n"
              "Äldre än 3 månader 1,8 1,8\nAvsättningar -1,1 -0,8\nTotalt 267,3 210,6\n")  # the receivables-ageing table printed above the maturity one on the real p.101
    full101 = age101 + medcap101
    assert x._year_column(full101, 2025) == (0, 2)  # unchanged page-level default: the page's FIRST header, the ageing table's
    rows101 = x._page_rows(full101)
    assert x._row_year_column(rows101, rows101.index("Totalt 718,7 377,6 – –"), 2025) == (0, 4)  # the maturity table's own header, Group side first
    assert x._row_year_column(rows101, rows101.index("Totalt 267,3 210,6"), 2025) == (0, 2)  # the ageing row anchors to its own table
    norows101 = x._page_rows(full101.replace(" Koncernen Moderbolaget", ""))
    assert x._row_year_column(norows101, norows101.index("Totalt 718,7 377,6 – –"), 2025) is None  # repeated year, no Group/Parent words: unknowable, declines as before
    catrows = x._page_rows(cat)
    assert x._row_year_column(catrows, catrows.index("Profit before tax 2,067 1,344"), 2025) == (0, 2)  # single-table page: the anchored header is the page's
    # ... end to end: the model computes due_within_1_year = 54,3 + 48,0 = 102,3 correctly but fabricates its quote,
    # so the value is dropped as computed, not read -- yet both rows are printed, and with the maturity table's own
    # 4-column header the rows printed directly above the "1 – 5 år" operand row close the identity in every column
    # (102.3+616.5+0 vs 718.7, 60.8+316.7+0 vs 377.6, the Moderbolaget columns nil throughout)
    x.call_llm = lambda *a, **k: {"fields": [
        {"key": "total_debt", "value": 718.7, "unit": "MSEK", "period": "2025", "raw_label": "Totalt", "source": {"page": 1, "quote": "Totalt 718,7 377,6 – –"}},
        {"key": "due_1_to_5_years", "value": 616.5, "unit": "MSEK", "period": "2025", "raw_label": "1 – 5 år", "source": {"page": 1, "quote": "1 – 5 år 616,5 316,7 – –"}},
        {"key": "due_within_1_year", "value": 102.3, "unit": "MSEK", "period": "2025", "raw_label": "6 månader eller mindre", "source": {"page": 1, "quote": "6 månader eller mindre 54,3 + 6 – 12 månader 48,0 = 102,3"}},
        {"key": "due_after_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None}]}
    out = x.extract([full101, medcap102], [1, 2], dm, {"fiscal_year": 2025})
    within = next(f for f in out["fields"] if f["key"] == "due_within_1_year")
    assert within["value"] == 102.3 and "value_derived" in within["evidence"] and within["source"]["quote"] \
        == "6 månader eller mindre 54,3 41,8 – – 6 – 12 månader 48,0 19,0 – –", (within, out["warnings"])
    assert within["confidence"] == 1.0 and within["raw_label"] == "6 månader eller mindre + 6 – 12 månader", within
    # the identity itself closes in every column (54.3+48.0+616.5 = 718.8 vs 718.7, 41.8+19.0+316.7 = 377.5 vs 377.6,
    # the Moderbolaget columns nil throughout) -- what keeps the reported check open is due_after_5_years: its ">5år"
    # header sits on the contractual table one page over, so v044's present-label rule refuses the false 0, and the
    # carrying table genuinely prints no >5y row. Passing would mean relaxing that rule, not this lane's territory.
    assert not out["checks"][0]["passed"] and out["checks"][0]["detail"] == "missing: due_after_5_years", out["checks"]
    total = next(f for f in out["fields"] if f["key"] == "total_debt")
    bucket15 = next(f for f in out["fields"] if f["key"] == "due_1_to_5_years")
    assert (total["value"], total["confidence"]) == (718.7, 0.9) and (bucket15["value"], bucket15["confidence"]) == (616.5, 1.0), (total, bucket15)
    # ... and a repeated year with no Group/Parent named above the rows must not fire: Volvo-style segment
    # repetition stays unknowable, the field stays null exactly as before the anchoring existed
    out = x.extract([full101.replace(" Koncernen Moderbolaget", ""), medcap102], [1, 2], dm, {"fiscal_year": 2025})
    within = next(f for f in out["fields"] if f["key"] == "due_within_1_year")
    assert within["value"] is None and within["confidence"] == 0.0 and not within["evidence"], (within, out["warnings"])
    assert not out["checks"][0]["passed"], out["checks"]
    # v043: EXTRACT_TWO_PASS (default off) -- pass 1 is a small "which candidate page" question over a
    # head-of-page snippet of *every* candidate (not just the top-2 the single-pass window shows), pass 2
    # is the existing extraction prompt fed only the page(s) pass 1 picks. Candidate 3 (never reached by
    # the old pages[:2] window) is the real note; 1-2 are decoys.
    import os
    decoy1 = "Five-year summary\nMSEK\n2025 2024 2023 2022 2021\nNet sales 100 90 80 70 60\n"
    decoy2 = "Segment overview\nNothing about borrowings here.\n"
    real = ("Note 20 Borrowings\nMSEK\n2025 2024\nTotal borrowings 32 703 34 500\nWithin 1 year 3 538 4 100\n"
            "1-5 years 29 165 30 000\n1-5 years, of which fixed rate 10 000 9 000\n")
    decoy4 = "Appendix\nUnrelated content, never a pass-1 candidate.\n"  # page 4: not in `pages`, only reachable as page 3's default +1 companion
    full_answer = {"fields": [
        {"key": "total_debt", "value": 32703, "unit": "MSEK", "period": "2025", "raw_label": "Total borrowings", "source": {"page": 3, "quote": "Total borrowings 32,703"}},
        {"key": "due_within_1_year", "value": 3538, "unit": "MSEK", "period": "2025", "raw_label": "Within 1 year", "source": {"page": 3, "quote": "Within 1 year 3,538"}},
        {"key": "due_1_to_5_years", "value": 29165, "unit": "MSEK", "period": "2025", "raw_label": "1-5 years", "source": {"page": 3, "quote": "1-5 years 29,165"}},
        {"key": "due_after_5_years", "value": None, "unit": None, "period": None, "raw_label": None, "source": None}]}
    calls = []

    def fake_llm(system, user, schema=x.RESPONSE_SCHEMA, name="extraction"):
        calls.append((name, "=== PAGE 1 ===" in user, "=== PAGE 3 ===" in user))
        return {"pages": [3]} if name == "page_select" else full_answer
    x.call_llm = fake_llm

    calls.clear()
    out = x.extract([decoy1, decoy2, real, decoy4], [1, 2, 3], dm, {"fiscal_year": 2025})
    assert calls == [("extraction", True, False)], calls  # off: exactly the old single call, over pages[:2]; page 3 never shown
    assert not any(w.startswith("two_pass") for w in out["warnings"]), out["warnings"]

    os.environ["EXTRACT_TWO_PASS"] = "1"
    try:
        calls.clear()
        out = x.extract([decoy1, decoy2, real, decoy4], [1, 2, 3], dm, {"fiscal_year": 2025})
        assert calls == [("page_select", True, True), ("extraction", False, True)], calls  # pass 1 sees every candidate; pass 2 only the pages it picked
        # v045: a single-page reply ({"pages": [3]}) is no longer taken at face value -- it is repaired with
        # the default companion (3+1=4, page 4 was never itself a candidate), so the companion page single-pass
        # always got for free (locate.candidate_pages forces pages[0]+1 into position 2) is not lost here either.
        assert "two_pass: page [3, 4] selected from candidates [1, 2, 3]" in out["warnings"], out["warnings"]
        got = {f["key"]: (f["value"], f["confidence"]) for f in out["fields"]}
        assert got["total_debt"] == (32703, 1.0) and got["due_within_1_year"] == (3538, 1.0) and got["due_1_to_5_years"] == (29165, 1.0), (got, out["warnings"])

        def illegal_llm(system, user, schema=x.RESPONSE_SCHEMA, name="extraction"):
            calls.append((name, "=== PAGE 1 ===" in user, "=== PAGE 3 ===" in user))
            return {"pages": [99]} if name == "page_select" else full_answer  # 99 is not a candidate: illegal
        x.call_llm = illegal_llm
        calls.clear()
        out = x.extract([decoy1, decoy2, real, decoy4], [1, 2, 3], dm, {"fiscal_year": 2025})
        assert calls == [("page_select", True, True), ("extraction", True, False)], calls  # illegal pick falls back to pages[:2]
        assert any("page selection failed or illegal" in w for w in out["warnings"]), out["warnings"]
    finally:
        del os.environ["EXTRACT_TWO_PASS"]

    # v045: _select_pages itself -- the companion repair/validation rules, direct (no EXTRACT_TWO_PASS/extract()
    # wiring needed here, unlike the end-to-end checks above).
    four = ["p1 text", "p2 text", "p3 text", "p4 text"]
    x.call_llm = lambda *a, **k: {"pages": [2]}
    assert x._select_pages(dm, [1, 2, 3], four) == [2, 3]  # single-page reply repaired with the default +1
    x.call_llm = lambda *a, **k: {"pages": [4]}
    assert x._select_pages(dm, [1, 2, 4], four) == [3, 4]  # primary is the last page: +1 doesn't exist, falls back to -1
    x.call_llm = lambda *a, **k: {"pages": [2, 1]}
    assert x._select_pages(dm, [1, 2, 3], four) == [1, 2]  # the model's own -1 override, honoured as given
    x.call_llm = lambda *a, **k: {"pages": [2, 4]}
    assert x._select_pages(dm, [1, 2, 3, 4], four) is None  # companion not adjacent to the primary: illegal
    x.call_llm = lambda *a, **k: {"pages": [2, 3]}
    assert x._select_pages(dm, [1, 2], four) == [2, 3]  # companion (3) need not itself be a candidate -- only the primary must be
    x.call_llm = lambda *a, **k: {"pages": [99]}
    assert x._select_pages(dm, [1, 2, 3], four) is None  # primary outside the candidate list: illegal, same as v043
    x.call_llm = lambda *a, **k: {"pages": [2, 3, 4]}
    assert x._select_pages(dm, [1, 2, 3, 4], four) is None  # more than 2 pages: illegal, unchanged from v043

    # v045: pass-1's own snippet -- running headers (locate.strip_boilerplate) and bare page-number lines
    # dropped, ~1200-char head, plus (Apotea's own failure mode, docs/acrylic/evidence/v043.md) any schema
    # keyword line found beyond that head, numbered, so a heading pushed past the cutoff by filler still surfaces.
    captured = {}

    def capture_llm(system, user, schema=x.PAGE_SELECT_SCHEMA, name="page_select"):
        captured["user"] = user
        return {"pages": [1, 2]}
    x.call_llm = capture_llm
    running_header = "ACME GROUP ANNUAL REPORT 2025"
    filler = "\n".join(f"Filler line number {i} of running prose unrelated to the statement." for i in range(30))  # > PAGE_SELECT_SNIPPET chars
    p1 = f"{running_header}\n7\n{filler}\nNote 20 Borrowings\nTotal borrowings 32,703 34,500\n"
    p2 = f"{running_header}\n8\nSegment overview, nothing about borrowings here.\n"
    other_pages = [f"{running_header}\n{n}\nUnrelated page." for n in range(20, 29)]  # > 10% of the doc repeats running_header
    x._select_pages(dm, [1, 2], [p1, p2] + other_pages)
    user = captured["user"]
    assert running_header not in user, user  # running header stripped (locate.strip_boilerplate)
    assert "7" not in user.splitlines(), user  # bare page-number line stripped (not just "differs per page", see locate's own comment)
    assert "\n...\n" in user  # the head/keyword-hits separator only appears once something was found beyond the head
    assert any(l.endswith(": Note 20 Borrowings") for l in user.splitlines()), user  # the heading, past the head cutoff, surfaces numbered
    print("confidence self-check ok")


if __name__ == "__main__":
    demo()
