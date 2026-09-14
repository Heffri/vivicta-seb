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
    # ... but not when the comparative column disagrees (a coincidence in the fiscal year is not a proof)
    out = x.extract([cat.replace("-53", "-99")], [1], sch, {"fiscal_year": 2025})
    assert out["fields"][1]["confidence"] == 0.5, out["fields"][1]
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
    print("confidence self-check ok")


if __name__ == "__main__":
    demo()
