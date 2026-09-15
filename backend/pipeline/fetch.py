"""Find + download a company's annual report PDF into data/reports/ (the cache) and register it in index.json.
Sources, cheapest first: MFN feed (aggregates Cision too) and Nasdaq notices, then the web (DuckDuckGo html) when the
feeds only carried press releases or ESEF zips (AstraZeneca, Lundin Gold, SkiStar).
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

REPORTS = Path(__file__).resolve().parents[2] / "data" / "reports"
INDEX = REPORTS / "index.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
MAX_TRIES = 6
NOT_AR = re.compile(r"general meeting|st[äa]mma|notice|kallelse|nomination|valberedning|20-f|interim|delårs|quarter", re.I)
IS_AR = re.compile(r"annual|årsredovisning|års- och", re.I)
# a PDF that is not *the* annual report even though the search matched: Nordea's Pillar 3 report, AGM decks, quarterlies
BAD_URL = re.compile(r"interim|q[1-4]\b|quarter|delars|half-?year|risk|pillar|remuneration|ersattning|sustainab|hallbarhet|governance|bolagsstyrning|presentation|agm|stamma|prospect", re.I)
NOT_REPORT = re.compile(r"capital and risk management|pillar 3|remuneration report|sustainability (report|statement)|corporate governance report|prospectus|interim report|half-year|year-end report|bokslutskommunik", re.I)


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
    if str(year) not in text:
        return None, f"{year} not in first 20 pages"
    head = "".join(doc[i].get_text() for i in range(min(3, doc.page_count)))
    if NOT_REPORT.search(head) and not IS_AR.search(head):
        return None, f"not an annual report: {NOT_REPORT.search(head).group(0)!r} on the cover"
    return doc, text


def _load_index():
    return json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else []


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
    return [f"https://{h}{path}" for h in hosts for path in
            ("/investor-relations/annual-report.html", "/investor-relations.html", "/en/investors", "/investors", "/")]


def fetch_report(company: str, year: int, dest_dir=REPORTS) -> dict:
    dest_dir = Path(dest_dir)
    fname = f"{slugify(company)}_{year}.pdf"
    index = _load_index()
    for e in index:  # cache hit
        if e["file"] == fname and (dest_dir / fname).exists():
            return {**e, "tried": []}
    tried, toks, stub_pages = [], _toks(company), []
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
            continue
        if not doc:
            print(f"{url} -> {text}")
            if data.startswith(b"%PDF"):  # not a download error: a page an RNS-style notice may name its own site on
                stub_pages += [u for u in _stub_pages(data, toks) if u not in stub_pages]
            if i == len(candidates) and stub_pages:  # every direct candidate failed: try the issuer's own site (AstraZeneca)
                candidates += [u for u in _harvest(stub_pages, year) if u not in candidates]
                stub_pages = []
            continue
        print(f"{url} -> ok ({doc.page_count} pages, {time.time() - t0:.0f}s)")
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / fname).write_bytes(data)
        low = text.lower()
        entry = {"file": fname, "company": company, "fiscal_year": year,
                 "language": "sv" if low.count("årsredovisning") > low.count("annual report") else "en",
                 "source_url": url, "tags": ["fetched"], "note": None, "fetched_at": dt.date.today().isoformat()}
        index = [e for e in index if e["file"] != fname] + [entry]
        s = json.dumps(index, ensure_ascii=False, indent=2)
        s = re.sub(r'\[\s+("[^\]]*?")\s+\]', lambda m: "[" + re.sub(r",\s+", ", ", m.group(1)) + "]", s)  # tags on one line
        INDEX.write_text(s + "\n", encoding="utf-8")
        return {**entry, "tried": tried}
    raise LookupError(tried)


if __name__ == "__main__":
    print(json.dumps(fetch_report(sys.argv[1], int(sys.argv[2])), ensure_ascii=False, indent=2))
