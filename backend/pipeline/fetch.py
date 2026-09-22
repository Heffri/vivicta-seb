"""Find and validate a company's annual report PDF, then cache it locally.

A cached PDF is reused first. With a Codex/Claude provider, the connected model's
live web search finds report links, IR pages or registry listings before feed scraping.
A targeted IR-page follow-up is allowed (at most two model searches). Every PDF
must pass issuer, fiscal-year and report-type checks; complete reports are preferred.
MFN/Nasdaq and traditional web discovery remain fallback sources when AI search
is unavailable or cannot retrieve a valid report.
discover() runs before all of that: it resolves the typed query to concrete legal
entities (saved reports first, then one model ask) so the user confirms which
company/document is meant; fetch_report(url=...) then tries that link first.
CLI: python -m pipeline.fetch "Boliden" 2025"""
import datetime as dt
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import pymupdf as fitz

from . import collection, jobs, llm, paths, report_listing, report_period

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
MAX_TRIES = 6


class FetchAttempts(list):
    """Keep the compatible URL list plus actionable per-attempt diagnostics."""
    def __init__(self):
        super().__init__()
        self.failures = []
        self.listings = []


def _failure(tried, url, reason, kind="rejected"):
    if isinstance(tried, FetchAttempts):
        tried.failures.append({"url": url, "reason": str(reason)[:400], "kind": kind})


def failure_response(company, year, error):
    tried = error.args[0] if error.args else []
    note = error.args[1] if len(error.args) > 1 else None
    failures = getattr(tried, "failures", [])
    listings = getattr(tried, "listings", [])
    if listings:
        code, status = "report_listed", 409
        detail = f"An annual report for {company} {year} is listed online, but its PDF could not be downloaded and verified automatically. Open the report listing to obtain the PDF, then upload it."
    elif note:
        code, status = "search_unavailable", 502
        detail = f"Report search could not complete for {company} {year}. {note}"
    elif any(f["kind"] == "download" for f in failures):
        code, status = "download_failed", 502
        detail = f"No report could be downloaded and verified for {company} {year}. Some source sites failed or blocked access; this does not mean the report is unpublished."
    else:
        code, status = "report_unavailable", 404
        detail = f"Automatic lookup did not find a verified annual-report PDF or listing for {company} {year}. This does not establish whether the company publishes an annual report."
    return status, {"detail": detail, "code": code, "tried": tried, "attempts": failures, "listings": listings}


NOT_AR = re.compile(r"general meeting|st[äa]mma|notice|kallelse|nomination|valberedning|20-f|interim|delårs|quarter", re.I)
IS_AR = re.compile(r"annual|[åa]rsredovisning|[åa]rs-?\s*och", re.I)
# a PDF that is not *the* annual report even though the search matched: Nordea's Pillar 3 report, AGM decks, quarterlies
BAD_URL = re.compile(r"interim|q[1-4]\b|quarter|delars|half-?year|risk|pillar|remuneration|ersattning|sustainab|hallbarhet|governance|bolagsstyrning|presentation|agm|stamma|prospect", re.I)
NOT_REPORT = re.compile(r"capital and risk management|pillar 3|remuneration report|sustainability (report|statement)|corporate governance report|prospectus|interim report|half-year|year-end report|bokslutskommunik", re.I)

# ---- fourth source (v074): the model's own web search, after feeds + crawl + DDG are exhausted ----

MAX_MODEL_CANDIDATES = 3  # each one still goes through the same download + validation as every other source
SEARCH_SCHEMA = {  # codex/claude ignore the schema (llm.py); it states the reply shape the prompt asks for
    "type": "object",
    "properties": {"candidates": {"type": "array", "items": {"type": "object", "properties": {
        "url": {"type": "string"}, "title": {"type": "string"}, "reason": {"type": "string"}}}}},
    "required": ["candidates"],
}
SEARCH_SYSTEM = (
    "You are locating a company's official annual report PDF using web search. Reply with JSON only, no prose: "
    '{"candidates": [{"url": "https://...", "title": "...", "reason": "..."}]}. '
    "Rules: at most 3 candidates, best first; every URL must be a direct link to the annual report PDF itself for "
    "the stated fiscal year. Prefer the company's own investor-relations site or an official regulatory filing "
    "repository; reputable registry mirrors are also acceptable. Exclude ESEF/xBRL zip packages, interim or quarterly reports, sustainability, remuneration, "
    "governance or capital-markets reports, and press releases. Prefer the complete annual report (the full "
    "document), not a summary, highlights, at-a-glance, or annual review excerpt. If you cannot find a direct PDF "
    "link, a URL for the company's investor-relations or annual-report page is also acceptable. "
    "Also search reputable company-information services and registry mirrors for this exact legal entity's "
    "annual accounts. A company-specific listing page for the requested year is useful even if downloading "
    "requires browser verification, login or payment. Return that listing URL; never invent a direct PDF URL."
)
# ---- second ask (v081): only after every fourth-source candidate and the fifth source's generic IR-path
# guesses have both failed -- ask once more, this time only for the IR/annual-report-archive page itself ----
MAX_IR_PAGE_CANDIDATES = 2
IR_PAGE_SYSTEM = (
    "A direct link to the company's official annual report PDF could not be found or downloaded. Reply with JSON "
    'only, no prose: {"candidates": [{"url": "https://...", "title": "...", "reason": "..."}]}. '
    "Rules: at most 2 candidates, best first; every URL must be an HTML page, never a PDF. Search the company's "
    "own report archive AND reputable registry/company-information services (for example Hitta or a country's "
    "corporate filing service). Prefer a company-specific page explicitly listing the requested year's annual "
    "report or statutory accounts. Include listings even when downloading requires browser verification, login "
    "or payment. Check the legal entity, not its parent or a similarly named subsidiary. Do not infer that no "
    "report exists just because there is no direct PDF link."
)
# the complete-report preference (v081): Nestle's real Annual Review is 67p, well under this floor; a summary/
# highlights/at-a-glance/short/in-brief excerpt is accepted only when nothing among the candidates clears it
FULL_REPORT_MIN_PAGES = 80
SUMMARY_WORDS = re.compile(r"\bsummary\b|highlights|at[-_ ]a[-_ ]glance|\bshort\b|in[-_ ]brief", re.I)

# ---- discover: resolve a typed fragment to concrete legal entities *before* anything is downloaded ----
# The typed text used to be the identity end to end (cache filename, index.json company, Results header) and
# the model's title/reason were dropped in _model_candidates. discover() keeps them: saved reports first (no
# model call), then one web-search ask; the user confirms one card and fetch_report(url=...) takes its link first.

MAX_DISCOVER_CANDIDATES = 5
DISCOVER_SCHEMA = {  # codex/claude ignore the schema (llm.py); it states the reply shape the prompt asks for
    "type": "object",
    "properties": {"candidates": {"type": "array", "items": {"type": "object", "properties": {
        "legal_name": {"type": "string"}, "ticker": {"type": ["string", "null"]}, "exchange": {"type": ["string", "null"]},
        "country": {"type": ["string", "null"]}, "org_number_or_lei": {"type": ["string", "null"]},
        "fiscal_year_end": {"type": ["string", "null"]}, "document_title": {"type": ["string", "null"]},
        "document_type": {"type": ["string", "null"]}, "url": {"type": ["string", "null"]}, "reason": {"type": "string"}},
        "required": ["legal_name", "ticker", "exchange", "country", "org_number_or_lei", "fiscal_year_end",
                     "document_title", "document_type", "url", "reason"]}}},
    "required": ["candidates"],
}
DISCOVER_SYSTEM = (
    "You are resolving a company query to concrete legal entities and locating each one's official annual report "
    "PDF using web search. Reply with JSON only, no prose: "
    '{"candidates": [{"legal_name": "...", "ticker": "...", "exchange": "...", "country": "...", '
    '"org_number_or_lei": "...", "fiscal_year_end": "...", "document_title": "...", "document_type": "...", '
    '"url": "https://...", "reason": "..."}]}. '
    "Rules: at most 5 distinct legal entities matching the query, most likely first. A query like 'intel' is a "
    "fragment -- resolve it to legal entities (Intel Corporation), never echo the fragment as a company. "
    "legal_name is the registered name; ticker and exchange as listed (INTC, NASDAQ); country as an ISO 3166-1 "
    "alpha-2 code; org_number_or_lei the registration number or LEI; fiscal_year_end the month the fiscal year "
    "ends (Dec); document_title the report's own title for the stated fiscal year; document_type one of "
    '"annual report", "10-K", "20-F", "annual and sustainability report". url is a direct link to that '
    "document's PDF, preferably hosted on the company's own investor-relations site or an official regulatory filing "
    "repository; reputable registry mirrors are also acceptable. Use null when no source is known; exclude ESEF/xBRL zip packages, interim or quarterly reports, "
    "sustainability, remuneration, governance or capital-markets reports, and press releases. Prefer the complete "
    "annual report, not a summary, highlights, at-a-glance, or annual review excerpt. Unknown fields are null, "
    "never guessed. If no direct PDF is found, url may instead be the exact company's annual-account listing "
    "on a reputable registry or company-information service; explain that it is a listing in reason."
)


