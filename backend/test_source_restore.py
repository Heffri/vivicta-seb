"""Restore a saved report without replacing its edition or publishing a failed parse."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient

import app
from pipeline import kb, parse


def pdf_bytes(label):
    with pymupdf.open() as doc:
        doc.new_page().insert_text((50, 50), label)
        return doc.tobytes()


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for mock in [patch.dict(os.environ, {"KB_DIR": str(self.root / "kb")}),
                     patch.object(app, "LIBRARY", self.root / "reports"),
                     patch.object(app, "UPLOADS", self.root / "uploads"),
                     *[patch.object(app, key, {}) for key in ("reports", "library_paths", "texts_cache", "library_pages")]]:
            mock.start()
            self.addCleanup(mock.stop)
        app.LIBRARY.mkdir()
        self.client = TestClient(app.app)
        self.original = pdf_bytes("Original income statement 203 206")
        self.other = pdf_bytes("Another edition with different page numbers")

    def save(self, company="Example Industries", stem="example_2025"):
        folder = self.root / "kb" / stem
        folder.mkdir(parents=True)
        meta = {"company": company, "fiscal_year": 2025, "pages": 1, "sha256": kb.sha256(self.original),
                "source_url": f"https://example.com/{stem}.pdf", "filename": f"{stem}.pdf", "language": "en"}
        (folder / "meta.json").write_text(json.dumps(meta))
        (folder / "pages.jsonl").write_text(json.dumps({"page": 1, "text": "Original income statement 203 206"}) + "\n")
        (folder / "extractions").mkdir()
        (folder / "extractions" / "debt_maturity.json").write_text('{"fields": [], "reviews": "preserve me"}')
        return meta

    def test_fetch_restores_saved_source_for_multiple_companies_without_discovery(self):
        for company, stem in [("ABB", "abb_2025"), ("AstraZeneca", "astrazeneca_2025"), ("Example Industries", "example_2025")]:
            with self.subTest(company=company):
                meta = self.save(company, stem)
                with patch.object(app.fetch, "_get", return_value=self.original) as get, patch.object(app.fetch, "fetch_report") as discover:
                    response = self.client.post("/api/reports/fetch", json={"company": company, "year": 2025})
                self.assertEqual(response.status_code, 200, response.text)
                get.assert_called_once_with(meta["source_url"])
                discover.assert_not_called()
                self.assertEqual((app.LIBRARY / meta["filename"]).read_bytes(), self.original)
                self.assertTrue(app.pdf_available(response.json()["report_id"]))

    def test_wrong_cached_edition_is_hidden_and_repaired_without_changing_saved_evidence(self):
        meta = self.save()
        (app.LIBRARY / meta["filename"]).write_bytes(self.other)
        folder = self.root / "kb" / "example_2025"
        before = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        self.assertEqual(self.client.get("/api/reports/lib-example_2025/pdf").status_code, 409)
        self.assertEqual(app.report_texts("lib-example_2025"), ["Original income statement 203 206"])
        with patch.object(app.fetch, "_get", return_value=self.original):
            response = self.client.post("/api/kb/example_2025/pdf")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/api/reports/lib-example_2025/pdf").content, self.original)
        self.assertEqual(next((app.LIBRARY / "replaced").glob("*.pdf")).read_bytes(), self.other)
        self.assertEqual(before, {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()})

    def test_changed_publisher_pdf_is_rejected_and_existing_files_preserved(self):
        meta = self.save()
        with patch.object(app.fetch, "_get", return_value=self.other):
            response = self.client.post("/api/kb/example_2025/pdf")
        self.assertEqual(response.status_code, 409)
        self.assertFalse((app.LIBRARY / meta["filename"]).exists())
        self.assertEqual(kb._meta("example_2025"), meta)

    def test_download_failure_can_retry_and_extract_retains_saved_text(self):
        self.save()
        with patch.object(app.fetch, "_get", side_effect=OSError("offline")), patch.object(app.fetch, "fetch_report") as discover:
            self.assertEqual(self.client.post("/api/kb/example_2025/pdf").status_code, 502)
            response = self.client.post("/api/reports/fetch", json={"company": "Example Industries", "year": 2025})
            self.assertEqual(response.status_code, 200)
            discover.assert_not_called()
        self.assertFalse(app.pdf_available("lib-example_2025"))
        with patch.object(app.fetch, "_get", return_value=self.original):
            self.assertEqual(self.client.post("/api/kb/example_2025/pdf").status_code, 200)

    def test_matching_cache_is_reused_without_network(self):
        meta = self.save()
        (app.LIBRARY / meta["filename"]).write_bytes(self.original)
        with patch.object(app.fetch, "_get") as get:
            self.assertEqual(self.client.post("/api/kb/example_2025/pdf").status_code, 200)
            get.assert_not_called()

    def test_registration_rejects_a_different_edition(self):
        meta = self.save()
        (app.LIBRARY / meta["filename"]).write_bytes(self.other)
        with self.assertRaises(app.HTTPException) as error:
            app.register_library(meta | {"file": meta["filename"]})
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(kb._meta("example_2025"), meta)

    def test_failed_registration_does_not_publish_state_and_retry_reparses(self):
        path = app.LIBRARY / "new_2025.pdf"
        path.write_bytes(self.original)
        entry = {"file": path.name, "company": "New", "fiscal_year": 2025}
        # Reproduce the old bug: a saved-text report already existed before PDF registration.
        app.reports["lib-new_2025"] = {"pages": 1, "stem": path.stem}
        app.texts_cache["lib-new_2025"] = ["Saved text"]
        with patch.object(kb, "load_texts", side_effect=[parse.OCRUnavailable("missing language"), (["Parsed text"], {})]) as load:
            with self.assertRaises(parse.OCRUnavailable):
                app.register_library(entry)
            self.assertNotIn("lib-new_2025", app.library_paths)
            self.assertEqual(app.texts_cache["lib-new_2025"], ["Saved text"])
            app.register_library(entry)
            self.assertEqual(load.call_count, 2)
            self.assertEqual(app.texts_cache["lib-new_2025"], ["Parsed text"])

    def test_unknown_stem_cannot_download(self):
        with patch.object(app.fetch, "_get") as get:
            self.assertEqual(self.client.post("/api/kb/unknown_2025/pdf").status_code, 404)
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
