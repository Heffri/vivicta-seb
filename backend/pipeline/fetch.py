"""Find + download a company's annual report PDF into data/reports/ (the cache) and register it in index.json.
Sources, cheapest first: MFN feed (aggregates Cision too), then DuckDuckGo html with filetype:pdf.
CLI: python -m pipeline.fetch "Boliden" 2025"""
import datetime as dt
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
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


def slugify(name):
    name = re.sub(r"\(publ\)|\bAB\b|\bLtd\.?\b|\bplc\b|\bGroup\b|\bCompany\b|\bser\.? ?[A-D]\b|\s[A-D]$", "", name, flags=re.I)  # "ABB Ltd"/"Telia Company" -> curated stems
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


def _mfn(company, year):
    q = urllib.parse.quote
    try:
        hits = json.loads(_get(f"https://mfn.se/search/companies?limit=5&query={q(company)}"))
    except Exception as e:
        print(f"mfn company search failed: {e}")
        return []
    if not hits:
        return []
    slug = hits[0]["slug"]
    items = []
    for query in (f"annual report {year}", f"årsredovisning {year}"):
        try:
            items += json.loads(_get(f"https://mfn.se/all/a/{slug}.json?limit=30&query={q(query)}"))["items"]
        except Exception as e:
            print(f"mfn feed failed: {e}")
    scored = []
    for it in items:
        c, t = it["content"], it["content"]["title"]
        if not IS_AR.search(t) or NOT_AR.search(t) or str(year) not in t:
            continue
        for a in c.get("attachments", []):
            u = a["url"]
            if not (a.get("content_type") == "application/pdf" or u.lower().endswith(".pdf")):
                continue
            s = (it["properties"].get("lang") == "en") * 2 - ("/Public/" in u) * 3  # release PDF, not the report
            s += 2 * bool(re.search(rf"annual|ar|{year}", u.rsplit("/", 1)[-1], re.I))
            scored.append((s, u))
    return [u for _, u in sorted(scored, key=lambda x: -x[0])]


def _nasdaq(company, year):
    """Nasdaq Nordic company news: every listed issuer's "Annual Financial Report" notice carries the PDF as an attachment
    (TRATON, Asker, Vitrolife ... also the ESEF zip, unused). MFN covers most Swedish issuers; this covers the rest."""
    tok = next((t for t in slugify(company).split("_") if len(t) >= 3), company.lower())
    q = urllib.parse.urlencode({"type": "json", "showAttachments": "true", "showCnsSpecific": "true", "showCompany": "true", "countResults": "false",
                                "freeText": company, "cnscategory": "Annual Financial Report", "globalGroup": "exchangeNotice",
                                "globalName": "NordicMainMarkets", "displayLanguage": "en", "limit": 30, "start": 0, "dir": "DESC"})
    try:
        items = json.loads(_get("https://api.news.eu.nasdaq.com/news/query.action?" + q))["results"]["item"]
    except Exception as e:
        print(f"nasdaq news failed: {e}")
        return []
    scored = []
    for it in items:
        names = " ".join(a.get("fileName", "") for a in it.get("attachment", []))
        if tok not in it.get("company", "").lower() or NOT_AR.search(it.get("headline", "")):
            continue
        if str(year) not in it.get("headline", "") + names and not it.get("published", "").startswith(str(year + 1)):
            continue  # the report for FY2025 is published in 2026
        for a in it.get("attachment", []):
            n = a.get("fileName", "")
            if a.get("mimetype") != "application/pdf" or BAD_URL.search(n) or re.search(r"press|release|meddelande", n, re.I):
                continue
            sc = 3 * bool(IS_AR.search(n)) + (str(year) in n) + (it.get("language") == "en")
            scored.append((sc, a["attachmentUrl"]))
    return [u for _, u in sorted(scored, key=lambda x: -x[0])]


def _ddg(company, year):
    tok = slugify(company).split("_")[0]
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
            sc += 2 * (tok in urllib.parse.urlparse(u).netloc) - 5 * bool(BAD_URL.search(l))
            out[u] = sc
    return [u for u, _ in sorted(out.items(), key=lambda x: -x[1])]


def _crawl(company, year):
    """Search without filetype:, then harvest annual-report PDF links from the company's own pages among the top hits
    (the press release "X has published its annual report 2025", the IR reports page). Nordea's report is not found by
    a filetype:pdf search but is linked from both."""
    tok = slugify(company).split("_")[0]
    pages = []
    for q in (f"{company} annual report {year}", f"{company} årsredovisning {year}"):
        try:
            s = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(q)).decode("utf-8", "ignore")
        except Exception as e:
            print(f"ddg failed: {e}")
            continue
        for m in re.findall(r'uddg=([^&"]+)', s):
            u = urllib.parse.unquote(m)
            if ".pdf" not in u.lower() and tok in urllib.parse.urlparse(u).netloc and u not in pages:
                pages.append(u)
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


def find_report(company: str, year: int) -> list[str]:
    """Candidate PDF URLs, best first."""
    urls = _mfn(company, year) + _nasdaq(company, year)  # structured feeds first, web search only when neither knows the issuer
    if not urls:
        urls = _crawl(company, year) + _ddg(company, year)
    return list(dict.fromkeys(urls))


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
    tok = next((t for t in slugify(company).split("_") if len(t) >= 3), company.lower())  # "nibe", "abb", "volvo"
    if not re.search(rf"\b{re.escape(tok)}", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()):
        return None, f"issuer mismatch: {tok!r} not in first 20 pages"  # DDG happily returns some other company's report
    if str(year) not in text:
        return None, f"{year} not in first 20 pages"
    head = "".join(doc[i].get_text() for i in range(min(3, doc.page_count)))
    if NOT_REPORT.search(head) and not IS_AR.search(head):
        return None, f"not an annual report: {NOT_REPORT.search(head).group(0)!r} on the cover"
    return doc, text


def _load_index():
    return json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else []


def fetch_report(company: str, year: int, dest_dir=REPORTS) -> dict:
    dest_dir = Path(dest_dir)
    fname = f"{slugify(company)}_{year}.pdf"
    index = _load_index()
    for e in index:  # cache hit
        if e["file"] == fname and (dest_dir / fname).exists():
            return {**e, "tried": []}
    tried = []
    for url in find_report(company, year)[:MAX_TRIES]:
        tried.append(url)
        t0 = time.time()
        try:
            data = _get(url)
            doc, text = _validate(data, company, year)
        except Exception as e:
            print(f"{url} -> {e}")
            continue
        if not doc:
            print(f"{url} -> {text}")
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
