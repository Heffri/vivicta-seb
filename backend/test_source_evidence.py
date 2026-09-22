"""Source evidence tests: python -m unittest test_source_evidence -v."""
import tempfile
import unittest
from pathlib import Path

import pymupdf
from fastapi import HTTPException
from fastapi.testclient import TestClient
import app
from pipeline import source_evidence


def report_fixture():
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page(width=600, height=800)
    page = doc[1]
    page.insert_text((45, 45), "Consolidated income statement", fontsize=18)
    page.insert_text((400, 90), "2025", fontsize=12)
    page.insert_text((490, 90), "2024", fontsize=12)
    for label, current, previous, y in [
        ("Sales of products", "27,669", "25,531", 130),
        ("Interest and dividend income", "203", "206", 170),
        ("Unrelated other income", "203", "2030", 220),
        ("Financial expenses", "(86)", "(74)", 270),
    ]:
        page.insert_text((45, y), label, fontsize=12)
        page.insert_text((400, y), current, fontsize=12)
        page.insert_text((490, y), previous, fontsize=12)
    page.insert_text((45, 350), "Revenue increased by 12.5 percent.", fontsize=12)
    return doc


class EvidenceTests(unittest.TestCase):
    def test_table_numbers_stay_with_their_label_and_ignore_unrelated_repeats(self):
        with report_fixture() as doc:
            found = source_evidence.locate(doc[1], ["Interest and dividend income 203 206"])
            self.assertEqual(found['matched_quotes'], 1)
            self.assertEqual(len(found['numbers']), 2)
            self.assertEqual(len(found['keywords']), 4)
            self.assertTrue(all(150 < r.y0 < 175 for r in found['numbers'] + found['keywords']))

    def test_partial_numbers_and_unmatched_quotes_are_not_highlighted(self):
        with report_fixture() as doc:
            found = source_evidence.locate(doc[1], ["Revenue increased by 12 percent", "Debt is 999"])
            self.assertFalse(found['numbers'])
            self.assertFalse(found['keywords'])
            self.assertFalse(source_evidence.locate(doc[1], ["203"])['numbers'])

    def test_accounting_negatives_and_keyword_only_passages(self):
        with report_fixture() as doc:
            self.assertEqual(len(source_evidence.locate(doc[1], ['Financial expenses (86) (74)'])['numbers']), 2)
            self.assertTrue(source_evidence.locate(doc[1], ['Consolidated income statement'])['keywords'])

    def test_duplicate_and_overlapping_quotes_are_counted_without_duplicate_rectangles(self):
        with report_fixture() as doc:
            found = source_evidence.locate(doc[1], ['Interest and dividend income 203 206', 'Interest and dividend income 203', 'Interest and dividend income 203'])
            self.assertEqual(found['total_quotes'], 2)
            self.assertEqual(found['matched_quotes'], 2)
            self.assertEqual(len(found['numbers']), 2)

    def test_annotation_copy_keeps_all_pages_and_original_bytes_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.pdf'
            with report_fixture() as original:
                original.save(path)
            before = path.read_bytes()
            report_id = 'test-source-evidence'
            app.reports[report_id] = {'report_id': report_id, 'filename': path.name, 'pages': 3}
            app.library_paths[report_id] = path
            try:
                result = app.report_pdf(report_id, page=2, quote=['Interest and dividend income 203 206'])
                self.assertEqual(result.media_type, 'application/pdf')
                with pymupdf.open(stream=result.body, filetype='pdf') as annotated:
                    self.assertEqual(len(annotated), 3)
                    self.assertFalse(list(annotated[0].annots() or []))
                    self.assertEqual(len(list(annotated[1].annots())), 2)
                    self.assertFalse(list(annotated[2].annots() or []))
                    colors = [a.colors['stroke'] for a in annotated[1].annots()]
                    self.assertEqual(len(colors), 2)
                    self.assertGreater(colors[0][2], colors[0][0])
                    self.assertGreater(colors[1][0], colors[1][2])
                self.assertEqual(path.read_bytes(), before)
                with TestClient(app.app) as client:
                    url = f'/api/reports/{report_id}'
                    query = [('page', '2'), ('quote', 'Interest and dividend income 203 206')]
                    pdf = client.get(url + '/pdf', params=query)
                    self.assertEqual(pdf.status_code, 200)
                    self.assertTrue(pdf.content.startswith(b'%PDF-'))
                    evidence = client.get(url + '/pages/2/evidence', params={'quote': query[1][1]})
                    self.assertEqual(evidence.status_code, 200)
                    self.assertEqual(len(evidence.json()['numbers']), 2)
                    self.assertEqual(client.get(url + '/pdf').content, before)
                    self.assertEqual(client.get(url + '/pdf', params={'quote': 'Income'}).status_code, 422)
                    self.assertEqual(client.get(url + '/pages/2/evidence', params={'quote': ''}).status_code, 422)
                with self.assertRaises(HTTPException):
                    app.report_pdf(report_id, page=9, quote=['Income'])
                with self.assertRaises(HTTPException):
                    app.page_evidence(report_id, 0, ['Income'])
            finally:
                app.reports.pop(report_id, None)
                app.library_paths.pop(report_id, None)

    def test_rotated_preview_coordinates_and_annotation_alignment(self):
        with report_fixture() as doc:
            page = doc[1]
            page.set_rotation(90)
            found = source_evidence.locate(page, ['Interest and dividend income 203 206'])
            result = source_evidence.response(page, found)
            self.assertEqual((result['width'], result['height']), (800, 600))
            self.assertEqual(result['numbers'][0], list(found['numbers'][0] * page.rotation_matrix))
            source_evidence.annotate(page, found)
            self.assertEqual(len(list(page.annots())), 2)

    def test_empty_text_layer_and_input_limits(self):
        with pymupdf.open() as doc:
            page = doc.new_page()
            found = source_evidence.locate(page, ['Interest income 203'])
            self.assertEqual(found['matched_quotes'], 0)
        for quotes in ([], [''], ['a' * 8001], ['x'] * 21, ['x' * 8000] * 4):
            with self.assertRaises(HTTPException):
                app.evidence_quotes(quotes)


if __name__ == '__main__':
    unittest.main()
