"""Offline reachability of the locator's candidate window against labelled pages. No model, no network.

    python scripts/locate_reach.py --section debt_maturity            # 87 eval/labels.csv companies
    python scripts/locate_reach.py --section income_statement        # 101 stored-extraction companies
    python scripts/locate_reach.py --section debt_maturity --baseline origin/acrylic

For every labelled company the expected page(s) are compared with locate.candidate_pages():
    debt_maturity -- eval/labels.csv expected_page, one column per row (a company may hold several);
    income_statement -- the majority source.page of the stored data/kb extraction, the v008 measure
    (labels.csv covers only 12 income companies; the stored set is the 101-company red line v008 used).
Each expected page classifies as
    in          listed among the candidates
    adjacent    ±1 of a listed candidate (the reach of the two-pass companion rule, v045/v120)
    unreachable neither, with a non-empty candidate list
    empty       the company's candidate list is empty (oresund's shape) -- company-wide, dominates
A company takes its worst page's class, so "reachable" (in or adjacent) means every labelled field's
page is in the window. Each row also prints the candidate list and, from locate.scored_pages, the
expected page's own rank and score whenever it scored at all -- rank above top_n or "noscore" (no
keyword on the page, it never entered the ranking) is the why for every miss.

--baseline loads locate.py AS OF that git ref (git show, the replay_check mechanism) and prints both
sides' four-bucket totals plus the per-company class moves, so one run reads a change's whole effect;
without it the current tree is measured alone. Read-only: data/ is never written.
"""
import argparse
import csv
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import locate as cur  # noqa: E402

CLASSES = ("in", "adjacent", "unreachable", "empty")


def load_baseline(ref: str):
    """locate.py as of a git ref, imported as pipeline._reach_baseline_locate (self-contained: imports only re)."""
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:backend/pipeline/locate.py"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="locate_reach_")) / "_reach_baseline_locate.py"
    tmp.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("pipeline._reach_baseline_locate", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_texts(stem_dir: pathlib.Path) -> list[str] | None:
    """pages.jsonl -> texts indexed by page-1; None when missing/empty. Split on '\\n', not splitlines():
    page text may hold U+2028, which splitlines() breaks apart (the same rule as pipeline.kb._pages)."""
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


def debt_expected() -> dict[str, list[int]]:
    """stem -> sorted expected pages from eval/labels.csv debt_maturity rows (rows without a page contribute none)."""
    out: dict[str, list[int]] = {}
    with open(ROOT / "eval" / "labels.csv", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["section"] != "debt_maturity" or not (row.get("expected_page") or "").strip():
                continue
            stem = row["report_file"][:-4] if row["report_file"].lower().endswith(".pdf") else row["report_file"]
            try:
                page = int(row["expected_page"])
            except ValueError:
                continue
            pages = out.setdefault(stem, [])
            if page not in pages:
                pages.append(page)
    return {s: sorted(p) for s, p in out.items()}


def stored_expected() -> dict[str, int]:
    """stem -> majority source.page of the stored income_statement extraction (the v008 measure)."""
    out: dict[str, int] = {}
    for ext in sorted((ROOT / "data" / "kb").glob("*/extractions/income_statement.json")):
        try:
            fields = json.loads(ext.read_text(encoding="utf-8")).get("fields", [])
        except (ValueError, OSError):
            continue
        votes: dict[int, int] = {}
        for f in fields:
            src = f.get("source") if isinstance(f, dict) else None
            if isinstance(src, dict) and isinstance(src.get("page"), int) and not isinstance(src["page"], bool):
                votes[src["page"]] = votes.get(src["page"], 0) + 1
        if votes:
            out[ext.parents[1].name] = max(votes, key=lambda p: (votes[p], -p))
    return out


def page_class(expected: int, pages: list[int]) -> str:
    if expected in pages:
        return "in"
    if any(abs(expected - p) == 1 for p in pages):
        return "adjacent"
    return "unreachable"


def classify(expected: list[int], pages: list[int]) -> str:
    if not pages:
        return "empty"
    worst = {"in": 0, "adjacent": 1, "unreachable": 2}
    return max((page_class(p, pages) for p in expected), key=lambda c: worst[c])


def rank_of(expected: int, scored: list[tuple[float, int]]) -> str:
    for rank, (score, page) in enumerate(scored, 1):
        if page == expected:
            return f"#{rank} @{score:.2f}"
    return "noscore"


def measure(mod, stems: dict[str, list[int]], schema: dict, kb: pathlib.Path):
    rows = []
    for stem in sorted(stems):
        texts = load_texts(kb / stem)
        if texts is None:
            rows.append((stem, stems[stem], None, None, "no pages.jsonl"))
            continue
        pages = mod.candidate_pages(texts, schema)
        scored = mod.scored_pages(texts, schema) if hasattr(mod, "scored_pages") else []
        ranks = [rank_of(p, scored) for p in stems[stem]]
        rows.append((stem, stems[stem], pages, ranks, classify(stems[stem], pages)))
    return rows


def tally(rows) -> dict[str, int]:
    t = {c: 0 for c in CLASSES}
    for row in rows:
        if row[4] in t:
            t[row[4]] += 1
    return t


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Swedish stems on a GBK console
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", required=True, choices=["debt_maturity", "income_statement"])
    ap.add_argument("--baseline", default=None, help="git ref providing the old locate.py (default: none, current tree only)")
    ap.add_argument("--only", default="", help="only companies whose stem contains this substring")
    ap.add_argument("--out", default=None, help="write the report here too (UTF-8, LF)")
    a = ap.parse_args()

    schema = json.loads((ROOT / "backend" / "schemas" / f"{a.section}.json").read_text("utf-8"))
    kb = ROOT / "data" / "kb"
    if a.section == "debt_maturity":
        expected = debt_expected()
    else:
        expected = {s: [p] for s, p in stored_expected().items()}
    expected = {s: p for s, p in expected.items() if a.only in s}

    old = load_baseline(a.baseline) if a.baseline else None
    lines = [f"locate_reach: section {a.section}, {len(expected)} companies"
             + (f", baseline {a.baseline} vs worktree" if old else ", worktree only")]
    now_rows = measure(cur, expected, schema, kb)
    old_rows = measure(old, expected, schema, kb) if old else None

    def table(rows, tag):
        lines.append(f"\n{tag}:")
        for stem, exp, pages, ranks, cls in rows:
            if pages is None:
                lines.append(f"  {stem:<44} {cls:<12} expected {exp} -- {ranks}")
                continue
            marks = " ".join(f"{p}:{c[0]}{'(' + r + ')' if c != 'in' and r else ''}"
                             for p, c, r in zip(exp, (page_class(p, pages) for p in exp), ranks or []))
            lines.append(f"  {stem:<44} {cls:<12} expected {marks}  cands {pages}")
        t = tally(rows)
        reach = t["in"] + t["adjacent"]
        lines.append(f"totals {tag}: in {t['in']} / adjacent {t['adjacent']} / unreachable {t['unreachable']}"
                     f" / empty {t['empty']}  -- reachable(in|adjacent) {reach}/{sum(t.values())}")

    table(now_rows, "worktree")
    if old_rows:
        table(old_rows, "baseline")
        moved = [(n[0], o[4], n[4]) for n, o in zip(now_rows, old_rows) if n[4] != o[4]]
        lines.append(f"\nclass moves baseline -> worktree: {len(moved)}")
        for stem, was, now in moved:
            lines.append(f"  {stem:<44} {was} -> {now}")
    report = "\n".join(lines) + "\n"
    print(report, end="")
    if a.out:
        pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)


if __name__ == "__main__":
    main()
