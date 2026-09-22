"""Self-check for AI-first report discovery: the model's own web search and the
IR-page retrieval that follows when
a model candidate turns out to be a page instead of a direct PDF. Also v081: the second model ask (only
after the fourth source and the first IR-page crawl both fail) and the complete-report-over-summary
ranking. `llm.web_lookup` is faked (a scripted function, no CLI, no network beyond a loopback
http.server that serves a handful of generated PDFs and static HTML pages), and `_candidates` is
patched out for the same reason -- this needs no MFN/Nasdaq/DuckDuckGo access and no model call.
Run: python -m pipeline.test_fetch"""
import json
import os
import random
import tempfile
import threading
import functools
import http.server
from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz

import app
from . import fetch, jobs

COMPANY, YEAR = "Nestle", 2025
GOOD_PATH, GONE_PATH = "/nestle-annual-report-2025.pdf", "/deleted.pdf"
# a name-filtered candidate: BAD_URL drops it before any download, mirroring what the real flow does
# with the interim/quarterly links a model sometimes proposes alongside the real report
INTERIM_URL = f"https://ir.example.com/{COMPANY.lower()}-q4-interim-report.pdf"
# v080: pages the model may hand back instead of a direct PDF link, and the report's own IR-page trail
IR_PAGE_PATH = "/ir/reports.html"                 # a direct PDF link among an interim one -- filtered
IR_HOP_INDEX_PATH = "/ir/index.html"               # no PDF link itself, links one hop to IR_HOP_PATH
IR_HOP_PATH = "/ir/reports-2025.html"
IR_MULTI_PATH = "/ir/all-reports.html"             # links both a shorter and a longer valid PDF
REVIEW_PATH, FULL_PATH = "/nestle-annual-review-2025.pdf", "/nestle-annual-report-2025-full.pdf"
# Shell's own shape: BAD_URL's "sustainab" term sits in an *earlier* path segment, not the filename
SHELL_SHAPE_PATH = "/sustainability/reporting-centre/nestle-annual-report-2025.pdf"
COUNTER_EXAMPLE_URL = "https://ir.example.com/annual-report/interim-q3.pdf"  # bad filename still wins
# v081: a page with nothing useful on it (the first IR crawl attempt must genuinely run and fail before
# the second ask fires), and two shapes of summary volume -- one flagged by its own filename, one only
# by its page count (Nestle's real Annual Review: a clean name, just short)
EMPTY_IR_PAGE_PATH = "/ir/empty.html"
SUMMARY_PATH = "/nestle-annual-report-highlights-2025.pdf"
REVIEW_SHAPE_PATH = "/nestle-annual-review-2025-en.pdf"


def _write_pdf(path: Path, pages: int = 90):
    """A `pages`-page PDF that passes _validate for (Nestle, 2025): text layer > 5000 chars in the first
    20 pages (insert_text clips long lines at the page edge, so several short ones), the issuer
    token and the year in there, "Annual Report" on the cover."""
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{COMPANY} Annual Report {YEAR}")
        for i in range(8):
            page.insert_text((72, 100 + 14 * i), f"{COMPANY} revenue, operating profit and financial statements.")
    doc.save(path)
    doc.close()


KB = Path(__file__).resolve().parents[2] / "data" / "kb"  # the committed corpus: real report page text, no PDFs
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"  # test-owned frozen inputs, independent of the corpus


def _kb_pages(stem: str):
    """Per-page texts for a KB stem -- the same parse the backend serves.
    split('\n'), not splitlines(): page text may hold U+2028 (the pipeline.kb._pages rule)."""
    lines = (KB / stem / "pages.jsonl").read_text(encoding="utf-8").split("\n")
    return [json.loads(l)["text"] for l in lines if l.strip()]


def _kb_page_texts(stem: str):
    """(first-three-pages text, full text) for a KB stem."""
    pages = _kb_pages(stem)
    return "".join(pages[:3]), "".join(pages)


def _mtg_fy2021_cover_pages():
    """MTG's real FY2021 first three pages (cover / contents / contents), frozen into
    fixtures/mtg_fy2021_cover_pages.jsonl from the pre-rebuild KB entry -- the first three lines of
    `git show 8a0e784~1:data/kb/modern_times_2025/pages.jsonl` byte for byte. That entry was MTG's
    148-page FY2021 report, the v122 defect; 8a0e784 rebuilt the stem from the real FY2025 document,
    so the defect text the anchored year check must refuse no longer exists in data/kb and the
    year-gate tests read it from here (same jsonl shape, same split('\n') rule as _kb_pages)."""
    lines = (FIXTURES / "mtg_fy2021_cover_pages.jsonl").read_text(encoding="utf-8").split("\n")
    return [json.loads(l)["text"] for l in lines if l.strip()]


