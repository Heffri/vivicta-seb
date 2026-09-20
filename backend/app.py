"""SEB annual-report parser, backend. The contract is docs/API.md; change it there first."""
import csv
import io
import json
import os
import re
import time
from pathlib import Path

import pymupdf
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel

from pipeline import extract as extract_mod, fetch, kb, locate, parse, ppt, runtime, maturity
from datetime import datetime, timezone

load_dotenv()
HERE = Path(__file__).parent
UPLOADS = HERE / "uploads"
UPLOADS.mkdir(exist_ok=True)
SCHEMAS = HERE / "schemas"
LIBRARY = HERE.parent / "data" / "reports"  # bundled reports; index.json is committed, PDFs via `python data/fetch.py`
FIXTURE = HERE / "fixtures" / "sample_extraction.json"
COMPANIES = json.loads((HERE.parent / "data" / "companies.json").read_text(encoding="utf-8"))  # Nasdaq Stockholm, data/companies_build.py
CSV_HEADER = "report_id,company,fiscal_year,section,key,label,value,unit,period,raw_label,page,quote,confidence,calculation,components,debt_scope".split(",")

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
    section: str
    force: bool = False


class LibraryBody(BaseModel):
    file: str


class AskBody(BaseModel):
    question: str
    report_ids: list[str]


class FetchBody(BaseModel):
    company: str
    year: int


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
    return await run_in_threadpool(register_upload, data, file.filename)


def register_upload(data: bytes, filename: str | None):
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
    texts_cache[report_id], parsing = kb.load_texts(report_id, pdf_path(report_id), sha)
    texts = report_texts(report_id)
    company, fiscal_year = guess_meta(texts)
    reports[report_id] = {"report_id": report_id, "filename": filename or "upload.pdf", "pages": len(texts), "company": company, "fiscal_year": fiscal_year, "stem": report_id}
    kb.save_report(report_id, {"company": company, "fiscal_year": fiscal_year, "language": None, "source_url": None, "pages": len(texts),
                               "sha256": sha, "filename": reports[report_id]["filename"], **parsing}, texts)  # ponytail: uploads land in data/kb/up-<sha>/ too; prune before committing if they are not public reports
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
        digest = kb.sha256(library_paths[report_id].read_bytes())
        stem = Path(entry["file"]).stem
        texts_cache[report_id], parsing = kb.load_texts(stem, library_paths[report_id], digest)
        texts = report_texts(report_id)
        reports[report_id] = {"report_id": report_id, "filename": entry["file"], "pages": len(texts),
                              "company": entry["company"], "fiscal_year": entry["fiscal_year"], "stem": Path(entry["file"]).stem}  # curated beats guess_meta
        kb.save_report(Path(entry["file"]).stem, {k: entry.get(k) for k in ("company", "fiscal_year", "language", "source_url")}
                       | {"pages": len(texts), "sha256": digest, "filename": entry["file"], **parsing}, texts)
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
    if not (1990 <= body.year <= 2100) or len(body.company) > 100:
        raise HTTPException(400, "bad company/year")
    slug = fetch.slugify(body.company)
    entry = next((e for e in library_index() if e["fiscal_year"] == body.year and fetch.slugify(e["company"]) == slug), None)
    if not entry:
        t0 = time.time()
        try:
            entry = fetch.fetch_report(body.company, body.year, LIBRARY)  # 10-90 s: MFN -> DuckDuckGo, validates PDF + text layer
        except LookupError as e:
            return JSONResponse({"detail": f"no annual report found for {body.company} {body.year}", "tried": e.args[0]}, status_code=404)
        print(f"[fetch] {body.company} {body.year} -> {entry['file']} from {entry['source_url']} in {time.time() - t0:.0f}s")
    return register_library(entry)


@app.get("/api/reports/{report_id}")
def read_report(report_id: str):
    return get_report(report_id)


