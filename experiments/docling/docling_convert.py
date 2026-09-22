"""Docling side of the parser comparison: PDF -> texts: list[str], one string per page, via Docling's
own DocumentConverter -- the exact analogue of backend/pipeline/parse.py's page_texts() for our own
parser. Runs under experiments/docling/.venv (Docling is NOT installed in backend/.venv and is never
installed there): compare.py (which runs under backend/.venv to import backend.pipeline.extract) shells
out to this script to produce a per-stem JSON cache, the same split scan_all_compare.py's cached-KB
trick uses to keep the two sides comparable without cross-installing dependencies into either venv.

    experiments/docling/.venv/Scripts/python experiments/docling/docling_parse.py --all
    experiments/docling/.venv/Scripts/python experiments/docling/docling_parse.py --only skf_2025

Default DocumentConverter()/PdfPipelineOptions(): do_ocr=True (force_full_page_ocr=False -- OCR only
where a page has no native text layer, e.g. saab_2025's scanned pages) and do_table_structure=True in
TableFormerMode.ACCURATE. This is Docling exactly as a new user would run it, unmodified, since the
comparison is meant to score the tool's out-of-the-box behaviour, not a tuned configuration.

Page indexing: DoclingDocument.export_to_markdown(page_no=n) is asked for page n directly (1-based,
the same convention parse.page_texts() uses: texts[n-1] is page n). Spot-checked against skf_2025 pages
1-3 (cover / contents / "What we do") and it lines up 1:1 with the PDF's own page numbers -- Docling
does not renumber or drop pages here, so any page_hit_rate gap in the comparison is not an artifact of
this step.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PDFS = ROOT / "pdfs"
CACHE = ROOT / "cache"
STEMS = ["atlas_copco_2025", "ericsson_2025", "investor_2025", "saab_2025", "skf_2025"]


def convert_one(stem: str) -> dict:
    from docling.document_converter import DocumentConverter  # imported lazily: only exists in this venv

    pdf_path = PDFS / f"{stem}.pdf"
    conv = DocumentConverter()
    started = time.perf_counter()
    result = conv.convert(str(pdf_path))
    convert_s = time.perf_counter() - started
    doc = result.document
    n = doc.num_pages()
    export_started = time.perf_counter()
    texts = [doc.export_to_markdown(page_no=p) or "" for p in range(1, n + 1)]
    export_s = time.perf_counter() - export_started
    return {
        "stem": stem, "num_pages": n, "convert_seconds": round(convert_s, 3),
        "export_seconds": round(export_s, 3), "status": str(result.status),
        "texts": texts,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="single stem to convert (default: all 5)")
    ap.add_argument("--all", action="store_true", help="convert all 5, skipping stems already cached")
    ap.add_argument("--force", action="store_true", help="re-convert even if a cache file already exists")
    args = ap.parse_args()
    CACHE.mkdir(exist_ok=True)

    stems = [args.only] if args.only else STEMS
    for stem in stems:
        out_path = CACHE / f"{stem}.json"
        if out_path.exists() and not args.force:
            print(f"[skip] {stem}: {out_path} already cached (--force to redo)")
            continue
        print(f"[convert] {stem} ...", flush=True)
        started = time.perf_counter()
        try:
            data = convert_one(stem)
        except Exception as e:
            print(f"[FAIL] {stem}: {type(e).__name__}: {e}")
            continue
        out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"[done] {stem}: {data['num_pages']} pages, convert {data['convert_seconds']:.1f}s, "
              f"export {data['export_seconds']:.1f}s, wall {time.perf_counter() - started:.1f}s -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
