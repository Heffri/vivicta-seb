"""Regression checks from the Wallenberg report-download audit (no network/model)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from pipeline import fetch


def accounts(company="Example AB", year=2025, title="Annual report", balance=True):
    with pymupdf.open() as doc:
        for i in range(8):
            p = doc.new_page()
            p.insert_text((50, 50), f"{company}\n{title} {year}\nPage {i + 1}")
            p.insert_text((50, 130), "Income statement\nRevenue 1200\nExpenses (700)\nProfit 500")
            if balance:
                p.insert_text((50, 240), "Balance sheet\nAssets 2000\nEquity 1500\nDebt 500")
        return doc.tobytes()


class FetchCoverageTests(unittest.TestCase):
    def test_short_statutory_accounts_are_valid(self):
        doc, text = fetch._validate(accounts(), "Example AB", 2025)
        self.assertIsNotNone(doc, text)
        self.assertEqual(len(doc), 8)
        doc.close()

    def test_short_brochure_or_incomplete_statement_is_not_annual_accounts(self):
        for data in [accounts(title="Report card"), accounts(balance=False)]:
            doc, why = fetch._validate(data, "Example AB", 2025)
            self.assertIsNone(doc)
            self.assertIn("lacks annual accounts", why)

    def test_wrong_company_year_and_interim_remain_rejected(self):
        for data in [accounts(company="Other AB"), accounts(year=2024), accounts(title="Interim report")]:
            doc, _ = fetch._validate(data, "Example AB", 2025)
            self.assertIsNone(doc)

    def test_numeric_brand_does_not_accept_unrelated_company(self):
        doc, why = fetch._validate(accounts(company="Candles Scandinavia AB"), "3 Scandinavia", 2025)
        self.assertIsNone(doc)
        self.assertIn("issuer mismatch", why)

    def test_subsidiary_accounts_do_not_replace_group_accounts(self):
        doc, why = fetch._validate(accounts(company="Nefab Danmark A/S"), "Nefab", 2025)
        self.assertIsNone(doc)
        self.assertIn("issuer mismatch", why)

    def test_verified_brand_aliases_are_not_treated_as_other_issuers(self):
        for requested, printed in [("Vectura", "Vectura Fastigheter AB"), ("3 Scandinavia", "Hi3G Scandinavia AB"), ("Sobi", "Swedish Orphan Biovitrum AB")]:
            doc, why = fetch._validate(accounts(company=printed), requested, 2025)
            self.assertIsNotNone(doc, why)
            doc.close()

    def test_parent_report_mentioning_holding_in_body_is_rejected(self):
        with pymupdf.open(stream=accounts(company="Investor AB")) as doc:
            doc[4].insert_text((50, 360), "Sarnova is one of our holdings.")
            data = doc.tobytes()
        doc, why = fetch._validate(data, "Sarnova", 2025)
        self.assertIsNone(doc)
        self.assertIn("issuer mismatch", why)

    def test_unaccented_swedish_archive_links_are_found(self):
        url = "https://example.com/archive/"
        links = fetch._ir_links(url, '<a href="/KS_Arsredovisning_2025.pdf"><img src="cover.png"></a>', 2025)
        self.assertIn("https://example.com/KS_Arsredovisning_2025.pdf", links)

    def test_combined_report_filename_and_explicit_title_reach_content_validation(self):
        self.assertTrue(fetch._filename_clear("https://example.com/quarterly-results/Annual%20and%20Sustainability%20Report_2025.pdf", fetch.BAD_URL))
        self.assertTrue(fetch._candidate_clear("https://example.com/sustainability-report-2025.pdf", "Annual and Sustainability Report 2025"))
        self.assertFalse(fetch._candidate_clear("https://example.com/sustainability-report-2025.pdf", "Sustainability Report 2025"))
        self.assertFalse(fetch._candidate_clear("https://example.com/interim-q3.pdf", "Annual and Sustainability Report"))

    def test_raw_unicode_urls_are_encoded_without_changing_existing_signature(self):
        with patch.object(fetch.urllib.request, "urlopen") as request:
            fetch._get("https://example.com/Årsrapport 2025.pdf?signature=a%2Fb+c")
            self.assertEqual(request.call_args.args[0].full_url, "https://example.com/%C3%85rsrapport%202025.pdf?signature=a%2Fb+c")

    def test_curated_source_is_used_before_a_new_model_search(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory)
            url = "https://example.com/accounts.pdf"
            (dest / "index.json").write_text(json.dumps([{"file": "example_2025.pdf", "company": "Example AB", "fiscal_year": 2025, "source_url": url}]))
            with patch.object(fetch, "_get", return_value=accounts()) as get, patch.object(fetch, "_model_candidates") as model:
                entry = fetch.fetch_report("Example AB", 2025, dest)
            get.assert_called_once_with(url)
            model.assert_not_called()
            self.assertEqual(entry["source_url"], url)

    def test_unavailable_download_and_model_failure_have_distinct_statuses(self):
        attempts = fetch.FetchAttempts()
        attempts.append("https://example.com/owner.pdf")
        fetch._failure(attempts, attempts[0], "issuer mismatch")
        status, body = fetch.failure_response("Example", 2025, LookupError(attempts, None))
        self.assertEqual((status, body["code"]), (404, "report_unavailable"))
        fetch._failure(attempts, "https://example.com/report.pdf", "HTTP 403", "download")
        status, body = fetch.failure_response("Example", 2025, LookupError(attempts, None))
        self.assertEqual((status, body["code"]), (502, "download_failed"))
        self.assertEqual(len(body["attempts"]), 2)
        status, body = fetch.failure_response("Example", 2025, LookupError([], "provider unavailable"))
        self.assertEqual((status, body["code"]), (502, "search_unavailable"))

    def test_search_context_resolves_collection_identity_without_relabeling_owner_report(self):
        context = fetch._collection_context("IPCO")
        self.assertIn("FAM holdings", context)
        self.assertIn("own accounts", context)
        self.assertIn("Patricia Industries", fetch._collection_context("Atlas Antibodies AB"))
        self.assertEqual(fetch._collection_context("Unrelated Company"), "")


if __name__ == "__main__":
    unittest.main()
