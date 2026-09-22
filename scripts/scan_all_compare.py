"""Compare the targeted candidate-page extraction against a brute-force full-document scan.

    backend/.venv/Scripts/python scripts/scan_all_compare.py --section income_statement --limit 5
    backend/.venv/Scripts/python scripts/scan_all_compare.py --section debt_maturity --only ericsson --all

Reads pages.jsonl straight from the already-cached data/kb/<stem>/ -- no PDF, no upload, the same
corpus eval/labels.csv is scored against (scripts/locate_reach.py uses the same trick to stay
offline). Needs a real model call either way: LLM_PROVIDER must be configured (see backend/.env.example).

Two extraction calls per company, both through the exact same extract.extract() call, scoring and
evidence checks:
  targeted  locate.candidate_pages()'s pages[:2]/pages[:4] window -- today's production behaviour.
  scan_all  EXTRACT_SCAN_ALL=1: every page of the document, two at a time, stopping as soon as every
            schema field already has a value -- "let the model search the entire PDF" from first
            principles, ignoring locate.py's guess of where to look.
A difference in the result is a difference in *which pages got read*, nothing else. Cost is read off
each mode's own timings (model seconds, attempts) -- the resources the brute-force approach spends to
buy (or fail to buy) accuracy.

Scored against eval/labels.csv with the same evaluate()/print_report() the live eval harness uses,
including its "null" = "this row does not apply to this company" convention.
"""
import argparse
import csv
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["FEWSHOT"] = "0"  # stable prompts independent of company/run order, same as scripts/benchmark.py
from pipeline import extract as extract_mod, llm, locate  # noqa: E402

KB = ROOT / "data" / "kb"


def load_eval_run():
    """eval/run.py has no __init__.py sibling; load it as a module by path, like locate_reach.py
    loads a baseline locate.py -- reuses evaluate()/print_report() instead of re-deriving scoring."""
    spec = importlib.util.spec_from_file_location("_eval_run", ROOT / "eval" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_texts(stem_dir: Path) -> list[str] | None:
    """pages.jsonl -> texts indexed by page-1; None when missing/empty. Same rule as pipeline.kb._pages."""
    p = stem_dir / "pages.jsonl"
    if not p.exists():
        return None
    texts: list[str] = []
    for line in p.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        d = json.loads(line)
        n = d.get("page")
        if isinstance(n, int) and n >= 1:
            while len(texts) < n:
                texts.append("")
            texts[n - 1] = d.get("text") or ""
    return texts or None


def load_meta(stem_dir: Path) -> dict:
    p = stem_dir / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def labels_for_section(labels_path: Path, section: str) -> dict[str, list[dict]]:
    by_stem: dict[str, list[dict]] = {}
    with open(labels_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["section"] != section:
                continue
            stem = row["report_file"][:-4] if row["report_file"].lower().endswith(".pdf") else row["report_file"]
            by_stem.setdefault(stem, []).append(row)
    return by_stem


def run_mode(stem: str, texts: list[str], schema: dict, report_meta: dict, scan_all: bool) -> dict:
    if scan_all:
        os.environ["EXTRACT_SCAN_ALL"] = "1"
    else:
        os.environ.pop("EXTRACT_SCAN_ALL", None)
    pages = locate.candidate_pages(texts, schema)
    started = time.perf_counter()
    try:
        result = extract_mod.extract(list(texts), list(pages), schema, report_meta)
    except Exception as e:
        result = {"fields": [], "warnings": [f"error: {type(e).__name__}: {e}"],
                  "timings": {"model": 0.0, "attempts": 0, "validate": round(time.perf_counter() - started, 3)}}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", required=True, choices=["income_statement", "debt_maturity"])
    ap.add_argument("--labels", default=str(ROOT / "eval" / "labels.csv"))
    ap.add_argument("--only", default="", help="only companies whose stem contains this substring")
    ap.add_argument("--limit", type=int, default=5, help="max companies to run (default 5; ignored with --all)")
    ap.add_argument("--all", action="store_true", help="run every labelled company for this section")
    ap.add_argument("--out", type=Path, help="write raw per-mode results as JSON here too")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    evalrun = load_eval_run()
    schema = json.loads((ROOT / "backend" / "schemas" / f"{args.section}.json").read_text("utf-8"))
    by_stem = labels_for_section(Path(args.labels), args.section)
    stems = sorted(s for s in by_stem if args.only in s)
    if not args.all:
        stems = stems[:args.limit]
    if not stems:
        print(f"no labelled {args.section} companies matched --only {args.only!r}")
        return 1

    modes = ["targeted", "scan_all"]
    scored = {m: [] for m in modes}
    raw = {m: {} for m in modes}
    skipped = []
    for stem in stems:
        stem_dir = KB / stem
        texts = load_texts(stem_dir)
        if texts is None:
            skipped.append(stem)
            continue
        meta = load_meta(stem_dir)
        report_meta = {"report_id": f"lib-{stem}", "company": meta.get("company"),
                       "fiscal_year": meta.get("fiscal_year"), "stem": stem}
        for mode in modes:
            print(f"[{mode}] {stem} ...", flush=True)
            result = run_mode(stem, texts, schema, report_meta, scan_all=(mode == "scan_all"))
            raw[mode][stem] = result
            scored[mode].extend(evalrun.evaluate(by_stem[stem], {args.section: result}))

    if skipped:
        print(f"\nskipped (no cached pages.jsonl): {', '.join(skipped)}")

    for mode in modes:
        print(f"\n=== {mode} ===")
        evalrun.print_report(scored[mode], no_fail=True)
        attempts = sum(r["timings"]["attempts"] for r in raw[mode].values())
        model_s = sum(r["timings"]["model"] for r in raw[mode].values())
        print(f"cost: {attempts} model calls, {model_s:.1f}s model time across {len(raw[mode])} companies")

    if args.out:
        model = os.getenv("LLM_MODEL") or {"codex": "gpt-5.6-terra", "claude": "claude-sonnet-5"}.get(llm.provider(), "fixture")
        args.out.write_text(json.dumps({
            "provider": llm.provider(), "model": model, "section": args.section,
            "companies": list(raw["targeted"]), "skipped": skipped,
            "modes": {m: {stem: {"fields": r["fields"], "warnings": r["warnings"], "timings": r["timings"]}
                          for stem, r in raw[m].items()} for m in modes},
        }, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
