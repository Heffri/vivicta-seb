"""Self-check for the KB: save idempotency (v024) + BM25 retrieval, the retrieval three-state and
EMBED_MODEL invalidation (v034), empty-retrieval short-circuit (v059), KB open without the cached
PDF (v092). Run: python -m pipeline.test_kb"""
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _env(**vals):
    """Temporarily set/unset LLM_* env vars (None = unset); restores whatever was there before."""
    vals.setdefault("EMBED_BASE_URL", None)
    saved = {k: os.environ.get(k) for k in vals}
    for k, v in vals.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# A tiny mixed en/sv report: page 1 carries the revenue line, page 2 the (Swedish) operating profit
# and a debt-maturity line, page 3 is unrelated prose so there is something that must NOT outrank.
PAGES = {
    1: "Net sales were 1 234 MSEK in 2025, up from 1 100 MSEK. Net sales grew in all regions.",
    2: "Rörelseresultatet uppgick till 200 MSEK år 2025. Räntebärande skulder som förfaller inom ett år uppgick till 50 MSEK.",
    3: "Cash flow from operations was strong. The company invests in new factories and equipment for the future.",
}


def _seed(kb, tmp) -> str:
    """Isolated KB_DIR + a three-page demo report with one committed income_statement extraction."""
    os.environ["KB_DIR"] = str(tmp)
    kb._vecs.clear()
    kb._pages_cache.clear()
    kb._bm25_cache.clear()
    kb._entry_cache.clear()
    stem = "acme_2025"
    meta = {"company": "Acme", "fiscal_year": 2025, "language": "sv", "source_url": None,
            "pages": 3, "sha256": "beef", "filename": "acme.pdf"}
    kb.save_report(stem, meta, [PAGES[i] for i in (1, 2, 3)])
    x = {"report_id": stem, "company": "Acme", "fiscal_year": 2025, "currency": "MSEK", "section": "income_statement",
         "fields": [
             {"key": "revenue", "label": "Revenue", "value": 1234, "unit": "MSEK", "period": "2025", "raw_label": "Net sales",
              "source": {"page": 1, "quote": "Net sales were 1 234 MSEK"}, "confidence": 1.0, "evidence": []},
             {"key": "operating_profit", "label": "Operating profit", "value": 200, "unit": "MSEK", "period": "2025",
              "raw_label": "Rörelseresultatet", "source": {"page": 2, "quote": "Rörelseresultatet uppgick till 200 MSEK"},
              "confidence": 1.0, "evidence": []}],
         "checks": [], "warnings": []}
    kb.save_extraction(stem, "income_statement", x)
    return stem