def _pdf_from_page_texts(path: Path, page_texts, filler_lines=None, filler_pages=0):
    """A PDF whose leading pages carry the given texts line by line (latin-1 for the base-14 font,
    which only shifts dashes etc.), optionally followed by dense filler pages for the text-layer
    and page-count gates."""
    doc = fitz.open()
    for t in page_texts:
        page = doc.new_page()
        for i, line in enumerate((t or "").splitlines() or [""]):
            page.insert_text((72, 72 + 14 * i), line.encode("latin-1", "replace").decode("latin-1")[:90])
    for _ in range(filler_pages):
        page = doc.new_page()
        for i, line in enumerate(filler_lines):
            page.insert_text((72, 72 + 14 * i), line.encode("latin-1", "replace").decode("latin-1")[:90])
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
    """Stands in for llm.web_lookup: records its arguments, replays a scripted behaviour. v081's
    second ask uses its own system prompt (IR_PAGE_SYSTEM), so it can be scripted separately via
    FAKE_WEB_REPLY_IR_PAGE when set; falls back to the same FAKE_WEB_REPLY otherwise, which is what
    every pre-v081 test still does (it never sets the new env var)."""

    def __init__(self):
        self.calls = []

    def __call__(self, system, user, schema, name="web_lookup", job_id=None):
        self.calls.append({"system": system, "user": user, "schema": schema, "job_id": job_id})
        key = "FAKE_WEB_REPLY_IR_PAGE" if system == fetch.IR_PAGE_SYSTEM and "FAKE_WEB_REPLY_IR_PAGE" in os.environ else "FAKE_WEB_REPLY"
        reply = os.environ[key]
        if reply == "raise":
            raise RuntimeError("codex exec exited 1: 429 Too Many Requests")
        return reply


def _reply(candidates):
    return json.dumps({"candidates": candidates})


def _url(base, path):
    return base + path


