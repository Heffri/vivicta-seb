"""Offline contract check: python -m pipeline.test_global_ask (from backend/)."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app
from . import kb


def check():
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"KB_DIR": tmp, "LLM_BASE_URL": "http://unused/v1"}):
        library, uploads = Path(tmp) / "pdfs", Path(tmp) / "uploads"
        library.mkdir()
        uploads.mkdir()
        kb._pages_cache.clear()
        kb._bm25_cache.clear()
        with patch.multiple(app, LIBRARY=library, UPLOADS=uploads, reports={}, library_paths={}, texts_cache={}, extractions={},
                            COMPANIES=[{"name": "Acme AB", "sector": "Industrials"}]), TestClient(app.app) as client:
            def seed(stem, company="Acme AB", year=2025):
                text = "Revenue 100 MSEK. Operating profit 20 MSEK."
                kb.save_report(stem, {"company": company, "fiscal_year": year, "pages": 1,
                                      "filename": stem + ".pdf", "sha256": stem}, [text])
                kb.save_extraction(stem, "income_statement", {
                    "section": "income_statement", "fields": [
                        {"key": "revenue", "label": "Revenue", "value": 100, "unit": "MSEK", "period": str(year),
                         "source": {"page": 1, "quote": text}}], "checks": [], "warnings": []})
                return stem

            with patch.object(app, "_llm_configured", return_value=False), patch.object(kb.llm, "chat", side_effect=AssertionError("model called")):
                empty = client.post("/api/ask", json={"question": "revenue"}).json()
                assert "no parsed reports" in empty["answer"] and empty["citations"] == []
                seed("acme_2025")
                no_model = client.post("/api/ask", json={"question": "revenue"}).json()
                assert "Connect a model" in no_model["answer"] and no_model["citations"] == []
                assert "152" not in no_model["answer"]

            seed("acme_2024", year=2024)
            seed("up-1234", company="Unknown")
            (library / "acme_2025.pdf").write_bytes(b"only checking availability")
            listing = {r["stem"]: r for r in client.get("/api/kb").json()}
            assert listing["acme_2025"]["sector"] == "Industrials"
            assert listing["up-1234"]["sector"] is None
            assert listing["acme_2025"]["pdf_available"] is True
            assert listing["acme_2024"]["pdf_available"] is False
            assert listing["up-1234"]["report_id"] == "up-1234"
            app.reports.clear()  # stable IDs restore after process restart, without a PDF
            assert client.get("/api/reports/lib-acme_2024").json()["fiscal_year"] == 2024
            assert client.get("/api/reports/lib-acme_2024/pdf").status_code == 409
            assert client.get("/api/reports/lib-acme_2024/pages/1.png").status_code == 409
            saved = client.get("/api/kb/acme_2024/income_statement").json()
            assert saved["stem"] == "acme_2024" and saved["pdf_available"] is False
            assert client.get("/api/kb/up-1234/income_statement").status_code == 200
            assert client.get("/api/kb/acme_2024/pages/1").json()["text"].startswith("Revenue")
            assert client.get("/api/kb/acme_2024/pages/0").status_code == 404
            assert client.get("/api/kb/acme_2024/pages/2").status_code == 404
            assert client.get("/api/kb/..%5Csecret/pages/1").status_code == 404

            # Opening saved text before fetching the PDF must not make registration a no-op.
            assert app.report_texts("lib-acme_2024")[0].startswith("Revenue")
            (library / "acme_2024.pdf").write_bytes(b"newly fetched PDF")
            fresh = "Revenue 100 MSEK. Operating profit 20 MSEK. Fresh PDF text."
            with patch.object(app.parse, "page_texts", return_value=[fresh]) as parser:
                entry = {"file": "acme_2024.pdf", "company": "Acme AB", "fiscal_year": 2024}
                app.register_library(entry)
                app.register_library(entry)  # an already registered PDF still avoids reparsing
                assert parser.call_count == 1
            assert app.report_texts("lib-acme_2024") == [fresh]
            assert app.require_pdf("lib-acme_2024") == library / "acme_2024.pdf"
            assert client.get("/api/kb/acme_2024/income_statement").json()["pdf_available"] is True
            assert next(e for e in client.get("/api/kb").json() if e["stem"] == "acme_2024")["pdf_available"] is True

            invalid = [{"question": " "}, {"question": "x" * 2001},
                       {"question": "x", "report_ids": []}, {"question": "x", "report_stems": []},
                       {"question": "x", "report_ids": None}, {"question": "x", "report_stems": None},
                       {"question": "x", "report_ids": ["lib-acme_2025"], "report_stems": ["acme_2025"]}]
            with patch.object(kb, "ask", side_effect=AssertionError("invalid input reached model")):
                for body in invalid:
                    assert client.post("/api/ask", json=body).status_code == 400, body
                for key in ("report_ids", "report_stems"):
                    assert client.post("/api/ask", json={"question": "x", key: ["../secret"]}).status_code == 404

            answer = {"question": "revenue", "answer": "ok", "citations": [], "warnings": [], "model": "test"}
            with patch.object(app, "_llm_configured", return_value=True), patch.object(kb, "ask", return_value=answer) as mocked:
                assert client.post("/api/ask", json={"question": "revenue"}).status_code == 200
                assert set(mocked.call_args.args[0]) == {"acme_2024", "acme_2025", "up-1234"}
                assert mocked.call_args.kwargs["keyword_only"] is True
                client.post("/api/ask", json={"question": "revenue", "report_stems": ["acme_2024"]})
                assert mocked.call_args.args[0] == ["acme_2024"]
                client.post("/api/ask", json={"question": "revenue", "report_ids": ["lib-acme_2025"]})
                assert mocked.call_args.args[0] == ["acme_2025"] and mocked.call_args.kwargs["keyword_only"] is False

            # A configured embedding endpoint must never embed the whole KB for a global query.
            stems = [seed(f"company_{i}", company=f"Company {i}") for i in range(20)]
            with patch.object(kb, "embed", side_effect=AssertionError("global request embedded reports")):
                hits = kb.search(stems, "revenue", keyword_only=True)
                assert 0 < len(hits) <= 16 and all(len(h["text"]) <= 1600 for h in hits)
                with patch.object(kb.llm, "chat", side_effect=AssertionError("empty search called model")):
                    result = kb.ask(stems, "xyzzyunfindable", keyword_only=True)
                    assert result["citations"] == [] and any("model not called" in w for w in result["warnings"])

            # Identical company, page and quote across two years must never choose the first report.
            quote = "Revenue 100 MSEK."
            hits = [{"stem": s, "page": 1, "text": quote, "score": 1} for s in ("acme_2024", "acme_2025")]
            citation = {"company": "Acme AB", "page": 1, "quote": quote}
            with patch.object(kb, "search", return_value=hits), patch.object(kb.llm, "chat") as model:
                def respond(c):
                    model.return_value = json.dumps({"answer": "Revenue", "citations": [c]})
                    return kb.ask(["acme_2024", "acme_2025"], "revenue", keyword_only=True)

                assert respond(citation)["citations"] == []
                proper = citation | {"report_stem": "acme_2024", "fiscal_year": 2024}
                cited = respond(proper)["citations"]
                assert len(cited) == 1 and cited[0]["stem"] == "acme_2024" and cited[0]["fiscal_year"] == 2024
                assert respond(proper | {"fiscal_year": 2025})["citations"] == []
                assert respond(proper | {"report_stem": "outside_scope"})["citations"] == []
                assert respond(proper | {"page": True})["citations"] == []
                assert respond(proper | {"quote": "invented quote"})["citations"] == []
    kb._pages_cache.clear()
    kb._bm25_cache.clear()
    print("global Ask scope, saved sources, sectors, bounded retrieval and year citations: ok")


if __name__ == "__main__":
    check()
