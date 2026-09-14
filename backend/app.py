"""SEB annual-report parser, backend. The contract is docs/API.md; change it there first."""
import csv
import io
import json
import os
import re
import uuid
from pathlib import Path

import pymupdf
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from pipeline import extract as extract_mod, locate, parse

load_dotenv()
HERE = Path(__file__).parent
UPLOADS = HERE / "uploads"
UPLOADS.mkdir(exist_ok=True)
SCHEMAS = HERE / "schemas"
LIBRARY = HERE.parent / "data" / "reports"  # bundled reports; index.json is committed, PDFs via `python data/fetch.py`
FIXTURE = HERE / "fixtures" / "sample_extraction.json"
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
    report_id = uuid.uuid4().hex[:12]
    pdf_path(report_id).write_bytes(data)
    texts = report_texts(report_id)
    company, fiscal_year = guess_meta(texts)
    reports[report_id] = {"report_id": report_id, "filename": file.filename or "upload.pdf", "pages": len(texts), "company": company, "fiscal_year": fiscal_year}
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


@app.post("/api/reports/from-library")
def report_from_library(body: LibraryBody):
    entry = next((e for e in library_index() if e["file"] == body.file), None)
    if not entry or "/" in body.file or "\\" in body.file:  # trust boundary: index basenames only, never a path
        raise HTTPException(404, f"not in library: {body.file!r}; see GET /api/library")
    report_id = "lib-" + Path(body.file).stem  # deterministic: same file twice = same report
    if report_id not in reports:
        library_paths[report_id] = LIBRARY / body.file
        reports[report_id] = {"report_id": report_id, "filename": body.file, "pages": len(report_texts(report_id)),
                              "company": entry["company"], "fiscal_year": entry["fiscal_year"]}  # curated beats guess_meta
    return reports[report_id]


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


@app.post("/api/reports/{report_id}/extract")
def run_extract(report_id: str, body: ExtractBody):
    report = get_report(report_id)
    schema = load_schema(body.section)
    if not os.getenv("LLM_BASE_URL"):  # frontend dev mode: no model configured
        result = json.loads(FIXTURE.read_text(encoding="utf-8")) | {"report_id": report_id}
    else:
        texts = report_texts(report_id)
        pages = locate.candidate_pages(texts, schema)
        print(f"[extract] {report_id} {body.section}: candidate pages {pages}")
        result = extract_mod.extract(texts, pages, schema, report)
    extractions[report_id] = result
    return result


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