def demo():
    env_keys = ("LLM_PROVIDER", "FAKE_WEB_REPLY", "FAKE_WEB_REPLY_IR_PAGE", "KB_DIR")
    saved = {k: os.environ.get(k) for k in env_keys}
    patched = {}
    server = None
    try:
        with tempfile.TemporaryDirectory(prefix="test-fetch-") as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "public").mkdir()
            (tmp / "public" / "ir").mkdir()
            (tmp / "public" / SHELL_SHAPE_PATH.lstrip("/")).parent.mkdir(parents=True)
            _write_pdf(tmp / "public" / GOOD_PATH.lstrip("/"))
            _write_pdf(tmp / "public" / REVIEW_PATH.lstrip("/"), pages=45)
            _write_pdf(tmp / "public" / FULL_PATH.lstrip("/"), pages=60)
            _write_pdf(tmp / "public" / SHELL_SHAPE_PATH.lstrip("/"))
            _write_pdf(tmp / "public" / SUMMARY_PATH.lstrip("/"), pages=45)
            _write_pdf(tmp / "public" / REVIEW_SHAPE_PATH.lstrip("/"), pages=45)
            (tmp / "public" / EMPTY_IR_PAGE_PATH.lstrip("/")).write_text(
                "<p>Investor relations. No reports listed here.</p>\n", encoding="utf-8")
            (tmp / "public" / IR_PAGE_PATH.lstrip("/")).write_text(
                f'<a href="/{COMPANY.lower()}-q4-interim-2025.pdf">Q4 interim report</a>\n'
                f'<a href="{GOOD_PATH}">Annual Report 2025</a>\n', encoding="utf-8")
            (tmp / "public" / IR_HOP_INDEX_PATH.lstrip("/")).write_text(
                f'<a href="{IR_HOP_PATH}">Annual reports</a>\n', encoding="utf-8")
            (tmp / "public" / IR_HOP_PATH.lstrip("/")).write_text(
                f'<a href="{GOOD_PATH}">Annual Report 2025</a>\n', encoding="utf-8")
            (tmp / "public" / IR_MULTI_PATH.lstrip("/")).write_text(
                f'<a href="{REVIEW_PATH}">Annual Review 2025</a>\n'
                f'<a href="{FULL_PATH}">Annual Report 2025</a>\n', encoding="utf-8")
            server, base = _http_server(tmp / "public")
            good_url, gone_url = _url(base, GOOD_PATH), _url(base, GONE_PATH)

            fake = _FakeWebLookup()
            # v194 fix: this used to store (original, replacement) 2-tuples and the restore loop below
            # set the attribute back to the whole tuple, not just `original` -- harmless as long as
            # nothing called fetch.llm.web_lookup/fetch._candidates again in this process after demo()
            # returned, which held until demo_candidates_events() below started doing exactly that.
            patched["web_lookup"] = fetch.llm.web_lookup
            fetch.llm.web_lookup = fake
            patched["_candidates"] = fetch._candidates
            fetch._candidates = lambda company, year, job_id=None: []

            # An isolated ARP_DATA_DIR may begin with no reports/index.json. Treat that
            # as an empty cache so the fetch route can proceed to discovery rather than 500.
            empty_library = tmp / "empty-library"
            empty_library.mkdir()
            with patch.object(app, "LIBRARY", empty_library):
                assert app.library_index() == []

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
            fetch._candidates = lambda company, year, job_id=None: (_ for _ in ()).throw(AssertionError('AI success must not scrape feeds'))
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
            fetch._candidates = lambda company, year, job_id=None: []

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

            # 9. Legacy sources remain available after AI discovery fails.
            dest3 = tmp / "reports3"
            fetch._candidates = lambda company, year, job_id=None: [good_url]
            os.environ["FAKE_WEB_REPLY"] = "raise"
            calls_before = len(fake.calls)
            entry3 = fetch.fetch_report(COMPANY, YEAR, dest3)
            assert entry3["source_url"] == good_url and entry3["tags"] == ["fetched"] and entry3["note"] is None, entry3
            assert len(fake.calls) == calls_before + 2, "model discovery precedes feed fallback"
            fetch._candidates = lambda company, year, job_id=None: []  # back to "nothing above the model layer" for 10-12

            # 10. v080 fifth source: the model names the issuer's IR page instead of a direct PDF --
            #     fetch_report crawls it, drops the interim link (no IS_AR match) and registers the
            #     real report link found next to it, with a source-specific note/tag pair
            dest4 = tmp / "reports4"
            ir_page_url = _url(base, IR_PAGE_PATH)
            os.environ["FAKE_WEB_REPLY"] = _reply([{"url": ir_page_url, "title": "Investor relations", "reason": "no direct pdf found"}])
            entry4 = fetch.fetch_report(COMPANY, YEAR, dest4)
            assert entry4["source_url"] == good_url, entry4
            assert entry4["note"] == "IR page crawl" and entry4["tags"] == ["fetched", "foreign"], entry4
            assert entry4["tried"] == [ir_page_url, good_url], entry4["tried"]

            # 11. v080: the crawled page links both a shorter and a longer valid report (Nestlé's
            #     Annual Review next to its actual Annual Report) -- the fifth source downloads both
            #     within budget and keeps the one with more pages, not just the first one found
            dest5 = tmp / "reports5"
            multi_url = _url(base, IR_MULTI_PATH)
            os.environ["FAKE_WEB_REPLY"] = _reply([{"url": multi_url, "title": "Reports", "reason": "ir page"}])
            entry5 = fetch.fetch_report(COMPANY, YEAR, dest5)
            assert entry5["source_url"] == _url(base, FULL_PATH), entry5

            # 12. v080: the IR page itself carries no PDF link but points one hop to a same-domain
            #     reports page that does -- the crawl follows that single hop and finds it there
            dest6 = tmp / "reports6"
            hop_index_url = _url(base, IR_HOP_INDEX_PATH)
            os.environ["FAKE_WEB_REPLY"] = _reply([{"url": hop_index_url, "title": "Investors", "reason": "ir landing page"}])
            entry6 = fetch.fetch_report(COMPANY, YEAR, dest6)
            assert entry6["source_url"] == good_url and entry6["note"] == "IR page crawl", entry6

            # 13. v080: a direct link that 404s outright (Shell's expired asset-store URL) leaves no
            #     page to crawl -- _host_guesses derives the same IR-path guesses _stub_pages makes,
            #     seeded from the dead URL's own domain, gated on that domain actually naming the company
            toks = fetch._toks(COMPANY)
            guesses = fetch._host_guesses("https://www.nestle.com/assets/stale-token/annual-report-2025.pdf", toks)
            assert guesses == [f"https://www.nestle.com{p}" for p in fetch._IR_PATHS], guesses
            assert fetch._host_guesses("https://cdn.example.com/report.pdf", toks) == [], "unrelated domain must not be guessed"

            # 14. v080 follow-up: BAD_URL's "sustainab" term sitting in an *earlier* path segment (Shell's
            #     real shape: /sustainability/reporting-centre/.../shell-annual-report-2025.pdf) must not
            #     drop a model candidate whose filename plainly names the report -- end to end, the model
            #     candidate now survives _model_candidates and the direct download succeeds (no crawl needed)
            dest8 = tmp / "reports8"
            shell_shape_url = _url(base, SHELL_SHAPE_PATH)
            os.environ["FAKE_WEB_REPLY"] = _reply([{"url": shell_shape_url, "title": "Annual Report 2025", "reason": "shell shape"}])
            entry8 = fetch.fetch_report(COMPANY, YEAR, dest8)
            assert entry8["source_url"] == shell_shape_url, entry8
            assert entry8["note"] == "model search (codex)" and entry8["tags"] == ["fetched", "foreign"], entry8
            assert entry8["tried"] == [shell_shape_url], entry8["tried"]

            # 15. counter-example: the filename itself is still bad (interim-q3.pdf) even though an
            #     earlier path segment happens to read "annual-report" -- still dropped pre-fetch
            os.environ["FAKE_WEB_REPLY"] = _reply([{"url": COUNTER_EXAMPLE_URL, "title": "Q3", "reason": "counter-example"}])
            urls, note = fetch._model_candidates(COMPANY, YEAR)
            assert urls == [], urls

            # unit-level check of the carve-out itself, both directions
            assert fetch._filename_clear(shell_shape_url, fetch.BAD_URL) is True, "clean filename clears a bad rest-of-path"
            assert fetch._filename_clear(COUNTER_EXAMPLE_URL, fetch.BAD_URL) is False, "a bad filename still rejects"

            # 16. v081: the second model ask fires only after every fourth-source candidate AND the
            #     first IR-page crawl attempt have both failed -- here the model's only "direct link"
            #     candidate is itself an IR page with nothing on it, so the first crawl genuinely runs
            #     and finds nothing; the second, more targeted ask then names the real reports page,
            #     and exactly two model calls happen in total (never a third)
            dest9 = tmp / "reports9"
            calls_before_16 = len(fake.calls)
            empty_ir_url = _url(base, EMPTY_IR_PAGE_PATH)
            os.environ["FAKE_WEB_REPLY"] = _reply([{"url": empty_ir_url, "title": "IR", "reason": "no direct pdf found"}])
            os.environ["FAKE_WEB_REPLY_IR_PAGE"] = _reply([{"url": hop_index_url, "title": "Investor relations", "reason": "archive page"}])
            entry9 = fetch.fetch_report(COMPANY, YEAR, dest9)
            assert entry9["source_url"] == good_url and entry9["note"] == "IR page crawl", entry9
            assert entry9["tried"] == [empty_ir_url, good_url], entry9["tried"]
            assert len(fake.calls) == calls_before_16 + 2, "exactly two model calls: the direct-link ask and the IR-page ask"
            assert fake.calls[-2]["system"] == fetch.SEARCH_SYSTEM, fake.calls[-2]
            assert fake.calls[-1]["system"] == fetch.IR_PAGE_SYSTEM, fake.calls[-1]
            os.environ.pop("FAKE_WEB_REPLY_IR_PAGE", None)

            # 17. v081: when more than one model candidate downloads and validates, the complete
            #     report wins even when a summary-shaped one is listed first -- proves ranking
            #     replaced "first success wins", not just "reject the summary outright"
            dest10 = tmp / "reports10"
            summary_url = _url(base, SUMMARY_PATH)
            os.environ["FAKE_WEB_REPLY"] = _reply([
                {"url": summary_url, "title": "Annual Report Highlights 2025", "reason": "short version"},
                {"url": good_url, "title": "Annual Report 2025", "reason": "official IR pdf"},
            ])
            entry10 = fetch.fetch_report(COMPANY, YEAR, dest10)
            assert entry10["source_url"] == good_url, entry10
            assert entry10["note"] == "model search (codex)", entry10

            # 18. v081: a lone model candidate that validates but stays under the 80-page floor is
            #     still accepted (better than nothing) but flagged as a summary volume -- Nestle's
            #     real Annual Review is exactly this shape: a clean filename ("review", not any of
            #     summary/highlights/at-a-glance/short/in-brief), just short
            dest11 = tmp / "reports11"
            review_shape_url = _url(base, REVIEW_SHAPE_PATH)
            os.environ["FAKE_WEB_REPLY"] = _reply([{"url": review_shape_url, "title": "Annual Review 2025", "reason": "only option"}])
            entry11 = fetch.fetch_report(COMPANY, YEAR, dest11)
            assert entry11["source_url"] == review_shape_url, entry11
            assert entry11["note"] == "model search (codex); summary volume", entry11
            assert entry11["tags"] == ["fetched", "foreign"], entry11

            # 19. unit-level checks of the ranking helpers and the second ask's own candidate filter
            assert fetch._is_full_report("https://x/annual-report-2025.pdf", 90) is True
            assert fetch._is_full_report("https://x/annual-report-2025.pdf", 79) is False, "just under the floor"
            assert fetch._is_full_report("https://x/annual-report-highlights-2025.pdf", 200) is False, "long but summary-named"
            hits = [("https://x/short-clean.pdf", b"", "", 60),
                    ("https://x/long-highlights.pdf", b"", "", 200),
                    ("https://x/long-clean.pdf", b"", "", 90)]
            assert fetch._best_model_candidate(hits)[0] == "https://x/long-clean.pdf", \
                "only the candidate that is both long enough and cleanly named wins"
            os.environ["FAKE_WEB_REPLY_IR_PAGE"] = _reply([{"url": _url(base, "/a.pdf"), "title": "actually a pdf"}])
            ir_urls, ir_note = fetch._ir_page_candidates(COMPANY, YEAR)
            assert ir_urls == [] and ir_note is None, (ir_urls, ir_note)  # a PDF-shaped URL is dropped: this ask is for a page
            os.environ["FAKE_WEB_REPLY_IR_PAGE"] = _reply([{"url": _url(base, "/ir/page1.html")}, {"url": _url(base, "/ir/page2.html")},
                                                            {"url": _url(base, "/ir/page3.html")}])
            ir_urls, ir_note = fetch._ir_page_candidates(COMPANY, YEAR)
            assert ir_urls == [_url(base, "/ir/page1.html"), _url(base, "/ir/page2.html")], ir_urls  # capped at MAX_IR_PAGE_CANDIDATES
            os.environ.pop("FAKE_WEB_REPLY_IR_PAGE", None)

            # 20. v122 red proof, end to end: MTG's real FY2021 cover/title/contents as the first three
            #     pages of an otherwise plausible candidate (forward-looking "2025" filler after), served
            #     off the loopback server exactly like the download that put the wrong document in the KB.
            #     The old year-anywhere check registered this exact shape; the anchored check must refuse
            #     it, and the reason on the tried list must name the year the cover does name.
            os.environ.pop("LLM_PROVIDER", None)  # feeds-only: no model layer between the candidate and the year gate
            dest12 = tmp / "reports12"
            mtg_pages = _mtg_fy2021_cover_pages()  # frozen FY2021 pages; the KB stem is the FY2025 report since 8a0e784
            mtg_head = "".join(mtg_pages)
            mtg_path = "/mtg-annual-and-cr-report-2021.pdf"
            _pdf_from_page_texts(tmp / "public" / mtg_path.lstrip("/"), mtg_pages,
                                 filler_lines=["Modern Times Group revenue, operating profit and financial statements.",
                                               "Target for 2025: organic growth across our gaming portfolio.",
                                               "Modern Times Group segment performance, cash flow and balance sheet.",
                                               "Forward-looking statement: by 2025 the group expects margin expansion.",
                                               "Modern Times Group notes to the financial statements and other information.",
                                               "Strategy update: the plan for 2025 builds on the studios' strong pipelines.",
                                               "Modern Times Group corporate responsibility summary and statutory statement.",
                                               "Outlook: management expectations for 2025 and the years beyond."] * 2,
                                 filler_pages=45)
            mtg_url = _url(base, mtg_path)
            fetch._candidates = lambda company, year, job_id=None: [mtg_url]
            try:
                fetch.fetch_report("Modern Times Group", 2025, dest12)
                assert False, "expected LookupError: the FY2021 document must not pass the anchored year check"
            except LookupError as e:
                assert e.args[0] == [mtg_url, "2025 not on the first 3 pages and no accounting period for it; cover names 2021"], e.args
            assert not list(dest12.glob("*.pdf")), "the refused document must not be stored"

            # 21. the anchored rule's own shapes: the fiscal year (plain or split-year, both spellings)
            #     on the cover, or an accounting period ending in it; a bare year elsewhere never is one
            fy = fetch._fiscal_year_re(2025)
            assert fy.search("ANNUAL REPORT 2025") and fy.search("Annual Report 2024/25") and fy.search("2024/2025"), fy.pattern
            assert not fy.search("2024") and not fy.search("2026 plans"), fy.pattern
            period = fetch._period_re(2025)
            for shape in ("1 januari–31 december 2025", "1 January – 31 December 2025", "1 september 2024–31 augusti 2025",
                          "September 1, 2024–August 31, 2025", "financial year 2025", "Financial Year 2025",
                          "fiscal year 2025", "räkenskapsåret 2025"):
                assert period.search(shape), shape
            for shape in ("growth target for 2025", "by 2025 the group will", "31 december 2024", "December 31, 2024",
                          "financial year 2024", "interim report Q3 2025"):
                assert not period.search(shape), shape

            # 22. the title-year detail, both directions: MTG's real head names 2021 above the title;
            #     an earlier year with no report wording, or report wording with no earlier year, names nothing
            assert fetch._title_year(mtg_head, 2025) == "2021"
            assert fetch._title_year("Quarterly update 2021 for investors", 2025) is None
            assert fetch._title_year("Annual Report with no year on the cover", 2025) is None
            assert fetch._title_year("Årsredovisning 2023", 2025) == "2023"

            # 23. Dustin's real cover passes: its FY2025 report is exactly the split-fiscal-year shape
            #     the anchored rule must keep accepting ("September 1, 2024–August 31, 2025")
            dustin_head, _ = _kb_page_texts("dustin_2025")
            dustin_path = tmp / "public" / "dustin-annual-and-sustainability-2025.pdf"
            _pdf_from_page_texts(dustin_path, _kb_pages("dustin_2025")[:3],
                                 filler_lines=["Dustin Group revenue, operating profit and financial statements.",
                                               "Dustin Group segment performance, cash flow and balance sheet.",
                                               "Dustin Group notes to the financial statements and other information.",
                                               "Dustin Group corporate responsibility summary and statutory statement."] * 3,
                                 filler_pages=45)
            doc, text = fetch._validate(dustin_path.read_bytes(), "Dustin Group", 2025)
            assert doc is not None, text

            # 24. the escape hatch on its own: a cover whose first three pages never name the year is
            #     still accepted when an accounting period ending in the fiscal year is stated later
            #     in the text -- and refused once that statement names only the prior year (ASCII
            #     hyphen: the base-14 insertion font latin-1-mangles a dash, covered as U+2013 in 21)
            for body, want in ((["Annual and Sustainability Report", "", "Contents", "", "",
                                 "The financial year comprises 1 January - 31 December 2025."], True),
                               (["Annual and Sustainability Report", "", "Contents", "", "",
                                 "The prior financial year comprised 1 January - 31 December 2024."], False)):
                p = tmp / "public" / f"period-{'ok' if want else 'no'}.pdf"
                _pdf_from_page_texts(p, body, filler_pages=0)
                with fitz.open(p) as d:
                    assert fetch._year_ok(d, 2025) is want, (body, want)

            # 25. five random real reports from the committed corpus pass the same rule on their real
            #     page text. modern_times_2025 is in the pool like any other stem now: since 8a0e784
            #     rebuilt the entry from the real FY2025 report, its cover names 2025 and it passes
            #     the positive check -- the FY2021 defect text case 20 refuses lives on only in the
            #     fixture, not in the corpus (scripts/kb_year_audit.py is what flags any stem that
            #     still fails this rule on its stored pages)
            stems = sorted(p.name for p in KB.iterdir() if (p / "meta.json").exists())
            assert len(stems) >= 200, f"expected the committed corpus, found {len(stems)} entries"
            for stem in random.Random(122).sample(stems, 5):
                meta = json.loads((KB / stem / "meta.json").read_text(encoding="utf-8"))
                head, full = _kb_page_texts(stem)
                assert fetch._fiscal_year_re(meta["fiscal_year"]).search(head) or fetch._period_re(meta["fiscal_year"]).search(full), \
                    f"{stem}: real FY{meta['fiscal_year']} report fails the anchored year check -- audit it"

            # 26. v122 ruling follow-up: an issuer that styles itself only by its acronym is accepted
            #     when the initials of its name (at least three letters) stand whole-word on the cover
            #     -- MTG's real FY2025 report (the one that escaped into the feed) says "MTG" from
            #     page 2 and first spells "Modern Times Group" on page 41 -- while an acronym mention
            #     in the body of an unrelated report accepts nothing
            assert fetch._acronym("Modern Times Group") == "mtg"
            assert fetch._acronym("ABB Ltd") is None, "fewer than three initials survive"
            assert fetch._acronym("Atlas Copco") is None
            assert fetch._acronym("Asea Brown Boveri") == "abb"
            acr_path = tmp / "public" / "mtg-annual-and-sustainability-2025.pdf"
            _pdf_from_page_texts(acr_path,
                                 ["MTG", "Annual and Sustainability report 2025", "Content"],
                                 filler_lines=["MTG gaming studios revenue, operating profit and cash flow.",
                                               "MTG segment performance and notes to the financial statements."] * 4,
                                 filler_pages=45)
            doc, text = fetch._validate(acr_path.read_bytes(), "Modern Times Group", 2025)
            assert doc is not None, text
            body_path = tmp / "public" / "unrelated-with-mtg-in-body.pdf"
            _pdf_from_page_texts(body_path,
                                 ["Someone Else Group", "Annual and Sustainability report 2025", "Content"],
                                 filler_lines=["Someone Else Group revenue, operating profit and cash flow.",
                                               "Platform partners such as MTG deliver parts of the roadmap."] * 4,
                                 filler_pages=45)
            doc, text = fetch._validate(body_path.read_bytes(), "Modern Times Group", 2025)
            assert doc is None and "issuer mismatch" in text, text
            # the ruling's own counter-example: "ABB" in the body of a competitor's report does not
            # make that report Asea Brown Boveri's own
            abb_path = tmp / "public" / "volvo-with-abb-supplier.pdf"
            _pdf_from_page_texts(abb_path,
                                 ["Volvo Group", "Annual Report 2025", "Content"],
                                 filler_lines=["Volvo Group revenue, operating profit and cash flow.",
                                               "Electrification components come from suppliers such as ABB."] * 4,
                                 filler_pages=45)
            doc, text = fetch._validate(abb_path.read_bytes(), "Asea Brown Boveri", 2025)
            assert doc is None and "issuer mismatch" in text, text

            # 27. discover, model path: one DISCOVER_SYSTEM ask, identity fields kept per candidate, an
            #     interim-named link nulled (the entity stays), a candidate without a legal name dropped,
            #     dedupe on collection.identity ("Nestle Ltd" is the same entity as the saved "Nestle"),
            #     local first, capped at MAX_DISCOVER_CANDIDATES. `dest` holds nestle_2025.pdf from case 2.
            os.environ["LLM_PROVIDER"] = "codex"
            os.environ["KB_DIR"] = str(tmp / "kb-empty")
            calls_before_27 = len(fake.calls)
            os.environ["FAKE_WEB_REPLY"] = _reply([
                {"legal_name": "Nestle Ltd", "ticker": "NESN", "exchange": "SIX", "country": "CH", "org_number_or_lei": None,
                 "fiscal_year_end": "Dec", "document_title": "Annual Report 2025", "document_type": "Annual Report", "url": good_url, "reason": "the Swiss parent"},
                {"legal_name": "Nestle India Limited", "ticker": "NESTLEIND", "exchange": "NSE", "country": "IN", "org_number_or_lei": "L15202MH1959PLC011311",
                 "fiscal_year_end": "Mar", "document_title": "Annual Report 2024-25", "document_type": "annual report", "url": INTERIM_URL, "reason": "listed subsidiary"},
                {"legal_name": "", "url": good_url, "reason": "no name"},
                {"legal_name": "Nestle Nigeria Plc", "url": "ftp://nope", "reason": "not http"},
                {"legal_name": "Nestle Malaysia Berhad", "reason": "a"},
                {"legal_name": "Nestle Pakistan Limited", "reason": "b"},
                {"legal_name": "Nestle Lanka PLC", "reason": "c"},
            ])
            found = fetch.discover("nestle", YEAR, country="Switzerland", hint="the parent", dest_dir=dest)
            assert len(fake.calls) == calls_before_27 + 1 and fake.calls[-1]["system"] == fetch.DISCOVER_SYSTEM, fake.calls[-1]
            assert "Query: nestle" in fake.calls[-1]["user"] and "Country: Switzerland" in fake.calls[-1]["user"] and "Hint: the parent" in fake.calls[-1]["user"]
            assert found["note"] is None, found
            names = [c["legal_name"] for c in found["candidates"]]
            assert names == ["Nestle", "Nestle India Limited", "Nestle Nigeria Plc", "Nestle Malaysia Berhad", "Nestle Pakistan Limited"], names
            saved_c, india = found["candidates"][:2]
            assert saved_c["saved"] is True and saved_c["stem"] == "nestle_2025" and saved_c["url"] == good_url, saved_c
            assert saved_c["reason"] == "saved PDF in the report cache" and saved_c["document_type"] == "annual report", saved_c
            assert india["saved"] is False and india["stem"] is None and india["url"] is None, india  # interim link nulled, entity kept
            assert india["ticker"] == "NESTLEIND" and india["exchange"] == "NSE" and india["country"] == "IN", india
            assert india["org_number_or_lei"] == "L15202MH1959PLC011311" and india["fiscal_year_end"] == "Mar", india
            assert india["document_title"] == "Annual Report 2024-25" and india["document_type"] == "annual report" and india["reason"] == "listed subsidiary", india
            assert found["candidates"][2]["url"] is None, found["candidates"][2]  # ftp:// is not a link we would download
            assert set(found["candidates"][0]) == {"legal_name", "ticker", "exchange", "country", "org_number_or_lei", "fiscal_year_end",
                                                   "document_title", "document_type", "url", "reason", "saved", "stem"}

            # 28. discover, saved matches: a text-only data/kb stem counts (saved: true, its stem), only
            #     for the asked year, and the roster alias resolves ("seb" finds the bank); no model call
            #     without a search provider, the note says why; a failed model call is a note too
            kb = tmp / "kb"
            (kb / "nestle_2024").mkdir(parents=True)
            (kb / "nestle_2024" / "meta.json").write_text(json.dumps({"company": "Nestle", "fiscal_year": 2024, "source_url": None}), encoding="utf-8")
            (kb / "seb_2025").mkdir()
            (kb / "seb_2025" / "meta.json").write_text(json.dumps({"company": "Skandinaviska Enskilda Banken AB (publ)", "fiscal_year": 2025}), encoding="utf-8")
            os.environ["KB_DIR"] = str(kb)
            os.environ.pop("LLM_PROVIDER", None)
            calls_before_28 = len(fake.calls)
            found = fetch.discover("Nestle", 2024, dest_dir=dest)
            assert len(fake.calls) == calls_before_28, "no search provider: web_lookup must not run"
            assert [(c["legal_name"], c["saved"], c["stem"]) for c in found["candidates"]] == [("Nestle", True, "nestle_2024")], found
            assert found["note"] and "codex or claude" in found["note"], found
            assert fetch.discover("Nestle", 2023, dest_dir=dest)["candidates"] == []
            assert [c["stem"] for c in fetch.discover("seb", 2025, dest_dir=dest)["candidates"]] == ["seb_2025"]
            assert fetch.discover("", 2025, dest_dir=dest)["candidates"] == []
            os.environ["LLM_PROVIDER"] = "codex"
            os.environ["FAKE_WEB_REPLY"] = "raise"
            found = fetch.discover("Nestle", YEAR, dest_dir=dest)
            assert [c["stem"] for c in found["candidates"]] == ["nestle_2025"] and "429" in found["note"], found

            # 29. fetch_report(url=...): the confirmed link is downloaded and validated first -- no model
            #     call at all when it holds -- and lands with its own note; the cache filename still follows
            #     the (confirmed legal) name
            dest13 = tmp / "reports13"
            calls_before_29 = len(fake.calls)
            os.environ["FAKE_WEB_REPLY"] = "raise"
            entry13 = fetch.fetch_report(COMPANY, YEAR, dest13, url=good_url)
            assert len(fake.calls) == calls_before_29, "a confirmed url that validates must not cost a model call"
            assert entry13["source_url"] == good_url and entry13["note"] == "confirmed url" and entry13["tried"] == [good_url], entry13
            assert entry13["file"] == "nestle_2025.pdf" and entry13["tags"] == ["fetched"] and (dest13 / "nestle_2025.pdf").exists(), entry13
            review13 = fetch.fetch_report(COMPANY, YEAR, tmp / "reports13b", url=review_shape_url)
            assert review13["note"] == "confirmed url; summary volume", review13

            # 30. ...and falls through when it fails: a dead link (404) and somebody else's report (issuer
            #     mismatch) each land on the tried list, then the model's own candidate is taken as before
            dest14 = tmp / "reports14"
            os.environ["FAKE_WEB_REPLY"] = _reply([{"url": good_url, "title": "Annual Report 2025", "reason": "official IR pdf"}])
            entry14 = fetch.fetch_report(COMPANY, YEAR, dest14, url=gone_url)
            assert entry14["source_url"] == good_url and entry14["note"] == "model search (codex)", entry14
            assert entry14["tried"] == [gone_url, good_url], entry14["tried"]
            other_url = _url(base, "/unrelated-with-mtg-in-body.pdf")
            entry15 = fetch.fetch_report(COMPANY, YEAR, tmp / "reports15", url=other_url)
            assert entry15["source_url"] == good_url and entry15["tried"] == [other_url, good_url], entry15["tried"]

            # 31. v194: discover(job_id=...) records directory -> model_search -> done, with the
            #     model's suggested candidates riding on the model_search event's own data
            os.environ["FAKE_WEB_REPLY"] = _reply([
                {"legal_name": "Nestle Ltd", "ticker": "NESN", "exchange": "SIX", "country": "CH", "org_number_or_lei": None,
                 "fiscal_year_end": "Dec", "document_title": "Annual Report 2025", "document_type": "annual report", "url": good_url, "reason": "the Swiss parent"},
            ])
            found = fetch.discover("nestle", YEAR, dest_dir=dest, job_id="job-discover-1")
            job = jobs.get("job-discover-1")
            assert job["job_id"] == "job-discover-1" and job["done"] is True and job["stage"] == "done" and job["error"] is None, job
            stages = [e["stage"] for e in job["events"]]
            assert stages[:2] == ["directory", "directory"] and "model_search" in stages and stages[-1] == "done", stages
            search_events = [e for e in job["events"] if e["stage"] == "model_search"]
            assert any(e.get("data", {}).get("candidates") for e in search_events), search_events

            # 32. v194: fetch_report(job_id=...) end to end through the model-search path -- a verify
            #     event with the real page count, and a download event whose total matches the
            #     loopback server's real Content-Length (the byte-progress path actually ran, not
            #     just "did not crash")
            dest16 = tmp / "reports16"
            os.environ["FAKE_WEB_REPLY"] = _reply([{"url": good_url, "title": "Annual Report 2025", "reason": "official IR pdf"}])
            entry16 = fetch.fetch_report(COMPANY, YEAR, dest16, job_id="job-fetch-model-1")
            assert entry16["source_url"] == good_url, entry16
            job = jobs.get("job-fetch-model-1")
            assert job["done"] is True and job["stage"] == "done" and job["error"] is None, job
            stages = [e["stage"] for e in job["events"]]
            assert stages[0] == "directory" and "model_search" in stages and "verify" in stages and "download" in stages and stages[-1] == "done", stages
            verify_events = [e for e in job["events"] if e["stage"] == "verify"]
            assert any(e["text"] == f"{good_url} -> ok (90 pages)" for e in verify_events), verify_events
            download_events = [e for e in job["events"] if e["stage"] == "download"]
            real_size = (tmp / "public" / GOOD_PATH.lstrip("/")).stat().st_size
            assert download_events[-1]["data"] == {"bytes": real_size, "total": real_size}, (download_events[-1], real_size)

            # 33. v194: _get()'s own chunked-read path -- a file big enough to cross the throttle
            #     threshold produces more than the one final event, bytes increase monotonically, and
            #     the last event's bytes/total match the real file size exactly
            big_path = tmp / "public" / "big.bin"
            big_path.write_bytes(os.urandom(fetch.DOWNLOAD_CHUNK * fetch.DOWNLOAD_STEP_EVERY * 3))
            data = fetch._get(_url(base, "/big.bin"), job_id="job-get-chunks", label="big.bin")
            assert len(data) == big_path.stat().st_size
            dl = [e for e in jobs.get("job-get-chunks")["events"] if e["stage"] == "download"]
            assert len(dl) >= 2, "a large enough file must produce more than just the final event"
            assert [e["data"]["bytes"] for e in dl] == sorted(e["data"]["bytes"] for e in dl), "bytes must increase monotonically"
            assert dl[-1]["data"]["bytes"] == dl[-1]["data"]["total"] == big_path.stat().st_size, dl[-1]
            assert dl[0]["text"].startswith("downloading ") and dl[-1]["text"].startswith("downloaded "), dl

            # 34. v194: every source failing still ends with a "failed" job event carrying the same
            #     detail the /fetch route's own 404 would show
            dest17 = tmp / "reports17"
            fetch._candidates = lambda company, year, job_id=None: []  # explicit, not relying on case 20's leftover patch
            os.environ["FAKE_WEB_REPLY"] = "raise"
            try:
                fetch.fetch_report(COMPANY, YEAR, dest17, job_id="job-fetch-failed-1")
                assert False, "expected LookupError"
            except LookupError:
                pass
            job = jobs.get("job-fetch-failed-1")
            assert job["done"] is True and job["stage"] == "failed" and job["error"], job
            assert job["error"].startswith(f"no annual report found for {COMPANY} {YEAR}"), job["error"]

            # 35. v194: without a job_id, none of the above touches the jobs table at all
            before = len(jobs._jobs)
            fetch.fetch_report(COMPANY, YEAR, tmp / "reports18", url=good_url)
            assert len(jobs._jobs) == before, "a job_id-less call must not create a job"
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


