"""Self-check for fetch.py's fourth source (v074): the model's own web search, asked only when the
feeds and the plain web search produced nothing. `llm.web_lookup` is faked (a scripted function, no
CLI, no network beyond a loopback http.server that serves one generated PDF), and `_candidates` is
patched out for the same reason -- this needs no MFN/Nasdaq/DuckDuckGo access and no model call.
Run: python -m pipeline.test_fetch"""
import json
import os
import tempfile
import threading
import functools
import http.server
from pathlib import Path

import pymupdf as fitz

from . import fetch

COMPANY, YEAR = "Nestle", 2025
GOOD_PATH, GONE_PATH = "/nestle-annual-report-2025.pdf", "/deleted.pdf"
# a name-filtered candidate: BAD_URL drops it before any download, mirroring what the real flow does
# with the interim/quarterly links a model sometimes proposes alongside the real report
INTERIM_URL = f"https://ir.example.com/{COMPANY.lower()}-q4-interim-report.pdf"


def _write_pdf(path: Path):
    """A 45-page PDF that passes _validate for (Nestle, 2025): text layer > 5000 chars in the first
    20 pages (insert_text clips long lines at the page edge, so several short ones), the issuer
    token and the year in there, "Annual Report" on the cover."""
    doc = fitz.open()
    for _ in range(45):
        page = doc.new_page()
        page.insert_text((72, 72), f"{COMPANY} Annual Report {YEAR}")
        for i in range(8):
            page.insert_text((72, 100 + 14 * i), f"{COMPANY} revenue, operating profit and financial statements.")
    doc.save(path)
    doc.close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # keep the self-check output clean
        pass


def _http_server(directory: Path):
    """Loopback server serving the generated PDF; ephemeral port, quiet logs."""
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class _FakeWebLookup:
    """Stands in for llm.web_lookup: records its arguments, replays a scripted behaviour."""

    def __init__(self):
        self.calls = []

    def __call__(self, system, user, schema, name="web_lookup"):
        self.calls.append({"system": system, "user": user, "schema": schema})
        reply = os.environ["FAKE_WEB_REPLY"]
        if reply == "raise":
            raise RuntimeError("codex exec exited 1: 429 Too Many Requests")
        return reply


def _reply(candidates):
    return json.dumps({"candidates": candidates})


def _url(base, path):
    return base + path


