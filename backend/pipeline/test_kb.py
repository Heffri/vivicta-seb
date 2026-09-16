"""Self-check for the KB: save idempotency (v024) + BM25 retrieval, the retrieval three-state and
EMBED_MODEL invalidation (v034). Run: python -m pipeline.test_kb"""
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _env(**vals):
    """Temporarily set/unset LLM_* env vars (None = unset); restores whatever was there before."""
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
    with tempfile.TemporaryDirectory() as tmp:
        with _env(LLM_BASE_URL=None, LLM_PROVIDER="codex"):
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
            assert out["answer"] == fake["answer"]
            assert len(out["citations"]) == 1, out["citations"]
            assert out["citations"][0]["page"] == 1 and out["citations"][0]["company"] == "Acme"
            assert 0 <= out["citations"][0]["score"] <= 1
            assert any("quote not found" in w for w in out["warnings"]), out["warnings"]
    print("kb ask citation verification ok")


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
                first = emb.open(encoding="utf-8").readline()
                assert json.loads(first)["embed_model"] == "fake-b", "meta line missing/wrong"
                assert all("text" in json.loads(l) for l in emb.read_text(encoding="utf-8").split("\n")[1:] if l), \
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


if __name__ == "__main__":
    demo()
    test_retrieval_modes()
    test_bm25_ranking()
    test_stopwords_neutral()
    test_swedish_prefix_stem()
    test_bm25_mode_never_embeds()
    test_ask_citation_verification()
    test_embed_model_invalidation()
    test_app_gates()
    print("kb self-check ok")
