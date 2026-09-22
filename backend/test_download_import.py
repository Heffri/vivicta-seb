"""Browser imports must verify content and preserve saved reports/reviews."""
import json
import os
import tempfile
import unittest
import pymupdf
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import app
from test_fetch_coverage import accounts


class DownloadImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for mock in [patch.dict(os.environ, {'KB_DIR': str(self.root / 'kb')}),
                     patch.object(app, 'LIBRARY', self.root / 'reports'),
                     *[patch.object(app, key, {}) for key in ('reports', 'library_paths', 'texts_cache', 'library_pages')]]:
            mock.start()
            self.addCleanup(mock.stop)
        self.client = TestClient(app.app)

    def upload(self, data, company='Example AB', year=2025, source='https://registry.example/company/1'):
        return self.client.post('/api/reports/import-download', files={'file': ('download.pdf', data, 'application/pdf')},
                                data={'company': company, 'year': str(year), 'source_url': source})

    def test_valid_download_registered_with_provenance_for_multiple_companies(self):
        for company in ['The Grand Group AB', 'Atlas Antibodies AB', 'Example Manufacturing Ltd']:
            response = self.upload(accounts(company), company)
            self.assertEqual(response.status_code, 200, response.text)
            report = response.json()
            self.assertEqual(report['company'], company)
            self.assertEqual(report['fiscal_year'], 2025)
            self.assertTrue(app.pdf_available(report['report_id']))
            meta = app.kb._meta(report['stem'])
            self.assertEqual(meta['source_url'], 'https://registry.example/company/1')

    def test_wrong_issuer_year_html_and_incomplete_accounts_never_saved(self):
        for data in [accounts('Other AB'), accounts(year=2024), b'<html>captcha</html>', accounts(balance=False)]:
            response = self.upload(data)
            self.assertEqual(response.status_code, 400, response.text)
        self.assertFalse(app.LIBRARY.exists())

    def test_reimport_reuses_report_and_preserves_reviews(self):
        data = accounts()
        first = self.upload(data).json()
        folder = self.root / 'kb' / first['stem'] / 'extractions'
        folder.mkdir(exist_ok=True)
        review = folder / 'debt_maturity.json'
        review.write_text('{"reviewed":true}')
        again = self.upload(data).json()
        self.assertEqual(first['report_id'], again['report_id'])
        self.assertEqual(review.read_text(), '{"reviewed":true}')
        self.assertEqual(len(json.loads((app.LIBRARY / 'index.json').read_text())), 1)

    def test_different_edition_keeps_earlier_pdf_and_metadata(self):
        old = accounts()
        first = self.upload(old).json()
        original_path = app.pdf_path(first['report_id'])
        saved_meta = app.kb._meta(first['stem'])
        new = accounts(title='Annual financial report')
        second = self.upload(new).json()
        self.assertNotEqual(first['report_id'], second['report_id'])
        self.assertEqual(original_path.read_bytes(), old)
        self.assertEqual(app.kb._meta(first['stem']), saved_meta)

    def test_invalid_source_is_rejected(self):
        self.assertEqual(self.upload(accounts(), source='file:///tmp/report.pdf').status_code, 400)

    def test_historical_accounts_survive_reload_and_candidate_scope(self):
        from test_report_period import pdf, prospectus
        response = self.upload(pdf(prospectus()), 'Example Industries Inc.', 2023)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual(report['statement_pages'], [2, 3, 4, 5])
        self.assertIn('not a standalone annual report', report['source_notice'])
        app.reports.clear()
        reloaded = app.get_report(report['report_id'])
        self.assertEqual(reloaded['document_type'], 'registration_statement')
        def candidates(texts, schema, **kw):
            self.assertEqual(texts[0], '')
            self.assertEqual(texts[5:], ['', ''])
            self.assertIn('Revenue', texts[3])
            return [4]
        with patch.object(app.locate, 'candidate_pages', side_effect=candidates):
            found = self.client.get(f"/api/reports/{report['report_id']}/candidates?section=income_statement")
        self.assertEqual(found.status_code, 200, found.text)
        self.assertEqual(found.json()[0]['page'], 4)
        self.assertIn('PROSPECTUS', app.report_texts(report['report_id'])[0])
        chunks = app.kb.chunks(report['stem'])
        self.assertTrue(chunks)
        self.assertTrue(all(c['page'] in [2, 3, 4, 5] for c in chunks))

    def test_same_filing_for_two_audited_years_retains_selected_year(self):
        from test_report_period import pdf, prospectus
        data = pdf(prospectus())
        one = self.upload(data, 'Example Industries Inc.', 2023).json()
        two_response = self.upload(data, 'Example Industries Inc.', 2022)
        self.assertEqual(two_response.status_code, 200, two_response.text)
        two = two_response.json()
        self.assertNotEqual(one['report_id'], two['report_id'])
        self.assertEqual(two['fiscal_year'], 2022)

    def test_scanned_report_uses_ocr_text_for_validation_and_saves_original_bytes(self):
        with pymupdf.open(stream=accounts(), filetype='pdf') as original, pymupdf.open() as scanned:
            texts = [page.get_text() for page in original]
            for page in original:
                scanned.new_page().insert_image(page.rect, pixmap=page.get_pixmap())
            data = scanned.tobytes()
        def ocr(page, metadata):
            metadata['ocr_pages'].append(page.number + 1)
            return texts[page.number]
        with patch.object(app.parse, 'page_text', side_effect=ocr) as read:
            response = self.upload(data)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual(read.call_count, len(texts))
        self.assertEqual(app.pdf_path(report['report_id']).read_bytes(), data)
        self.assertEqual(app.kb._meta(report['stem'])['ocr_pages'], list(range(1, 9)))
        self.assertEqual(list(app.kb._pages(report['stem']).values()), texts)
        with patch.object(app.parse, 'page_text', return_value='Wrong Company AB Annual report 2024'):
            self.assertEqual(self.upload(data).status_code, 400)


if __name__ == '__main__':
    unittest.main()
