"""SEB annual-report parser, backend. The contract is docs/API.md; change it there first."""
import argparse
import csv
import io
import json
import logging
import os
import re
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pymupdf
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from pipeline import extract as extract_mod, fetch, kb, llm, locate, parse, paths, ppt

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


class ExtractBody(BaseModel):
    section: str


class LibraryBody(BaseModel):
    file: str


class AskBody(BaseModel):
    question: str
    report_ids: list[str]


class FetchBody(BaseModel):
    company: str
    year: int
    country: str | None = None  # v074: optional context for the model search when the directory has no hit ("Switzerland")
    hint: str | None = None     # v074: free-text hint for the model search ("FY ends 30 June", the report's exact title)


def pdf_path(report_id: str) -> Path:
    return library_paths.get(report_id) or UPLOADS / f"{report_id}.pdf"


def report_texts(report_id: str) -> list[str]:
    if report_id not in texts_cache:
        texts_cache[report_id] = parse.page_texts(pdf_path(report_id))
    return texts_cache[report_id]


def library_index() -> list[dict]:
    """index.json entries whose PDF is actually on disk."""
    entries = json.loads((LIBRARY / "index.json").read_text(encoding="utf-8"))
    return [e for e in entries if (LIBRARY / e["file"]).exists()]


def get_report(report_id: str) -> dict:
    if report_id not in reports:
        raise HTTPException(404, f"unknown report_id {report_id!r}")
    return reports[report_id]


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
        return register_library(cached)
    report_id = "up-" + sha[:12]  # deterministic: same upload twice = same report + same KB folder
    if report_id in reports:
        return reports[report_id]
    pdf_path(report_id).write_bytes(data)
    texts = report_texts(report_id)
    company, fiscal_year = guess_meta(texts)
    reports[report_id] = {"report_id": report_id, "filename": file.filename or "upload.pdf", "pages": len(texts), "company": company, "fiscal_year": fiscal_year, "stem": report_id}
    kb.save_report(report_id, {"company": company, "fiscal_year": fiscal_year, "language": None, "source_url": None, "pages": len(texts),
                               "sha256": sha, "filename": reports[report_id]["filename"]}, texts)  # ponytail: uploads land in data/kb/up-<sha>/ too; prune before committing if they are not public reports
    return reports[report_id]


@app.get("/api/library")
def list_library():
    out = []
    for e in library_index():
        if e["file"] not in library_pages:
            with pymupdf.open(LIBRARY / e["file"]) as doc:
                library_pages[e["file"]] = doc.page_count
        out.append(e | {"pages": library_pages[e["file"]]})
    return out


def register_library(entry: dict) -> dict:
    """Register a cached PDF (curated or fetched) exactly like an upload; same file twice = same report_id."""
    report_id = "lib-" + Path(entry["file"]).stem
    if report_id not in reports:
        library_paths[report_id] = LIBRARY / entry["file"]
        texts = report_texts(report_id)
        reports[report_id] = {"report_id": report_id, "filename": entry["file"], "pages": len(texts),
                              "company": entry["company"], "fiscal_year": entry["fiscal_year"], "stem": Path(entry["file"]).stem}  # curated beats guess_meta
        kb.save_report(Path(entry["file"]).stem, {k: entry.get(k) for k in ("company", "fiscal_year", "language", "source_url")}
                       | {"pages": len(texts), "sha256": kb.sha256(library_paths[report_id].read_bytes()), "filename": entry["file"]}, texts)
    return reports[report_id]


def register_kb_only(stem: str) -> dict:
    """Register a KB entry whose PDF is not cached, from its stored meta.json (v092): the stored extraction,
    CSV, PPTX and Compare all work; only page images and /pdf 404 with a fetch-it hint. Once the PDF
    arrives, kb_extraction takes the register_library path instead — both ids may coexist, and list_kb
    points at the real one. Never parses or writes anything, unlike its sibling above."""
    report_id = "kb-" + stem
    if report_id not in reports:
        m = json.loads((kb.kb_dir() / stem / "meta.json").read_text(encoding="utf-8"))
        reports[report_id] = {"report_id": report_id, "filename": m.get("filename") or f"{stem}.pdf", "pages": m.get("pages", 0),
                              "company": m.get("company"), "fiscal_year": m.get("fiscal_year"), "stem": stem}
    return reports[report_id]


