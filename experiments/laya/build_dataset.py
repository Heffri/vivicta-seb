#!/usr/bin/env python
"""Build the applicable-vs-not-applicable binary eval set from eval/labels.csv.

Label: expected_value == "null" (case-insensitive, stripped) -> "not_applicable"; anything else
(a number, or any other non-empty string) -> "applicable". Rows for report_file
nordic_industrials_2025.pdf are dropped -- they are the example/placeholder rows called out in
eval/README.md ("no KB stem and never score") and there is no data/kb/nordic_industrials_2025
directory to pull report text from.

Context text per (report_file, section) is built the same way the real extraction pipeline picks
candidate pages: backend/pipeline/locate.candidate_pages(texts, schema), reading straight from the
already-OCR'd/parsed data/kb/<stem>/pages.jsonl. This is read-only reuse of existing pipeline code
and pre-extracted page text -- no backend server, no LLM calls, no edits to backend/ or eval/.

Output: experiments/laya/dataset.json, one row per label row:
  {report_file, section, key, expected_value, target, field_label, synonyms, context_text}
"""
import csv
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LABELS_CSV = os.path.join(ROOT, "eval", "labels.csv")
SCHEMAS_DIR = os.path.join(ROOT, "backend", "schemas")
KB_DIR = os.path.join(ROOT, "data", "kb")
LOCATE_PY = os.path.join(ROOT, "backend", "pipeline", "locate.py")
OUT_PATH = os.path.join(HERE, "dataset.json")

CONTEXT_CHAR_BUDGET = 3200  # ~ fits laya-multilingual's ~768-token state budget with room for instructions


def load_locate():
    spec = importlib.util.spec_from_file_location("locate_standalone", LOCATE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_schema(section):
    with open(os.path.join(SCHEMAS_DIR, f"{section}.json"), encoding="utf-8") as f:
        return json.load(f)


def load_pages(stem):
    path = os.path.join(KB_DIR, stem, "pages.jsonl")
    if not os.path.isfile(path):
        return None
    by_page = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip("\n")
            if not line:
                continue
            row = json.loads(line)
            by_page[row["page"]] = row.get("text") or ""
    if not by_page:
        return []
    n = max(by_page)
    return [by_page.get(i, "") for i in range(1, n + 1)]


def build_context(texts, schema, locate, budget=CONTEXT_CHAR_BUDGET):
    pages = locate.candidate_pages(texts, schema, top_n=10)
    chunks = []
    used = 0
    for p in pages:
        if not (1 <= p <= len(texts)):
            continue
        t = texts[p - 1]
        if not t:
            continue
        take = t[: max(0, budget - used)]
        if not take:
            break
        chunks.append(f"[p.{p}]\n{take}")
        used += len(take)
        if used >= budget:
            break
    return "\n\n".join(chunks)


def main():
    locate = load_locate()
    with open(LABELS_CSV, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    schemas = {}
    fields_by_section = {}
    for section in ("income_statement", "debt_maturity"):
        schemas[section] = load_schema(section)
        fields_by_section[section] = {fl["key"]: fl for fl in schemas[section]["fields"]}

    pages_cache = {}
    context_cache = {}
    out = []
    skipped_no_kb = 0
    for row in rows:
        report_file = row["report_file"]
        stem = report_file[:-4] if report_file.lower().endswith(".pdf") else report_file
        section = row["section"]
        key = row["key"]
        expected = (row.get("expected_value") or "").strip()

        if stem not in pages_cache:
            pages_cache[stem] = load_pages(stem)
        texts = pages_cache[stem]
        if texts is None:
            skipped_no_kb += 1
            continue

        cache_key = (stem, section)
        if cache_key not in context_cache:
            context_cache[cache_key] = build_context(texts, schemas[section], locate)
        context_text = context_cache[cache_key]

        field = fields_by_section[section].get(key, {})
        target = "not_applicable" if expected.lower() == "null" else "applicable"

        out.append({
            "report_file": report_file,
            "stem": stem,
            "section": section,
            "key": key,
            "expected_value": row.get("expected_value"),
            "target": target,
            "field_label": field.get("label", key),
            "field_description": field.get("description", ""),
            "synonyms": field.get("synonyms", []),
            "context_text": context_text,
            "context_chars": len(context_text),
        })

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    n = len(out)
    n_na = sum(1 for r in out if r["target"] == "not_applicable")
    print(f"wrote {n} rows to {OUT_PATH} ({skipped_no_kb} skipped, no kb dir)")
    print(f"not_applicable: {n_na} ({100*n_na/n:.1f}%)  applicable: {n - n_na} ({100*(n-n_na)/n:.1f}%)")
    print(f"distinct reports: {len(pages_cache)}")
    empty_ctx = sum(1 for r in out if r["context_chars"] == 0)
    print(f"rows with empty context text: {empty_ctx}")


if __name__ == "__main__":
    main()
