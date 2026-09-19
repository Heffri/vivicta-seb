"""Find + download a company's annual report PDF into data/reports/ (the cache) and register it in index.json.
Sources, cheapest first: MFN feed (aggregates Cision too) and Nasdaq notices, then the web (DuckDuckGo html) when the
feeds only carried press releases or ESEF zips (AstraZeneca, Lundin Gold, SkiStar). Fourth (v074), only after all of
those fail and a CLI model provider is configured: the model's own web search, asked for official annual-report PDF
links for foreign companies the Swedish feeds never carry (Nestlé, Siemens, Shell ...). Fifth (v080), only after all
of those fail too: crawl any page-shaped leftover from the earlier attempts -- a model reply that names the issuer's
IR page instead of a direct PDF, a DDG hit that served a page, or the guessed investor-relations path for the domain
of a direct link that 404d (Shell's stale asset-store URL) -- one hop deep, for the report PDF itself. If that still
finds nothing, one more model call (v081) asks only for the IR/annual-report-archive page itself (never a PDF link),
fed into the same crawl -- at most two model calls total. The fourth source also downloads every one of its own
candidates rather than stopping at the first that validates, and keeps the most complete one, since the model is
now asked to prefer the full report over a summary/highlights volume.
CLI: python -m pipeline.fetch "Boliden" 2025"""
import datetime as dt
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import pymupdf as fitz

from . import llm, paths

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
MAX_TRIES = 6
NOT_AR = re.compile(r"general meeting|st[äa]mma|notice|kallelse|nomination|valberedning|20-f|interim|delårs|quarter", re.I)
IS_AR = re.compile(r"annual|årsredovisning|års- och", re.I)
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
    "the stated fiscal year, hosted on the company's own investor-relations site or an official regulatory filing "
    "repository; exclude ESEF/xBRL zip packages, interim or quarterly reports, sustainability, remuneration, "
    "governance or capital-markets reports, and press releases. Prefer the complete annual report (the full "
    "document), not a summary, highlights, at-a-glance, or annual review excerpt. If you cannot find a direct PDF "
    "link, a URL for the company's investor-relations or annual-report page is also acceptable."
)
# ---- second ask (v081): only after every fourth-source candidate and the fifth source's generic IR-path
# guesses have both failed -- ask once more, this time only for the IR/annual-report-archive page itself ----
MAX_IR_PAGE_CANDIDATES = 2
IR_PAGE_SYSTEM = (
    "A direct link to the company's official annual report PDF could not be found or downloaded. Reply with JSON "
    'only, no prose: {"candidates": [{"url": "https://...", "title": "...", "reason": "..."}]}. '
    "Rules: at most 2 candidates, best first; every URL must be an HTML page, never a PDF, on the company's own "
    "site -- its investor-relations page or its annual-report archive/library page -- from which the official "
    "annual report PDF for the stated fiscal year can be reached."
)
# the complete-report preference (v081): Nestle's real Annual Review is 67p, well under this floor; a summary/
# highlights/at-a-glance/short/in-brief excerpt is accepted only when nothing among the candidates clears it
FULL_REPORT_MIN_PAGES = 80
SUMMARY_WORDS = re.compile(r"\bsummary\b|highlights|at[-_ ]a[-_ ]glance|\bshort\b|in[-_ ]brief", re.I)


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
    fname = label.rsplit("/", 1)[-1].split("?", 1)[0]
    if any(p.search(fname) for p in patterns):
        return False
    if IS_AR.search(fname):
        return True
    return not any(p.search(label) for p in patterns)