@app.post("/api/reports/from-library")
def report_from_library(body: LibraryBody):
    entry = next((e for e in library_index() if e["file"] == body.file), None)
    if not entry or "/" in body.file or "\\" in body.file:  # trust boundary: index basenames only, never a path
        raise HTTPException(404, f"not in library: {body.file!r}; see GET /api/library")
    return register_library(entry)


@app.get("/api/companies")
def list_companies(q: str = ""):
    cached: dict[str, list[int]] = {}
    for e in library_index():
        cached.setdefault(fetch.slugify(e["company"]), []).append(e["fiscal_year"])
    q = q.strip().lower()
    hits = [c for c in COMPANIES if q in c["name"].lower() or q in c["ticker"].lower()]
    hits.sort(key=lambda c: (not c["name"].lower().startswith(q), c["name"]))  # prefix matches first
    return [c | {"cached_years": sorted(set(cached.get(fetch.slugify(c["name"]), [])))} for c in hits[:50]]


@app.post("/api/reports/fetch")
def fetch_report(body: FetchBody):
    if not (1990 <= body.year <= 2100) or len(body.company) > 100 or (body.country and len(body.country) > 60) or (body.hint and len(body.hint) > 300):
        raise HTTPException(400, "bad company/year")
    slug = fetch.slugify(body.company)
    entry = next((e for e in library_index() if e["fiscal_year"] == body.year and fetch.slugify(e["company"]) == slug), None)
    if not entry:
        t0 = time.time()
        try:
            # 10-90 s: MFN -> Nasdaq -> DuckDuckGo, then -- only with a codex/claude provider -- the
            # model's own web search (fetch.py's fourth source, what the Swedish feeds never carry).
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
    if not pdf_path(report_id).exists():  # KB-only report (v092): registered from meta.json, no PDF behind it
        raise HTTPException(404, f"the PDF for {report['stem']!r} is not cached; fetch it from Extract (directory search) to see the pages")
    return FileResponse(pdf_path(report_id), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{report["filename"]}"'})


@app.get("/api/reports/{report_id}/pages/{n}.png")
def page_png(report_id: str, n: int):
    report = get_report(report_id)
    if not 1 <= n <= report["pages"]:
        raise HTTPException(404, f"page {n} out of range 1..{report['pages']}")
    if not pdf_path(report_id).exists():  # KB-only report (v092): pages exist (meta.json says so), the PDF does not
        raise HTTPException(404, f"the PDF for {report['stem']!r} is not cached; fetch it from Extract (directory search) to see the pages")
    with pymupdf.open(pdf_path(report_id)) as doc:
        png = doc[n - 1].get_pixmap(dpi=150).tobytes("png")
    return Response(png, media_type="image/png")


@app.post("/api/reports/{report_id}/extract")
def run_extract(report_id: str, body: ExtractBody):
    report = get_report(report_id)
    schema = load_schema(body.section)
    if not _llm_configured():  # frontend dev mode: no model configured
        result = json.loads(FIXTURE.read_text(encoding="utf-8")) | {"report_id": report_id}
    else:
        texts = report_texts(report_id)
        pages = locate.candidate_pages(texts, schema)
        print(f"[extract] {report_id} {body.section}: candidate pages {pages}")
        result = extract_mod.extract(texts, pages, schema, report)
        kb.save_extraction(report["stem"], body.section, result)  # fixture results never enter the KB
    extractions[report_id] = result
    return result


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
    if not body.report_ids:
        raise HTTPException(400, "report_ids is empty")
    if len(body.question) > 2000:  # trust boundary: the question goes straight into the prompt
        raise HTTPException(400, "question too long (max 2000 chars)")
    ids = {get_report(r)["stem"]: r for r in body.report_ids}  # stem -> report_id; 404 on unknown ids
    if not _llm_configured():  # frontend dev mode: canned Answer, one citation
        return {"question": body.question, "answer": "Fixture mode (LLM_BASE_URL unset). Revenue was 152 340 MSEK [Nordic Industrials p.64].",
                "citations": [{"report_id": body.report_ids[0], "company": "Nordic Industrials AB (fictional fixture)", "fiscal_year": 2025,
                               "page": 64, "quote": "Intäkter 152 340 141 902", "score": 0.91}],
                "warnings": ["fixture answer: LLM_BASE_URL unset"], "model": "fixture"}
    t0 = time.time()
    answer = kb.ask(list(ids), body.question, ids=ids)  # retrieval (BM25 or hybrid) + a real model call
    print(f"[ask] {body.report_ids}: {len(answer['citations'])} citations, {len(answer['warnings'])} warnings in {time.time() - t0:.1f}s")
    return answer


@app.get("/api/kb")
def list_kb():
    kb_only = {r["stem"]: rid for rid, r in reports.items() if rid.startswith("kb-")}
    real = {r["stem"]: rid for rid, r in reports.items() if not rid.startswith("kb-")}
    by_stem = {**kb_only, **real}  # once the PDF is cached, its real registration outranks the KB-only one
    cached = {e["file"] for e in library_index()}
    return [e | {"report_id": by_stem.get(e["stem"]), "pdf_cached": f"{e['stem']}.pdf" in cached} for e in kb.entries()]


@app.get("/api/kb/{stem}/{section}")
def kb_extraction(stem: str, section: str):
    """Stored extraction from the knowledge base, re-attached to a live report_id. With the PDF cached that is
    a full re-registration (page images work); without it (v092) a KB-only report serves the stored extraction,
    CSV, PPTX and Compare, and only the page/PDF endpoints 404 with a fetch hint. No model call either way."""
    path = kb.kb_dir() / stem / "extractions" / f"{section}.json"
    if not re.fullmatch(r"[a-z0-9_]+", stem) or not re.fullmatch(r"[a-z0-9_]+", section) or not path.exists():
        raise HTTPException(404, f"no {section!r} extraction for {stem!r}; see GET /api/kb")
    entry = next((e for e in library_index() if e["file"] == f"{stem}.pdf"), None)
    report_id = (register_library(entry) if entry else register_kb_only(stem))["report_id"]
    extractions[report_id] = json.loads(path.read_text(encoding="utf-8")) | {"report_id": report_id}
    return extractions[report_id]


@app.get("/api/config")
def config():
    # codex/claude defaults live in llm.py; not "fixture" only for a provider _llm_configured() already accepts without LLM_MODEL
    model = os.getenv("LLM_MODEL") or {"codex": "gpt-5.6-terra", "claude": "claude-sonnet-5"}.get(llm.provider(), "fixture")
    return {"model": model, "embed_model": kb.embed_model(), "base_url": os.getenv("LLM_BASE_URL"),
            "llm": _llm_configured(), "provider": llm.provider() if _llm_configured() else "fixture",
            "retrieval": kb.retrieval_mode(),  # v034: "hybrid" | "bm25" | "fixture"
            "maturity_basis": extract_mod.debt_basis()}  # v089: "carrying" (default) | "undiscounted", env DEBT_BASIS


@app.get("/api/reports/{report_id}/extraction.csv")
def extraction_csv(report_id: str):
    get_report(report_id)
    x = extractions.get(report_id)
    if not x:
        raise HTTPException(404, "no extraction yet; POST /extract first")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADER)
    for f in x["fields"]:
        src = f.get("source") or {}
        w.writerow([x["report_id"], x["company"], x["fiscal_year"], x["section"], f["key"], f["label"], f["value"],
                    f["unit"], f["period"], f["raw_label"], src.get("page"), src.get("quote"), f["confidence"]])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{report_id}_{x["section"]}.csv"'})


@app.get("/api/reports/{report_id}/extraction.pptx")
def extraction_pptx(report_id: str):
    get_report(report_id)
    x = extractions.get(report_id)
    if not x:
        raise HTTPException(404, "no extraction yet; POST /extract first")
    data = ppt.build_pptx(x)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{report_id}_{x["section"]}.pptx"'})


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
