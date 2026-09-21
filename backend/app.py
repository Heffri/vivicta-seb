"""SEB annual-report parser, backend. The contract is docs/API.md; change it there first."""
import argparse
import copy
import datetime
import threading
import csv
import io
import json
import logging
import math
import os
import re
import statistics
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pymupdf
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, FiniteFloat
from typing import Literal
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from pipeline import extract as extract_mod, fetch, kb, llm, locate, parse, paths, ppt, collection, workbench

load_dotenv()
UPLOADS = paths.uploads_dir()
SCHEMAS = paths.schemas_dir()
LIBRARY = paths.reports_dir()  # bundled reports; index.json is committed, PDFs via `python data/fetch.py`
def _llm_configured() -> bool:
    """A model answers /extract when an OpenAI-compatible endpoint is set, or when the Codex or Claude CLI provider
    is selected (v031: LLM_PROVIDER=codex needs no base URL; v039: same for claude). /ask runs on that model too:
    since v034 its retrieval falls back to pure BM25 without LLM_BASE_URL (kb.retrieval_mode()), and /index then
    reports keyword-only chunks instead of embedding anything."""
    return bool(os.getenv("LLM_BASE_URL")) or llm.provider() in ("codex", "claude")


FIXTURE = paths.fixture_path()
COMPANIES = json.loads(paths.companies_path().read_text(encoding="utf-8"))  # Nasdaq Stockholm, data/companies_build.py
CSV_HEADER = "report_id,company,fiscal_year,section,key,label,value,unit,period,raw_label,page,quote,confidence".split(",")

app = FastAPI(title="vivicta backend")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

reports: dict[str, dict] = {}      # ponytail: in-memory, add sqlite if restarts must survive
extractions: dict[str, dict] = {}  # report_id -> last Extraction
library_paths: dict[str, Path] = {}  # report_id -> PDF in data/reports/ (library reports are served in place, not copied)
library_pages: dict[str, int] = {}   # file -> page_count, for GET /api/library
texts_cache: dict[str, list[str]] = {}  # ponytail: page texts per report, unbounded; Saab is 231 pages, fine for a demo


@app.exception_handler(parse.OCRUnavailable)
async def ocr_unavailable(_request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


class ExtractBody(BaseModel):
    force: bool = False
    reuse_saved: bool = False
    section: str


class FillBody(BaseModel):
    field: str = Field(pattern=r"^[a-z0-9_]+$")
    pages: list[int] = Field(min_length=1, max_length=2)


class ReviewComponent(BaseModel):
    value: FiniteFloat
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=8000)
    label: str = Field(default="", max_length=160)


class ReviewBody(BaseModel):
    section: str = Field(pattern=r"^[a-z0-9_]+$")
    key: str
    expected: dict
    decision: Literal["confirmed", "corrected", "unresolved"]
    reviewer: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)
    value: FiniteFloat | str | None = None
    unit: str | None = Field(default=None, max_length=80)
    period: str | None = Field(default=None, max_length=80)
    source_page: int | None = Field(default=None, ge=1)
    source_quote: str | None = Field(default=None, max_length=8000)
    components: list[ReviewComponent] | None = Field(default=None, max_length=50)


class BasisBody(BaseModel):
    section: str = Field(pattern=r"^[a-z0-9_]+$")
    expected: dict
    values: dict[str, str]
    reviewer: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=2000)


review_lock = threading.Lock()  # Local file store: serialize review read/modify/write.


class LibraryBody(BaseModel):
    file: str


class AskBody(BaseModel):
    question: str
    report_ids: list[str] | None = None
    report_stems: list[str] | None = None


class FetchBody(BaseModel):
    download_pdf: bool = False
    company: str
    year: int
    country: str | None = None  # v074: optional context for the model search when the directory has no hit ("Switzerland")
    hint: str | None = None     # v074: free-text hint for the model search ("FY ends 30 June", the report's exact title)


def pdf_path(report_id: str) -> Path:
    return library_paths.get(report_id) or UPLOADS / f"{report_id}.pdf"


def report_texts(report_id: str) -> list[str]:
    if report_id not in texts_cache:
        if pdf_path(report_id).is_file():
            stem = report_id[4:] if report_id.startswith("lib-") else report_id
            digest = kb.sha256(pdf_path(report_id).read_bytes())
            texts_cache[report_id], parsing = kb.load_texts(stem, pdf_path(report_id), digest)
            if kb._meta(stem):
                kb.save_report(stem, kb._meta(stem) | parsing | {"sha256": digest, "pages": len(texts_cache[report_id])}, texts_cache[report_id])
        else:
            report = get_report(report_id)
            pages = kb._pages(report["stem"])
            texts_cache[report_id] = [pages.get(n, "") for n in range(1, report["pages"] + 1)]
    return texts_cache[report_id]


def fill_texts(report_id: str) -> list[str]:
    """Read a fill window without registering or rewriting a report in the knowledge base."""
    if report_id in texts_cache:
        return texts_cache[report_id]
    report = get_report(report_id)
    saved_pages_path = kb.kb_dir() / report["stem"] / "pages.jsonl"
    if saved_pages_path.is_file():
        pages = kb._pages(report["stem"])
        texts = [pages.get(n, "") for n in range(1, report["pages"] + 1)]
    elif pdf_path(report_id).is_file():
        texts = parse.page_texts(pdf_path(report_id))
    else:
        raise HTTPException(404, "No saved page text is available for this report")
    texts_cache[report_id] = texts
    return texts


def library_index() -> list[dict]:
    """index.json entries whose PDF is actually on disk."""
    index = LIBRARY / "index.json"
    if not index.is_file():
        return []  # an isolated ARP_DATA_DIR starts with an empty report cache
    entries = json.loads(index.read_text(encoding="utf-8"))
    return [e for e in entries if (LIBRARY / e["file"]).exists()]


def get_report(report_id: str) -> dict:
    if report_id not in reports:
        stem = report_id[4:] if report_id.startswith("lib-") else report_id
        if re.fullmatch(r"[a-z0-9_-]+", stem) and report_id == saved_report_id(stem) and (kb.kb_dir() / stem / "meta.json").is_file() and (kb.kb_dir() / stem / "pages.jsonl").is_file():
            meta = kb._meta(stem)
            filename = meta.get("filename") or f"{stem}.pdf"
            # Saved metadata is not allowed to choose a file outside the PDF cache.
            if isinstance(filename, str) and Path(filename).name == filename and "/" not in filename and "\\" not in filename:
                cached = LIBRARY / filename
                if not stem.startswith("up-") and cached.is_file():
                    library_paths[report_id] = cached
            reports[report_id] = {"report_id": report_id, "filename": filename, "pages": meta.get("pages", 0),
                                  "company": meta.get("company"), "fiscal_year": meta.get("fiscal_year"), "stem": stem}
    if report_id not in reports:
        raise HTTPException(404, f"unknown report_id {report_id!r}")
    return reports[report_id]