def _model_candidates(company, year, country=None, hint=None):
    """Ask the model for official annual-report PDF links. (urls, note): at most MAX_MODEL_CANDIDATES
    cleaned URLs, best first, plus a short note for the eventual 404 detail -- the model being
    unavailable or replying with something unparseable is not the same thing as "no links found"."""
    user = f"Company: {company}\nFiscal year: {year}"
    if country:
        user += f"\nCountry: {country}"
    if hint:
        user += f"\nHint: {hint}"
    try:
        data = json.loads(llm.web_lookup(SEARCH_SYSTEM, user, SEARCH_SCHEMA))
    except Exception as e:  # the CLI's RuntimeError, a timeout, or bad JSON -- one clear note either way
        print(f"model search failed: {e}")
        return [], f"model search ({llm.provider()}) failed: {str(e)[:200]}"
    urls = []
    for c in (data.get("candidates") or [])[:MAX_MODEL_CANDIDATES]:
        u = str(c.get("url", "")).strip() if isinstance(c, dict) else ""
        if not u.startswith(("http://", "https://")) or not _filename_clear(u, BAD_URL):
            print(f"model candidate dropped: {u!r}")  # not a direct link, or an interim/risk/AGM URL by name
            continue
        urls.append(u)
        # models hand back percent-encoded paths (Siemens' asset API: uuid%3A... -> 400s); the decoded
        # twin is a free second try for servers that only accept the raw characters
        if (dec := urllib.parse.unquote(u)) != u and _filename_clear(dec, BAD_URL):
            urls.append(dec)
    return urls, None


def _ir_page_candidates(company, year, country=None, hint=None):
    """The second model ask (v081): (urls, note) like _model_candidates, but only ever called once
    every fourth-source candidate and the fifth source's own generic IR-path guesses have already
    failed, asking this time only for the company's IR/annual-report-archive page -- never a PDF --
    so v080's crawl (_ir_page_report) has a page the model actually named instead of only a guessed
    generic path. At most MAX_IR_PAGE_CANDIDATES URLs; a candidate that is itself a PDF is dropped,
    since that is exactly what the first ask already tried and failed at."""
    user = f"Company: {company}\nFiscal year: {year}"
    if country:
        user += f"\nCountry: {country}"
    if hint:
        user += f"\nHint: {hint}"
    try:
        data = json.loads(llm.web_lookup(IR_PAGE_SYSTEM, user, SEARCH_SCHEMA))
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
    return max(hits, key=lambda h: (h[3] >= FULL_REPORT_MIN_PAGES, _label_clean(h[0]), h[3]))


def _get(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


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


def _head_text(doc):
    """The first three pages -- cover, title page, contents: where a report names its own year."""
    return "".join(doc[i].get_text() for i in range(min(3, doc.page_count)))


def _title_year(head, year):
    """An earlier year standing alone on a report-titled cover ("Annual Report 2021", or MTG's
    year-above-the-title layout), or None -- the detail that explains a v122 rejection: in such a
    document the target year typically appears only in forward-looking text, which is exactly how
    the old year-anywhere check was satisfied."""
    if not _TITLE_WORDS.search(head):
        return None
    older = [int(m.group(0)) for m in re.finditer(r"\b(?:19|20)\d{2}\b", head) if int(m.group(0)) < year]
    return str(max(older)) if older else None


def _year_ok(doc, year):
    """v122: is this plausibly the fiscal-`year` report? The year itself -- or the split-year
    "2024/25" / "2024/2025" cover shape -- must sit on the first three pages (cover, title page,
    contents), or an accounting period ending in the year must be stated anywhere in the text.
    A mere mention on some later page no longer passes: MTG's FY2021 report slipped through the
    old year-anywhere check on six forward-looking "2025" target mentions."""
    if _fiscal_year_re(year).search(_head_text(doc)):
        return True
    return bool(_period_re(year).search("".join(doc[i].get_text() for i in range(doc.page_count))))


def _year_reason(doc, year):
    """The v122 rejection reason for a PDF _year_ok refused (None when it passes). When the first
    three pages title the report with an earlier year, the reason names it: that is a corpus-defect
    finding worth keeping on the tried list, not just another candidate miss."""
    if _year_ok(doc, year):
        return None
    ty = _title_year(_head_text(doc), year)
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
    """Search without filetype:, then harvest annual-report PDF links from the company's own pages among the top hits
    (the press release "X has published its annual report 2025", the IR reports page). Nordea's report is not found by
    a filetype:pdf search but is linked from both. Also tries any company-domain page an MFN release itself links to
    (Lundin Gold's release attaches only its own 2-page release text; the report lives one click away on its IR site) —
    useful even when DDG's bot challenge blocks the search below."""
    toks, name = _toks(company), _name(company)
    pages = list(_mfn_pages(company, year))
    for q in (f"{name} annual report {year}", f"{name} årsredovisning {year}"):
        try:
            s = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(q)).decode("utf-8", "ignore")
        except Exception as e:
            print(f"ddg failed: {e}")
            continue
        for m in re.findall(r'uddg=([^&"]+)', s):
            u = urllib.parse.unquote(m)
            if ".pdf" not in u.lower() and any(t in urllib.parse.urlparse(u).netloc for t in toks) and u not in pages:
                pages.append(u)
    return _harvest(pages, year)