def demo():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KB_DIR"] = tmp
        from . import kb, parse
        assert kb.kb_dir() == Path(tmp).resolve(), kb.kb_dir()  # env var actually redirects kb_dir()

        stem = "acme_2025"
        meta = {"company": "Acme", "fiscal_year": 2025, "language": "en", "source_url": None,
                "pages": 2, "sha256": "deadbeef", "filename": "acme.pdf"}
        texts = ["page one text", "page two text"]
        d = kb.kb_dir() / stem

        kb.save_report(stem, meta, texts)
        meta_1, pages_1 = (d / "meta.json").read_bytes(), (d / "pages.jsonl").read_bytes()
        meta_mtime_1, pages_mtime_1 = (d / "meta.json").stat().st_mtime_ns, (d / "pages.jsonl").stat().st_mtime_ns
        assert json.loads(meta_1)["parser"] == parse.PARSER_VERSION

        time.sleep(0.01)  # mtime-resolution guard: a same-tick rewrite could pass by accident
        kb.save_report(stem, meta, texts)  # same sha256, same parser -> must be a no-op
        assert (d / "meta.json").read_bytes() == meta_1, "meta.json rewritten on a same-sha256/same-parser save"
        assert (d / "pages.jsonl").read_bytes() == pages_1, "pages.jsonl rewritten on a same-sha256/same-parser save"
        assert (d / "meta.json").stat().st_mtime_ns == meta_mtime_1, "meta.json mtime changed on a no-op save"
        assert (d / "pages.jsonl").stat().st_mtime_ns == pages_mtime_1, "pages.jsonl mtime changed on a no-op save"

        # sha256 change -> the upgrade/re-parse path stays: rewrite, even at the same parser version
        time.sleep(0.01)
        meta_new_sha = {**meta, "sha256": "beefdead"}
        kb.save_report(stem, meta_new_sha, ["new page one", "new page two"])
        meta_2 = (d / "meta.json").read_bytes()
        assert meta_2 != meta_1, "sha256 change did not rewrite meta.json"
        assert json.loads(meta_2)["sha256"] == "beefdead"
        assert (d / "pages.jsonl").read_bytes() != pages_1, "sha256 change did not rewrite pages.jsonl"

        # PARSER_VERSION bump -> rewrite, even at the same sha256 (the v2->v3 upgrade path)
        old_version = parse.PARSER_VERSION
        parse.PARSER_VERSION = old_version + 1
        try:
            time.sleep(0.01)
            kb.save_report(stem, meta_new_sha, ["new page one", "new page two"])
            meta_3 = (d / "meta.json").read_bytes()
            assert meta_3 != meta_2, "parser version bump did not rewrite meta.json"
            assert json.loads(meta_3)["parser"] == old_version + 1

            time.sleep(0.01)  # same (sha256, parser) again post-bump -> back to a no-op
            kb.save_report(stem, meta_new_sha, ["new page one", "new page two"])
            assert (d / "meta.json").read_bytes() == meta_3, "meta.json rewritten on a no-op save after the version bump"
        finally:
            parse.PARSER_VERSION = old_version

        # legacy meta with no "parser" key at all (pre-existing data/kb entries) -> writes once, then idempotent
        (d / "meta.json").write_text(json.dumps({"sha256": meta_new_sha["sha256"], "pages": 2}), encoding="utf-8")
        pre = (d / "meta.json").read_bytes()
        kb.save_report(stem, meta_new_sha, ["new page one", "new page two"])  # upgrade write: legit, allowed once
        post_1 = (d / "meta.json").read_bytes()
        assert post_1 != pre and json.loads(post_1)["parser"] == old_version
        time.sleep(0.01)
        kb.save_report(stem, meta_new_sha, ["new page one", "new page two"])  # now idempotent
        assert (d / "meta.json").read_bytes() == post_1, "second save after the legacy upgrade still rewrote meta.json"

    print("kb save idempotency ok")


# ---- v034: retrieval three-state -----------------------------------------------------------

def test_retrieval_modes():
    from . import kb
    with _env(LLM_BASE_URL="http://x/v1"):
        assert kb.retrieval_mode() == "hybrid", "LLM_BASE_URL set -> embeddings + BM25"
    with _env(LLM_BASE_URL=None, LLM_PROVIDER="codex"):
        assert kb.retrieval_mode() == "bm25", "codex-only -> keyword retrieval, no embeddings"
    with _env(LLM_BASE_URL=None, LLM_PROVIDER="claude"):
        assert kb.retrieval_mode() == "bm25", "claude-only -> keyword retrieval, no embeddings"
    with _env(LLM_BASE_URL=None, LLM_PROVIDER=None):
        assert kb.retrieval_mode() == "fixture", "nothing configured -> fixture"
    print("kb retrieval three-state ok")


# ---- v034: BM25 ranking --------------------------------------------------------------------

