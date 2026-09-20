"""Offline locator check: run locate.candidate_pages() over every data/kb/*/pages.jsonl; no model, no network.

    python scripts/locate_check.py --section debt_maturity [--only substr] [--top 5]

For each company it prints the top candidate pages with the head of the page text, plus a crude
"looks like the section" marker. The marker is a heuristic triage aid for a human eyeballing the
output, NOT a score: a page counts when it mentions a maturity word (matur-/förfall-/due), at least
one schema field synonym, and is digit-dense (>= 0.05, tables ~0.15-0.3, prose ~0.01) -- i.e. it
looks like a numeric table about maturities. Computed on the same boilerplate-stripped text the
scorer sees, so it explains the ranking rather than the raw page.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import locate  # noqa: E402

MATURITY_WORD = re.compile(r"matur|förfall|\bdue\b(?!\s+to\b)", re.I)  # "due to" is causal, not a deadline


def looks_like_maturity_note(text: str, synonyms: list[str]) -> bool:
    low = " ".join(text.lower().split())
    digits = sum(c.isdigit() for c in text) / max(len(text), 1)
    return bool(MATURITY_WORD.search(low)) and any(s in low for s in synonyms) and digits >= 0.05


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="debt_maturity")
    ap.add_argument("--only", default="", help="only companies whose stem contains this substring")
    ap.add_argument("--top", type=int, default=5, help="candidate pages to print per company")
    a = ap.parse_args()

    schema = json.loads((ROOT / "backend" / "schemas" / f"{a.section}.json").read_text("utf-8"))
    synonyms = sorted({s.lower() for f in schema.get("fields", []) for s in f.get("synonyms", [])})
    kb = ROOT / "data" / "kb"
    stems = sorted(d.name for d in kb.iterdir() if (d / "pages.jsonl").exists() and a.only in d.name)

    flagged = {1: 0, "top5": 0}
    for stem in stems:
        texts = [json.loads(l)["text"] for l in (kb / stem / "pages.jsonl").read_text("utf-8").split("\n") if l]
        pages = locate.candidate_pages(texts, schema)
        stripped = locate.strip_boilerplate(texts)
        print(f"{stem}  ({len(texts)}p)", flush=True)
        for rank, page in enumerate(pages[: a.top], 1):
            low = " ".join(stripped[page - 1].lower().split())
            hit = looks_like_maturity_note(stripped[page - 1], synonyms)
            print(f"  {rank}. p.{page:<4} [{'x' if hit else ' '}] {low[:locate.HEADING_CHARS][:80]!r}", flush=True)
            if hit:
                flagged["top5"] += 1
                if rank == 1:
                    flagged[1] += 1
    print(f"\n{len(stems)} companies, section {a.section}: {flagged[1]}/{len(stems)} top-1 and "
          f"{flagged['top5']}/{len(stems) * min(a.top, 8)} shown pages look like a debt-maturity note "
          f"(heuristic flag, not a score; debt-shaped words, so not meaningful for other sections)", flush=True)


if __name__ == "__main__":
    main()