HISTORICAL_SEARCH = (
    " Treat the requested year as the FISCAL period, not the publication/filing year. "
    "Search historical archives and financial-results pages, including filings published the following year. "
    "Recognize Form 10-K, 20-F and 40-F, including PDF links with numeric filenames. "
    "Use alternate official issuer-hosted copies when a regulator blocks downloads. "
    "Prefer that year's standalone annual report. If it does not exist (for example before an IPO), "
    "a registration statement (S-1/F-1 or prospectus) containing this exact issuer's audited annual "
    "balance sheet AND income statement for the requested year is an acceptable fallback. "
    "Label that fallback explicitly as a registration statement with historical audited accounts in "
    "the title/reason/document_type, never as an annual report. Do not use reserve attestations, "
    "interim accounts, another entity's accounts, or assume a year exists merely from comparisons. "
    "Failure to find or download a source does not prove it was never published."
)
SEARCH_SYSTEM += HISTORICAL_SEARCH
DISCOVER_SYSTEM += HISTORICAL_SEARCH
IR_PAGE_SYSTEM += HISTORICAL_SEARCH


def websearch_provider() -> "str | None":
    """The CLI provider a model search may use, or None: only codex/claude have a web-search tool
    (llm.web_lookup raises for anything else), so an openai/fixture backend never reaches level 4."""
    try:
        p = llm.provider()
    except ValueError:
        return None
    return p if p in ("codex", "claude") else None


def _filename_clear(label, *patterns):
    """True if none of `patterns` (BAD_URL, NOT_REPORT) should reject `label`, once a hit in its last
    path segment -- the actual filename -- is treated as decisive: a hit *earlier* in the path is
    ignored when the filename itself names an annual report (IS_AR) and is not itself flagged (Shell's
    real annual-report PDF sits under a "sustainability/reporting-centre" IR section; BAD_URL's
    "sustainab" term matches that section name, not the file, which is plainly shell-annual-report-
    2025.pdf). A hit *in* the filename itself (interim-q3.pdf) still rejects outright, wherever it sits."""
    label = urllib.parse.unquote(label)
    fname = label.rsplit("/", 1)[-1].split("?", 1)[0]
    # A combined annual report legitimately includes sustainability/governance chapters.
    # Keep rejecting stand-alone topic reports, interim statements and meeting notices.
    if re.search(r"annual[-_\s]+(?:(?:and|&)[-_\s]+sustainability[-_\s]+)?report|[åa]rsredovisning", fname, re.I):
        fname = re.sub(r"sustainab\w*|h[åa]llbarhet\w*|(?:corporate[-_\s]+)?governance|bolagsstyrning", "", fname, flags=re.I)
    if any(p.search(fname) for p in patterns):
        return False
    if IS_AR.search(fname):
        return True
    return not any(p.search(label) for p in patterns)


def _collection_context(company):
    member = collection.member(company)
    if not member:
        return ""
    context = f"\nCompany context: {member[0]} in the Wallenberg collection ({member[1]}). "
    if metadata := collection.report_metadata(company):
        context += (f"This holding is also discussed inside "
                    f"{metadata['reports_in']}'s annual report. ")
    return context + "Find this entity's own accounts, not a similarly named business or the owner's report."


def _candidate_clear(url, title):
    # Publishers sometimes call a combined annual report simply sustainability-report.pdf.
    # A search result's explicit title lets it reach content validation, never bypass it.
    combined = re.search(r"annual\s+(?:and|&)\s+sustainability\s+report", title, re.I)
    hard_topic = re.search(r"interim|q[1-4]\b|quarter|delars|half-?year|pillar|prospect|agm|stamma", urllib.parse.unquote(url), re.I)
    registration = re.search(r"registration statement|prospectus|\b[SF]-1\b", title, re.I)
    registration_url = re.sub("prospect", "", url, flags=re.I) if registration else url
    return _filename_clear(registration_url, BAD_URL) or bool(combined and not hard_topic)


def _model_candidates(company, year, country=None, hint=None, job_id=None):
    """Ask the model for official annual-report PDF links. (urls, note): at most MAX_MODEL_CANDIDATES
    cleaned URLs, best first, plus a short note for the eventual 404 detail -- the model being
    unavailable or replying with something unparseable is not the same thing as "no links found".
    job_id (v194) rides through to llm.web_lookup, which surfaces the web_search tool's own query
    terms as job-progress events while this call runs (codex only; see llm._codex_search_events)."""
    user = f"Company: {company}\nFiscal year: {year}" + _collection_context(company)
    if country:
        user += f"\nCountry: {country}"
    if hint:
        user += f"\nHint: {hint}"
    try:
        data = json.loads(llm.web_lookup(SEARCH_SYSTEM, user, SEARCH_SCHEMA, job_id=job_id))
        if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
            raise ValueError("invalid response shape: expected an object with a candidates array")
    except Exception as e:  # the CLI's RuntimeError, a timeout, or bad JSON -- one clear note either way
        print(f"model search failed: {e}")
        return [], f"model search ({llm.provider()}) failed: {str(e)[:200]}"
    urls = []
    for c in (data.get("candidates") or [])[:MAX_MODEL_CANDIDATES]:
        u = str(c.get("url", "")).strip() if isinstance(c, dict) else ""
        if not u.startswith(("http://", "https://")) or not _candidate_clear(u, str(c.get("title", ""))):
            print(f"model candidate dropped: {u!r}")  # not a direct link, or an interim/risk/AGM URL by name
            continue
        urls.append(u)
        # models hand back percent-encoded paths (Siemens' asset API: uuid%3A... -> 400s); the decoded
        # twin is a free second try for servers that only accept the raw characters
        if (dec := urllib.parse.unquote(u)) != u and _filename_clear(dec, BAD_URL):
            urls.append(dec)
    return urls, None


def _ir_page_candidates(company, year, country=None, hint=None, job_id=None):
    """The second model ask (v081): (urls, note) like _model_candidates, but only ever called once
    every fourth-source candidate and the fifth source's own generic IR-path guesses have already
    failed, asking for an issuer archive or company-specific registry listing -- never a PDF --
    so v080's crawl (_ir_page_report) has a page the model actually named instead of only a guessed
    generic path. At most MAX_IR_PAGE_CANDIDATES URLs; a candidate that is itself a PDF is dropped,
    since that is exactly what the first ask already tried and failed at. job_id: see _model_candidates."""
    user = f"Company: {company}\nFiscal year: {year}" + _collection_context(company)
    if country:
        user += f"\nCountry: {country}"
    if hint:
        user += f"\nHint: {hint}"
    try:
        data = json.loads(llm.web_lookup(IR_PAGE_SYSTEM, user, SEARCH_SCHEMA, job_id=job_id))
        if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
            raise ValueError("invalid response shape: expected an object with a candidates array")
    except Exception as e:
        print(f"model IR-page search failed: {e}")
        return [], f"IR-page search ({llm.provider()}) failed: {str(e)[:200]}"
    urls = []
    for c in (data.get("candidates") or [])[:MAX_IR_PAGE_CANDIDATES]:
        u = str(c.get("url", "")).strip() if isinstance(c, dict) else ""
        if not u.startswith(("http://", "https://")) or u.lower().split("?", 1)[0].endswith(".pdf"):
            print(f"model IR-page candidate dropped: {u!r}")  # not a link, or a PDF instead of a page
            continue
        urls.append(u)
    return urls, None


def _candidate(legal_name, **kw):
    """One discover candidate in the docs/API.md shape; identity fields are model-reported unless `saved`."""
    c = {"legal_name": str(legal_name).strip(), "ticker": None, "exchange": None, "country": None, "org_number_or_lei": None,
         "fiscal_year_end": None, "document_title": None, "document_type": None, "url": None, "reason": "", "saved": False, "stem": None}
    c.update(kw)
    return c


def _str(v):
    return (str(v).strip() or None) if v is not None else None


class NoStandaloneReport(LookupError):
    """A curated holding is disclosed in its parent report, not as a fetchable issuer report."""


def private_report_note(metadata):
    """User-facing availability fact shared by discover and fetch; never an AI-search failure."""
    note = f"Private company — reported inside {metadata['reports_in']}'s annual report ({metadata['collection_group']})"
    return note if metadata.get('report_stem') else note + "; the parent report is not saved locally"


def _saved_name_key(name):
    """The report-cache spelling used for an exact saved-report identity -- keep this aligned with the
    filename normalisation in `_name`/`slugify`, rather than treating a search prefix as a company."""
    return slugify(_name(str(name))) if name else ""


def _identifier(value):
    """Case/format-insensitive exact comparison for ticker, ISIN, or a stored legal identifier."""
    return re.sub(r"[^a-z0-9]", "", str(value).casefold()) if value else ""