def test_bm25_ranking():
    from . import kb
    with tempfile.TemporaryDirectory() as tmp:
        with _env(LLM_BASE_URL=None, LLM_PROVIDER="codex"):  # bm25 mode: pure keyword ranking
            stem = _seed(kb, tmp)
            hits = kb.search([stem], "what was net sales in 2025", k=8)
            assert hits, "no hits at all"
            # the chunk carrying the exact printed label + figure outranks everything...
            assert hits[0]["page"] == 1 and "Net sales" in hits[0]["text"], hits[0]
            # ...including the Swedish operating-profit page, which shares only the year and the unit
            order = [h["page"] for h in hits]
            assert order.index(1) < order.index(2), f"paraphrase page outranked the exact-label page: {order}"
            # unrelated page 3 has zero query-token overlap: never in the top-3
            assert 3 not in order[:3], f"unrelated prose in top-3: {order[:3]}"
            # a fact chunk (start == -1) from the extraction always rides along (rule kept from cosine mode)
            assert any(h["page"] == 2 for h in hits), "operating-profit fact chunk missing from hits"
    print("kb bm25 ranking ok")


def test_stopwords_neutral():
    from . import kb
    with tempfile.TemporaryDirectory() as tmp:
        with _env(LLM_BASE_URL=None, LLM_PROVIDER="codex"):
            stem = _seed(kb, tmp)
            a = kb.search([stem], "net sales", k=8)
            b = kb.search([stem], "what was the net sales", k=8)  # stop words only
            assert [h["text"] for h in a] == [h["text"] for h in b], "stop words changed the ranking"


def test_swedish_prefix_stem():
    from . import kb
    with tempfile.TemporaryDirectory() as tmp:
        with _env(LLM_BASE_URL=None, LLM_PROVIDER="codex"):
            stem = _seed(kb, tmp)
            definite = kb.search([stem], "rörelseresultatet", k=8)   # the form printed on the page
            bare = kb.search([stem], "rörelseresultat", k=8)         # dictionary form
            assert definite and definite[0]["page"] == 2, definite[0] if definite else None
            assert [h["text"] for h in definite] == [h["text"] for h in bare], \
                "7-char prefix stemmer did not fold rörelseresultatet/rörelseresultat together"
    print("kb bm25 stopwords + sv prefix ok")


def test_bm25_mode_never_embeds():
    from . import kb
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmp:
        with _env(LLM_BASE_URL=None, LLM_PROVIDER="codex"), patch.object(kb.llm, "chat", side_effect=RuntimeError("offline test")):
            stem = _seed(kb, tmp)
            orig = kb.embed

            def _boom(texts):
                raise AssertionError("embed() called in bm25 mode")

            kb.embed = _boom
            try:
                hits = kb.search([stem], "net sales", k=8)
                assert hits and hits[0]["page"] == 1
                out = kb.ask([stem], "net sales")  # retrieval half runs; llm.chat may fail, that's fine
                assert out["question"] == "net sales" and out["citations"] == []  # no llm -> dropped/empty
                assert not (kb.kb_dir() / stem / "embeddings.jsonl").exists(), "bm25 mode wrote embeddings.jsonl"
            finally:
                kb.embed = orig
    print("kb bm25 mode never embeds ok")


