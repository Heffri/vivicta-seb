"""Isolate the parsing step: our own PDF-to-text parser (backend/pipeline/parse.py) vs IBM's Docling,
feeding byte-identical texts into the exact same extract.extract() call and eval scoring. Everything
downstream of "texts: list[str]" is held fixed -- same locate.candidate_pages(), same extract.extract(),
same eval/labels.csv rows, same evaluate()/print_report() -- so any difference in the numbers is a
difference in what the parser handed the model, nothing else. Same shape as scripts/scan_all_compare.py
(targeted-mode logic borrowed from there directly), but the axis under test is the parser, not the page
window.

    backend/.venv/Scripts/python experiments/docling/compare.py
    backend/.venv/Scripts/python experiments/docling/compare.py --section income_statement
    backend/.venv/Scripts/python experiments/docling/compare.py --only ericsson --out experiments/docling/raw.json

Must run under backend/.venv (imports backend.pipeline.extract/locate/llm) -- Docling itself lives only
in experiments/docling/.venv, a second, isolated environment (`pip install docling` there, never into
backend/.venv). The two never need to import each other: Docling's own page-indexed texts are produced
once by docling_convert.py (run under its own venv) and cached as JSON under experiments/docling/cache/
<stem>.json; this script shells out to regenerate a stem's cache on demand if it's missing, exactly the
way locate_reach.py shells to `git show` for a baseline file it does not import.

Five companies (data/reports/index.json's source_url, downloaded once into experiments/docling/pdfs/,
sha256-verified against data/kb/<stem>/meta.json's cached hash so this is provably the same PDF our own
KB was built from): atlas_copco_2025, ericsson_2025, investor_2025, saab_2025, skf_2025.

Needs a real model call to produce a real accuracy comparison: LLM_PROVIDER must be configured (see
backend/.env.example) exactly as scan_all_compare.py needs it. With nothing configured, extract.extract()
still runs end to end -- each model call fails fast (KeyError on the unset LLM_BASE_URL, caught by
extract()'s own per-window try/except) and every field comes back null -- which exercises the full
pipeline (parse timing, locate.candidate_pages, extract.extract, eval scoring) without lying about
having real numbers. --out records which provider/model ran (or "fixture"/none) so a results file is
never mistaken for a scored run.

Ground-truth coverage warning: eval/labels.csv only labels 2 of these 5 companies at all --
atlas_copco_2025 (income_statement, 8 rows) and ericsson_2025 (debt_maturity, 2 rows). investor_2025,
saab_2025 and skf_2025 have zero labelled rows for either section (investor: investment company, income
statement checks fail by design per data/reports/index.json's own note; saab_2025: the English PDF is
image-only with no text layer -- see the parser-asymmetry note below; skf_2025: simply never labelled).
Their value/page accuracy prints "n/a" for both parsers alike -- not a tie, just nothing to score.
"""
import argparse
import csv
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["FEWSHOT"] = "0"  # stable prompts independent of company/run order, same as scripts/benchmark.py
from pipeline import extract as extract_mod, llm, locate, parse  # noqa: E402

PDFS = HERE / "pdfs"
CACHE = HERE / "cache"
KB = ROOT / "data" / "kb"
STEMS = ["atlas_copco_2025", "ericsson_2025", "investor_2025", "saab_2025", "skf_2025"]
SECTIONS = ["income_statement", "debt_maturity"]


