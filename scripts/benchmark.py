"""Measure five saved PDFs without changing the corpus. --live enables real model calls.

backend/.venv/Scripts/python scripts/benchmark.py --live --count 5
Output is JSON. KB writes go to a temporary directory. Embedding timing is optional (--index).
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import app
from pipeline import kb, llm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--index", action="store_true")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--section", choices=["income_statement", "debt_maturity"])
    parser.add_argument("--reports", nargs="+")
    args = parser.parse_args()
    preferred = ["atlas_copco_2025", "ericsson_2025", "investor_2025", "saab_2025", "skf_2025"]
    entries = sorted(app.library_index(), key=lambda e: preferred.index(Path(e["file"]).stem) if Path(e["file"]).stem in preferred else 100)
    if args.reports:
        entries = [e for e in entries if Path(e["file"]).stem in args.reports]
    original = kb.kb_dir()
    fewshot_n = int(os.getenv("FEWSHOT", "2"))
    sections = [args.section] if args.section else ["income_statement", "debt_maturity"]
    # Snapshot examples from the real KB before redirecting writes to the scratch directory.
    fewshots = {
        (Path(e["file"]).stem, section): kb.fewshot_examples(section, Path(e["file"]).stem, fewshot_n)
        for e in entries[:args.count] for section in sections
    }
    kb.fewshot_examples = lambda section, exclude_stem, n: fewshots.get((exclude_stem, section), [])[:n]
    results = []
    with tempfile.TemporaryDirectory(prefix="report-benchmark-") as directory:
        os.environ["KB_DIR"] = directory
        for entry in entries[:args.count]:
            stem = Path(entry["file"]).stem
            dest = Path(directory) / stem
            dest.mkdir()
            for name in ("meta.json", "pages.jsonl"):
                if (original / stem / name).exists():
                    shutil.copyfile(original / stem / name, dest / name)
            started = time.perf_counter()
            report = app.register_library(entry)
            registration = time.perf_counter() - started
            for section in sections:
                row = {"report": stem, "section": section, "registration_seconds": round(registration, 3)}
                if args.live:
                    try:
                        first = app.run_extract(report["report_id"], app.ExtractBody(section=section))
                        second = app.run_extract(report["report_id"], app.ExtractBody(section=section))
                        assert second["cached"] and second["timings"]["attempts"] == 0
                        row.update(fresh=first["timings"], cached=second["timings"],
                                   values={f["key"]: f["value"] for f in first["fields"]},
                                   warnings=first["warnings"], checks=first["checks"],
                                   fields=first["fields"], debt_scope=first.get("debt_scope"), context_source=first.get("context_source"),
                                   verified=sum("quote_on_page" in f["evidence"] for f in first["fields"]))
                    except Exception as e:
                        row["error"] = str(getattr(e, "detail", e))
                results.append(row)
                print(json.dumps(row), flush=True)
            if args.index:
                try:
                    started = time.perf_counter()
                    kb.index(stem)
                    cold = time.perf_counter() - started
                    started = time.perf_counter()
                    answer = kb.ask([stem], "What was revenue in 2025?")
                    results.append({"report": stem, "cold_index_seconds": round(cold, 3), "warm_ask_seconds": round(time.perf_counter() - started, 3),
                                    "citations": len(answer["citations"]), "warnings": answer["warnings"]})
                except Exception as e:
                    results.append({"report": stem, "index_error": str(e)})
    config = app.config()
    output = {
        "provider": llm.provider(), "model": config["model"], "live": args.live,
        "settings": {
            "reasoning": os.getenv("LLM_REASONING", "low"), "retrieval": config["retrieval"],
            "embed_model": config["embed_model"], "fewshot": fewshot_n,
            "fewshot_examples_by_report_section": {f"{stem}/{section}": len(examples)
                                                     for (stem, section), examples in fewshots.items()},
            "merge_runs": config["merge_runs"], "second_pass": config["second_pass"],
            "scan_all": config["scan_all"], "maturity_basis": config["maturity_basis"],
        },
        "results": results,
    }
    if args.output:
        args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