def test_ask_citation_verification():
    """ask()'s verbatim-quote check is unchanged by the new ranking: kept when on the page, dropped with a
    warning when not. llm.chat is faked so nothing leaves the process (LLM_PROVIDER=codex is only there
    so retrieval_mode() is bm25 -- the fake never sees the env)."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp:
        with _env(LLM_BASE_URL=None, LLM_PROVIDER="codex"):
            stem = _seed(kb, tmp)
            fake = {"answer": "Net sales were 1 234 MSEK [Acme p.1].",
                    "citations": [{"company": "Acme", "page": 1, "quote": "Net sales were 1 234 MSEK"},
                                  {"company": "Acme", "page": 2, "quote": "this sentence appears nowhere on page two"}]}
            orig = kb.llm.chat
            kb.llm.chat = lambda *a, **k: json.dumps(fake)
            try:
                out = kb.ask([stem], "what was net sales in 2025")
            finally:
                kb.llm.chat = orig
            assert "withheld" in out["answer"]
            assert len(out["citations"]) == 1, out["citations"]
            assert out["citations"][0]["page"] == 1 and out["citations"][0]["company"] == "Acme"
            assert 0 <= out["citations"][0]["score"] <= 1
            assert any("quote not found" in w for w in out["warnings"]), out["warnings"]
    print("kb ask citation verification ok")


# ---- v059: empty retrieval -----------------------------------------------------------------

def test_bm25_all_zero_returns_no_hits():
    """A query none of whose terms appear in the corpus (Swedish question, English report) leaves every
    raw BM25 score at 0 -> bm25-mode search returns [] instead of cover-page order. Hybrid mode is
    unchanged: cosine still has a signal there (identical fake vectors -> cosine 1.0 for every chunk)."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp:
        stem = _seed(kb, tmp)
        with _env(LLM_BASE_URL=None, LLM_PROVIDER="codex"):
            assert kb.search([stem], "hur mycket kostade kaffet", k=8) == [], "all-zero BM25 still returned hits"
        orig = kb.embed

        def _same(texts):  # every vector identical -> query/chunk cosine 1.0 in hybrid mode
            return [[1.0] + [0.0] * 63 for _ in texts]

        kb.embed = _same
        try:
            with _env(LLM_BASE_URL="http://x/v1"):  # hybrid mode: the empty gate must not fire
                assert kb.search([stem], "hur mycket kostade kaffet", k=8), "hybrid mode lost cosine-only hits"
        finally:
            kb.embed = orig
    print("kb bm25 all-zero -> no hits ok")


