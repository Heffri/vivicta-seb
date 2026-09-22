"""Company-independent listing and download regression tests (no network/model)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import fetch, report_listing
from test_fetch_coverage import accounts


def listing(company="Example AB", year=2025, action='<button>Download report</button>'):
    return f'<title>{company} - Company information</title><h1>{company}</h1><div><span>Annual report {year}</span>{action}</div>'


class ReportListingTests(unittest.TestCase):
    def test_multiple_issuers_years_languages_and_aliases(self):
        for company, printed, year in [('The Grand Group AB', 'The Grand Group AB', 2025),
                                       ('Example Industries', 'Example Industries', 2023),
                                       ('Sobi', 'Swedish Orphan Biovitrum AB', 2024)]:
            html = listing(printed, year).replace('Annual report', 'Årsredovisning').replace('Download report', 'Ladda ner rapport')
            result = report_listing.inspect('https://registry.example/company/1', html, company, year)
            self.assertEqual(result['fiscal_year'], year)
            self.assertEqual(result['company'], company)
            self.assertEqual(result['access'], 'manual_download')

    def test_parent_subsidiary_and_body_mentions_do_not_verify_identity(self):
        for html in [listing('Parent AB') + '<p>Example AB is a holding</p>', listing('Example Denmark AB'),
                     '<h1>Other AB</h1><h2>Example AB</h2><div>Annual report 2025<button>Download</button></div>']:
            self.assertIsNone(report_listing.inspect('https://registry.example', html, 'Example AB', 2025))

    def test_old_year_numbers_and_non_report_actions_are_not_listings(self):
        for html in [listing(year=2024) + '<p>Revenue 2025</p>',
                     '<h1>Example AB</h1><p>Annual report 2025 will be published soon</p>',
                     listing(action='<button>Subscribe</button>'),
                     listing().replace('Annual report 2025', 'Interim annual report 2025'),
                     listing().replace('Annual report 2025', 'Annual report 2025 not yet available'),
                     listing().replace('<div>', '<div hidden>')]:
            self.assertIsNone(report_listing.inspect('https://registry.example', html, 'Example AB', 2025), html)

    def test_listing_links_are_http_only(self):
        self.assertIsNone(report_listing.inspect('javascript:alert(1)', listing(), 'Example AB', 2025))
        self.assertIsNone(report_listing.http_url('https://example.com', 'javascript:downloadReport()'))
        self.assertIsNone(report_listing.http_url('https://example.com', 'http://['))
        self.assertIsNone(report_listing.inspect('https://registry.example', listing(action='<a href>Subscribe</a>'), 'Example AB', 2025))

    def test_registry_listing_on_archive_hop_is_preserved(self):
        start, archive = 'https://registry.example/company/1', 'https://registry.example/accounts'
        tried = fetch.FetchAttempts()
        with patch.object(fetch, '_get', side_effect=lambda url, **kw: b"<a href='/accounts'>Annual reports</a>" if url == start else listing().encode()):
            self.assertIsNone(fetch._ir_page_report([start], 'Example AB', 2025, tried))
        self.assertEqual(tried.listings[0]['url'], archive)

    def test_same_source_listing_aliases_are_deduplicated(self):
        tried = fetch.FetchAttempts()
        for url in ['https://registry.example/company/1', 'https://registry.example/company/1#reports', 'https://registry.example/company/example-ab', 'https://other.example/accounts']:
            fetch._record_listing(url, listing(), 'Example AB', 2025, tried)
        self.assertEqual(len(tried.listings), 2)

    def test_fetch_api_keeps_listing_state_separate_from_download_disabled(self):
        import app
        from fastapi.testclient import TestClient
        tried = fetch.FetchAttempts()
        tried.listings.append(report_listing.inspect('https://registry.example/company/1', listing(), 'Example AB', 2025))
        with patch.object(app.kb, 'entries', return_value=[]), patch.object(app, 'library_index', return_value=[]), \
             patch.object(app.fetch, 'fetch_report', side_effect=LookupError(tried, None)):
            response = TestClient(app.app).post('/api/reports/fetch', json={'company': 'Example AB', 'year': 2025})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'report_listed')
        self.assertEqual(response.json()['listings'][0]['fiscal_year'], 2025)

    def test_download_endpoint_without_pdf_suffix_is_followed_and_validated(self):
        page = 'https://registry.example/company/1'
        pdf = 'https://registry.example/download?id=12&year=2025'
        html = listing(action="<a href='/download?id=12&amp;year=2025' type='application/pdf'>Annual report 2025</a>")
        def get(url, **kwargs):
            return accounts() if url == pdf else html.encode()
        with tempfile.TemporaryDirectory() as directory, patch.object(fetch, '_get', side_effect=get), \
             patch.object(fetch, 'websearch_provider', return_value=None), patch.object(fetch, '_candidates', return_value=[]):
            result = fetch.fetch_report('Example AB', 2025, directory, url=page)
            self.assertEqual(result['source_url'], pdf)
            self.assertTrue((Path(directory) / result['file']).is_file())
        # The same endpoint with the wrong issuer must not be cached as a successful report.
        with tempfile.TemporaryDirectory() as directory, patch.object(fetch, '_get', side_effect=lambda url, **kw: accounts(company='Other AB') if url == pdf else html.encode()), \
             patch.object(fetch, 'websearch_provider', return_value=None), patch.object(fetch, '_candidates', return_value=[]):
            with self.assertRaises(LookupError) as caught:
                fetch.fetch_report('Example AB', 2025, directory, url=page)
            self.assertEqual(fetch.failure_response('Example AB', 2025, caught.exception)[1]['code'], 'report_listed')
            self.assertFalse(list(Path(directory).glob('*.pdf')))

    def test_model_registry_page_becomes_listing_not_extraction_or_missing_report(self):
        page = 'https://registry.example/company/1'
        with tempfile.TemporaryDirectory() as directory, patch.object(fetch, '_get', return_value=listing().encode()), \
             patch.object(fetch, 'websearch_provider', return_value='codex'), patch.object(fetch, '_model_candidates', return_value=([], None)), \
             patch.object(fetch, '_ir_page_candidates', return_value=([page], None)), patch.object(fetch, '_candidates', return_value=[]):
            with self.assertRaises(LookupError) as caught:
                fetch.fetch_report('Example AB', 2025, directory)
            status, result = fetch.failure_response('Example AB', 2025, caught.exception)
            self.assertEqual((status, result['code']), (409, 'report_listed'))
            self.assertEqual(result['listings'][0]['url'], page)
            self.assertFalse(list(Path(directory).glob('*.pdf')))
            # A later search failure does not erase an independently verified listing.
            self.assertEqual(fetch.failure_response('Example AB', 2025, LookupError(caught.exception.args[0], 'search timed out'))[1]['code'], 'report_listed')

    def test_wrong_year_or_unfetched_model_claim_never_becomes_confirmed_listing(self):
        page = 'https://registry.example/company/1'
        with tempfile.TemporaryDirectory() as directory, patch.object(fetch, '_get', return_value=listing(year=2024).encode()), \
             patch.object(fetch, 'websearch_provider', return_value='codex'), patch.object(fetch, '_model_candidates', return_value=([page], None)), \
             patch.object(fetch, '_ir_page_candidates', return_value=([], None)), patch.object(fetch, '_candidates', return_value=[]):
            with self.assertRaises(LookupError) as caught:
                fetch.fetch_report('Example AB', 2025, directory)
            self.assertEqual(fetch.failure_response('Example AB', 2025, caught.exception)[1]['code'], 'report_unavailable')

    def test_traditional_search_keeps_registry_pages_without_company_in_hostname(self):
        page = 'https://registry.example/company/1'
        with patch.object(fetch, '_mfn_pages', return_value=[]), patch.object(fetch, '_harvest', return_value=[]), \
             patch.object(fetch, '_get', return_value=f'<a href="/?uddg={page}">Company</a>'.encode()):
            self.assertIn(page, fetch._crawl('Example AB', 2025))

    def test_verified_listing_does_not_prevent_alternative_pdf_search(self):
        page = 'https://registry.example/company/1'
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory)
            fetch._remember_listings(dest, 'Example AB', 2025, [report_listing.inspect(page, listing(), 'Example AB', 2025)])
            pdf = 'https://issuer.example/annual-report-2025.pdf'
            with patch.object(fetch, '_get', side_effect=lambda url, **kw: accounts() if url == pdf else listing().encode()), \
                 patch.object(fetch, 'websearch_provider', return_value='fixture'), \
                 patch.object(fetch, '_model_candidates', return_value=([pdf], None)) as model:
                result = fetch.fetch_report('Example', 2025, dest)
            model.assert_called_once()
            self.assertEqual(result['source_url'], pdf)

    def test_cached_listing_is_retained_when_other_sources_fail(self):
        page = 'https://registry.example/company/1'
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory)
            fetch._remember_listings(dest, 'Example AB', 2025, [report_listing.inspect(page, listing(), 'Example AB', 2025)])
            with patch.object(fetch, '_get', return_value=listing().encode()), \
                 patch.object(fetch, 'websearch_provider', return_value=None), patch.object(fetch, '_candidates', return_value=[]):
                with self.assertRaises(LookupError) as caught:
                    fetch.fetch_report('Example', 2025, dest)
            self.assertEqual(fetch.failure_response('Example', 2025, caught.exception)[1]['code'], 'report_listed')

    def test_cached_listing_is_revalidated_and_not_reported_if_removed(self):
        page = 'https://registry.example/company/1'
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory)
            fetch._remember_listings(dest, 'Example AB', 2025, [report_listing.inspect(page, listing(), 'Example AB', 2025)])
            with patch.object(fetch, '_get', return_value=listing(year=2024).encode()), patch.object(fetch, 'websearch_provider', return_value=None), patch.object(fetch, '_candidates', return_value=[]):
                with self.assertRaises(LookupError) as caught:
                    fetch.fetch_report('Example AB', 2025, dest)
            self.assertEqual(fetch.failure_response('Example AB', 2025, caught.exception)[1]['code'], 'report_unavailable')

    def test_cached_listing_can_upgrade_to_a_newly_available_pdf(self):
        page, pdf = 'https://registry.example/company/1', 'https://registry.example/download/2025'
        html = listing(action=f'<a href="{pdf}">Download annual report 2025</a>')
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory)
            fetch._remember_listings(dest, 'Example AB', 2025, [report_listing.inspect(page, listing(), 'Example AB', 2025)])
            with patch.object(fetch, '_get', side_effect=lambda url, **kw: accounts() if url == pdf else html.encode()), patch.object(fetch, '_model_candidates') as model:
                result = fetch.fetch_report('Example AB', 2025, dest)
            model.assert_not_called()
            self.assertEqual(result['source_url'], pdf)


if __name__ == '__main__':
    unittest.main()