def load_eval_run():
    """eval/run.py has no __init__.py sibling; load it as a module by path, like scan_all_compare.py
    and locate_reach.py both do -- reuses evaluate()/print_report() instead of re-deriving scoring."""
    spec = importlib.util.spec_from_file_location("_eval_run", ROOT / "eval" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_meta(stem: str) -> dict:
    """data/kb/<stem>/meta.json when cached (all 5 targets have one); else a rough guess from the
    stem itself so the script still runs standalone against a fresh PDF with no KB entry at all --
    the fallback the task asked for, just never exercised for these 5 since all are already cached."""
    p = KB / stem / "meta.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    parts = stem.rsplit("_", 1)
    year = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None
    return {"company": parts[0].replace("_", " ").title(), "fiscal_year": year}


def our_texts(stem: str) -> tuple[list[str], float]:
    """backend/pipeline/parse.page_texts() on the downloaded PDF, timed. Fresh, not the cached
    pages.jsonl -- this is what buys a real parse_seconds number to put against Docling's own."""
    started = time.perf_counter()
    texts = parse.page_texts(str(PDFS / f"{stem}.pdf"))
    return texts, time.perf_counter() - started


def docling_texts(stem: str, regen: bool) -> tuple[list[str], dict]:
    """Docling's page-indexed texts for stem, from experiments/docling/cache/<stem>.json. Regenerated
    by shelling out to docling_convert.py under experiments/docling/.venv (never imported directly --
    Docling is not, and must not be, installed into backend/.venv, the environment this script itself
    runs under) when the cache is missing or --regen-docling asked for a redo."""
    cache_path = CACHE / f"{stem}.json"
    if regen or not cache_path.exists():
        venv_py = HERE / ".venv" / "Scripts" / "python.exe"
        if not venv_py.exists():
            venv_py = HERE / ".venv" / "bin" / "python"
        cmd = [str(venv_py), str(HERE / "docling_convert.py"), "--only", stem, "--force"]
        print(f"[docling] converting {stem} (no cache yet) ...", flush=True)
        subprocess.run(cmd, check=True, cwd=str(HERE))
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    timing = {"convert_seconds": data["convert_seconds"], "export_seconds": data["export_seconds"],
              "num_pages": data["num_pages"], "status": data.get("status")}
    return data["texts"], timing


def labels_for(labels_path: Path) -> dict[tuple[str, str], list[dict]]:
    """(stem, section) -> label rows, exact-stem match (not substring: saab_2025 vs saab_2025_sv is
    exactly the trap scan_all_compare.py's own stem rule avoids -- report_file[:-4] compared as a whole,
    never `in`/`startswith`, so saab_2025_sv's 8 rows never leak into saab_2025's count)."""
    by_key: dict[tuple[str, str], list[dict]] = {}
    with open(labels_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            stem = row["report_file"][:-4] if row["report_file"].lower().endswith(".pdf") else row["report_file"]
            by_key.setdefault((stem, row["section"]), []).append(row)
    return by_key


def run_extract(stem: str, texts: list[str], schema: dict, report_meta: dict) -> dict:
    """One targeted-mode extract.extract() call -- locate.candidate_pages()'s own window, today's
    production behaviour, no EXTRACT_SCAN_ALL. Mirrors scan_all_compare.py's run_mode(scan_all=False)."""
    os.environ.pop("EXTRACT_SCAN_ALL", None)
    pages = locate.candidate_pages(texts, schema)
    started = time.perf_counter()
    try:
        result = extract_mod.extract(list(texts), list(pages), schema, report_meta)
    except Exception as e:
        result = {"fields": [], "warnings": [f"error: {type(e).__name__}: {e}"],
                  "timings": {"model": 0.0, "attempts": 0, "validate": round(time.perf_counter() - started, 3)}}
    return pages, result


def summarize(results: list[dict]) -> dict:
    """Same arithmetic eval/run.py's print_report() prints, pulled out as numbers instead of console
    text so compare.py can put both parsers' rows in one RESULTS.md table. Not a new scoring rule --
    evaluate()'s own value_ok/page_ok fields, the same None-means-unscored convention, are all this reads."""
    value_rows = [r for r in results if r["value_ok"] is not None]
    page_rows = [r for r in results if r["page_ok"] is not None]
    value_correct = sum(r["value_ok"] for r in value_rows)
    page_correct = sum(r["page_ok"] for r in page_rows)
    return {"value_correct": value_correct, "value_total": len(value_rows),
            "page_correct": page_correct, "page_total": len(page_rows)}


def pct(correct: int, total: int) -> str:
    return "n/a" if total == 0 else f"{100 * correct / total:.1f}% ({correct}/{total})"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", choices=SECTIONS, help="default: both sections")
    ap.add_argument("--only", default="", help="only stems containing this substring")
    ap.add_argument("--labels", default=str(ROOT / "eval" / "labels.csv"))
    ap.add_argument("--regen-docling", action="store_true", help="reconvert every stem via docling_convert.py even if cached")
    ap.add_argument("--out", type=Path, help="write raw per-(stem,section,parser) results as JSON here too")
    ap.add_argument("--results-md", type=Path, default=HERE / "RESULTS.md", help="markdown report path")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    evalrun = load_eval_run()
    schemas = {s: json.loads((ROOT / "backend" / "schemas" / f"{s}.json").read_text("utf-8"))
               for s in (SECTIONS if not args.section else [args.section])}
    stems = [s for s in STEMS if args.only in s]
    all_labels = labels_for(Path(args.labels))

    provider = None
    try:
        provider = llm.provider()
    except Exception:
        pass
    configured = bool(os.getenv("LLM_BASE_URL") or provider in ("codex", "claude"))
    print(f"LLM provider: {provider!r}, configured: {configured} "
          f"({'real model calls' if configured else 'no provider set -- structural dry run, every field will be null'})")

    parse_times: dict[str, dict] = {}
    scored: dict[tuple[str, str], list[dict]] = {}   # (section, parser) -> eval rows
    raw: dict[str, dict] = {}                        # stem -> {section: {parser: result}}
    for stem in stems:
        print(f"\n=== {stem} ===", flush=True)
        meta = load_meta(stem)
        report_meta = {"report_id": f"docling-cmp-{stem}", "company": meta.get("company"),
                       "fiscal_year": meta.get("fiscal_year"), "stem": stem}

        t_ours, ours_s = our_texts(stem)
        t_docling, docling_timing = docling_texts(stem, args.regen_docling)
        parse_times[stem] = {"ours_seconds": round(ours_s, 3), **docling_timing,
                              "ours_pages": len(t_ours), "docling_pages": docling_timing["num_pages"]}
        print(f"  parse: ours {ours_s:.2f}s ({len(t_ours)} pages) | "
              f"docling {docling_timing['convert_seconds']:.1f}s convert + {docling_timing['export_seconds']:.2f}s export "
              f"({docling_timing['num_pages']} pages, status {docling_timing['status']})")
        if len(t_ours) != docling_timing["num_pages"]:
            print(f"  NOTE: page count differs -- ours {len(t_ours)} vs docling {docling_timing['num_pages']} "
                  f"(a mismatch here would misalign page_hit_rate; not the parsing quality itself)")

        raw[stem] = {}
        for section, schema in schemas.items():
            rows = all_labels.get((stem, section), [])
            raw[stem][section] = {}
            for parser_name, texts in (("ours", t_ours), ("docling", t_docling)):
                print(f"  [{section}/{parser_name}] extracting ...", flush=True)
                pages, result = run_extract(stem, texts, schema, report_meta)
                raw[stem][section][parser_name] = {"pages": pages, "result": result}
                if rows:
                    scored.setdefault((section, parser_name), []).extend(
                        evalrun.evaluate(rows, {section: result}))
                else:
                    print(f"    (no eval/labels.csv rows for {stem}/{section} -- not scored)")

    # ---- console report, same shape as scan_all_compare.py's per-mode print_report() ----
    for section in schemas:
        for parser_name in ("ours", "docling"):
            rows = scored.get((section, parser_name), [])
            print(f"\n=== {section} / {parser_name} ===")
            if rows:
                evalrun.print_report(rows, no_fail=True)
            else:
                print("no labelled rows for any company in this run")
            attempts = sum(raw[s][section][parser_name]["result"]["timings"]["attempts"]
                            for s in stems if section in raw[s])
            model_s = sum(raw[s][section][parser_name]["result"]["timings"]["model"]
                           for s in stems if section in raw[s])
            print(f"cost: {attempts} model calls, {model_s:.1f}s model time across {len(stems)} companies")

    # ---- RESULTS.md ----
    lines = ["# Docling vs our parser -- parsing-step comparison\n",
              f"Provider: `{provider}`, configured: {configured}. "
              + ("Real model calls." if configured else
                 "**No LLM provider configured -- these are structural dry-run numbers "
                 "(every field null, fast KeyError on the unset LLM_BASE_URL). Not a real accuracy "
                 "comparison. Set LLM_BASE_URL/LLM_API_KEY or LLM_PROVIDER=codex/claude in backend/.env "
                 "and rerun this script for real numbers.**"),
              "",
              "## Parse time (the isolated variable)",
              "",
              "| company | pages | ours (s) | docling convert (s) | docling export (s) | docling total (s) |",
              "|---|---|---|---|---|---|"]
    for stem in stems:
        pt = parse_times[stem]
        lines.append(f"| {stem} | {pt['ours_pages']} | {pt['ours_seconds']:.2f} | "
                      f"{pt['convert_seconds']:.1f} | {pt['export_seconds']:.2f} | "
                      f"{pt['convert_seconds'] + pt['export_seconds']:.1f} |")
    lines += ["", "## Extraction accuracy and cost (same extract.extract() call, texts source varied)", ""]
    for section in schemas:
        lines.append(f"### {section}")
        lines.append("")
        lines.append("| parser | value accuracy | page hit-rate | model calls | model seconds |")
        lines.append("|---|---|---|---|---|")
        for parser_name in ("ours", "docling"):
            s = summarize(scored.get((section, parser_name), []))
            attempts = sum(raw[st][section][parser_name]["result"]["timings"]["attempts"] for st in stems)
            model_s = sum(raw[st][section][parser_name]["result"]["timings"]["model"] for st in stems)
            lines.append(f"| {parser_name} | {pct(s['value_correct'], s['value_total'])} | "
                          f"{pct(s['page_correct'], s['page_total'])} | {attempts} | {model_s:.1f} |")
        lines.append("")
    lines += [
        "## Ground-truth coverage caveat",
        "",
        "eval/labels.csv only labels 2 of these 5 companies for either section: "
        "**atlas_copco_2025** (income_statement, 8 rows) and **ericsson_2025** (debt_maturity, 2 rows). "
        "**investor_2025**, **saab_2025** and **skf_2025** have zero labelled rows for income_statement "
        "or debt_maturity -- both parsers show `n/a` there, which is an absence of ground truth, not a "
        "tie. Real signal in this run comes from 8 + 2 = 10 labelled fields total across both parsers; "
        "treat the percentages accordingly.",
        "",
        "## Known fairness caveats",
        "",
        "- **saab_2025 is image-only (no text layer)** per data/reports/index.json's own note. Our "
        "parser (backend/pipeline/parse.py) has no OCR fallback wired in yet (see its own module "
        "docstring: \"Next for a teammate: scanned reports need an OCR fallback\") and returns near-empty "
        "text for it. Docling ships OCR on by default (do_ocr=True, force_full_page_ocr=False -- OCR "
        "kicks in exactly where a page has no native text layer, i.e. exactly this file) and may return "
        "real text where ours returns nothing. That is a genuine capability gap this project has not "
        "built yet, not a parsing-quality difference on text both tools can already see -- and saab_2025 "
        "has zero labelled rows either way, so it cannot move the scored accuracy numbers above, only "
        "the parse-time and page-count rows.",
        "- **investor_2025** is an investment company; data/reports/index.json's own note says "
        "\"income-statement checks fail by design\" for it -- it was never going to score well on "
        "income_statement regardless of parser.",
        "- Both parsers were run through the *identical* extract.extract() call, locate.candidate_pages() "
        "window, and eval scoring; the only thing that differs between the \"ours\" and \"docling\" rows "
        "above is which `texts: list[str]` extract() was handed.",
    ]
    args.results_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {args.results_md}")

    if args.out:
        model = os.getenv("LLM_MODEL") or {"codex": "gpt-5.6-terra", "claude": "claude-sonnet-5"}.get(provider or "", "none")
        args.out.write_text(json.dumps({
            "provider": provider, "configured": configured, "model": model,
            "companies": stems, "parse_times": parse_times,
            "raw": {s: {sec: {p: {"pages": raw[s][sec][p]["pages"],
                                    "fields": raw[s][sec][p]["result"]["fields"],
                                    "warnings": raw[s][sec][p]["result"]["warnings"],
                                    "timings": raw[s][sec][p]["result"]["timings"]}
                                   for p in ("ours", "docling")}
                          for sec in raw[s]} for s in stems},
        }, indent=2), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