def demo_candidates_events():
    """v194: _candidates() itself -- not the fetch_report()-level mock the main demo() uses throughout
    -- reports mfn -> nasdaq -> ddg in order, and its dedupe/cap computation is unchanged (same URLs,
    same order a plain `_mfn(...) + _nasdaq(...)` / `_crawl(...) + _ddg(...)` merge always produced)."""
    saved = {name: getattr(fetch, name) for name in ("_mfn", "_nasdaq", "_crawl", "_ddg")}
    try:
        fetch._mfn = lambda company, year: ["https://mfn.example/a.pdf", "https://mfn.example/b.pdf"]
        fetch._nasdaq = lambda company, year: ["https://mfn.example/b.pdf", "https://nasdaq.example/c.pdf"]  # "b" overlaps mfn: one entry, not two
        fetch._crawl = lambda company, year: ["https://crawl.example/d.pdf"]
        fetch._ddg = lambda company, year: ["https://mfn.example/a.pdf", "https://ddg.example/e.pdf"]  # "a" is already a feed: dropped from the second half
        urls = list(fetch._candidates("Acme", 2025, job_id="job-candidates-1"))
        assert urls == ["https://mfn.example/a.pdf", "https://mfn.example/b.pdf", "https://nasdaq.example/c.pdf",
                        "https://crawl.example/d.pdf", "https://ddg.example/e.pdf"], urls
        job = jobs.get("job-candidates-1")
        stages = [e["stage"] for e in job["events"]]
        assert stages == ["mfn", "nasdaq", "nasdaq", "ddg", "ddg"], stages
        assert "3 feed candidate(s)" in job["events"][2]["text"], job["events"][2]
        assert "2 more candidate(s)" in job["events"][4]["text"], job["events"][4]
    finally:
        for name, original in saved.items():
            setattr(fetch, name, original)
    print("fetch._candidates job-events self-check ok")


if __name__ == "__main__":
    demo()
    demo_candidates_events()