def saved_report_id(stem: str) -> str:
    return stem if stem.startswith("up-") else "lib-" + stem


def require_pdf(report_id: str) -> Path:
    get_report(report_id)
    path = pdf_path(report_id)
    if not path.is_file():
        raise HTTPException(409, "The PDF is no longer cached. Saved page text is available in the knowledge base; fetch the PDF again to view it.")
    return path


def load_schema(name: str) -> dict:
    path = SCHEMAS / f"{name}.json"
    if not re.fullmatch(r"[a-z0-9_]+", name) or not path.exists():
        raise HTTPException(404, f"unknown section {name!r}; see GET /api/schemas")
    return json.loads(path.read_text(encoding="utf-8"))


def guess_meta(texts: list[str]) -> tuple[str | None, int | None]:
    """Best-effort company + fiscal year from the first 3 pages; None when unsure.
    # ponytail: two regexes; ask the LLM about the cover page if this is too dumb."""
    raw = "\n".join(texts[:3])
    head = re.sub(r"\s+", " ", raw)  # not normalize_ws: that one glues digits to words
    co = r"([A-ZÅÄÖ][\w&.-]*(?: [A-ZÅÄÖ&][\w&.-]*){0,4} (?:AB|plc|PLC|ASA|Oyj|A/S|Ltd|Inc)\b(?: \(publ\))?)"
    company = re.search(rf"^[ \t]*{co}[ \t]*$", raw, re.M) or re.search(rf"\b{co}", head)  # own line first, then anywhere
    report = r"(?:annual\D{0,30}?report|årsredovisning)"
    year = re.search(rf"{report}\D{{0,40}}?(20\d\d)\b|\b(20\d\d) {report}", head, re.I)
    return (company.group(1) if company else None), (int(year.group(1) or year.group(2)) if year else None)


@app.get("/api/schemas")
def list_schemas():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SCHEMAS.glob("*.json"))]


@app.post("/api/reports")
async def upload_report(file: UploadFile = File(...)):
    data = await file.read()
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            assert doc.is_pdf and doc.page_count > 0
    except Exception:
        raise HTTPException(400, "file is not a readable PDF")
    sha = kb.sha256(data)
    cached = next((e for e in library_index() if e.get("sha256") == sha or (LIBRARY / e["file"]).stat().st_size == len(data) and kb.sha256((LIBRARY / e["file"]).read_bytes()) == sha), None)
    if cached:  # same bytes as a cached report: reuse its stem, so the KB gets no duplicate and few-shot excludes it correctly
        return await run_in_threadpool(register_library, cached)
    report_id = "up-" + sha[:12]  # deterministic: same upload twice = same report + same KB folder
    if report_id in reports:
        return reports[report_id]
    pdf_path(report_id).write_bytes(data)
    texts, parsing = await run_in_threadpool(kb.load_texts, report_id, pdf_path(report_id), sha)
    texts_cache[report_id] = texts
    company, fiscal_year = guess_meta(texts)
    reports[report_id] = {"report_id": report_id, "filename": file.filename or "upload.pdf", "pages": len(texts), "company": company, "fiscal_year": fiscal_year, "stem": report_id}
    kb.save_report(report_id, {"company": company, "fiscal_year": fiscal_year, "language": None, "source_url": None, "pages": len(texts),
                               "sha256": sha, "filename": reports[report_id]["filename"]} | parsing, texts)  # ponytail: uploads land in data/kb/up-<sha>/ too; prune before committing if they are not public reports
    return reports[report_id]


@app.get("/api/library")
def list_library(collection_name: Literal["all", "wallenberg", "midcap"] = "all"):
    in_scope = collection.scope(collection_name)
    out = []
    for e in library_index():
        if not in_scope(e.get("company")):
            continue
        if e["file"] not in library_pages:
            with pymupdf.open(LIBRARY / e["file"]) as doc:
                library_pages[e["file"]] = doc.page_count
        out.append(e | {"pages": library_pages[e["file"]]})
    return out


def register_library(entry: dict) -> dict:
    """Register a cached PDF (curated or fetched) exactly like an upload; same file twice = same report_id."""
    report_id = "lib-" + Path(entry["file"]).stem
    path = LIBRARY / entry["file"]
    if report_id not in reports or library_paths.get(report_id) != path:
        library_paths[report_id] = path
        texts_cache.pop(report_id, None)  # a restored text-only report must now read the fetched PDF
        digest = kb.sha256(path.read_bytes())
        texts, parsing = kb.load_texts(path.stem, path, digest)
        texts_cache[report_id] = texts
        reports[report_id] = {"report_id": report_id, "filename": entry["file"], "pages": len(texts),
                              "company": entry["company"], "fiscal_year": entry["fiscal_year"], "stem": Path(entry["file"]).stem}  # curated beats guess_meta
        kb.save_report(Path(entry["file"]).stem, {k: entry.get(k) for k in ("company", "fiscal_year", "language", "source_url")}
                       | {"pages": len(texts), "sha256": digest, "filename": entry["file"]} | parsing, texts)
    return reports[report_id]


@app.post("/api/reports/from-library")
def report_from_library(body: LibraryBody):
    entry = next((e for e in library_index() if e["file"] == body.file), None)
    if not entry or "/" in body.file or "\\" in body.file:  # trust boundary: index basenames only, never a path
        raise HTTPException(404, f"not in library: {body.file!r}; see GET /api/library")
    return register_library(entry)


@app.get("/api/companies")
def list_companies(q: str = "", collection_name: Literal["all", "wallenberg", "midcap"] = "all"):
    cached: dict[str, list[int]] = {}
    for e in library_index():
        cached.setdefault(collection.identity(e["company"]), []).append(e["fiscal_year"])
    q = q.strip().lower()
    directory = collection.directory(COMPANIES, collection_name)
    hits = [c for c in directory if q in c["name"].lower() or q in c["ticker"].lower()]
    hits.sort(key=lambda c: (not c["name"].lower().startswith(q), c["name"]))  # prefix matches first
    return [c | {"cached_years": sorted(set(cached.get(collection.identity(c["name"]), [])))} for c in hits[:50]]