def _directory_identifiers():
    """Directory identifiers keyed by its own normalised name and collection identity. Reports/index.json
    predates ticker/ISIN fields, so the company catalogue supplies them for an otherwise bare saved entry."""
    try:
        rows = json.loads(paths.companies_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        ids = {_identifier(row.get(k)) for k in ("ticker", "isin", "org_number_or_lei")}
        out.append((_saved_name_key(row["name"]), collection.identity(row["name"]), ids - {""}, _str(row.get("ticker"))))
    return out


def _saved_identifiers(company, row, directory):
    """Identifiers written with the saved row plus matching directory metadata. The collection identity
    bridge is only to look up a catalogued ticker/ISIN (for example the bank's long legal name -> SEB),
    never a fuzzy query match."""
    name_key, identity = _saved_name_key(company), collection.identity(company or "")
    identifiers = {_identifier(row.get(k)) for k in ("ticker", "isin", "org_number_or_lei")}
    ticker = _str(row.get("ticker"))
    for directory_name, directory_identity, directory_ids, directory_ticker in directory:
        if directory_name == name_key or directory_identity == identity:
            identifiers.update(directory_ids)
            ticker = ticker or directory_ticker
    return identifiers - {""}, ticker


def _local_candidates(query, year, dest_dir):
    """Deterministic saved reports for `year`: normalised company name equality, or exact ticker/ISIN.
    The report cache comes first, then data/kb text-only stems. A prefix is intentionally not a match:
    ambiguity must continue to model-backed web discovery unless the user explicitly overrides a saved hit."""
    query_name, query_identifier = _saved_name_key(query), _identifier(query)
    if not query_name and not query_identifier:
        return []
    rows = [(Path(e["file"]).stem, e.get("company"), e.get("fiscal_year"), e.get("source_url"), "saved PDF in the report cache", e)
            for e in _load_index(dest_dir) if (dest_dir / e["file"]).exists()]
    for p in sorted(paths.kb_dir().glob("*/meta.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append((p.parent.name, m.get("company"), m.get("fiscal_year"), m.get("source_url"), "saved page text in the knowledge base", m))
    directory = _directory_identifiers()
    out, seen = [], set()
    for stem, company, fy, url, reason, row in rows:
        key = _saved_name_key(company)
        identifiers, ticker = _saved_identifiers(company, row, directory)
        if fy != year or not key or key in seen or not (query_name == key or query_identifier in identifiers):
            continue
        seen.add(key)
        out.append(_candidate(company, ticker=ticker, document_type=row.get("document_type") or "annual report", url=url,
                              reason=row.get("source_notice") or reason, saved=True, stem=stem))
    return out


def _model_discover(query, year, country=None, hint=None, job_id=None):
    """The one discover model call: (candidates, note) like _model_candidates, but every candidate is a legal
    entity with its identity fields kept. A link that is not http(s) or is interim/risk/AGM-named (BAD_URL) is
    nulled, not the whole candidate -- fetch_report searches for that entity itself when url is null.
    job_id: see _model_candidates."""
    user = f"Query: {query}\nFiscal year: {year}" + _collection_context(query)
    if country:
        user += f"\nCountry: {country}"
    if hint:
        user += f"\nHint: {hint}"
    try:
        data = json.loads(llm.web_lookup(DISCOVER_SYSTEM, user, DISCOVER_SCHEMA, job_id=job_id))
        if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
            raise ValueError("invalid response shape: expected an object with a candidates array")
    except Exception as e:  # the CLI's RuntimeError, a timeout, or bad JSON -- one clear note either way
        print(f"model discover failed: {e}")
        return [], f"model search ({llm.provider()}) failed: {str(e)[:200]}"
    out = []
    for c in (data.get("candidates") or []):
        if not isinstance(c, dict) or not _str(c.get("legal_name")):
            continue
        u = _str(c.get("url"))
        if u and (not u.startswith(("http://", "https://")) or not _candidate_clear(u, str(c.get("document_title", "")))):
            print(f"model candidate link dropped: {u!r}")
            u = None
        out.append(_candidate(c["legal_name"], ticker=_str(c.get("ticker")), exchange=_str(c.get("exchange")),
                              country=_str(c.get("country")), org_number_or_lei=_str(c.get("org_number_or_lei")),
                              fiscal_year_end=_str(c.get("fiscal_year_end")), document_title=_str(c.get("document_title")),
                              document_type=_str(c.get("document_type")) or None, url=u, reason=_str(c.get("reason")) or ""))
    return out, None


def discover(company: str, year: int, country: "str | None" = None, hint: "str | None" = None, dest_dir: "Path | None" = None,
            job_id: "str | None" = None, force_web: bool = False) -> dict:
    """{"candidates": [...], "note": str | None}: which legal entities a typed query could mean, for the user to
    confirm one before any download. A deterministic saved report (normalised name equality or exact
    ticker/ISIN) returns immediately with no model call. `force_web=True` is the analyst's explicit
    override; otherwise an uncertain/missing local match gets one web-search ask for up to
    MAX_DISCOVER_CANDIDATES distinct entities with their official report PDF URL for the year when known.
    Dedupe is collection.identity, not a bare casefold, so a saved "ABB" and the model's "ABB Ltd"
    are one card.

    job_id (v194, optional): reports the directory/model_search stages, the model's own query terms
    and candidate names, and a final done event to pipeline.jobs -- a no-op when job_id is None."""
    dest_dir = Path(dest_dir) if dest_dir is not None else paths.reports_dir()
    if (private := collection.report_metadata(company)) and private.get("no_standalone_report"):
        # A name occurrence in a parent report is not evidence that the subsidiary issued that
        # report. Do not let a model turn the parent PDF into a confirmed child-company candidate.
        note = private_report_note(private)
        jobs.step(job_id, "directory", note)
        jobs.step(job_id, "done", "private holding; parent report only")
        return {"candidates": [], "note": note, "source": "saved", "skipped_web_search": True}
    jobs.step(job_id, "directory", f"checking saved reports for {company} ({year})")
    local = _local_candidates(company, year, dest_dir)
    if local and not force_web:
        jobs.step(job_id, "directory", f"{len(local)} saved match(es); saved report found, web search skipped")
        jobs.step(job_id, "done", f"{len(local)} saved candidate(s)")
        return {"candidates": local, "note": None, "source": "saved", "skipped_web_search": True}
    jobs.step(job_id, "directory", f"{len(local)} saved match(es); searching the web anyway" if local else "no saved match")
    found, note = [], None
    if websearch_provider():
        jobs.step(job_id, "model_search", "asking the connected model to search the web")
        found, note = _model_discover(company, year, country, hint, job_id=job_id)
        jobs.step(job_id, "model_search", f"model suggested {len(found)} entit{'y' if len(found) == 1 else 'ies'}" if found else (note or "model suggested nothing"),
                 candidates=[{"legal_name": c["legal_name"], "url": c["url"]} for c in found])
    else:
        note = "web search needs a codex or claude provider (Settings); only saved reports are listed"
        jobs.step(job_id, "model_search", note)
    out, seen = [], set()
    for c in local + found:
        key = collection.identity(c["legal_name"])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    out = out[:MAX_DISCOVER_CANDIDATES]
    jobs.step(job_id, "done", f"{len(out)} candidate(s)")
    return {"candidates": out, "note": note, "source": "web", "skipped_web_search": False}


def _label_clean(url):
    """True unless the URL's own filename reads like a summary/highlights/at-a-glance/short/in-brief
    excerpt (v081) -- the model's title isn't kept past this call, so the filename is what's left to
    check once every candidate has already downloaded and validated as a real annual report."""
    fname = url.rsplit("/", 1)[-1].split("?", 1)[0]
    return not SUMMARY_WORDS.search(fname)


def _is_full_report(url, pages):
    """The complete-report bar itself (v081): both the page-count floor and a clean filename."""
    return pages >= FULL_REPORT_MIN_PAGES and _label_clean(url)


def _best_model_candidate(hits):
    """hits: (url, data, text, pages) for every model candidate that downloaded and validated.
    Rank by (clears the full-report bar, a clean filename, page count) and take the first -- a
    summary volume is only kept when nothing in `hits` clears the bar (Nestle's real Annual Review,
    67p with an otherwise clean filename, is exactly that case)."""
    return max(hits, key=lambda h: (getattr(h[2], "metadata", {}).get("document_type") != "registration_statement", h[3] >= FULL_REPORT_MIN_PAGES, _label_clean(h[0]), h[3]))


DOWNLOAD_CHUNK = 65536      # bytes read per socket call once job_id opts into progress events
DOWNLOAD_STEP_EVERY = 8     # ~512 KB between events -- enough to show movement on a 50+ MB PDF, not a flood


def _get(url, timeout=60, job_id=None, label=None):
    """job_id (v194, optional): streams the read in DOWNLOAD_CHUNK pieces and reports "download"
    progress (bytes so far, total -- total is None when the server sends no Content-Length) every
    DOWNLOAD_STEP_EVERY chunks, plus one final event with the true total read. Every existing call
    site (job_id left unset) still does one unbuffered r.read(), byte for byte as before."""
    # Keep existing escapes/signatures intact while encoding raw spaces and Unicode paths.
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if not job_id:
            return r.read()
        total = r.headers.get("Content-Length")
        total = int(total) if total and total.isdigit() else None
        chunks, read, n = [], 0, 0
        while chunk := r.read(DOWNLOAD_CHUNK):
            chunks.append(chunk)
            read += len(chunk)
            n += 1
            if n % DOWNLOAD_STEP_EVERY == 0:
                jobs.step(job_id, "download", f"downloading {label or url}", bytes=read, total=total)
        jobs.step(job_id, "download", f"downloaded {label or url}", bytes=read, total=total)
        return b"".join(chunks)


def _unzip(data):
    """Some issuers wrap the ESEF filing package around nothing but the report PDF (SkiStar): pull it out if so."""
    if not data.startswith(b"PK"):
        return data
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        pdfs = [n for n in z.namelist() if n.lower().endswith(".pdf")]
        if pdfs:
            return z.read(max(pdfs, key=lambda n: z.getinfo(n).file_size))  # biggest: the report, not a cover/appendix
    except Exception as e:
        print(f"zip extract failed: {e}")
    return data


def _fold(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()  # "Industrivärden" -> "industrivarden"


def slugify(name):
    name = re.sub(r"\(publ\)|\bAB\b|\bLtd\.?\b|\bplc\b|\bGroup\b|\bCompany\b|\bser\.? ?[A-D]\b|\s[A-D]$", "", name, flags=re.I)  # "ABB Ltd"/"Telia Company" -> curated stems
    return re.sub(r"[^a-z0-9]+", "_", _fold(name)).strip("_")


def _name(company):
    return re.sub(r"(?<!\S)[^\s.]{1,4}\.(?=\s)", "", company).strip()  # Nasdaq's list abbreviates: "Fast. Balder", "Sv. Handelsbanken"


def _toks(company):
    """The name's identifying words, at most two: "Lundin Gold" is not Lundin Mining, "Volvo Car" is not Volvo."""
    toks = [t for t in slugify(_name(company)).split("_") if len(t) >= 3 and t not in ("holding", "holdings", "corp", "corporation", "international", "aktiebolag", "aktiebolaget", "the", "and")]
    return toks[:2] or [company.lower()]


def _acronym(company):
    """The name's initials as one word, when at least three letters survive ("Modern Times Group"
    -> "mtg"): how a report that styles itself only by the acronym -- MTG's FY2025 annual and
    sustainability report says "MTG" from page 2 and first spells the full name on page 41 -- can
    still prove whose it is. Legal suffixes never contribute; None below three letters
    ("ABB Ltd" -> "a", "Atlas Copco" -> "ac"). data/companies.json carries no alias/former-name
    field today, so the acronym is the one name the issuer check accepts beyond the full one."""
    stem = _fold(re.sub(r"\(publ\)|\bLtd\b|\bplc\b|\bAB\b", "", company, flags=re.I))
    acr = "".join(w[0] for w in re.split(r"[^a-z]+", stem) if w)
    return acr if len(acr) >= 3 else None


def _year_re(year):
    return re.compile(rf"\b{year}\b|\b{year - 1}/{year % 100}\b")  # SkiStar's "Annual Report 2024/25" is the FY2025 report


# ---- v122: the year check is anchored to the cover/first pages and the accounting period ----
# "the year anywhere in the text" let MTG's FY2021 Annual and CR Report through as modern_times_2025:
# 122 of its 148 pages say 2021, and its only "2025" mentions are six pages of forward-looking targets.

_PERIOD_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december"
                  "|januari|februari|mars|maj|juni|juli|augusti|oktober")
TITLE_YEAR_MARK = "; cover names "  # _year_reason's detail when an earlier year titles the cover -- kept on the tried list
_TITLE_WORDS = re.compile(r"annual[\w\s&-]*report|årsredovisning", re.I)


def _fiscal_year_re(year):
    """_year_re plus the full "2024/2025" split-year form -- feed titles shorten it, covers print both."""
    return re.compile(rf"{_year_re(year).pattern}|\b{year - 1}\s*/\s*{year}\b")


def _period_re(year):
    """An accounting period ending in `year`, the wordings issuers actually print: a dated range
    ("1 januari–31 december 2025", Dustin's English "September 1, 2024–August 31, 2025") or a named
    fiscal year ("financial year 2025", "räkenskapsåret 2025"). A bare year elsewhere never matches."""
    y, m, dash = str(year), _PERIOD_MONTHS, "[–—−-]"
    return re.compile(
        rf"\b\d{{1,2}}\s+(?:{m})(?:\s+\d{{4}})?\s*{dash}\s*\d{{1,2}}\s+(?:{m})\s+{y}\b"     # 1 januari–31 december 2025
        rf"|(?:{m})\s+\d{{1,2}},?\s*(?:\d{{4}})?\s*{dash}\s*(?:{m})\s+\d{{1,2}},?\s*{y}\b"  # September 1, 2024–August 31, 2025
        rf"|\b(?:financial|fiscal) year {y}\b"
        rf"|\bräkenskapsåret {y}\b", re.I)


def _head_text(doc, page_texts=None):
    """The first three pages -- cover, title page, contents: where a report names its own year."""
    return "".join(page_texts[:3]) if page_texts is not None else "".join(doc[i].get_text() for i in range(min(3, doc.page_count)))


def _title_year(head, year):
    """An earlier year standing alone on a report-titled cover ("Annual Report 2021", or MTG's
    year-above-the-title layout), or None -- the detail that explains a v122 rejection: in such a
    document the target year typically appears only in forward-looking text, which is exactly how
    the old year-anywhere check was satisfied."""
    if not _TITLE_WORDS.search(head):
        return None
    older = [int(m.group(0)) for m in re.finditer(r"\b(?:19|20)\d{2}\b", head) if int(m.group(0)) < year]
    return str(max(older)) if older else None


def _year_ok(doc, year, page_texts=None):
    """v122: is this plausibly the fiscal-`year` report? The year itself -- or the split-year
    "2024/25" / "2024/2025" cover shape -- must sit on the first three pages (cover, title page,
    contents), or an accounting period ending in the year must be stated anywhere in the text.
    A mere mention on some later page no longer passes: MTG's FY2021 report slipped through the
    old year-anywhere check on six forward-looking "2025" target mentions."""
    declared = report_period.declared_year(_head_text(doc, page_texts))
    if declared is not None:
        return declared == year
    if _fiscal_year_re(year).search(_head_text(doc, page_texts)):
        return True
    return bool(_period_re(year).search("".join(page_texts) if page_texts is not None else "".join(doc[i].get_text() for i in range(doc.page_count))))


def _year_reason(doc, year, page_texts=None):
    """The v122 rejection reason for a PDF _year_ok refused (None when it passes). When the first
    three pages title the report with an earlier year, the reason names it: that is a corpus-defect
    finding worth keeping on the tried list, not just another candidate miss."""
    declared = report_period.declared_year(_head_text(doc, page_texts))
    if declared is not None and declared != year:
        return f"fiscal-year mismatch: requested {year}, document reports {declared}" + TITLE_YEAR_MARK + str(declared)
    if _year_ok(doc, year, page_texts):
        return None
    ty = _title_year(_head_text(doc, page_texts), year)
    return f"{year} not on the first 3 pages and no accounting period for it" + (TITLE_YEAR_MARK + ty if ty else "")


def _mfn_slugs(company):
    """Matching MFN company-feed slugs, best-named first: "PPI Public Property Invest" is filed under its own name only
    when searched without the "PPI" acronym prefix, and its actual report sits under a second, differently-named hit
    ("Public Property Invest ASA", the Norwegian parent) — so every hit that names at least one token is a candidate."""
    q, toks, hits = urllib.parse.quote, _toks(company), {}
    queries = (company, " ".join(company.split()[1:]), " ".join(toks))
    for query in dict.fromkeys(w for w in queries if w):
        try:
            found = json.loads(_get(f"https://mfn.se/search/companies?limit=5&query={q(query)}"))
        except Exception as e:
            print(f"mfn company search failed: {e}")
            continue
        for h in found:
            if any(t in _fold(h.get("name", "")) for t in toks):
                hits[h["slug"]] = h
    return [h["slug"] for h in sorted(hits.values(), key=lambda h: -sum(t in _fold(h["name"]) for t in toks))]


def _mfn_items(slug, year):
    """Matching-item (IS_AR, right year) feed entries for a company slug, most recent query first."""
    items, q = [], urllib.parse.quote
    for query in (f"annual report {year}", f"årsredovisning {year}"):
        try:
            items += json.loads(_get(f"https://mfn.se/all/a/{slug}.json?limit=30&query={q(query)}"))["items"] or []
        except Exception as e:
            print(f"mfn feed failed: {e}")
    yr = _year_re(year)
    return [it for it in items if IS_AR.search(it["content"]["title"]) and not NOT_AR.search(it["content"]["title"]) and yr.search(it["content"]["title"])]


def _mfn(company, year):
    for slug in _mfn_slugs(company)[:2]:
        if urls := _mfn_feed(slug, year):
            return urls
    return []


def _mfn_feed(slug, year):
    scored = []
    for it in _mfn_items(slug, year):
        for a in it["content"].get("attachments", []):
            u, ct = a["url"], a.get("content_type", "")
            is_pdf, is_zip = ct == "application/pdf" or u.lower().endswith(".pdf"), ct in ("application/zip", "application/x-zip-compressed") or u.lower().endswith(".zip")
            if not (is_pdf or is_zip):
                continue
            s = (it["properties"].get("lang") == "en") * 2 - ("/Public/" in u) * 3 - 2 * is_zip  # release PDF, not the report; zip needs unwrapping, try plain PDFs first
            s += 2 * bool(re.search(rf"annual|ar|{year}", u.rsplit("/", 1)[-1], re.I))
            scored.append((s, u))
    return [u for _, u in sorted(scored, key=lambda x: -x[0])]


def _mfn_pages(company, year):
    """Same-domain, non-PDF links inside matching MFN releases: the release text often points at the issuer's own IR
    page rather than attaching the report PDF directly (Lundin Gold's "Publishes 2025 Annual Report" release attaches
    only its own 2-page release text; the actual report lives one click away, on lundingold.com)."""
    toks = _toks(company)
    out = []
    for slug in _mfn_slugs(company)[:2]:
        for it in _mfn_items(slug, year):
            for href in re.findall(r'https?://[^\s"<>]+', it["content"].get("html", "") or it["content"].get("text", "")):
                if ".pdf" not in href.lower() and any(t in urllib.parse.urlparse(href).netloc for t in toks) and href not in out:
                    out.append(href)
    return out


def _nasdaq(company, year):
    """Nasdaq Nordic company news: every listed issuer's "Annual Financial Report" notice carries the PDF as an attachment
    (TRATON, Asker, Vitrolife ... also the ESEF zip, unused). MFN covers most Swedish issuers; this covers the rest."""
    toks = _toks(company)
    q = urllib.parse.urlencode({"type": "json", "showAttachments": "true", "showCnsSpecific": "true", "showCompany": "true", "countResults": "false",
                                "freeText": _name(company), "cnscategory": "Annual Financial Report", "globalGroup": "exchangeNotice",
                                "globalName": "NordicMainMarkets", "displayLanguage": "en", "limit": 30, "start": 0, "dir": "DESC"})
    try:
        items = json.loads(_get("https://api.news.eu.nasdaq.com/news/query.action?" + q))["results"]["item"]
    except Exception as e:
        print(f"nasdaq news failed: {e}")
        return []
    scored, yr = [], _year_re(year)
    for it in items:
        names = " ".join(a.get("fileName", "") for a in it.get("attachment", []))
        headline = it.get("headline", "")
        if not all(t in _fold(it.get("company", "")) for t in toks) or not IS_AR.search(headline) or NOT_AR.search(headline):
            continue  # a same-week "Year-End Report" carries no PDF worth trying and used to slip past NOT_AR alone
        if not yr.search(it.get("headline", "") + names) and not it.get("published", "").startswith(str(year + 1)):
            continue  # the report for FY2025 is published in 2026
        for a in it.get("attachment", []):
            n, mt = a.get("fileName", ""), a.get("mimetype", "")
            is_pdf, is_zip = mt == "application/pdf", mt in ("application/zip", "application/x-zip-compressed")
            if not (is_pdf or is_zip) or BAD_URL.search(n) or re.search(r"press|release|meddelande", n, re.I):
                continue
            sc = 3 * bool(IS_AR.search(n)) + (str(year) in n) + (it.get("language") == "en") - 2 * is_zip
            scored.append((sc, a["attachmentUrl"]))
    return [u for _, u in sorted(scored, key=lambda x: -x[0])]


def _ddg(company, year):
    toks, company = _toks(company), _name(company)
    out = {}
    for q in (f"{company} annual report {year} filetype:pdf", f"{company} årsredovisning {year} filetype:pdf"):
        try:
            s = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(q)).decode("utf-8", "ignore")
        except Exception as e:
            print(f"ddg failed: {e}")
            continue
        for m in re.findall(r'uddg=([^&"]+)', s):
            u = urllib.parse.unquote(m)
            if ".pdf" not in u.lower() or u in out:
                continue
            l = u.lower()
            sc = 3 * (str(year) in l) + 2 * bool(re.search(r"annual|arsredovisning|annual-report", l))
            sc += 2 * any(t in urllib.parse.urlparse(u).netloc for t in toks) - 5 * bool(BAD_URL.search(l))
            out[u] = sc
    return [u for u, _ in sorted(out.items(), key=lambda x: -x[1])]


def _harvest(pages, year):
    """Annual-report PDF links found on a handful of already-located company pages."""
    out = {}
    for page in pages[:3]:
        try:
            html = _get(page).decode("utf-8", "ignore")
        except Exception as e:
            print(f"crawl {page} -> {e}")
            continue
        for href, text in re.findall(r'href="([^"]+\.pdf[^"]*)"[^>]*>(.*?)</a>', html, re.I | re.S):
            u = urllib.parse.urljoin(page, href)
            l = (u + " " + re.sub(r"<[^>]+>", " ", text)).lower()
            out[u] = 3 * (str(year) in l) + 2 * bool(re.search(r"annual|arsredovisning|årsredovisning", l)) - 5 * bool(BAD_URL.search(l))
    return [u for u, sc in sorted(out.items(), key=lambda x: -x[1]) if sc > 0]


def _crawl(company, year):
    """Search without filetype:, then harvest PDFs and retain issuer/registry listing pages among the top hits
    (the press release "X has published its annual report 2025", the IR reports page). Nordea's report is not found by
    a filetype:pdf search but is linked from both. Also tries any company-domain page an MFN release itself links to
    (Lundin Gold's release attaches only its own 2-page release text; the report lives one click away on its IR site) —
    useful even when DDG's bot challenge blocks the search below."""
    name = _name(company)
    pages = list(_mfn_pages(company, year))
    for q in (f"{name} annual report {year}", f"{name} årsredovisning {year}"):
        try:
            s = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(q)).decode("utf-8", "ignore")
        except Exception as e:
            print(f"ddg failed: {e}")
            continue
        for m in re.findall(r'uddg=([^&"]+)', s):
            u = urllib.parse.unquote(m)
            if report_listing.http_url(u, u) and ".pdf" not in u.lower() and u not in pages:
                pages.append(u)
    # Keep listing pages for issuer/year inspection, including registry mirrors whose
    # domain does not contain the company's name. Bound the crawl as before.
    return list(dict.fromkeys(_harvest(pages, year) + pages[:MAX_CRAWL_SEEDS]))


def _candidates(company, year, job_id=None):
    """Candidate PDF URLs, best first: the structured feeds, then (only if those are exhausted) the web — the feeds often carry
    just the press release or the ESEF zip (AstraZeneca, Lundin Gold, SkiStar) while the report sits on the company's site.
    job_id (v194): one mfn/nasdaq event pair for the feed lookup, one ddg event pair for the crawl+DuckDuckGo fallback --
    the same two groups this function already computes, just named and reported, the URLs and their order unchanged."""
    jobs.step(job_id, "mfn", f"searching MFN for {company} ({year})")
    mfn_urls = _mfn(company, year)
    jobs.step(job_id, "nasdaq", f"searching Nasdaq company news for {company} ({year})")
    nasdaq_urls = _nasdaq(company, year)
    feeds = list(dict.fromkeys(mfn_urls + nasdaq_urls))[:MAX_TRIES]
    jobs.step(job_id, "nasdaq", f"{len(feeds)} feed candidate(s)" if feeds else "no feed candidates")
    yield from feeds
    jobs.step(job_id, "ddg", f"crawling the company's own pages and DuckDuckGo for {company} ({year})")
    rest = [u for u in dict.fromkeys(_crawl(company, year) + _ddg(company, year)) if u not in feeds][:MAX_TRIES]
    jobs.step(job_id, "ddg", f"{len(rest)} more candidate(s)" if rest else "no more candidates")
    yield from rest


def find_report(company: str, year: int) -> list[str]:
    return list(_candidates(company, year))


def _validate(data, company, year, page_texts=None):
    """(doc, text) if this is a real text-layer annual report *of this company*, else (None, reason)."""
    if not data.startswith(b"%PDF"):
        return None, "not a PDF"
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.page_count < 3:
        pages = doc.page_count
        doc.close()
        return None, f"only {pages} pages"
    if page_texts is not None and len(page_texts) != doc.page_count:
        doc.close()
        raise ValueError("Page text count does not match the PDF")
    text = "".join(page_texts[:20]) if page_texts is not None else "".join(doc[i].get_text() for i in range(min(20, doc.page_count)))
    if len(text.strip()) < 200:
        doc.close()
        return None, "no text layer"
    head = _head_text(doc, page_texts)
    key = collection.identity(company)
    aliases = {key, *(alias for alias, target in collection.ALIASES.items() if target == key)}
    normalized_head = collection.normalize(head)
    cover_alias = any(re.search(r"\b" + r"\s+".join(map(re.escape, alias.split())) + r"\b", normalized_head) for alias in aliases if alias)
    # A subsidiary sharing the brand is not the requested group's report (e.g. Nefab Danmark A/S).
    def issuer_key(name):
        name = re.sub(r"\b(?:a/s|a s|as|holding|holdings|corporation|corp|limited)\b", "", _fold(name), flags=re.I)
        return collection.identity(name)
    wanted = issuer_key(company)
    # Parent coverage is context, not a ban on a subsidiary's own accounts. Reject
    # an explicitly titled parent PDF even if the subsidiary is mentioned repeatedly.
    if parent := collection.report_metadata(company):
        owner = issuer_key(parent["reports_in"])
        cover = page_texts[0] if page_texts is not None else doc[0].get_text()
        for line in cover.splitlines()[:12]:
            title_name = IS_AR.split(line, maxsplit=1)[0].strip(" -:|")
            if issuer_key(title_name) == owner:
                doc.close()
                return None, f"issuer mismatch: cover names parent {parent['reports_in']!r}, not {company!r}"
    for line in (page_texts[0] if page_texts is not None else doc[0].get_text()).splitlines():
        label = " ".join(line.split())
        if len(label) < 100 and re.search(r"\b(?:AB|A/S|Ltd\.?|plc|Inc\.?|Oyj)(?:\s*\(publ\))?$", label, re.I):
            claimed = issuer_key(label)
            if wanted and claimed.startswith(wanted + " "):
                doc.close()
                return None, f"issuer mismatch: cover names {label!r}, not {company!r}"
    # Numeric brand names must match as a phrase: "3 Scandinavia" is not "Candles Scandinavia".
    name = collection.normalize(company)
    if re.search(r"\b\d+\b", name) and not cover_alias:
        doc.close()
        return None, "issuer mismatch: numeric company name not on the cover"
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    missing = [t for t in _toks(company) if not re.search(rf"\b{re.escape(t)}\b", plain)]  # "nibe", "abb", "lundin gold" (not Lundin Mining)
    if missing:
        # v122 ruling: the issuer may style itself only by its acronym, when the initials (at least
        # three letters) stand whole-word on the cover -- that is how MTG's own FY2025 report reads.
        # An acronym in the body alone accepts nothing: an unrelated report naming "ABB" as a
        # supplier is still somebody else's report (DDG happily returns those).
        acr = _acronym(company)
        if not cover_alias and not (acr and re.search(rf"\b{acr}\b", _fold(head))):
            doc.close()
            return None, f"issuer mismatch: {missing[0]!r} not in first 20 pages"
    # Portfolio-company names in the body of an owner's report are not issuer evidence.
    # Image-only covers have no searchable title; retain the body check for those files.
    if len(re.sub(r"\W", "", head)) >= 100:
        missing_head = [t for t in _toks(company) if not re.search(rf"\b{re.escape(t)}\b", _fold(head))]
        acr = _acronym(company)
        if missing_head and not cover_alias and not (acr and re.search(rf"\b{acr}\b", _fold(head))):
            doc.close()
            return None, "issuer mismatch: company is mentioned in the body but not identified on the first pages"
    if report_period.REGISTRATION.search(head):
        all_texts = page_texts if page_texts is not None else [page.get_text() for page in doc]
        metadata = report_period.historical_accounts(all_texts, company, year)
        if not metadata:
            doc.close()
            return None, f"registration statement lacks verified audited annual accounts for {company} FY{year}"
        return doc, report_period.ValidatedText(text, **metadata)
    if reason := _year_reason(doc, year, page_texts):  # v122: the year on the first pages or an accounting period, not "anywhere"
        doc.close()
        return None, reason
    if NOT_REPORT.search(head) and not IS_AR.search(head):
        reason = f"not an annual report: {NOT_REPORT.search(head).group(0)!r} on the cover"
        doc.close()
        return None, reason
    if doc.page_count <= 40:
        # Small private-company statutory accounts are often much shorter than listed reports.
        # Accept their content, while still rejecting notices, brochures and topic-only reports.
        full = _fold(" ".join(page_texts) if page_texts is not None else " ".join(page.get_text() for page in doc))
        title = re.search(r"annual[\w\s&-]*report|arsredovisning|annual accounts|financial statements", _fold(head))
        income = re.search(r"income statement|statement of (?:comprehensive )?income|profit and loss|resultatrakning|rapport over (?:total)?resultat", full)
        balance = re.search(r"balance sheet|statement of financial position|balansrakning|rapport over finansiell stallning", full)
        if not (title and income and balance):
            doc.close()
            return None, "short document lacks annual accounts (report title, income statement and balance sheet)"
        if not cover_alias and any(not re.search(rf"\b{re.escape(t)}\b", _fold(head)) for t in _toks(company)):
            doc.close()
            return None, "issuer mismatch: short accounts do not name the company on the first pages"
    return doc, text


def _load_index(dest_dir: Path) -> list:
    p = dest_dir / "index.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


_IR_PATHS = ("/investor-relations/annual-report.html", "/investor-relations.html", "/en/investors", "/investors", "/")


def _ir_guesses(hosts):
    return [f"https://{h}{path}" for h in hosts for path in _IR_PATHS]


def _stub_pages(data, toks):
    """A short "we published our annual report" notice PDF often names the issuer's own website (AstraZeneca's Nasdaq
    notice: "The Annual Report is also available on the Company's website www.astrazeneca.com") -- harvest that domain's
    likely investor-relations pages as one more place to look, when every feed attachment turns out to be this stub."""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        text = "".join(doc[i].get_text() for i in range(min(3, doc.page_count)))
    except Exception:
        return []
    hosts = set()
    for m in re.findall(r"(?:https?://|www\.)[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", text, re.I):
        netloc = (urllib.parse.urlparse(m if "://" in m else "https://" + m).netloc or m).lower()
        if any(t in netloc for t in toks):
            hosts.add(netloc)
    return _ir_guesses(hosts)


# ---- fifth source (v080): crawl a page-shaped leftover from levels 1-4 for the report PDF, one hop deep ----

MAX_CRAWL_SEEDS = 4        # candidate pages to start a crawl from
MAX_CRAWL_CANDIDATES = 8   # harvested PDF links actually downloaded + validated
CRAWL_TIMEOUT = 20         # seconds, per HTTP GET (a page, a hop, or a candidate PDF)
CRAWL_BUDGET = 90          # seconds, wall-clock across the whole fifth-source attempt


def _host_guesses(url, toks):
    """IR-page path guesses for the domain of a direct link that failed outright (Shell's expired asset-store
    URL): the same guesses _stub_pages makes from a stub PDF's own text, seeded from the dead URL's own host."""
    netloc = urllib.parse.urlparse(url).netloc.lower()
    return _ir_guesses({netloc}) if netloc and any(t in netloc for t in toks) else []


def _ir_links(page_url, html, year):
    """PDF/download links passing the same IS_AR/BAD_URL/NOT_REPORT gate as every other source, scored by
    year + annual-report wording + same-domain-as-the-page (issuers usually host the PDF next to the page that
    links it). Page count -- what actually separates a summary volume from the full report -- only exists once
    a candidate is downloaded; the caller compares that across every harvested survivor."""
    domain = urllib.parse.urlparse(page_url).netloc
    out = {}
    document = report_listing.Document(html)
    parents = {id(child): parent for parent in document.nodes for child in parent.parts if isinstance(child, report_listing.Node)}
    section_year = None
    for node in document.nodes:
        if re.fullmatch(r"h[1-6]", node.tag) and len(node.text()) < 120:
            if heading_year := re.search(r"\b(?:19|20)\d{2}\b", node.text()):
                section_year = int(heading_year[0])
        if node.tag != "a" or not (href := node.attrs.get("href")):
            continue
        u = report_listing.http_url(page_url, href)
        if not u:
            continue
        text = " ".join(filter(None, (node.text(), node.attrs.get("aria-label"), node.attrs.get("title"))))
        # Ordinary publisher download endpoints need not end in .pdf. Never run
        # JavaScript buttons or manufacture authenticated/challenge download URLs.
        downloadable = ".pdf" in href.lower() or "download" in node.attrs or node.attrs.get("type") == "application/pdf" or re.search(r"(?:download|attachment|document|/media/)", href, re.I)
        if not downloadable:
            continue
        label = (u + " " + text).lower()
        # A common filing row labels the HTML link "10-K" and the adjacent PDF
        # merely "PDF". Use its small containing row, never the whole archive.
        if not re.search(r"annual|[åa]rsredovisning|\b(?:10-K|20-F|40-F)\b", label, re.I) and re.fullmatch(r"\s*(?:PDF|Download|View)\s*", text, re.I):
            parent = parents.get(id(node))
            if parent and len(parent.text()) < 300:
                label += " " + parent.text().lower()
        annual = re.search(r"annual|[åa]rsredovisning|\b(?:10-K|20-F|40-F)\b", label, re.I)
        registration = re.search(r"registration statement|prospectus|\b(?:S-1|F-1)\b", label, re.I)
        allowed = _candidate_clear(u, text) if registration else _filename_clear(label, BAD_URL, NOT_REPORT)
        if not (annual or registration) or not allowed:
            continue
        out[u] = 6 * (str(year) in label or section_year == year) + bool(re.search(r"annual report|annual review|rsredovisning", label)) \
            + (urllib.parse.urlparse(u).netloc == domain)
    return out


def _record_listing(url, html, company, year, tried):
    if company and isinstance(tried, FetchAttempts):
        listing = report_listing.inspect(url, html, company, year)
        # Mirrors often link the same report through a slug, a numeric URL, a
        # decoded URL and #reports. Offer one verified listing per source host.
        if listing and not any(urllib.parse.urlsplit(row["url"]).hostname == urllib.parse.urlsplit(url).hostname for row in tried.listings):
            tried.listings.append(listing)


def _crawl_ir_page(start_url, year, deadline, company=None, tried=None):
    """Links scored for a single page, then -- only when the page itself carries nothing -- one hop into
    same-domain sub-pages that read like a reports/investor-relations index (a landing page one click above
    the actual per-year report link)."""
    domain = urllib.parse.urlparse(start_url).netloc
    try:
        html = _get(start_url, timeout=CRAWL_TIMEOUT).decode("utf-8", "ignore")
    except Exception as e:
        return {}, f"IR page crawl {start_url} -> {e}"
    _record_listing(start_url, html, company, year, tried)
    found = _ir_links(start_url, html, year)
    if found or time.time() > deadline:
        return found, None
    hops = []
    for node in report_listing.Document(html).nodes:
        if node.tag != "a" or not (href := node.attrs.get("href")):
            continue
        u = report_listing.http_url(start_url, href)
        if not u or ".pdf" in u.lower() or urllib.parse.urlparse(u).netloc != domain or u in hops:
            continue
        if urllib.parse.urldefrag(u)[0] == urllib.parse.urldefrag(start_url)[0]:
            continue
        if re.search(r"annual.?report|investor|\bir\b|rsredovisning|financial.?results|financial.?reports|sec.?filings|archive", u + " " + node.text(), re.I):
            hops.append(u)
    hops.sort(key=lambda u: -bool(re.search(r"financial.?results|annual.?reports?|archive", u, re.I)))
    for page in hops[:3]:
        if time.time() > deadline:
            break
        try:
            html2 = _get(page, timeout=CRAWL_TIMEOUT).decode("utf-8", "ignore")
        except Exception as e:
            print(f"IR page crawl hop {page} -> {e}")
            continue
        _record_listing(page, html2, company, year, tried)
        found.update(_ir_links(page, html2, year))
    return found, None


def _verify_text(url, doc, text):
    """The verify-stage progress line for one downloaded + validated candidate (v194) -- the same
    "ok (N pages)" / rejection-reason shape every print(f"{url} -> ...") in this file already uses."""
    return f"{url} -> ok ({doc.page_count} pages)" if doc else f"{url} -> {text}"


def _ir_page_report(seeds, company, year, tried, job_id=None):
    """Fifth source (v080): crawl candidate IR/report pages for the report PDF itself, at most one hop deep.
    Every harvested link still runs the full download+validate chain, appended to `tried` like every other
    candidate; unlike the earlier sources (first validated survivor wins) this one downloads every harvested
    candidate within budget and keeps the one with the most pages, because the page linking a summary volume
    often links the full report right next to it (Nestlé's Annual Review vs. its actual Annual Report).
    job_id (v194): one "ir_page" event per seed page read, one "download"/"verify" pair per harvested
    candidate (byte progress rides on _get; see jobs.py)."""
    deadline = time.time() + CRAWL_BUDGET
    ranked = {}
    for page in seeds[:MAX_CRAWL_SEEDS]:
        if time.time() > deadline:
            break
        jobs.step(job_id, "ir_page", f"reading {page}")
        found, err = _crawl_ir_page(page, year, deadline, company, tried)
        if err:
            print(err)
            _failure(tried, page, err, "download")
            continue
        for u, sc in found.items():
            if u in ranked:
                continue
            ranked[u] = sc
            if (dec := urllib.parse.unquote(u)) != u and dec not in ranked:
                ranked[dec] = sc  # the same %-decoded-twin trick as the model candidates (v074)
    ordered = [u for u, _ in sorted(ranked.items(), key=lambda x: -x[1])][:MAX_CRAWL_CANDIDATES]
    best = None
    for url in ordered:
        if time.time() > deadline:
            break
        tried.append(url)
        t0 = time.time()
        try:
            data = _unzip(_get(url, timeout=CRAWL_TIMEOUT, job_id=job_id, label=url) if job_id else _get(url, timeout=CRAWL_TIMEOUT))
            doc, text = _validate(data, company, year)
        except Exception as e:
            print(f"{url} -> {e}")
            jobs.step(job_id, "verify", f"{url} -> {e}")
            _failure(tried, url, e, "download")
            continue
        jobs.step(job_id, "verify", _verify_text(url, doc, text))
        if not doc:
            print(f"{url} -> {text}")
            _failure(tried, url, text)
            if TITLE_YEAR_MARK in text:  # v122: a cover naming an older year is a finding, not just a miss
                tried.append(text)
            continue
        pages = doc.page_count
        doc.close()
        print(f"{url} -> ok ({pages} pages, {time.time() - t0:.0f}s, IR page crawl)")
        if not best or _best_model_candidate([best, (url, data, text, pages)])[0] == url:
            best = (url, data, text, pages)
    return best[:3] if best else None


def _entry(fname, company, year, url, text, note=None, tags=("fetched",)):
    low = text.lower()
    return {"file": fname, "company": company, "fiscal_year": year,
            "language": "sv" if low.count("årsredovisning") > low.count("annual report") else "en",
            "source_url": url, "tags": list(tags), "note": note, "fetched_at": dt.date.today().isoformat(),
            **getattr(text, "metadata", {})}


def _write_index(dest_dir, index):
    s = json.dumps(index, ensure_ascii=False, indent=2)
    s = re.sub(r'\[\s+("[^\]]*?")\s+\]', lambda m: "[" + re.sub(r",\s+", ", ", m.group(1)) + "]", s)  # tags on one line
    tmp = dest_dir / "index.json.tmp"
    tmp.write_text(s + "\n", encoding="utf-8")
    os.replace(tmp, dest_dir / "index.json")  # a concurrent GET /api/library never reads a half-written file


_INDEX_LOCK = threading.Lock()


class ReportStoreError(RuntimeError):
    """A validated download could not be durably published. Safe to show to API callers."""


def _upsert_index(dest_dir, entry):
    """Re-read under the lock, then replace the row with the same file: three parallel fetches (the UI's
    pool of 3) each add their own row instead of the last writer dropping the others'."""
    with _INDEX_LOCK:
        _write_index(dest_dir, [e for e in _load_index(dest_dir) if e["file"] != entry["file"]] + [entry])


def _drop_index(dest_dir, fname):
    """Forget one unusable cache row without disturbing parallel writers."""
    with _INDEX_LOCK:
        if (dest_dir / "index.json").exists():
            _write_index(dest_dir, [e for e in _load_index(dest_dir) if e.get("file") != fname])


def _readable_pdf(path: Path) -> bool:
    """A cache hit must be a PDF PyMuPDF can actually open, not merely an existing filename."""
    try:
        with fitz.open(path) as doc:
            return bool(doc.is_pdf and doc.page_count > 0)
    except Exception:
        return False


def _publish_pdf(dest_dir: Path, fname: str, data: bytes) -> Path:
    """Durably stage and validate a PDF before atomically making its final name visible.

    The index is updated by the caller only after this returns. An interrupted write or rename
    therefore leaves no final file for library_index/register_library to mistake for a report.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / fname
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=dest_dir, prefix=f".{fname}.", suffix=".tmp", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        if not _readable_pdf(tmp_path):
            raise ValueError("the staged file is not a readable PDF")
        os.replace(tmp_path, final)
        tmp_path = None
        if not _readable_pdf(final):  # verify the final path too; rename must never publish a ghost
            final.unlink(missing_ok=True)
            raise ValueError("the published file is not a readable PDF")
        return final
    except Exception as e:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                print(f"PDF temp cleanup failed ({type(cleanup_error).__name__}): {cleanup_error}")
        print(f"PDF publish failed ({type(e).__name__}): {e}")
        raise ReportStoreError("Downloaded report could not be saved and validated; retry download.") from e


def _publish_report(dest_dir: Path, entry: dict, data: bytes) -> None:
    """Commit the PDF first and its index row second; roll the file back if indexing fails."""
    final = _publish_pdf(dest_dir, entry["file"], data)
    try:
        _upsert_index(dest_dir, entry)
    except Exception as e:
        try:
            final.unlink(missing_ok=True)
        except OSError as cleanup_error:
            print(f"unindexed PDF cleanup failed ({type(cleanup_error).__name__}): {cleanup_error}")
        print(f"report index publish failed ({type(e).__name__}): {e}")
        raise ReportStoreError("Downloaded report could not be indexed; retry download.") from e


def _listing_sources(dest_dir, company, year):
    try:
        rows = json.loads((dest_dir / "report-listings.json").read_text(encoding="utf-8"))
        return [row for row in rows if isinstance(row, dict) and row.get("fiscal_year") == year
                and collection.identity(row.get("company")) == collection.identity(company)
                and isinstance(row.get("url"), str) and report_listing.http_url(row["url"], row["url"])]
    except (OSError, ValueError, TypeError):
        return []


def _remember_listings(dest_dir, company, year, listings):
    """Remember source URLs, not report contents. Every reuse must recheck live HTML."""
    if not listings:
        return
    try:
        with _INDEX_LOCK:
            path = dest_dir / "report-listings.json"
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
                rows = rows if isinstance(rows, list) else []
            except (OSError, ValueError):
                rows = []
            rows = [row for row in rows if isinstance(row, dict) and not (row.get("fiscal_year") == year and collection.identity(row.get("company")) == collection.identity(company))]
            dest_dir.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(rows + listings, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, path)
    except OSError as exc:
        print(f"Could not remember report listings: {exc}")


def fetch_report(company: str, year: int, dest_dir: "Path | None" = None, country: "str | None" = None, hint: "str | None" = None,
                 url: "str | None" = None, job_id: "str | None" = None) -> dict:
    """Reuse cached PDFs, then ask the connected model to search official sources.

    Model-directed PDF/IR discovery runs before legacy feeds and web scraping.
    Every candidate still passes issuer, fiscal-year and report-type validation.
    `url` (a discover candidate the user confirmed) is tried before any source of our own;
    `company` is then the confirmed legal name, and the cache filename follows it as always.

    job_id (v194, optional): every source below reports its stage, each candidate's download
    progress and verify outcome, and a final done/failed event to pipeline.jobs -- a no-op when
    job_id is None. See jobs.py's module docstring and docs/API.md's Progress tracking section.
    """
    dest_dir = Path(dest_dir) if dest_dir is not None else paths.reports_dir()
    if (private := collection.report_metadata(company)) and private.get("no_standalone_report"):
        # This check intentionally precedes URL download, model discovery and legacy feeds.
        note = private_report_note(private)
        jobs.step(job_id, "failed", note)
        raise NoStandaloneReport(note)
    fname = f"{slugify(company)}_{year}.pdf"
    jobs.step(job_id, "directory", f"checking the report cache for {company} ({year})")
    index = _load_index(dest_dir)
    for e in index:  # cache hit
        if e["file"] == fname and (dest_dir / fname).exists():
            if _readable_pdf(dest_dir / fname):
                jobs.step(job_id, "done", f"{e['file']} (already cached)")
                return {**e, "tried": []}
            # A previous interrupted/externally damaged download is not a cache hit. Remove both
            # halves before retrying so /api/library cannot expose a row PyMuPDF cannot open.
            jobs.step(job_id, "verify", f"{e['file']} is unreadable; removing it before retry")
            try:
                (dest_dir / fname).unlink(missing_ok=True)
                _drop_index(dest_dir, fname)
                index = [row for row in index if row.get("file") != fname]
            except OSError as err:
                print(f"corrupt report cache cleanup failed ({type(err).__name__}): {err}")
                raise ReportStoreError("The incomplete cached report could not be removed; retry download.") from err
    # Curated source links remain useful even before their PDF is downloaded.
    if not url:
        known = next((e for e in index if e.get("fiscal_year") == year and collection.identity(e.get("company")) == collection.identity(company) and e.get("source_url")), None)
        if known:
            url = known["source_url"]
    tried, toks, stub_pages, page_seeds = FetchAttempts(), _toks(company), [], []
    model_note = None
    # A verified listing is a reusable discovery source across aliases. Recheck
    # its page each time: the publisher may add a direct download or remove it.
    known_listings = _listing_sources(dest_dir, company, year) if not url else []
    if known_listings:
        if found := _ir_page_report([row["url"] for row in known_listings][:MAX_CRAWL_SEEDS], company, year, tried, job_id=job_id):
            source, data, text = found
            entry = _entry(fname, company, year, source, text, note="verified listing source")
            _publish_report(dest_dir, entry, data)
            jobs.step(job_id, "done", f"{entry['file']} (verified listing source)")
            return {**entry, "tried": tried}
        if tried.listings:
            _remember_listings(dest_dir, company, year, tried.listings)
            # A listing is evidence of publication, not a downloaded report.
            # Continue discovery: another source may offer a normal PDF link.
    if url:  # the confirmed link first: same download + validation as every other source, then fall through
        tried.append(url)
        t0 = time.time()
        try:
            data = _unzip(_get(url, job_id=job_id, label=url) if job_id else _get(url))
            doc, text = _validate(data, company, year)
        except Exception as e:
            print(f"{url} -> {e}")
            jobs.step(job_id, "verify", f"{url} -> {e}")
            _failure(tried, url, e, "download")
            data, doc, text = b"", None, ""
        else:
            jobs.step(job_id, "verify", _verify_text(url, doc, text))
        if doc:
            pages = doc.page_count
            doc.close()
            print(f"{url} -> ok ({pages} pages, {time.time() - t0:.0f}s, confirmed url)")
            note = "confirmed url" if _is_full_report(url, pages) else "confirmed url; summary volume"
            entry = _entry(fname, company, year, url, text, note=note)
            _publish_report(dest_dir, entry, data)
            jobs.step(job_id, "done", f"{entry['file']} ({note})")
            return {**entry, "tried": tried}
        if text:
            print(f"{url} -> {text}")
            _failure(tried, url, text)
            if TITLE_YEAR_MARK in text:  # v122: a cover naming an older year is a finding, not just a miss
                tried.append(text)
            if not data.startswith(b"%PDF"):  # the confirmed link was a page, not a PDF: crawl it (v080)
                page_seeds.append(url)
    if p := websearch_provider():
        jobs.step(job_id, "model_search", "asking the connected model to search the web")
        urls, model_note = _model_candidates(company, year, country, hint, job_id=job_id)
        jobs.step(job_id, "model_search", f"model suggested {len(urls)} candidate(s)" if urls else (model_note or "model suggested no candidates"), urls=urls)
        hits = []  # (url, data, text, pages) for every candidate that downloads + validates (v081: rank, don't stop at the first)
        for url in urls:
            if url in tried:
                continue
            tried.append(url)
            t0 = time.time()
            try:
                data = _unzip(_get(url, job_id=job_id, label=url) if job_id else _get(url))
                doc, text = _validate(data, company, year)
            except Exception as e:
                print(f"{url} -> {e}")
                jobs.step(job_id, "verify", f"{url} -> {e}")
                _failure(tried, url, e, "download")
                page_seeds += [u for u in _host_guesses(url, toks) if u not in page_seeds]  # a dead link: guess its own IR page (v080)
                continue
            jobs.step(job_id, "verify", _verify_text(url, doc, text))
            if not doc:  # no stub-page harvest here: the model was asked for direct PDF links only
                print(f"{url} -> {text}")
                _failure(tried, url, text)
                if TITLE_YEAR_MARK in text:  # v122: a cover naming an older year is a finding, not just a miss
                    tried.append(text)
                if not data.startswith(b"%PDF") and url not in page_seeds:  # the model named a page, not a PDF (v080)
                    page_seeds.append(url)
                continue
            pages = doc.page_count
            doc.close()
            print(f"{url} -> ok ({pages} pages, {time.time() - t0:.0f}s)")
            hits.append((url, data, text, pages))
        if hits:
            # v081: prefer the complete report over a summary volume when more than one candidate
            # validated; accept a summary only when nothing among them clears the full-report bar
            url, data, text, pages = _best_model_candidate(hits)
            note = f"model search ({p})" if _is_full_report(url, pages) else f"model search ({p}); summary volume"
            entry = _entry(fname, company, year, url, text, note=note, tags=["fetched", "foreign"])
            _publish_report(dest_dir, entry, data)
            jobs.step(job_id, "done", f"{entry['file']} ({note})")
            return {**entry, "tried": tried}
    # Follow the official IR pages returned by the model before broad fallback discovery.
    if page_seeds and (found := _ir_page_report(page_seeds, company, year, tried, job_id=job_id)):
        url, data, text = found
        entry = _entry(fname, company, year, url, text, note="IR page crawl", tags=["fetched", "foreign"])
        _publish_report(dest_dir, entry, data)
        jobs.step(job_id, "done", f"{entry['file']} (IR page crawl)")
        return {**entry, "tried": tried}
    # One targeted follow-up can find the official archive when direct links fail.
    # At most two model searches per uncached report.
    if p:
        jobs.step(job_id, "ir_page", "asking the connected model for the investor-relations page")
        feedback = "Previous attempts failed: " + "; ".join(f"{f['url']}: {f['reason']}" for f in tried.failures[-6:])
        ir_urls, ir_note = _ir_page_candidates(company, year, country, "\n".join(filter(None, [hint, feedback])), job_id=job_id)
        jobs.step(job_id, "ir_page", f"model suggested {len(ir_urls)} page(s)" if ir_urls else (ir_note or "model suggested no pages"), urls=ir_urls)
        new_seeds = [u for u in ir_urls if u not in page_seeds]
        if new_seeds and (found := _ir_page_report(new_seeds, company, year, tried, job_id=job_id)):
            url, data, text = found
            entry = _entry(fname, company, year, url, text, note="IR page crawl", tags=["fetched", "foreign"])
            _publish_report(dest_dir, entry, data)
            jobs.step(job_id, "done", f"{entry['file']} (IR page crawl)")
            return {**entry, "tried": tried}
        if ir_note:
            model_note = f"{model_note}; {ir_note}" if model_note else ir_note
    # Traditional sources are a fallback, not a prerequisite for model search.
    # Start a fresh set of page seeds so failed AI pages are not crawled twice.
    page_seeds = []
    candidates = list(_candidates(company, year, job_id=job_id))
    i = 0
    while i < len(candidates):
        url = candidates[i]
        i += 1
        if url in tried:
            continue
        tried.append(url)
        t0 = time.time()
        try:
            data = _unzip(_get(url, job_id=job_id, label=url) if job_id else _get(url))
            doc, text = _validate(data, company, year)
        except Exception as e:
            print(f"{url} -> {e}")
            jobs.step(job_id, "verify", f"{url} -> {e}")
            _failure(tried, url, e, "download")
            page_seeds += [u for u in _host_guesses(url, toks) if u not in page_seeds]  # a dead link: guess its own IR page (v080)
            continue
        jobs.step(job_id, "verify", _verify_text(url, doc, text))
        if not doc:
            print(f"{url} -> {text}")
            _failure(tried, url, text)
            if TITLE_YEAR_MARK in text:  # v122: a cover naming an older year is a finding, not just a miss
                tried.append(text)
            if data.startswith(b"%PDF"):  # not a download error: a page an RNS-style notice may name its own site on
                stub_pages += [u for u in _stub_pages(data, toks) if u not in stub_pages]
            elif url not in page_seeds:  # a page, not a PDF (a DDG hit that served an IR page): crawl it (v080)
                page_seeds.append(url)
            if i == len(candidates) and stub_pages:  # every direct candidate failed: try the issuer's own site (AstraZeneca)
                candidates += [u for u in _harvest(stub_pages, year) if u not in candidates]
                stub_pages = []
            continue
        pages = doc.page_count
        doc.close()
        print(f"{url} -> ok ({pages} pages, {time.time() - t0:.0f}s)")
        entry = _entry(fname, company, year, url, text)
        _publish_report(dest_dir, entry, data)
        jobs.step(job_id, "done", entry["file"])
        return {**entry, "tried": tried}
    if page_seeds and (found := _ir_page_report(page_seeds, company, year, tried, job_id=job_id)):
        url, data, text = found
        entry = _entry(fname, company, year, url, text, note="IR page crawl")
        _publish_report(dest_dir, entry, data)
        jobs.step(job_id, "done", f"{entry['file']} (IR page crawl)")
        return {**entry, "tried": tried}
    _remember_listings(dest_dir, company, year, tried.listings)
    jobs.step(job_id, "failed", f"no annual report found for {company} {year}" + (f"; {model_note}" if model_note else ""))
    raise LookupError(tried, model_note)


if __name__ == "__main__":
    print(json.dumps(fetch_report(sys.argv[1], int(sys.argv[2])), ensure_ascii=False, indent=2))
