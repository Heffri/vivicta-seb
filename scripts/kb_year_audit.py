"""Audit the knowledge base against fetch.py's anchored fiscal-year rule; zero model calls.

    python scripts/kb_year_audit.py --kb data/kb

Every <stem>/meta.json's fiscal_year is checked against the entry's own parsed pages.jsonl with the
same gate fetch.py's _validate applies to a downloaded candidate PDF: the fiscal year (or the
split-year "2024/25" / "2024/2025" cover shape) on the first three pages, or an accounting period
ending in it anywhere in the text -- fetch._fiscal_year_re / fetch._period_re, the two regexes
_year_ok composes, so there is no second copy of the rule to drift. The regexes run on page text
rather than an open PDF because the report files themselves are not part of the repo.

Entries failing both are the modern_times_2025 class of corpus defect: a document stored under a
fiscal year its cover does not name, kept alive by forward-looking mentions of the target year.
One line per suspicious entry (cover years, title-year detail, source_url); exit status is always
0 -- this is a report for the evidence file, not a gate.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import fetch  # noqa: E402


def cover_years(head):
    return sorted({m.group(0) for m in re.finditer(r"\b(?:19|20)\d{2}\b", head)}, reverse=True)


def main():
    ap = argparse.ArgumentParser(description="list KB entries whose stored fiscal year their own pages do not support")
    ap.add_argument("--kb", default="data/kb", help="knowledge-base directory (default: data/kb)")
    args = ap.parse_args()
    kb = pathlib.Path(args.kb)
    stems = sorted(p for p in kb.iterdir() if (p / "meta.json").exists()) if kb.is_dir() else []
    checked = suspicious = 0
    for d in stems:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        year = meta.get("fiscal_year")
        if not isinstance(year, int):
            print(f"skip {d.name}: fiscal_year {year!r} is not an int")
            continue
        checked += 1
        pages_file = d / "pages.jsonl"
        if not pages_file.exists():
            print(f"skip {d.name}: no pages.jsonl")
            continue
        rows = (json.loads(l) for l in pages_file.read_text(encoding="utf-8").split("\n") if l.strip())  # not splitlines(): page text may hold U+2028
        pages = [r["text"] for r in sorted(rows, key=lambda r: r["page"])]
        head, full = "".join(pages[:3]), "".join(pages)
        if fetch._fiscal_year_re(year).search(head) or fetch._period_re(year).search(full):
            continue
        suspicious += 1
        ty = fetch._title_year(head, year)
        print(f"SUSPICIOUS {d.name}: fiscal_year {year}, cover years {cover_years(head)}"
              + (f", cover names {ty}" if ty else "") + f", {meta.get('source_url', '')}")
    print(f"{checked} entries checked against the anchored year rule, {suspicious} suspicious")
    return 0


if __name__ == "__main__":
    sys.exit(main())