def _candidates(company, year):
    """Candidate PDF URLs, best first: the structured feeds, then (only if those are exhausted) the web — the feeds often carry
    just the press release or the ESEF zip (AstraZeneca, Lundin Gold, SkiStar) while the report sits on the company's site."""
    feeds = list(dict.fromkeys(_mfn(company, year) + _nasdaq(company, year)))[:MAX_TRIES]
    yield from feeds
    yield from [u for u in dict.fromkeys(_crawl(company, year) + _ddg(company, year)) if u not in feeds][:MAX_TRIES]


def find_report(company: str, year: int) -> list[str]:
    return list(_candidates(company, year))


def _validate(data, company, year):
    """(doc, text) if this is a real text-layer annual report *of this company*, else (None, reason)."""
    if not data.startswith(b"%PDF"):
        return None, "not a PDF"
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.page_count <= 40:
        return None, f"only {doc.page_count} pages"
    text = "".join(doc[i].get_text() for i in range(min(20, doc.page_count)))
    if len(text) <= 5000:
        return None, "no text layer"
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    missing = [t for t in _toks(company) if not re.search(rf"\b{re.escape(t)}", plain)]  # "nibe", "abb", "lundin gold" (not Lundin Mining)
    if missing:
        return None, f"issuer mismatch: {missing[0]!r} not in first 20 pages"  # DDG happily returns some other company's report
    if reason := _year_reason(doc, year):  # v122: the year on the first pages or an accounting period, not "anywhere"
        return None, reason
    head = "".join(doc[i].get_text() for i in range(min(3, doc.page_count)))
    if NOT_REPORT.search(head) and not IS_AR.search(head):
        return None, f"not an annual report: {NOT_REPORT.search(head).group(0)!r} on the cover"
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
    """.pdf links on a page that pass the same IS_AR/BAD_URL/NOT_REPORT gate as every other source, scored by
    year + annual-report wording + same-domain-as-the-page (issuers usually host the PDF next to the page that
    links it). Page count -- what actually separates a summary volume from the full report -- only exists once
    a candidate is downloaded; the caller compares that across every harvested survivor."""
    domain = urllib.parse.urlparse(page_url).netloc
    out = {}
    for href, text in re.findall(r'href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
        if ".pdf" not in href.lower():
            continue
        u = urllib.parse.urljoin(page_url, href)
        label = (u + " " + re.sub(r"<[^>]+>", " ", text)).lower()
        if not IS_AR.search(label) or not _filename_clear(label, BAD_URL, NOT_REPORT):
            continue
        out[u] = 2 * (str(year) in label) + bool(re.search(r"annual report|annual review|rsredovisning", label)) \
            + (urllib.parse.urlparse(u).netloc == domain)
    return out


def _crawl_ir_page(start_url, year, deadline):
    """Links scored for a single page, then -- only when the page itself carries nothing -- one hop into
    same-domain sub-pages that read like a reports/investor-relations index (a landing page one click above
    the actual per-year report link)."""
    domain = urllib.parse.urlparse(start_url).netloc
    try:
        html = _get(start_url, timeout=CRAWL_TIMEOUT).decode("utf-8", "ignore")
    except Exception as e:
        return {}, f"IR page crawl {start_url} -> {e}"
    found = _ir_links(start_url, html, year)
    if found or time.time() > deadline:
        return found, None
    hops = []
    for href, text in re.findall(r'href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
        u = urllib.parse.urljoin(start_url, href)
        if ".pdf" in u.lower() or urllib.parse.urlparse(u).netloc != domain or u in hops:
            continue
        if re.search(r"annual.?report|investor|\bir\b|rsredovisning", u + " " + text, re.I):
            hops.append(u)
    for page in hops[:3]:
        if time.time() > deadline:
            break
        try:
            html2 = _get(page, timeout=CRAWL_TIMEOUT).decode("utf-8", "ignore")
        except Exception as e:
            print(f"IR page crawl hop {page} -> {e}")
            continue
        found.update(_ir_links(page, html2, year))
    return found, None


def _ir_page_report(seeds, company, year, tried):
    """Fifth source (v080): crawl candidate IR/report pages for the report PDF itself, at most one hop deep.
    Every harvested link still runs the full download+validate chain, appended to `tried` like every other
    candidate; unlike the earlier sources (first validated survivor wins) this one downloads every harvested
    candidate within budget and keeps the one with the most pages, because the page linking a summary volume
    often links the full report right next to it (Nestlé's Annual Review vs. its actual Annual Report)."""
    deadline = time.time() + CRAWL_BUDGET
    ranked = {}
    for page in seeds[:MAX_CRAWL_SEEDS]:
        if time.time() > deadline:
            break
        found, err = _crawl_ir_page(page, year, deadline)
        if err:
            print(err)
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
            data = _unzip(_get(url, timeout=CRAWL_TIMEOUT))
            doc, text = _validate(data, company, year)
        except Exception as e:
            print(f"{url} -> {e}")
            continue
        if not doc:
            print(f"{url} -> {text}")
            if TITLE_YEAR_MARK in text:  # v122: a cover naming an older year is a finding, not just a miss
                tried.append(text)
            continue
        print(f"{url} -> ok ({doc.page_count} pages, {time.time() - t0:.0f}s, IR page crawl)")
        if not best or doc.page_count > best[3]:
            best = (url, data, text, doc.page_count)
    return best[:3] if best else None


def _entry(fname, company, year, url, text, note=None, tags=("fetched",)):
    low = text.lower()
    return {"file": fname, "company": company, "fiscal_year": year,
            "language": "sv" if low.count("årsredovisning") > low.count("annual report") else "en",
            "source_url": url, "tags": list(tags), "note": note, "fetched_at": dt.date.today().isoformat()}


def _write_index(dest_dir, index):
    s = json.dumps(index, ensure_ascii=False, indent=2)
    s = re.sub(r'\[\s+("[^\]]*?")\s+\]', lambda m: "[" + re.sub(r",\s+", ", ", m.group(1)) + "]", s)  # tags on one line
    (dest_dir / "index.json").write_text(s + "\n", encoding="utf-8")


def fetch_report(company: str, year: int, dest_dir: "Path | None" = None, country: "str | None" = None, hint: "str | None" = None) -> dict:
    """country/hint (v074) only feed the fourth source's prompt; levels 1-3 are name-driven already."""
    dest_dir = Path(dest_dir) if dest_dir is not None else paths.reports_dir()
    fname = f"{slugify(company)}_{year}.pdf"
    index = _load_index(dest_dir)
    for e in index:  # cache hit
        if e["file"] == fname and (dest_dir / fname).exists():
            return {**e, "tried": []}
    tried, toks, stub_pages, page_seeds = [], _toks(company), [], []
    candidates = list(_candidates(company, year))
    i = 0
    while i < len(candidates):
        url = candidates[i]
        i += 1
        tried.append(url)
        t0 = time.time()
        try:
            data = _unzip(_get(url))
            doc, text = _validate(data, company, year)
        except Exception as e:
            print(f"{url} -> {e}")
            page_seeds += [u for u in _host_guesses(url, toks) if u not in page_seeds]  # a dead link: guess its own IR page (v080)
            continue
        if not doc:
            print(f"{url} -> {text}")
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
        print(f"{url} -> ok ({doc.page_count} pages, {time.time() - t0:.0f}s)")
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / fname).write_bytes(data)
        entry = _entry(fname, company, year, url, text)
        index = [e for e in index if e["file"] != fname] + [entry]
        _write_index(dest_dir, index)
        return {**entry, "tried": tried}
    # fourth source: only now, with every feed and web candidate exhausted, and only when the
    # configured provider actually has a web-search tool (websearch_provider's codex/claude gate).
    model_note = None
    if p := websearch_provider():
        urls, model_note = _model_candidates(company, year, country, hint)
        hits = []  # (url, data, text, pages) for every candidate that downloads + validates (v081: rank, don't stop at the first)
        for url in urls:
            if url in tried:
                continue
            tried.append(url)
            t0 = time.time()
            try:
                data = _unzip(_get(url))
                doc, text = _validate(data, company, year)
            except Exception as e:
                print(f"{url} -> {e}")
                page_seeds += [u for u in _host_guesses(url, toks) if u not in page_seeds]  # a dead link: guess its own IR page (v080)
                continue
            if not doc:  # no stub-page harvest here: the model was asked for direct PDF links only
                print(f"{url} -> {text}")
                if TITLE_YEAR_MARK in text:  # v122: a cover naming an older year is a finding, not just a miss
                    tried.append(text)
                if not data.startswith(b"%PDF") and url not in page_seeds:  # the model named a page, not a PDF (v080)
                    page_seeds.append(url)
                continue
            print(f"{url} -> ok ({doc.page_count} pages, {time.time() - t0:.0f}s)")
            hits.append((url, data, text, doc.page_count))
        if hits:
            # v081: prefer the complete report over a summary volume when more than one candidate
            # validated; accept a summary only when nothing among them clears the full-report bar
            url, data, text, pages = _best_model_candidate(hits)
            note = f"model search ({p})" if _is_full_report(url, pages) else f"model search ({p}); summary volume"
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / fname).write_bytes(data)
            entry = _entry(fname, company, year, url, text, note=note, tags=["fetched", "foreign"])
            index = [e for e in index if e["file"] != fname] + [entry]
            _write_index(dest_dir, index)
            return {**entry, "tried": tried}
    # fifth source (v080): only now, with feeds/web/model all exhausted, crawl whatever page-shaped
    # leftovers those attempts produced (an IR page the model named directly, a DDG hit that served a
    # page instead of a PDF, or the guessed IR path for a direct link's own domain after it 404d).
    if page_seeds and (found := _ir_page_report(page_seeds, company, year, tried)):
        url, data, text = found
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / fname).write_bytes(data)
        entry = _entry(fname, company, year, url, text, note="IR page crawl", tags=["fetched", "foreign"])
        index = [e for e in index if e["file"] != fname] + [entry]
        _write_index(dest_dir, index)
        return {**entry, "tried": tried}
    # second ask (v081): only now, with the fourth source's direct links AND the fifth source's own
    # generic IR-path guesses both exhausted, ask the model once more -- this time only for the IR/
    # annual-report-archive page itself -- and crawl it the same way (at most 2 model calls total).
    if p:
        ir_urls, ir_note = _ir_page_candidates(company, year, country, hint)
        new_seeds = [u for u in ir_urls if u not in page_seeds]
        if new_seeds and (found := _ir_page_report(new_seeds, company, year, tried)):
            url, data, text = found
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / fname).write_bytes(data)
            entry = _entry(fname, company, year, url, text, note="IR page crawl", tags=["fetched", "foreign"])
            index = [e for e in index if e["file"] != fname] + [entry]
            _write_index(dest_dir, index)
            return {**entry, "tried": tried}
        if ir_note:
            model_note = f"{model_note}; {ir_note}" if model_note else ir_note
    raise LookupError(tried, model_note)


if __name__ == "__main__":
    print(json.dumps(fetch_report(sys.argv[1], int(sys.argv[2])), ensure_ascii=False, indent=2))