@app.post("/api/reports/fetch")
def fetch_report(body: FetchBody):
    if not (1990 <= body.year <= 2100) or len(body.company) > 100 or (body.country and len(body.country) > 60) or (body.hint and len(body.hint) > 300):
        raise HTTPException(400, "bad company/year")
    slug = fetch.slugify(body.company)
    if not body.download_pdf:
        saved = [e for e in kb.entries() if e.get("fiscal_year") == body.year and collection.identity(e.get("company")) == collection.identity(body.company)]
        if saved:
            saved.sort(key=lambda e: (e["stem"] != f"{slug}_{body.year}", e["stem"]))
            return get_report(saved_report_id(saved[0]["stem"]))
    entry = next((e for e in library_index() if e["fiscal_year"] == body.year and collection.identity(e["company"]) == collection.identity(body.company)), None)
    if not entry:
        if not body.download_pdf:
            raise HTTPException(409, "No saved report text or local PDF for this company and year. Enable PDF download explicitly or upload your own report.")
        t0 = time.time()
        try:
            # The connected model searches official sources first; feeds are fallback discovery.
            entry = fetch.fetch_report(body.company, body.year, LIBRARY, body.country, body.hint)
        except LookupError as e:
            detail = f"no annual report found for {body.company} {body.year}"
            if len(e.args) > 1 and e.args[1]:  # v074: a failed model search says so, with why
                detail += f"; {e.args[1]}"
            return JSONResponse({"detail": detail, "tried": e.args[0]}, status_code=404)
        print(f"[fetch] {body.company} {body.year} -> {entry['file']} from {entry['source_url']} in {time.time() - t0:.0f}s")
    return register_library(entry)


@app.get("/api/reports/{report_id}")
def read_report(report_id: str):
    return get_report(report_id)


