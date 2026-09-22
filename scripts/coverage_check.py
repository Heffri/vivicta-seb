"""Offline labelled-page coverage for locator candidates plus the w198 full-text sweep.

    python scripts/coverage_check.py
    python scripts/coverage_check.py --out docs/acrylic/evidence/w198/coverage.txt

Every debt_maturity row in eval/labels.csv with an expected page is one observation.  The
"before" measure is exact membership in locate.candidate_pages; the "after" measure adds the
field-specific sweep's best three not-yet-tried pages.  No model or network is used.
"""
import argparse
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import extract, locate  # noqa: E402


def load_texts(stem_dir: pathlib.Path) -> list[str] | None:
    """Load 1-based pages into a dense list without treating U+2028 as a record separator."""
    path = stem_dir / "pages.jsonl"
    if not path.exists():
        return None
    texts: list[str] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        row = json.loads(line)
        page = row.get("page")
        if isinstance(page, int) and not isinstance(page, bool) and page >= 1:
            while len(texts) < page:
                texts.append("")
            texts[page - 1] = row.get("text") or ""
    return texts or None


def labelled_rows() -> list[dict]:
    with (ROOT / "eval" / "labels.csv").open(newline="", encoding="utf-8-sig") as handle:
        rows = []
        for row in csv.DictReader(handle):
            if row.get("section") != "debt_maturity" or not (row.get("expected_page") or "").strip():
                continue
            try:
                row["expected_page"] = int(row["expected_page"])
            except ValueError:
                continue
            row["stem"] = pathlib.Path(row["report_file"]).stem
            rows.append(row)
        return rows


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", type=pathlib.Path, default=ROOT / "data" / "kb")
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()

    schema = json.loads((ROOT / "backend" / "schemas" / "debt_maturity.json").read_text(encoding="utf-8"))
    fields = {field["key"]: field for field in schema["fields"]}
    rows = labelled_rows()
    report_cache: dict[str, tuple[list[str] | None, list[int], set[int]]] = {}
    sweep_cache: dict[tuple[str, str], dict] = {}
    locator_hits = sweep_hits = 0
    uncovered: list[tuple[str, str, int, str]] = []

    for row in rows:
        stem, key, expected = row["stem"], row["key"], row["expected_page"]
        if stem not in report_cache:
            directory = args.kb / stem
            texts = load_texts(directory)
            try:
                meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            pending = {page for page in meta.get("ocr_pending", [])
                       if isinstance(page, int) and not isinstance(page, bool)}
            candidates = locate.candidate_pages(texts, schema, fiscal_year=meta.get("fiscal_year")) if texts else []
            report_cache[stem] = texts, candidates, pending
        texts, candidates, pending = report_cache[stem]
        if expected in candidates:
            locator_hits += 1
            continue
        field = fields.get(key)
        if texts is None or field is None:
            uncovered.append((stem, key, expected, "other: missing page text or schema field"))
            continue
        cache_key = stem, key
        if cache_key not in sweep_cache:
            sweep_cache[cache_key] = extract.sweep_pages(
                texts, field, tried_pages=candidates, top_n=3, ocr_pending=pending)
        swept = sweep_cache[cache_key]
        if expected in swept["pages"]:
            sweep_hits += 1
            continue
        if expected in pending:
            reason = "scanned page: ocr_pending"
        elif expected not in swept["hits"]:
            reason = "label page has no numeric synonym row"
        else:
            reason = "other: matching page ranked outside the top 3 sweep pages"
        uncovered.append((stem, key, expected, reason))

    total = len(rows)
    combined = locator_hits + sweep_hits
    lines = [
        f"coverage_check: debt_maturity labelled rows {total}",
        f"locator candidates {locator_hits}/{total}",
        f"full-text sweep supplemental {sweep_hits}/{total}",
        f"combined coverage {combined}/{total}",
        f"still uncovered {len(uncovered)}/{total}",
    ]
    if uncovered:
        lines.append("uncovered rows:")
        lines.extend(f"  {stem} {key} p.{page}: {reason}" for stem, key, page, reason in uncovered)
    report = "\n".join(lines) + "\n"
    print(report, end="")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