@app.get("/api/reports/{report_id}/pdf")
def report_pdf(report_id: str):
    report = get_report(report_id)  # FileResponse handles Range, so the browser viewer can seek
    return FileResponse(pdf_path(report_id), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{report["filename"]}"'})


@app.get("/api/reports/{report_id}/pages/{n}.png")
def page_png(report_id: str, n: int):
    report = get_report(report_id)
    if not 1 <= n <= report["pages"]:
        raise HTTPException(404, f"page {n} out of range 1..{report['pages']}")
    with pymupdf.open(pdf_path(report_id)) as doc:
        png = doc[n - 1].get_pixmap(dpi=150).tobytes("png")
    return Response(png, media_type="image/png")


def extraction_identity(report, schema, prompt):
    pipeline = [Path(__file__), *[Path(m.__file__) for m in (extract_mod, locate, parse, runtime, maturity)]]
    return kb.fingerprint({"report": kb._meta(report["stem"]), "schema": schema,
                           "pipeline": [kb.sha256(p.read_bytes()) for p in pipeline],
                           "model": runtime.model(), "provider": runtime.provider(), "prompt": prompt,
                           "settings": {k: os.getenv(k) for k in ("LLM_BASE_URL", "LLM_REASONING", "LLM_THINK", "LLM_NUM_CTX", "LLM_TIMEOUT")}})


@app.post("/api/reports/{report_id}/extract")
def run_extract(report_id: str, body: ExtractBody):
    started = time.perf_counter()
    report, schema = get_report(report_id), load_schema(body.section)
    if runtime.provider() == "fixture":
        result = json.loads(FIXTURE.read_text(encoding="utf-8")) | {"report_id": report_id, "provider": "fixture"}
    else:
        with kb.report_lock(report["stem"], "extract"):
            prompt = extract_mod.system_prompt(schema, report["stem"])
            identity = extraction_identity(report, schema, prompt)
            path = kb.kb_dir() / report["stem"] / "extractions" / f"{body.section}.json"
            saved = None
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            if not body.force and isinstance(saved, dict) and saved.get("cache_key") == identity:
                result = saved | {"report_id": report_id, "cached": True,
                                  "timings": {"parse": 0, "locate": 0, "model": 0, "validate": 0, "attempts": 0,
                                              "total": round(time.perf_counter() - started, 3)}}
            else:
                stage = time.perf_counter()
                texts = report_texts(report_id)
                parse_seconds = time.perf_counter() - stage
                stage = time.perf_counter()
                pages = locate.candidate_pages(texts, schema)
                locate_seconds = time.perf_counter() - stage
                if not pages:
                    raise HTTPException(422, "No candidate pages found for this section")
                try:
                    result = extract_mod.extract(texts, pages, schema, report, prompt=prompt)
                except (RuntimeError, ValueError, TimeoutError) as e:
                    raise HTTPException(502, f"Extraction failed: {e}") from e
                failures = [w for w in result["warnings"] if w.startswith("llm:")]
                if failures:
                    raise HTTPException(502, " ".join(failures))
                if kb._meta(report["stem"]).get("ocr_pages"):
                    result["warnings"].append("This report contains OCR text. Verify extracted figures against the rendered PDF, especially signs and decimal separators.")
                    ocr_pages = set(kb._meta(report["stem"])["ocr_pages"])
                    for f in result["fields"]:
                        sources = [f.get("source")] + [c["source"] for c in f.get("components", [])]
                        if any(s and s["page"] in ocr_pages for s in sources):
                            f["confidence"] = min(f["confidence"], 0.8)
                            f["evidence"].append("ocr_text")
                result.update(cache_key=identity, cached=False, model=runtime.model(), provider=runtime.provider(),
                              created_at=datetime.now(timezone.utc).isoformat())
                result["timings"].update(parse=round(parse_seconds, 3), locate=round(locate_seconds, 3),
                                          total=round(time.perf_counter() - started, 3))
                kb.save_extraction(report["stem"], body.section, result)
    extractions[report_id] = result
    return result


@app.post("/api/reports/{report_id}/index")
def index_report(report_id: str):
    report = get_report(report_id)
    if runtime.provider() == "fixture":
        return {"report_id": report_id, "chunks": 0, "embed_model": "fixture", "cached": True}
    try:
        return kb.index(report["stem"]) | {"report_id": report_id}
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    except Exception as e:
        raise HTTPException(502, f"Embedding index unavailable. Check EMBED_BASE_URL and EMBED_MODEL ({type(e).__name__}).") from None


@app.post("/api/ask")
def ask(body: AskBody):
    if not body.question.strip():
        raise HTTPException(400, "question is empty")
    if not body.report_ids:
        raise HTTPException(400, "report_ids is empty")
    if len(body.question) > 2000:  # trust boundary: the question goes straight into the prompt
        raise HTTPException(400, "question too long (max 2000 chars)")
    ids = {get_report(r)["stem"]: r for r in body.report_ids}  # stem -> report_id; 404 on unknown ids
    if runtime.provider() == "fixture":  # frontend dev mode: canned Answer, one citation
        return {"question": body.question, "answer": "Fixture mode (LLM_BASE_URL unset). Revenue was 152 340 MSEK [Nordic Industrials p.64].",
                "citations": [{"report_id": body.report_ids[0], "company": "Nordic Industrials AB (fictional fixture)", "fiscal_year": 2025,
                               "page": 64, "quote": "Intäkter 152 340 141 902", "score": 0.91}],
                "warnings": ["fixture answer: LLM_BASE_URL unset"], "model": "fixture"}
    t0 = time.time()
    try:
        answer = kb.ask(list(ids), body.question, ids=ids)  # indexes on demand
    except Exception as e:
        raise HTTPException(502, f"Retrieval failed. Check the embedding endpoint and rebuild outdated indexes ({type(e).__name__}).") from None
    if not answer["answer"] and answer["warnings"]:
        raise HTTPException(502, " ".join(answer["warnings"]))
    print(f"[ask] {body.report_ids}: {len(answer['citations'])} citations, {len(answer['warnings'])} warnings in {time.time() - t0:.1f}s")
    return answer


@app.get("/api/kb")
def list_kb():
    by_stem = {r["stem"]: rid for rid, r in reports.items()}
    return [e | {"report_id": by_stem.get(e["stem"])} for e in kb.entries()]


def knowledge_stem(stem):
    if not re.fullmatch(r"[a-z0-9_-]+", stem) or not (kb.kb_dir() / stem / "meta.json").exists():
        raise HTTPException(404, "Unknown knowledge-base report")
    return stem


@app.post("/api/knowledge/{stem}/open")
def open_knowledge(stem: str):
    knowledge_stem(stem)
    entry = next((e for e in library_index() if Path(e["file"]).stem == stem), None)
    if entry:
        return register_library(entry)
    meta = kb._meta(stem)
    path = UPLOADS / f"{stem}.pdf"
    if not stem.startswith("up-") or not path.exists():
        raise HTTPException(409, "Source PDF is unavailable. Upload or fetch it again.")
    if stem not in reports:
        digest = kb.sha256(path.read_bytes())
        texts, parsing = kb.load_texts(stem, path, digest)
        texts_cache[stem] = texts
        reports[stem] = {"report_id": stem, "stem": stem, "filename": meta.get("filename") or path.name,
                         "company": meta.get("company"), "fiscal_year": meta.get("fiscal_year"), "pages": len(texts)}
        kb.save_report(stem, meta | {"sha256": digest, "pages": len(texts)} | parsing, texts)
    return reports[stem]


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


@app.get("/api/kb/{stem}/{section}")
def kb_extraction(stem: str, section: str):
    knowledge_stem(stem)
    load_schema(section)
    path = kb.kb_dir() / stem / "extractions" / f"{section}.json"
    if not path.exists():
        raise HTTPException(404, "No saved extraction for this section")
    report_id = open_knowledge(stem)["report_id"]
    extractions[report_id] = saved_extraction(report_id, section)
    return extractions[report_id]


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


@app.get("/api/config")
def config():
    return {"model": runtime.model(), "provider": runtime.provider(), "reasoning": os.getenv("LLM_REASONING", "low"),
            "embed_model": kb.embed_model(), "embed_base_url": kb.embed_base_url(), "base_url": os.getenv("LLM_BASE_URL"),
            "llm": runtime.provider() != "fixture"}


@app.get("/api/reports/{report_id}/extraction.csv")
def extraction_csv(report_id: str, section: str | None = None):
    x = saved_extraction(report_id, section)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADER)
    for f in x["fields"]:
        src = f.get("source") or {}
        w.writerow([x["report_id"], x["company"], x["fiscal_year"], x["section"], f["key"], f["label"], f["value"],
                    f["unit"], f["period"], f["raw_label"], src.get("page"), src.get("quote"), f["confidence"],
                    f.get("calculation"), json.dumps(f.get("components", []), ensure_ascii=False), x.get("debt_scope")])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{report_id}_{x["section"]}.csv"'})


@app.get("/api/reports/{report_id}/extraction.pptx")
def extraction_pptx(report_id: str, section: str | None = None):
    x = saved_extraction(report_id, section)
    data = ppt.build_pptx(x)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{report_id}_{x["section"]}.pptx"'})