@app.get("/api/reports/{report_id}/pdf")
def report_pdf(report_id: str):
    report = get_report(report_id)  # FileResponse handles Range, so the browser viewer can seek
    return FileResponse(require_pdf(report_id), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{report["filename"]}"'})


@app.get("/api/reports/{report_id}/pages/{n}.png")
def page_png(report_id: str, n: int):
    report = get_report(report_id)
    if not 1 <= n <= report["pages"]:
        raise HTTPException(404, f"page {n} out of range 1..{report['pages']}")
    with pymupdf.open(require_pdf(report_id)) as doc:
        png = doc[n - 1].get_pixmap(dpi=150).tobytes("png")
    return Response(png, media_type="image/png")


NUMBER_TOKEN = re.compile(r"\d[\d\s   .,']*\d|\d")  # a printed number, same separator set as frontend/verification.ts's THOUSANDS


@app.get("/api/reports/{report_id}/pages/{n}/locate")
def page_locate(report_id: str, n: int, quote: str = Query(min_length=1)):
    """Zero-model (v179, consult item 12): where on the rendered page does this citation's quote
    sit? `page.search_for` on the verbatim quote first; a citation that never prints as one
    contiguous run (a wrapped table row) degrades to its own longest line, then to the longest
    digit run inside it (the shape a value alone would print as). `rects` are page-point boxes --
    the same top-down space page_png renders -- one per printed *line* a hit touches: MuPDF reports
    a match spanning two lines (an ordinary wrapped citation) as two adjacent rects, exactly like a
    genuine second, unrelated occurrence would add two more -- measured directly (a 2-line phrase
    printed twice returns 4 rects). `occurrences` divides that back out by the searched string's own
    line count, so a wrapped citation still reports 1 while a truly repeated line reports 2+; the
    frontend's "N matches" badge reads `occurrences`, not `len(rects)`, and every rect is still drawn
    either way. No PDF or nothing found leaves the page unframed."""
    report = get_report(report_id)
    if not 1 <= n <= report["pages"]:
        raise HTTPException(404, f"page {n} out of range 1..{report['pages']}")
    with pymupdf.open(require_pdf(report_id)) as doc:
        page = doc[n - 1]
        matched, searched, rects = "quote", quote, page.search_for(quote)
        if not rects:
            searched = max((l.strip() for l in quote.splitlines()), key=len, default="")
            matched, rects = "line", (page.search_for(searched) if searched else [])
        if not rects:
            searched = max(NUMBER_TOKEN.findall(quote), key=len, default="")
            matched, rects = "value", (page.search_for(searched) if searched else [])
        if not rects:
            matched, searched = "none", ""
        lines = searched.count("\n") + 1 if searched else 1
        occurrences = len(rects) // lines if lines > 1 and rects and len(rects) % lines == 0 else len(rects)
        return {"page": n, "width": page.rect.width, "height": page.rect.height, "matched": matched,
                "rects": [[r.x0, r.y0, r.x1, r.y1] for r in rects], "occurrences": occurrences}


@app.get("/api/reports/{report_id}/candidates")
def report_candidates(report_id: str, section: str = Query(min_length=1)):
    """Ranked candidate pages for a section (v164): the same deterministic locator the extractor
    runs (locate.candidate_pages), served before the model so the waiting UI can name the pages
    being read. No model call -- fixture mode computes them from the real page text like any other.
    heading = the page's de-boilerplated opening, whitespace-normalized (a peeks-at-the-page line)."""
    report = get_report(report_id)
    schema = load_schema(section)
    texts = report_texts(report_id)
    stripped = locate.strip_boilerplate(texts)
    return [{"page": page, "heading": " ".join(stripped[page - 1].split())[:80]}
            for page in locate.candidate_pages(texts, schema)]


@app.post("/api/reports/{report_id}/extract")
def run_extract(report_id: str, body: ExtractBody):
    report = get_report(report_id)
    with kb.report_lock(report["stem"], "extract"):
        schema = load_schema(body.section)
        identity = extraction_identity(report, schema, extract_mod.system_prompt(schema, report["stem"]))
        path = kb.kb_dir() / report["stem"] / "extractions" / f"{body.section}.json"
        if not body.force and path.is_file():
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                saved = None
            if isinstance(saved, dict) and (body.reuse_saved or saved.get("cache_key") == identity):
                return kb_extraction(report["stem"], body.section)
        return _run_extract(report_id, body)


def _run_extract(report_id: str, body: ExtractBody):
    started = time.perf_counter()
    report = get_report(report_id)
    schema = load_schema(body.section)
    saved = kb.kb_dir() / report["stem"] / "extractions" / f"{body.section}.json"
    if saved.exists() and has_reviews(saved_extraction(report_id, body.section)):
        raise HTTPException(409, "This section has human reviews. Keep the reviewed extraction instead of replacing it.")
    if not _llm_configured():  # frontend dev mode: no model configured
        # v164: the requested section overrides the fixture payload's own (an income-statement
        # sample) -- the UI reads extraction.section to re-locate the report (the not-found banner's
        # candidates call), and that must name the section the user actually ran.
        result = json.loads(FIXTURE.read_text(encoding="utf-8")) | {"report_id": report_id, "section": body.section}
    else:
        texts = report_texts(report_id)
        pages = locate.candidate_pages(texts, schema, fiscal_year=report.get("fiscal_year"))
        print(f"[extract] {report_id} {body.section}: candidate pages {pages}")
        if not pages:
            raise HTTPException(422, "No candidate pages found for this section")
        hints_retry = os.getenv("PAGE_SELECT_HINTS") == "retry"
        # v162: retry starts from the ordinary page-selection prompt even though the same request
        # may later selectively retry with markers.  Other values retain extract()'s old env read.
        result = extract_mod.extract(texts, pages, schema, report, page_select_hints=False) if hints_retry             else extract_mod.extract(texts, pages, schema, report)
        failures = [w for w in result["warnings"] if w.startswith("llm:")]
        if failures and not any(f.get("value") is not None for f in result["fields"]):
            raise HTTPException(502, " ".join(failures))
        from pipeline import merge  # v133: EXTRACT_MERGE_RUNS second-run merge; off (default) never reaches it
        mode = merge.mode()
        if mode != "off":  # docs/acrylic/evidence/v129.md: per-field union, the stored answer as a third majority vote
            stored = None
            if mode == "majority":
                saved_json = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else None
                # v129: the pipeline's own earlier answer votes; a reviewed extraction must not (and the
                # 409 gate above already refuses to re-extract one -- this is defense in depth).
                stored = None if saved_json is None or has_reviews(saved_json) else saved_json
            if mode == "majority" and stored is not None and merge.matches_stored(result, stored):
                result["warnings"].append("merge: run1 matches the stored answer field by field; second run skipped")
                result["merge"] = {"mode": mode, "runs": 1, "decisions": {f["key"]: "run1 (matches stored)" for f in result["fields"]}}
            else:
                field_values = {f.get("key"): f.get("value") for f in result.get("fields", []) if isinstance(f, dict)}
                first_identity_name = next((c.get("name") for c in schema.get("checks", []) if c.get("identity")),
                                           (schema.get("checks") or [{}])[0].get("name"))
                first_identity = next((c for c in result.get("checks", [])
                                       if c.get("name") == first_identity_name), None)
                retry_with_hints = hints_retry and (
                    not bool(first_identity and first_identity.get("passed"))
                    or any(field_values.get(sf["key"]) is None for sf in schema.get("fields", []))
                )
                run2 = extract_mod.extract(texts, pages, schema, report, page_select_hints=True) if retry_with_hints                     else extract_mod.extract(texts, pages, schema, report, page_select_hints=False) if hints_retry                     else extract_mod.extract(texts, pages, schema, report)
                combined_timings = {key: result.get("timings", {}).get(key, 0) + run2.get("timings", {}).get(key, 0) for key in ("model", "validate", "attempts")}
                kb.save_run(report["stem"], body.section, 1, result)  # the raw per-run answers, before decorate
                kb.save_run(report["stem"], body.section, 2, run2)
                result, decisions = merge.merge_runs(result, run2, stored, mode)
                result["timings"] = combined_timings
                if retry_with_hints:
                    result["merge"]["hints"] = "run2"
                merge.recheck(result, schema, texts, pages)  # the winner's own checks would misdescribe a field mix
            print(f"[extract] {report_id} {body.section}: merge={mode} runs={result['merge']['runs']}")
        failures = [w for w in result["warnings"] if w.startswith("llm:")]
        if failures and not any(f.get("value") is not None for f in result["fields"]):
            raise HTTPException(502, " ".join(failures))
        ocr_pages = set(kb._meta(report["stem"]).get("ocr_pages", []))
        if ocr_pages:
            result["warnings"].append("This report contains OCR text. Verify figures against the original PDF.")
            for field in result["fields"]:
                sources = [field.get("source")] + [c.get("source") for c in field.get("components", [])]
                if any(source and source.get("page") in ocr_pages for source in sources):
                    field["confidence"] = min(field.get("confidence", 0), 0.8)
                    field.setdefault("evidence", []).append("ocr_text")
        result.update(cache_key=extraction_identity(report, schema, extract_mod.system_prompt(schema, report["stem"])),
                      cached=False, model=os.getenv("LLM_MODEL"), provider=llm.provider())
        result.setdefault("timings", {})["total"] = round(time.perf_counter() - started, 3)
        result.update(stem=report["stem"], pdf_available=pdf_path(report_id).is_file())
        workbench.decorate(result, schema, {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "reason": "Recalculated explicit values after extraction"})
        with review_lock:
            if saved.exists() and has_reviews(json.loads(saved.read_text(encoding="utf-8"))):
                raise HTTPException(409, "A human review was saved during extraction. The reviewed result was preserved.")
            kb.save_extraction(report["stem"], body.section, result)  # fixture results never enter the KB
    extractions[report_id] = result
    return result


@app.post("/api/reports/{report_id}/fill")
def fill_field(report_id: str, body: FillBody, section: str = Query(pattern=r"^[a-z0-9_]+$")):
    """Return one analyst-directed candidate without changing the stored extraction.

    This is intentionally not a smaller `/extract`: the analyst chooses the complete one- or
    two-page window, so locator ranking and pass-one page selection cannot substitute another
    disclosure. Acceptance remains an ordinary, stale-checked human review.
    """
    report = get_report(report_id)
    schema = load_schema(section)
    current = saved_extraction(report_id, section)
    if has_reviews(current):
        raise HTTPException(409, "This section has human reviews. Keep the reviewed extraction instead of replacing it.")
    schema_fields = {field["key"] for field in schema["fields"]}
    if body.field not in schema_fields:
        raise HTTPException(422, f"Unknown field {body.field!r} for section {section!r}")
    current_field = next((field for field in current["fields"] if field.get("key") == body.field), None)
    if current_field is None or current_field.get("value") is not None:
        raise HTTPException(422, "Analyst-directed fill is only available for an empty field")
    if len(set(body.pages)) != len(body.pages):
        raise HTTPException(422, "Choose one or two distinct evidence pages")
    if not _llm_configured():
        raise HTTPException(422, "Demo mode does not support targeted field fill. Configure a model to read the selected page.")
    texts = fill_texts(report_id)
    if any(page < 1 or page > len(texts) for page in body.pages):
        raise HTTPException(422, "An evidence page is outside this report")
    result = extract_mod.extract(texts, body.pages, schema, report, fixed_pages=True)
    warnings = list(result.get("warnings", []))
    candidate = next((copy.deepcopy(field) for field in result.get("fields", [])
                      if isinstance(field, dict) and field.get("key") == body.field), None)
    source = candidate.get("source") if candidate else None
    source_page = source.get("page") if isinstance(source, dict) else None
    source_quote = source.get("quote") if isinstance(source, dict) else None
    if candidate is None or candidate.get("value") is None:
        candidate = None
        warnings.append(f"{body.field}: no value read from the supplied pages")
    elif not isinstance(source_page, int) or source_page not in body.pages:
        candidate = None
        warnings.append(f"{body.field}: candidate source is outside the supplied pages")
    elif not isinstance(source_quote, str) or not source_quote or not parse.quote_on_page(source_quote, texts[source_page - 1]):
        candidate = None
        warnings.append(f"{body.field}: candidate quote is not on its supplied source page")
    return {"candidate": candidate, "warnings": warnings}


@app.post("/api/reports/{report_id}/index")
def index_report(report_id: str):
    report = get_report(report_id)
    if not _llm_configured():
        return {"report_id": report_id, "chunks": 0, "embed_model": "fixture", "cached": True}
    if kb.retrieval_mode() == "bm25":  # codex/claude-only setup: no embeddings endpoint, retrieval is keyword-only
        return {"report_id": report_id, "chunks": len(kb.chunks(report["stem"])), "embed_model": "bm25", "cached": True}
    return kb.index(report["stem"]) | {"report_id": report_id}


@app.post("/api/ask")
def ask(body: AskBody):
    if not body.question.strip() or len(body.question) > 2000:
        raise HTTPException(400, "question must contain 1–2000 characters")
    supplied = body.model_fields_set
    if "report_ids" in supplied and "report_stems" in supplied:
        raise HTTPException(400, "choose report_ids or report_stems, not both")
    if any(key in supplied and not getattr(body, key) for key in ("report_ids", "report_stems")):
        raise HTTPException(400, "explicit report scope must not be empty or null")
    if body.report_ids is not None:
        ids = {get_report(r)["stem"]: r for r in body.report_ids}
    else:
        available = {e["stem"] for e in kb.entries()}
        stems = body.report_stems if body.report_stems is not None else sorted(available)
        if any(s not in available for s in stems):
            raise HTTPException(404, "unknown report stem; see GET /api/kb")
        ids = {s: saved_report_id(s) for s in stems}
    if not ids:
        return {"question": body.question, "answer": "The knowledge base has no parsed reports yet. Add a report first.",
                "citations": [], "warnings": ["No saved report pages available; model not called."], "model": ""}
    if not _llm_configured() and body.report_ids is None:
        return {"question": body.question, "answer": "Connect a model in Settings to ask questions about saved reports.",
                "citations": [], "warnings": ["No model configured; no answer was generated."], "model": ""}
    if not _llm_configured():  # frontend dev mode: canned Answer, one citation
        return {"question": body.question, "answer": "Fixture mode (LLM_BASE_URL unset). Revenue was 152 340 MSEK [Nordic Industrials p.64].",
                "citations": [{"report_id": body.report_ids[0], "company": "Nordic Industrials AB (fictional fixture)", "fiscal_year": 2025,
                               "page": 64, "quote": "Intäkter 152 340 141 902", "score": 0.91}],
                "warnings": ["fixture answer: LLM_BASE_URL unset"], "model": "fixture"}
    t0 = time.time()
    try:
        answer = kb.ask(list(ids), body.question, ids=ids, keyword_only=body.report_ids is None)
    except Exception as e:
        raise HTTPException(502, f"Retrieval failed. Check the embedding endpoint and rebuild outdated indexes ({type(e).__name__}).") from None
    if not answer["answer"] and answer["warnings"]:
        raise HTTPException(502, " ".join(answer["warnings"]))
    print(f"[ask] {body.report_ids}: {len(answer['citations'])} citations, {len(answer['warnings'])} warnings in {time.time() - t0:.1f}s")
    return answer


@app.get("/api/kb")
def list_kb(collection_name: Literal["all", "wallenberg", "midcap"] = "all"):
    normalize = lambda name: re.sub(r"[\W_]+", " ", name.casefold()).strip()
    sectors = {normalize(c["name"]): c.get("sector") for c in COMPANIES}
    in_scope = collection.scope(collection_name)
    out = []
    for e in kb.entries():
        if not in_scope(e.get("company")):
            continue
        report_id = saved_report_id(e["stem"])
        get_report(report_id)
        out.append(e | {"report_id": report_id, "pdf_available": pdf_path(report_id).is_file(),
                        "sector": sectors.get(normalize(e.get("company") or ""))})
    return out


def kb_export_extractions(section: str, collection_name: Literal["all", "wallenberg", "midcap"], q: str = "") -> list[dict]:
    """Load saved extracts directly: whole-universe exports never need a PDF or a model call."""
    schema = load_schema(section)
    query = q.strip().casefold()
    in_scope = collection.scope(collection_name)
    out = []
    for entry in kb.entries():
        if not in_scope(entry.get("company")):
            continue
        if query and query not in (entry.get("company") or "").casefold() and query not in entry["stem"].casefold():
            continue
        path = kb.kb_dir() / entry["stem"] / "extractions" / f"{section}.json"
        if not path.is_file():
            continue
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise HTTPException(409, f"Saved {section!r} extraction for {entry['stem']!r} is invalid") from None
        if not isinstance(saved, dict) or not isinstance(saved.get("fields"), list):
            raise HTTPException(409, f"Saved {section!r} extraction for {entry['stem']!r} is invalid")
        x = copy.deepcopy(saved) | {
            "report_id": saved_report_id(entry["stem"]),
            "stem": entry["stem"],
            "company": saved.get("company") or entry.get("company"),
            "fiscal_year": saved.get("fiscal_year") or entry.get("fiscal_year"),
            "section": section,
        }
        out.append(workbench.decorate(x, schema))
    return out


def export_review_status(x: dict) -> tuple[str, str]:
    statuses = sorted({str((field.get("human_review") or {}).get("decision")) for field in x["fields"]
                       if (field.get("human_review") or {}).get("decision")})
    return (", ".join(statuses), "yes" if statuses else "no")


def human_evidence_csv(field: dict) -> tuple[object, object, str]:
    """Only expose a citation as human-supplied when this review actually verified one."""
    source = (field.get("source") or {}) if (field.get("human_review") or {}).get("source_verified") else {}
    return source.get("page"), source.get("quote"), json.dumps(field.get("components", []), ensure_ascii=False)


def universe_csv_row(x: dict) -> list:
    """One downstream row per company, anchored to the total-debt field's existing CSV columns."""
    fields = {field["key"]: field for field in x["fields"]}
    total = fields.get("total_debt", {})
    source = total.get("source") or {}
    status, reviewed = export_review_status(x)
    return [x["report_id"], x.get("company"), x.get("fiscal_year"), x["section"], total.get("key", "total_debt"),
             total.get("label", "Total debt"), total.get("value"), total.get("unit"), total.get("period"),
             total.get("raw_label"), source.get("page"), source.get("quote"), total.get("confidence"), x["stem"],
             *[fields.get(key, {}).get("value") for key in ppt.BUCKET_ORDER], status, reviewed, x.get("ready", False),
             *human_evidence_csv(total)]


UNIVERSE_CSV_HEADER = CSV_HEADER + ["stem", *ppt.BUCKET_ORDER, "review_status", "human_review", "ready", "human_source_page", "human_source_quote", "components"]


def kb_export_filename(section: str, collection_name: str, q: str, extension: str) -> str:
    """Keep the browser download name ASCII-safe even when the visible KB filter is not."""
    filter_suffix = re.sub(r"[^A-Za-z0-9_-]+", "-", q.strip()).strip("-")
    return f"kb_{section}_{collection_name}{'_' + filter_suffix if filter_suffix else ''}.{extension}"


@app.get("/api/kb/export.csv")
def kb_export_csv(section: str = "debt_maturity", collection_name: Literal["all", "wallenberg", "midcap"] = Query("all", alias="collection"), q: str = ""):
    rows = kb_export_extractions(section, collection_name, q)
    if not rows:
        raise HTTPException(404, f"No saved {section!r} extractions match this collection and filter")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(UNIVERSE_CSV_HEADER)
    writer.writerows(universe_csv_row(x) for x in rows)
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{kb_export_filename(section, collection_name, q, "csv")}"'})


@app.get("/api/kb/export.pptx")
def kb_export_pptx(section: str = "debt_maturity", collection_name: Literal["all", "wallenberg", "midcap"] = Query("all", alias="collection"), q: str = ""):
    extractions = kb_export_extractions(section, collection_name, q)
    if not extractions:
        raise HTTPException(404, f"No saved {section!r} extractions match this collection and filter")
    data = ppt.build_deck(extractions, [ppt.summary_row(x) for x in extractions])
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{kb_export_filename(section, collection_name, q, "pptx")}"'})


@app.get("/api/kb/maturity-wall")
def kb_maturity_wall(section: Literal["debt_maturity"] = "debt_maturity", collection_name: Literal["all", "wallenberg", "midcap"] = Query("all", alias="collection")):
    """v174: deterministic upcoming-maturities list over the saved collection -- reads the same decorated
    extracts as the CSV/PPTX exports, zero model calls. 200 with empty rows when the collection has no
    debt_maturity extractions yet -- the empty state is the frontend's to render, not a 404.
    v180: every row also carries its data/companies.json `sector` (None when the company is not in the
    universe file) and a `complete` flag (ppt.complete_buckets: the stored identity check passed and both
    total_debt and due_within_1_year are present), aggregated per sector as `sectors` -- companies/complete
    counts plus median/min/max share over complete companies only, never over guessed figures."""
    normalize = lambda name: re.sub(r"[\W_]+", " ", name.casefold()).strip()  # same mapping as list_kb
    sector_of = {normalize(c["name"]): c.get("sector") for c in COMPANIES}
    extracts = kb_export_extractions(section, collection_name)
    wall = workbench.maturity_wall(extracts)
    by_stem = {x["stem"]: x for x in extracts}
    for row in wall["rows"]:
        row["sector"] = sector_of.get(normalize(row.get("company") or ""))
        row["complete"] = ppt.complete_buckets(by_stem.get(row["stem"], {}))
    grouped = {}
    for row in wall["rows"]:
        grouped.setdefault(row["sector"], []).append(row)
    wall["sectors"] = []
    for sector in sorted(grouped, key=lambda s: (s is None, s or "")):  # unknown sector groups last
        rows = grouped[sector]
        shares = sorted(r["share"] for r in rows if r["complete"] and r["share"] is not None)
        wall["sectors"].append({
            "sector": sector,
            "companies": len(rows),
            "complete": sum(1 for r in rows if r["complete"]),
            "median_share": round(statistics.median(shares), 4) if shares else None,
            "min": round(shares[0], 4) if shares else None,
            "max": round(shares[-1], 4) if shares else None,
        })
    return wall


@app.get("/api/kb/{stem}/pages/{page}")
def kb_page(stem: str, page: int):
    if not re.fullmatch(r"[a-z0-9_-]+", stem) or not (kb.kb_dir() / stem / "pages.jsonl").is_file():
        raise HTTPException(404, "unknown saved report")
    text = kb._pages(stem).get(page)
    if text is None:
        raise HTTPException(404, "page not found in saved report")
    return {"page": page, "text": text}


@app.get("/api/kb/{stem}/{section}")
def kb_extraction(stem: str, section: str):
    """Stored extraction from the knowledge base, re-attached to a live report_id. With the PDF cached that is
    a full re-registration (page images work); without it (v092) a KB-only report serves the stored extraction,
    CSV, PPTX and Compare, and only the page/PDF endpoints 404 with a fetch hint. No model call either way."""
    path = kb.kb_dir() / stem / "extractions" / f"{section}.json"
    if not re.fullmatch(r"[a-z0-9_-]+", stem) or not re.fullmatch(r"[a-z0-9_]+", section) or not path.exists():
        raise HTTPException(404, f"no {section!r} extraction for {stem!r}; see GET /api/kb")
    report_id = get_report(saved_report_id(stem))["report_id"]
    extractions[report_id] = saved_extraction(report_id, section) | {
        "report_id": report_id, "stem": stem, "pdf_available": pdf_path(report_id).is_file()}
    return workbench.decorate(extractions[report_id], load_schema(section))


@app.post("/api/reports/{report_id}/review")
def review_field(report_id: str, body: ReviewBody):
    report = get_report(report_id)
    stem = report["stem"]
    if not re.fullmatch(r"[a-z0-9_-]+", stem):
        raise HTTPException(400, "Invalid report identifier")
    reviewer = body.reviewer.strip()
    if not reviewer or (body.decision != "confirmed" and not body.note.strip()):
        raise HTTPException(422, "Enter your name and a note for corrections or unresolved reviews")
    source_requested = body.source_page is not None or body.source_quote is not None
    if source_requested and (body.source_page is None or not (body.source_quote or "").strip()):
        raise HTTPException(422, "Provide both a citation page and its quoted text")
    if body.components is not None and source_requested:
        raise HTTPException(422, "Use either one citation or component citations, not both")
    if body.components is not None and (body.decision != "corrected" or not body.components):
        raise HTTPException(422, "Component citations require a corrected figure and at least one component")
    required_correction = {"unit", "period"} | (set() if body.components is not None else {"value"})
    if body.decision == "corrected" and not required_correction <= body.model_fields_set:
        raise HTTPException(422, "Corrections require unit and period, plus a value or component citations")
    with review_lock:
        path = kb.kb_dir() / stem / "extractions" / f"{body.section}.json"
        if not path.is_file():
            raise HTTPException(409, "Only saved extractions can be reviewed. Extract with a configured model first.")
        result = json.loads(path.read_text(encoding="utf-8"))
        field = next((f for f in result["fields"] if f["key"] == body.key), None)
        if field is None:
            raise HTTPException(404, "Figure not found")
        if field != body.expected:
            raise HTTPException(409, "This figure changed. Reopen the report before reviewing it.")
        if body.decision == "corrected" and isinstance(body.value, str) and not isinstance(field.get("value"), str):
            raise HTTPException(422, "Enter a finite number with a decimal point, or leave the value blank")

        texts = report_texts(report_id) if source_requested or body.components is not None else []

        def verified_source(page: int, quote: str) -> dict:
            if page > len(texts):
                raise HTTPException(400, f"Citation page {page} does not exist in this saved report")
            quote = quote.strip()
            if not extract_mod.quote_on_page(quote, texts[page - 1]):
                raise HTTPException(400, f"Citation is not on page {page}")
            return {"page": page, "quote": quote}

        source = verified_source(body.source_page, body.source_quote) if source_requested else None
        components = ([dict(value=component.value, label=component.label.strip(),
                            **verified_source(component.page, component.quote)) for component in body.components]
                      if body.components is not None else None)
        previous = copy.deepcopy({k: v for k, v in field.items() if k != "review_history"})
        review = {"decision": body.decision, "reviewer": reviewer, "note": body.note.strip(),
                  "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        if source or components:
            review["source_verified"] = True
        if body.decision == "corrected":
            value = math.fsum(component["value"] for component in components) if components is not None else body.value
            field.update(value=value, unit=body.unit, period=body.period,
                         evidence=["human_reviewed", *(["components_sum"] if components is not None else [])], confidence=0)
            if components is not None:
                field["components"] = components
                field["source"] = {"page": components[0]["page"], "quote": components[0]["quote"]}
            else:
                field.pop("components", None)
                if source:
                    field["source"] = source
            for other in result["fields"]:
                other["evidence"] = [e for e in other.get("evidence", []) if e != "arith_ok"]
        elif source:
            field.update(source=source, evidence=["human_reviewed"], confidence=0)
        field["human_review"] = review
        field.setdefault("review_history", []).append({**review, "previous": previous})
        workbench.decorate(result, load_schema(body.section), review)
        kb.save_extraction(stem, body.section, result)
        result.update(report_id=report_id, stem=stem, pdf_available=pdf_path(report_id).is_file())
        extractions[report_id] = result
        return result


def has_reviews(result):
    return bool(result.get("basis_history")) or any(f.get("review_history") for f in result["fields"])


@app.post("/api/reports/{report_id}/basis")
def review_basis(report_id: str, body: BasisBody):
    stem = get_report(report_id)["stem"]
    if not re.fullmatch(r"[a-z0-9_-]+", stem):
        raise HTTPException(400, "Invalid report identifier")
    if not body.reviewer.strip() or not body.note.strip():
        raise HTTPException(422, "Enter your name and a basis review note")
    if set(body.values) - set(workbench.required(body.section)) or any(len(v) > 2000 for v in body.values.values()):
        raise HTTPException(422, "Invalid basis fields")
    for key, options in workbench.CHOICES.items():
        value = body.values.get(key, "").strip()
        if value and value not in options:
            raise HTTPException(422, f"Invalid {key} definition")
    with review_lock:
        path = kb.kb_dir() / stem / "extractions" / f"{body.section}.json"
        if not path.is_file():
            raise HTTPException(409, "Only saved extractions can be reviewed")
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("basis", {}) != body.expected:
            raise HTTPException(409, "The basis changed. Reopen the statement before saving.")
        basis = {"values": {k: v.strip() for k, v in body.values.items()}, "reviewer": body.reviewer.strip(),
                 "note": body.note.strip(), "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        result.setdefault("basis_history", []).append(dict(basis, previous=result.get("basis", {})))
        result["basis"] = basis
        workbench.decorate(result, load_schema(body.section), basis)
        kb.save_extraction(stem, body.section, result)
        result.update(report_id=report_id, stem=stem, pdf_available=pdf_path(report_id).is_file())
        extractions[report_id] = result
        return result


@app.get("/api/review-queue")
def review_queue(collection_name: Literal["all", "wallenberg", "midcap"] = "wallenberg"):
    out = []
    for report in list_kb(collection_name):
        for section in report["sections"]:
            x = kb_extraction(report["stem"], section)
            out.extend({"report": report, "section": section, **issue} for issue in x["issues"])
    return out


@app.get("/api/kb/{stem}/{section}/comparison")
def comparison(stem: str, section: str, previous_stem: str | None = None):
    current = kb_extraction(stem, section)
    candidates = [e for e in list_kb() if current.get("company") and e.get("company") and e["stem"] != stem and section in e["sections"] and e.get("fiscal_year") and current.get("fiscal_year") and e["fiscal_year"] < current["fiscal_year"] and collection.identity(e.get("company")) == collection.identity(current.get("company"))]
    if previous_stem is None:
        default = [e for e in candidates if e["fiscal_year"] == current.get("fiscal_year", 0) - 1]
        if len(default) != 1:
            return {"candidates": candidates, "rows": [], "reasons": ["Choose the prior-year source: multiple saved reports exist." if default else "The immediately preceding year is not saved. Select another saved year to compare."]}
        previous_stem = default[0]["stem"]
    if previous_stem not in {e["stem"] for e in candidates}:
        raise HTTPException(422, "Choose an earlier saved report for the same company and statement")
    previous = kb_extraction(previous_stem, section)
    return dict(workbench.compare(current, previous), candidates=candidates)


def export_extraction(report_id, section=None, previous_stem=None):
    report = get_report(report_id)
    x = kb_extraction(report["stem"], section) if section else extractions.get(report_id)
    if not x:
        raise HTTPException(404, "No extraction yet")
    x = workbench.decorate(copy.deepcopy(x), load_schema(x["section"]))
    if previous_stem:
        x["comparison"] = comparison(report["stem"], x["section"], previous_stem)
    return x


@app.get("/api/config")
def config():
    # codex/claude defaults live in llm.py; not "fixture" only for a provider _llm_configured() already accepts without LLM_MODEL
    model = os.getenv("LLM_MODEL") or {"codex": "gpt-5.6-terra", "claude": "claude-sonnet-5"}.get(llm.provider(), "fixture")
    from pipeline import merge  # v140: echo only -- the route never reaches the second-run path
    return {"model": model, "embed_model": kb.embed_model(), "embed_base_url": kb.embed_base_url(), "base_url": os.getenv("LLM_BASE_URL"),
            "llm": _llm_configured(), "provider": llm.provider() if _llm_configured() else "fixture",
            "retrieval": kb.retrieval_mode(),  # v034: "hybrid" | "bm25" | "fixture"
            "maturity_basis": extract_mod.debt_basis(),  # v089: "carrying" (default) | "undiscounted", env DEBT_BASIS
            "merge_runs": merge.mode()}  # v140: "off" (default) | "union" | "majority", env EXTRACT_MERGE_RUNS


@app.get("/api/reports/{report_id}/extraction.csv")
def extraction_csv(report_id: str, section: str | None = None, previous_stem: str | None = None):
    x = export_extraction(report_id, section, previous_stem)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADER + ["human_review", "reviewer", "reviewed_at", "review_note", "human_source_page", "human_source_quote", "components", "ready", "basis", "unresolved", "comparison", "review_history", "basis_history", "check_history"])
    for f in x["fields"]:
        src = f.get("source") or {}
        w.writerow([x["report_id"], x["company"], x["fiscal_year"], x["section"], f["key"], f["label"], f["value"],
                    f["unit"], f["period"], f["raw_label"], src.get("page"), src.get("quote"), f["confidence"], *[(f.get("human_review") or {}).get(k, "") for k in ("decision", "reviewer", "at", "note")], *human_evidence_csv(f), x.get("ready", False), json.dumps(x.get("basis", {})), json.dumps(x.get("issues", [])), json.dumps(x.get("comparison", {})), json.dumps(f.get("review_history", [])), json.dumps(x.get("basis_history", [])), json.dumps(x.get("check_history", []))])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{report_id}_{x["section"]}.csv"'})


@app.get("/api/reports/{report_id}/extraction.pptx")
def extraction_pptx(report_id: str, section: str | None = None, previous_stem: str | None = None,
                    prior_year: bool = False,  # v091: ?prior_year=1 adds the extraction's prior-year series when it carries one
                    per_year: bool = False):  # v109: ?per_year=1 swaps the three buckets for the report's own calendar-year columns when it carries them
    x = export_extraction(report_id, section, previous_stem)
    data = ppt.build_pptx(x, prior_year=prior_year, per_year=per_year)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{report_id}_{x["section"]}.pptx"'})



def knowledge_stem(stem):
    if not re.fullmatch(r"[a-z0-9_-]+", stem) or not (kb.kb_dir() / stem / "meta.json").exists():
        raise HTTPException(404, "Unknown knowledge-base report")
    return stem


@app.get("/api/knowledge/{stem}/chunks")
def knowledge_chunks(stem: str, q: str = Query("", max_length=200), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    knowledge_stem(stem)
    try:
        return kb.inspect_chunks(stem, q, offset, limit)
    except (ValueError, KeyError, TypeError, OSError):
        raise HTTPException(409, "Stored index is unreadable. Rebuild it.") from None


@app.post("/api/knowledge/{stem}/index")
def rebuild_knowledge(stem: str):
    knowledge_stem(stem)
    try:
        return kb.index(stem, force=True)
    except Exception as e:
        raise HTTPException(502, f"Index build failed: {type(e).__name__}: {e}") from None


def saved_extraction(report_id: str, section: str | None = None):
    started = time.perf_counter()
    report = get_report(report_id)
    if section is None:
        result = extractions.get(report_id)
        if result is None:
            raise HTTPException(404, "no extraction yet; POST /extract first")
        return result
    schema = load_schema(section)
    path = kb.kb_dir() / report["stem"] / "extractions" / f"{section}.json"
    if not path.exists():
        last = extractions.get(report_id)
        if last and last.get("provider") == "fixture" and last.get("section") == section:
            return last
        raise HTTPException(404, "No saved extraction for this section")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(result, dict) or result.get("section") != section or not isinstance(result.get("fields"), list):
            raise ValueError("Invalid extraction structure")
    except (OSError, ValueError) as e:
        raise HTTPException(409, "Saved extraction is unreadable. Run extraction again.") from e
    prompt = extract_mod.system_prompt(schema, report["stem"])
    return result | {"report_id": report_id, "cached": True,
                     "stale": result.get("cache_key") != extraction_identity(report, schema, prompt),
                     "timings": {"model": 0, "parse": 0, "locate": 0, "validate": 0, "attempts": 0,
                                 "total": round(time.perf_counter() - started, 3)}}


def extraction_identity(report, schema, prompt):
    from pipeline import merge
    pipeline = [Path(__file__), *[Path(m.__file__) for m in (extract_mod, locate, parse, llm, merge, workbench)]]
    return kb.fingerprint({"report": kb._meta(report["stem"]), "schema": schema,
                           "pipeline": [kb.sha256(p.read_bytes()) if p.is_file() else "packaged-cache-v1" for p in pipeline],
                           "model": os.getenv("LLM_MODEL") or {"codex": "gpt-5.6-terra", "claude": "claude-sonnet-5"}.get(llm.provider(), "fixture"), "provider": llm.provider(), "prompt": prompt,
                           "settings": {k: os.getenv(k) for k in ("LLM_BASE_URL", "LLM_REASONING", "LLM_THINK", "LLM_NUM_CTX", "LLM_TIMEOUT", "LLM_STRICT_SCHEMA", "DEBT_BASIS", "EXTRACT_MERGE_RUNS", "EXTRACT_TWO_PASS", "FEWSHOT")}})


@app.post("/api/knowledge/{stem}/open")
def open_knowledge(stem: str):
    knowledge_stem(stem)
    entry = next((e for e in library_index() if Path(e["file"]).stem == stem), None)
    if entry:
        return register_library(entry)
    report = get_report(saved_report_id(stem))
    if pdf_path(report["report_id"]).is_file():
        report_texts(report["report_id"])
    return report


# ---- static frontend (desktop build only; unset FRONTEND_DIST -> no route added, dev proxy unaffected) --------

FRONTEND_DIST = os.getenv("FRONTEND_DIST")
if FRONTEND_DIST:
    class SPAStaticFiles(StaticFiles):
        """A path with no matching file falls back to index.html (client-side routing). Registered after every
        /api/* route above, which Starlette always tries first, so this never shadows the API -- the api/ prefix
        check below is only a backstop for an /api/* typo that no real route matched. StaticFiles signals a miss
        by raising HTTPException(404), not by returning a 404 response, hence the try/except here. get_path()
        joins with os.path.join/normpath, so `path` uses OS-native separators (backslash on Windows) -- compare
        via Path(...).parts, not a literal "api/" prefix, or the guard silently never matches on Windows."""
        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404 and Path(path).parts[:1] != ("api",):
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


class _TeeToLog:
    """Mirrors console output into the rotating log file, so the existing print()-based diagnostics (here and in
    pipeline/*) are still visible when the packaged exe runs with no attached console. One record per non-empty line."""

    def __init__(self, stream, logger: logging.Logger):
        self._stream, self._logger = stream, logger

    def write(self, data: str) -> None:
        self._stream.write(data)
        for line in data.splitlines():
            if line.strip():
                self._logger.info(line)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()


def main() -> None:
    ap = argparse.ArgumentParser(prog="backend", description="SEB annual-report parser backend")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    log_dir = paths.data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    file_logger = logging.getLogger("backend.file")
    file_logger.setLevel(logging.INFO)
    file_logger.propagate = False
    handler = RotatingFileHandler(log_dir / "backend.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    file_logger.addHandler(handler)
    sys.stdout = _TeeToLog(sys.stdout, file_logger)  # covers both print() and uvicorn's own ext://sys.stdout handlers
    sys.stderr = _TeeToLog(sys.stderr, file_logger)

    uvicorn.run(app, host=args.host, port=args.port, loop="asyncio", http="h11", ws="none")


if __name__ == "__main__":
    main()