def demo():
    env_keys = ("LLM_PROVIDER", "FAKE_WEB_REPLY")
    saved = {k: os.environ.get(k) for k in env_keys}
    patched = {}
    server = None
    try:
        with tempfile.TemporaryDirectory(prefix="test-fetch-") as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "public").mkdir()
            _write_pdf(tmp / "public" / GOOD_PATH.lstrip("/"))
            server, base = _http_server(tmp / "public")
            good_url, gone_url = _url(base, GOOD_PATH), _url(base, GONE_PATH)

            fake = _FakeWebLookup()
            patched["web_lookup"] = fetch.llm.web_lookup, fake
            fetch.llm.web_lookup = fake
            patched["_candidates"] = fetch._candidates, (lambda company, year: [])
            fetch._candidates = lambda company, year: []

            dest = tmp / "reports"

            # 1. gate: with no CLI provider there is no fourth source -- web_lookup is never called,
            #    the LookupError carries no model note
            os.environ.pop("LLM_PROVIDER", None)
            try:
                fetch.fetch_report(COMPANY, YEAR, dest)
                assert False, "expected LookupError with the model gate off"
            except LookupError as e:
                assert e.args[0] == [] and (len(e.args) < 2 or not e.args[1]), e.args
            assert fake.calls == [], "web_lookup must not run without codex/claude"

            # 2. happy path: the model's first candidate is name-filtered (interim), the second is a
            #    real PDF on the loopback server -> registered with the model-search note + foreign tag
            os.environ["LLM_PROVIDER"] = "codex"
            os.environ["FAKE_WEB_REPLY"] = _reply([
                {"url": INTERIM_URL, "title": "Q4 interim", "reason": "wrong report"},
                {"url": good_url, "title": "Annual Report 2025", "reason": "official IR pdf"},
            ])
            entry = fetch.fetch_report(COMPANY, YEAR, dest, country="Switzerland", hint="FY ends 31 December")
            assert entry["source_url"] == good_url, entry
            assert entry["note"] == "model search (codex)", entry
            assert entry["tags"] == ["fetched", "foreign"], entry
            assert (dest / entry["file"]).exists()
            stored = [e for e in json.loads((dest / "index.json").read_text(encoding="utf-8")) if e["file"] == entry["file"]]
            assert stored and stored[0]["tags"] == ["fetched", "foreign"] and stored[0]["note"] == "model search (codex)", stored
            assert len(fake.calls) == 1
            call = fake.calls[0]
            assert call["system"] == fetch.SEARCH_SYSTEM and call["schema"] == fetch.SEARCH_SCHEMA, call
            assert "Company: Nestle" in call["user"] and "Fiscal year: 2025" in call["user"], call["user"]
            assert "Country: Switzerland" in call["user"] and "Hint: FY ends 31 December" in call["user"], call["user"]

            # 3. a cached report short-circuits everything: no candidates, no model call (the Swedish
            #    path and the foreign second call both go through here unchanged)
            again = fetch.fetch_report(COMPANY, YEAR, dest)
            assert again["tried"] == [] and again["file"] == entry["file"], again
            assert len(fake.calls) == 1, "cache hit must not re-search"

            # 4. unparseable model reply -> the 404 detail says the search itself failed
            dest2 = tmp / "reports2"
            os.environ["FAKE_WEB_REPLY"] = "I found some links, see https://example.com/report.pdf"
            try:
                fetch.fetch_report(COMPANY, YEAR, dest2)
                assert False, "expected LookupError on a non-JSON model reply"
            except LookupError as e:
                assert e.args[1] and "model search (codex) failed" in e.args[1], e.args

            # 5. an unavailable model (here: a 429) reads the same way
            os.environ["FAKE_WEB_REPLY"] = "raise"
            try:
                fetch.fetch_report(COMPANY, YEAR, dest2)
                assert False, "expected LookupError when the model call raises"
            except LookupError as e:
                assert e.args[1] and "429" in e.args[1], e.args

            # 6. every model candidate failing is still just "not found" -- no model note, and the
            #    BAD_URL candidate never even got fetched
            os.environ["FAKE_WEB_REPLY"] = _reply([
                {"url": INTERIM_URL, "title": "interim", "reason": "filtered"},
                {"url": gone_url, "title": "gone", "reason": "404 on download"},
            ])
            try:
                fetch.fetch_report(COMPANY, YEAR, dest2)
                assert False, "expected LookupError when all model candidates fail"
            except LookupError as e:
                assert e.args[0] == [gone_url], e.args  # the interim URL was dropped before the download
                assert len(e.args) < 2 or not e.args[1], e.args

            # 7. the candidate cap holds even when the model returns more than MAX_MODEL_CANDIDATES
            gone_urls = [_url(base, f"/gone{n}.pdf") for n in range(5)]
            os.environ["FAKE_WEB_REPLY"] = _reply([{"url": u} for u in gone_urls])
            try:
                fetch.fetch_report(COMPANY, YEAR, dest2)
                assert False, "expected LookupError for the capped candidate list"
            except LookupError as e:
                assert e.args[0] == gone_urls[: fetch.MAX_MODEL_CANDIDATES], e.args

            # 8. percent-encoded model URLs get a decoded twin right after them (Siemens' asset API
            #    400s on uuid%3A... but serves uuid:...); BAD_URL still filters both
            os.environ["FAKE_WEB_REPLY"] = _reply([
                {"url": "https://assets.example.com/api/uuid%3A428e/Annual-Report-2025.pdf", "title": "ar", "reason": "enc"},
                {"url": "https://assets.example.com/api/uuid%3A428e/q4-interim.pdf", "title": "q4", "reason": "enc bad"},
            ])
            urls, note = fetch._model_candidates(COMPANY, YEAR)
            assert urls == ["https://assets.example.com/api/uuid%3A428e/Annual-Report-2025.pdf",
                            "https://assets.example.com/api/uuid:428e/Annual-Report-2025.pdf"], urls
            assert note is None, note

            # 9. Swedish path unchanged: a candidate found above the model layer registers exactly as
            #    before (tags without "foreign", no note) and the model is never asked
            dest3 = tmp / "reports3"
            fetch._candidates = lambda company, year: [good_url]
            calls_before = len(fake.calls)
            entry3 = fetch.fetch_report(COMPANY, YEAR, dest3)
            assert entry3["source_url"] == good_url and entry3["tags"] == ["fetched"] and entry3["note"] is None, entry3
            assert len(fake.calls) == calls_before, "a feed-level hit must not trigger a model search"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for attr, original in patched.items():
            if attr == "web_lookup":
                fetch.llm.web_lookup = original
            else:
                setattr(fetch, attr, original)
        if server:
            server.shutdown()
            server.server_close()

    print("fetch self-check ok")


if __name__ == "__main__":
    demo()