def test_ask_empty_retrieval_skips_model():
    """v059: zero hits -> a fixed answer, no llm.chat call, empty citations, one retrieval warning; a
    question that does match still calls the model exactly once (unchanged path)."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp:
        with _env(LLM_BASE_URL=None, LLM_PROVIDER="codex"):
            stem = _seed(kb, tmp)
            calls: list = []
            orig = kb.llm.chat

            def _spy(*a, **k):
                calls.append(1)
                return json.dumps({"answer": "model was reached", "citations": []})

            kb.llm.chat = _spy
            try:
                out = kb.ask([stem], "hur mycket kostade kaffet")
                assert calls == [], "model called despite zero retrieval hits"
                assert out["citations"] == [] and "No passage" in out["answer"], out
                assert any("model not called" in w for w in out["warnings"]), out["warnings"]
                assert out["model"] == os.getenv("LLM_MODEL", "")
                hit_out = kb.ask([stem], "what was net sales in 2025")
                assert len(calls) == 1, "matching question did not call the model exactly once"
                assert hit_out["answer"] == "model was reached", hit_out["answer"]
            finally:
                kb.llm.chat = orig
    print("kb ask empty-retrieval skips model ok")


# ---- v034: EMBED_MODEL invalidation --------------------------------------------------------

def _fake_embed(kb, calls):
    """Deterministic offline stand-in for embed(): token-hash bag vectors (fake 'model'). Counts texts."""
    def fake(texts):
        calls.append(list(texts))
        out = []
        for t in texts:
            v = [0.0] * 64
            for tok in kb._tokens(t):
                v[int(hashlib_md5(tok), 16) % 64] += 1.0
            n = math_sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out
    return fake


def hashlib_md5(s):
    import hashlib
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def math_sqrt(x):
    import math
    return math.sqrt(x)


def test_embed_model_invalidation():
    from . import kb
    with tempfile.TemporaryDirectory() as tmp:
        with _env(LLM_BASE_URL="http://x/v1", EMBED_MODEL="fake-a"):  # hybrid mode: index() embeds
            stem = _seed(kb, tmp)
            calls: list = []
            orig = kb.embed
            kb.embed = _fake_embed(kb, calls)
            try:
                r1 = kb.index(stem)
                assert r1["cached"] is False and r1["chunks"] > 0 and r1["embed_model"] == "fake-a"
                n1 = sum(len(c) for c in calls)
                assert n1 > 0
                r2 = kb.index(stem)
                assert r2["cached"] is True, "second index() re-embedded everything"
                assert sum(len(c) for c in calls) == n1, "cached index() still called embed()"

                os.environ["EMBED_MODEL"] = "fake-b"
                r3 = kb.index(stem)
                assert r3["cached"] is False and r3["embed_model"] == "fake-b", "EMBED_MODEL change stayed cached"
                assert sum(len(c) for c in calls) > n1, "EMBED_MODEL change did not re-embed"
                emb = kb.kb_dir() / stem / "embeddings.jsonl"
                manifest = json.loads((emb.parent / "index.json").read_text(encoding="utf-8"))
                assert manifest["embed_model"] == "fake-b", "model manifest missing/wrong"
                assert all("text" in json.loads(l) for l in emb.read_text(encoding="utf-8").split("\n") if l), \
                    "a chunk row lost its text (or the meta line is not first)"

                # backward compat: a legacy file with no meta line is rebuilt exactly once, then cached
                rows = [l for l in emb.read_text(encoding="utf-8").split("\n") if l][1:]
                emb.write_text("\n".join(rows) + "\n", encoding="utf-8")
                kb._vecs.pop(stem, None)
                n2 = sum(len(c) for c in calls)
                r4 = kb.index(stem)
                assert r4["cached"] is False and sum(len(c) for c in calls) > n2, "legacy meta-less file was trusted"
                r5 = kb.index(stem)
                assert r5["cached"] is True, "post-legacy-rebuild index() not cached"
            finally:
                kb.embed = orig
    print("kb embed_model invalidation ok")


# ---- v034: FastAPI gates -------------------------------------------------------------------

def test_app_gates():
    """/api/ask, /api/reports/{id}/index and /api/config under the three states. kb.ask is monkeypatched
    so no provider (codex included) is ever really called."""
    with tempfile.TemporaryDirectory() as tmp:
        from . import kb
        stem = _seed(kb, tmp)
        import app as app_mod
        from fastapi.testclient import TestClient
        client = TestClient(app_mod.app)
        report = {"report_id": "t-1", "filename": "acme.pdf", "pages": 3, "company": "Acme", "fiscal_year": 2025, "stem": stem}
        sent = {"question": "q", "answer": "sentinel", "citations": [], "warnings": [], "model": "t"}
        orig_ask = app_mod.kb.ask
        app_mod.reports["t-1"] = report
        app_mod.kb.ask = lambda *a, **k: sent
        try:
            with _env(LLM_BASE_URL=None, LLM_PROVIDER="codex"):  # subscription-only setup
                r = client.post("/api/ask", json={"question": "net sales?", "report_ids": ["t-1"]})
                assert r.status_code == 200 and r.json()["answer"] == "sentinel", \
                    "codex-only setup still got the fixture answer"
                r = client.post("/api/reports/t-1/index")
                body = r.json()
                assert body["embed_model"] == "bm25" and body["chunks"] > 0 and body["cached"] is True, body
                assert not (Path(tmp) / stem / "embeddings.jsonl").exists(), "bm25 index wrote embeddings"
                assert client.get("/api/config").json()["retrieval"] == "bm25"
            with _env(LLM_BASE_URL=None, LLM_PROVIDER=None):  # frontend dev mode: fixture, unchanged
                r = client.post("/api/ask", json={"question": "q", "report_ids": ["t-1"]})
                assert r.json()["model"] == "fixture" and r.json()["warnings"] == ["fixture answer: LLM_BASE_URL unset"]
                assert client.get("/api/config").json()["retrieval"] == "fixture"
            with _env(LLM_BASE_URL="http://x/v1", LLM_PROVIDER=None):
                assert client.get("/api/config").json()["retrieval"] == "hybrid"
        finally:
            app_mod.kb.ask = orig_ask
            app_mod.reports.pop("t-1", None)
    print("kb app gates ok")


# ---- v092: KB open without the cached PDF ---------------------------------------------------

def test_kb_open_without_pdf():
    """GET /api/kb/{stem}/{section} with no cached PDF serves the stored extraction on the saved
    report id (lib-<stem>, meta from meta.json, no PDF path -- get_report's lazy registration):
    tables/CSV/PPTX work off the stored extraction, page images and /pdf 409 with a fetch-it hint,
    data/kb is not rewritten. Once the PDF arrives the same id gains its PDF path and pages render.
    (v092's own kb-<stem> registration was superseded by the team's saved_report_id path, 2026-09-18.)"""
    with tempfile.TemporaryDirectory() as tmp:
        from . import kb
        stem = _seed(kb, tmp)  # acme_2025 + income_statement in the isolated KB_DIR
        import app as app_mod
        from fastapi.testclient import TestClient
        client = TestClient(app_mod.app)
        orig_index, orig_library = app_mod.library_index, app_mod.LIBRARY
        mine = (f"lib-{stem}",)
        app_mod.library_index = lambda: []  # fresh-clone state: index.json exists, no PDF on disk
        meta_bytes = (kb.kb_dir() / stem / "meta.json").read_bytes()
        try:
            r = client.get(f"/api/kb/{stem}/income_statement")
            assert r.status_code == 200, f"open without the PDF: {r.status_code} {r.text}"  # was 409 pre-v092
            x = r.json()
            assert x["report_id"] == mine[0] and x["company"] == "Acme" and x["fields"][0]["value"] == 1234, x["report_id"]
            assert x["pdf_available"] is False, x.get("pdf_available")
            assert (kb.kb_dir() / stem / "meta.json").read_bytes() == meta_bytes, "PDF-less open rewrote meta.json"

            # exports ride the stored extraction alone -- no PDF anywhere
            csv = client.get(f"/api/reports/{mine[0]}/extraction.csv")
            assert csv.status_code == 200 and "revenue" in csv.text, csv.status_code
            pptx = client.get(f"/api/reports/{mine[0]}/extraction.pptx")
            assert pptx.status_code == 200 and pptx.headers["content-type"].startswith("application/vnd"), pptx.status_code

            # ...but the page endpoints say the PDF is missing (409, require_pdf)
            png = client.get(f"/api/reports/{mine[0]}/pages/1.png")
            assert png.status_code == 409 and "no longer cached" in png.json()["detail"], png.text
            pdf = client.get(f"/api/reports/{mine[0]}/pdf")
            assert pdf.status_code == 409 and "no longer cached" in pdf.json()["detail"], pdf.text

            entry = next(e for e in client.get("/api/kb").json() if e["stem"] == stem)
            assert entry["pdf_available"] is False and entry["report_id"] == mine[0], entry

            # the PDF arriving later: the same saved id picks up its PDF path and pages render
            import pymupdf
            libdir = Path(tmp) / "reports"
            libdir.mkdir()
            with pymupdf.open() as doc:
                for text in ("Net sales page", "operating profit page", "unrelated page"):
                    doc.new_page().insert_text((72, 72), text)
                doc.save(libdir / "acme.pdf")  # meta.json's own filename -- get_report joins on it, not on the stem
            app_mod.LIBRARY = libdir
            app_mod.library_index = lambda: [{"file": "acme.pdf", "company": "Acme", "fiscal_year": 2025}]
            app_mod.reports.pop(mine[0], None)  # a restart: get_report re-registers from meta.json and finds the PDF
            r2 = client.get(f"/api/kb/{stem}/income_statement")
            assert r2.status_code == 200 and r2.json()["report_id"] == mine[0] and r2.json()["pdf_available"] is True, r2.text
            entry2 = next(e for e in client.get("/api/kb").json() if e["stem"] == stem)
            assert entry2["report_id"] == mine[0] and entry2["pdf_available"] is True, entry2
            assert client.get(f"/api/reports/{mine[0]}/pages/1.png").status_code == 200, "cached PDF page still failing"
        finally:
            app_mod.library_index, app_mod.LIBRARY = orig_index, orig_library
            for k in mine:
                for d in (app_mod.reports, app_mod.extractions, app_mod.library_paths, app_mod.texts_cache):
                    d.pop(k, None)
    print("kb open without the cached PDF ok")


def test_catalog_content_availability():
    from . import kb
    with tempfile.TemporaryDirectory() as tmp, _env(KB_DIR=tmp):
        kb.save_report('empty_2025', {'company': 'Empty', 'pages': 2, 'sha256': 'empty-fixture'}, ['', '  '])
        kb.save_extraction('empty_2025', 'income_statement', {'fields': [{'key': 'revenue', 'value': None}]})
        entry = kb.entries()[0]
        assert not entry['text_available'] and not entry['figures_available'], entry
        # Replacing cached data must invalidate content flags, including numeric zero.
        pages = Path(tmp) / 'empty_2025/pages.jsonl'
        pages.write_text(json.dumps({'page': 1, 'text': 'Revenue 0'}) + '\n', encoding='utf-8')
        kb.save_extraction('empty_2025', 'income_statement', {'fields': [{'key': 'revenue', 'value': 0}]})
        entry = kb.entries()[0]
        assert entry['text_available'] and entry['figures_available'], entry
    print('Catalog counts actual saved text and non-null figures')


def test_entry_cache_warm_call_reads_no_files():
    """v173: once cached by file fingerprint, a second entries() call must be served by os.stat and
    directory listings alone -- zero file-content reads (proved with counting stubs)."""
    import builtins
    from . import kb
    with tempfile.TemporaryDirectory() as tmp, _env(KB_DIR=tmp):
        stem = _seed(kb, tmp)
        kb.entries()  # cold: fills the cache
        reads = []
        orig_read_text, orig_read_bytes, orig_open = Path.read_text, Path.read_bytes, builtins.open

        def counting_read(original, self, *args, **kwargs):
            reads.append(str(self))
            return original(self, *args, **kwargs)

        try:
            Path.read_text = lambda self, *a, **k: counting_read(orig_read_text, self, *a, **k)
            Path.read_bytes = lambda self, *a, **k: counting_read(orig_read_bytes, self, *a, **k)
            builtins.open = lambda file, *a, **k: (reads.append(str(file)), orig_open(file, *a, **k))[1]
            entries = kb.entries()
        finally:
            Path.read_text, Path.read_bytes, builtins.open = orig_read_text, orig_read_bytes, orig_open
        assert len(entries) == 1 and entries[0]["stem"] == stem, entries
        assert entries[0]["text_available"] and entries[0]["figures_available"], entries[0]
        assert reads == [], f"warm entries() read file contents: {reads}"
    print('Entry cache: a warm entries() call reads no file contents')


def test_entry_cache_write_visibility():
    """v173: writes invalidate by fingerprint -- a new extraction section and a new stem must be
    visible on the very next entries() call, with no manual eviction anywhere."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp, _env(KB_DIR=tmp):
        stem = _seed(kb, tmp)
        first = {e["stem"]: e for e in kb.entries()}
        assert first[stem]["sections"] == ["income_statement"], first[stem]
        kb.save_extraction(stem, "debt_maturity", {"fields": [{"key": "total_debt", "value": 1}]})
        kb.save_report("beta_2024", {"company": "Beta", "pages": 1, "sha256": "ff"}, ["Beta page one"])
        second = {e["stem"]: e for e in kb.entries()}
        assert second[stem]["sections"] == ["debt_maturity", "income_statement"], second[stem]
        assert second[stem]["figures_available"] is True, second[stem]
        assert set(second) == {stem, "beta_2024"}, sorted(second)
        assert second["beta_2024"]["text_available"] is True, second["beta_2024"]
    print('Entry cache: new sections and stems are visible on the next call')


# ---- w199: status=building only while a real write is in progress ---------------------------

def test_status_building_only_during_real_writes():
    """w199 (QA w195's poll storm): with no index task running -- fixture mode has none, embeddings
    are simply unavailable -- the status must be "missing", never "building", and a transient lock
    overlap must not survive the listing that observed it: the entry cache used to keep serving a
    building status it had picked up while a real write held the lock, which kept the frontend
    polling every 2 s forever. A held write lock still reports building, truthfully, while it runs."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp:
        stem = _seed(kb, tmp)
        assert kb.index_status(stem)["status"] == "missing", "quiet fixture stem is not missing"
        kb.entries()  # warm the entry cache with the quiet status

        acquired, release = threading.Event(), threading.Event()

        def writer():  # stands in for index()/save_report's real write: holds the stem lock only
            with kb.report_lock(stem):
                acquired.set()
                release.wait(5)

        t = threading.Thread(target=writer)
        t.start()
        assert acquired.wait(5)
        try:
            during = kb.index_status(stem)
            assert during["status"] == "building" and during["reason"] == "Report update in progress", during
            listing = {e["stem"]: e for e in kb.entries()}
            assert listing[stem]["status"] == "building", listing[stem]
        finally:
            release.set()
            t.join(5)
        # the write is over and nothing was written: the quiet status must come straight back --
        # before w199 the entry cache kept serving the building it had cached mid-write
        after = kb.index_status(stem)
        assert after["status"] == "missing", after
        cached = {e["stem"]: e for e in kb.entries()}
        assert cached[stem]["status"] == "missing", cached[stem]
    print("kb status building only during real writes ok")


def test_concurrent_reads_never_report_building():
    """w199: overlapping listings -- the poll storm's shape -- must never manufacture status
    "building" for a stem nobody is writing: readers used to hash under the write lock, so one
    listing's slow hash made every sibling listing's non-blocking acquire fail. The index here is
    real and fat enough that the hashing is exactly where the old code collided."""
    from . import kb
    with tempfile.TemporaryDirectory() as tmp:
        with _env(LLM_BASE_URL="http://x/v1"):
            _seed(kb, tmp)  # acme_2025: a second, never-indexed stem whose quiet status is "missing"
            kb.save_report("bulk_2025", {"company": "Bulk", "pages": 400, "sha256": "bulk"}, [f"page {n} text with revenue figures and operating profit for the year. " * 8 for n in range(400)])
            calls: list = []
            orig = kb.embed
            kb.embed = _fake_embed(kb, calls)
            try:
                assert kb.index("bulk_2025")["cached"] is False
            finally:
                kb.embed = orig
            quiet = kb.index_status("bulk_2025")["status"]
            assert quiet == "ready", quiet
            expected = {"bulk_2025": quiet, "acme_2025": kb.index_status("acme_2025")["status"]}
            observations: list = []
            barrier = threading.Barrier(8)

            def reader():
                barrier.wait()
                for _ in range(4):
                    observations.append(("bulk_2025", kb.index_status("bulk_2025")["status"]))
                    observations.extend((e["stem"], e["status"]) for e in kb.entries())

            threads = [threading.Thread(target=reader) for _ in range(8)]
            try:
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(30)
            finally:
                for t in threads:
                    if t.is_alive():
                        raise AssertionError("reader thread deadlocked")
            assert observations, "no status observations recorded"
            per_stem = {s for s, _ in observations}
            assert per_stem == set(expected), sorted(per_stem)
            assert all(status == expected[s] for s, status in observations), \
                f"concurrent reads manufactured other statuses: {sorted(set(observations))}"
    print("kb concurrent reads never report building ok")


if __name__ == "__main__":
    test_catalog_content_availability()
    test_entry_cache_warm_call_reads_no_files()
    test_entry_cache_write_visibility()
    test_status_building_only_during_real_writes()
    test_concurrent_reads_never_report_building()
    demo()
    test_retrieval_modes()
    test_bm25_ranking()
    test_stopwords_neutral()
    test_swedish_prefix_stem()
    test_bm25_mode_never_embeds()
    test_ask_citation_verification()
    test_bm25_all_zero_returns_no_hits()
    test_ask_empty_retrieval_skips_model()
    test_embed_model_invalidation()
    test_kb_open_without_pdf()
    test_app_gates()
    print("kb self-check ok")
