"""Historical discovery/period regressions, with no network or model calls."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from pipeline import fetch, report_period


def pdf(texts):
    with pymupdf.open() as doc:
        for text in texts:
            page = doc.new_page()
            page.insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=10)
        return doc.tobytes()


def prospectus(company="Example Industries Inc.", year=2023):
    return [
        f"FORM S-1\n{company}\nPROSPECTUS\nFiled 2025\nOffering of ordinary shares.",
        f"Report of Independent Registered Public Accounting Firm\nWe have audited the accompanying consolidated balance sheets of {company} as of December 31, {year} and {year-1}, and the related consolidated statements of operations and cash flows for the years then ended. In our opinion these financial statements present fairly the financial position and results of operations.",
        f"{company}\nCONSOLIDATED BALANCE SHEETS\nDecember 31, {year} and {year-1}\nAssets 1000 900\nLiabilities 400 300\nEquity 600 600",
        f"{company}\nCONSOLIDATED STATEMENTS OF OPERATIONS\nYears ended December 31, {year} and {year-1}\nRevenue 100 90\nExpenses 40 30\nNet income 60 60",
        "Notes to consolidated financial statements\nDebt maturity\nTotal debt 400\nDue within one year 100",
        "Report of Independent Registered Public Accounting Firm\nWe have audited the accounts of Other Fund.",
        "Other Fund\nCONSOLIDATED BALANCE SHEETS\n2023\nAssets 99999",
    ]


class HistoricalReportsTests(unittest.TestCase):
    def test_requested_year_ranks_accessible_link_labels(self):
        html = '<a href="/opaque-24.pdf" aria-label="10-K FY 2023 PDF">PDF</a><a href="/opaque-25.pdf" title="10-K FY 2024 PDF">PDF</a><a href="/quarter.pdf" aria-label="10-Q FY 2023 PDF">PDF</a>'
        links = fetch._ir_links("https://issuer.example/results", html, 2023)
        self.assertEqual(max(links, key=links.get), "https://issuer.example/opaque-24.pdf")
        self.assertNotIn("https://issuer.example/quarter.pdf", links)

    def test_numeric_filing_url_can_recover_through_financial_archive(self):
        start = "https://issuer.example/broken.pdf"
        archive = "https://issuer.example/financial-results"
        with patch.object(fetch, "_get", side_effect=[b'<a href="/financial-results">Financial Results</a>', b'<a href="/2023.pdf" aria-label="10-K FY 2023 PDF">PDF</a>']):
            links, error = fetch._crawl_ir_page(start, 2023, float("inf"))
        self.assertIsNone(error)
        self.assertIn("https://issuer.example/2023.pdf", links)

    def test_archive_heading_and_filing_row_disambiguate_numeric_pdf_names(self):
        html = '<h2>2025</h2><div><a>10-K</a><a href="/one.pdf">PDF</a></div><h2>2018</h2><div><a>10-K</a><a href="/two.pdf">PDF</a></div>'
        links = fetch._ir_links('https://issuer.example/archive', html, 2018)
        self.assertEqual(max(links, key=links.get), 'https://issuer.example/two.pdf')

    def test_period_beats_publication_and_comparative_year(self):
        for head in ["FORM 10-K\nFor the fiscal year ended December 30, 2023\nPublished January 2024; comparisons 2022", "2023 Annual Report\n2024 shareholders meeting", "Annual Report 2023\n2024 outlook"]:
            with pymupdf.open(stream=pdf([head, "Income statement", "Balance sheet"])) as doc:
                self.assertTrue(fetch._year_ok(doc, 2023))
                self.assertFalse(fetch._year_ok(doc, 2024))
                self.assertFalse(fetch._year_ok(doc, 2022))

    def test_split_fiscal_year_remains_valid(self):
        for title in ("Annual Report 2023/24", "Annual report 2023/2024"):
            self.assertEqual(report_period.declared_year(title), 2024)

    def test_multiple_companies_historical_accounts_keep_original_pages(self):
        for company, year in [("Example Industries Inc.", 2023), ("Another Systems Ltd", 2021)]:
            texts = prospectus(company, year)
            doc, text = fetch._validate(pdf(texts), company, year)
            self.assertIsNotNone(doc, text)
            doc.close()
            entry = fetch._entry("test.pdf", company, year, "https://issuer.example/s1.pdf", text)
            self.assertEqual(entry["document_type"], "registration_statement")
            self.assertEqual(entry["statement_pages"], [2, 3, 4, 5])
            scoped = report_period.extraction_texts(texts, entry)
            self.assertEqual(len(scoped), len(texts))
            self.assertEqual(scoped[0], "")
            self.assertEqual(scoped[5:], ["", ""])
            self.assertIn("Revenue 100", scoped[3])

    def test_prospectus_is_not_accepted_on_year_or_issuer_mention_alone(self):
        for texts, year in [(prospectus(), 2025), (prospectus("Other Company Inc."), 2023), (prospectus()[:1] + ["2023 annual revenue 100"] * 4, 2023)]:
            doc, reason = fetch._validate(pdf(texts), "Example Industries Inc.", year)
            self.assertIsNone(doc, reason)

    def test_unaudited_or_incomplete_statements_cannot_pass(self):
        for replacement in ("Unaudited condensed consolidated statements of operations\n2023 Revenue 100", "No income statement provided"):
            texts = prospectus()
            texts[3] = replacement
            self.assertIsNone(report_period.historical_accounts(texts, "Example Industries Inc.", 2023))

    def test_annual_report_preferred_to_larger_registration_filing(self):
        annual = ("annual.pdf", b"", "Annual report", 120)
        registration = ("s1.pdf", b"", report_period.ValidatedText("S-1", document_type="registration_statement"), 600)
        self.assertEqual(fetch._best_model_candidate([registration, annual]), annual)

    def test_fetch_persists_historical_source_metadata(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(fetch, "_get", return_value=pdf(prospectus())):
            entry = fetch.fetch_report("Example Industries Inc.", 2023, Path(directory), url="https://issuer.example/s1.pdf")
            self.assertEqual(entry["statement_pages"], [2, 3, 4, 5])
            self.assertEqual(fetch._load_index(Path(directory))[0]["document_type"], "registration_statement")


if __name__ == "__main__":
    unittest.main()
