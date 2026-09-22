#!/usr/bin/env python
"""Offline breakdown of stored eval results, including explainable miss buckets.

This deliberately reads the same labels, stored extractions and scoring predicates as
``eval/run.py``.  It does not start the API, download reports, or call a model.

    python scripts/eval_breakdown.py --stored-kb data/kb
    python scripts/eval_breakdown.py --stored-kb data/kb --section income_statement
    python scripts/eval_breakdown.py --stored-kb data/kb --labels eval/heldout-smallcap-2025.csv
    python scripts/eval_breakdown.py --stored-kb data/kb --out breakdown.md

The A--D bucket is a triage aid, not a claim that the heuristic has proved a
table's semantic meaning.  In particular, digit matching can locate a number
outside its intended cell; each result carries the locator and page-shape facts
needed for a follow-up inspection.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "backend"))

import run as ev_run  # noqa: E402 -- keep scoring byte-for-byte aligned with eval/run.py
from pipeline import locate  # noqa: E402


NULL = "null"
BY_DESIGN = {"value_derived", "printed_nil", "stated_zero", "identity_all_columns", "identity_kept"}
PARENT = re.compile(r"\b(?:parent company|parent|moderbolag(?:et|ets)?)\b", re.I)
GROUP = re.compile(r"\b(?:group|consolidated|koncern(?:en|ens)?)\b", re.I)
YEAR = re.compile(r"\b20\d\d\b")
LOCAL_PATH = re.compile(r"(?:[A-Za-z]:\\|/)(?:[^\s|\]\[\"']+[\\/])+[^\s|\]\[\"']*")


def cell(value: Any) -> str:
    """A compact, safe Markdown table cell."""
    if value is None or value == "":
        return "-"
    text = str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    return LOCAL_PATH.sub("<local-path>", text).strip() or "-"


def pct(numerator: int, denominator: int) -> str:
    return "n/a" if not denominator else f"{numerator}/{denominator} ({100 * numerator / denominator:.1f}%)"


def stem(report_file: str) -> str:
    return report_file[:-4] if report_file.lower().endswith(".pdf") else report_file


def stored_path(kb_dir: Path, report_file: str, section: str) -> Path:
    return kb_dir / stem(report_file) / "extractions" / f"{section}.json"


def load_stored(kb_dir: Path, report_file: str, section: str) -> dict[str, Any] | None:
    path = stored_path(kb_dir, report_file, section)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_pages(kb_dir: Path, report_file: str) -> dict[int, str]:
    path = kb_dir / stem(report_file) / "pages.jsonl"
    if not path.is_file():
        return {}
    pages: dict[int, str] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            page = item.get("page")
            if isinstance(page, int) and not isinstance(page, bool):
                pages[page] = item.get("text") or ""
    return pages


def load_schema(section: str) -> dict[str, Any] | None:
    path = ROOT / "backend" / "schemas" / f"{section}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def field_for(extraction: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    if not extraction:
        return None
    return next((item for item in extraction.get("fields", []) if item.get("key") == key), None)


def value_printed(value: Any, text: str) -> bool | None:
    """Use the extractor's numeric matcher, as scripts/page_miss.py does."""
    # Keeping this import local means --help and a missing stored KB need no pipeline import work.
    from pipeline import extract as cur

    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (int, float)):
        try:
            value = float(str(value).replace(" ", "").replace(",", "."))
        except ValueError:
            needle = re.sub(r"\s+", " ", str(value)).strip().lower()
            return bool(needle) and needle in re.sub(r"\s+", " ", text).lower()
    pattern = cur._num_pattern(value)
    return pattern is not None and re.search(pattern, cur._FOOTNOTE.sub("", text)) is not None


def candidate_pages(pages: dict[int, str], schema: dict[str, Any] | None) -> list[int]:
    if not pages or not schema:
        return []
    largest = max(pages)
    texts = [pages.get(page, "") for page in range(1, largest + 1)]
    return locate.candidate_pages(texts, schema)


def relevant_warnings(extraction: dict[str, Any] | None, key: str) -> list[str]:
    if not extraction:
        return []
    key_re = re.compile(rf"(?<![\w/]){re.escape(key)}(?![\w-])")
    warnings = extraction.get("warnings", [])
    field_warnings = [warning for warning in warnings if key_re.search(warning)]
    if field_warnings:
        return field_warnings
    # Timeouts and unit reconciliation are extraction-wide facts. They explain a null field even
    # when the warning did not name every field, without flooding a row with another key's repair.
    return [warning for warning in warnings
            if warning.lower().startswith(("llm:", "currency:", "page selection:"))]


def likely_writer(warnings: list[str]) -> str:
    """The same warning vocabulary mapping used by scripts/page_miss.py."""
    joined = " | ".join(warnings)
    for needle, name in (
        ("section subtotals on page", "_subtotal_pair_fill"),
        ("current-section Summa", "_subtotal_pair_fill"),
        ("finer-split", "_finer_split_rows"),
        ("by its column order", "_fill_bucket_columns"),
        ("dash is printed in the row's own column", "_fill_bucket_columns"),
        ("spans it whole", "_fill_bucket_columns"),
        ("column reading", "_fill_bucket_columns"),
        ("sits between the other rows", "_between_rows"),
        ("sums by maturity date", "_date_bucket_derive"),
        ("it is the sum of", "_derived_value"),
        ("sums to", "_derived_value/_between_rows"),
        ("filled from page", "statement-spread fill"),
        ("quote replaced by page", "quote repair"),
    ):
        if needle in joined:
            return name
    return "model" if not warnings else "warning (unmapped)"


def schema_synonyms(schema: dict[str, Any] | None, key: str) -> list[str]:
    if not schema:
        return []
    item = next((field for field in schema.get("fields", []) if field.get("key") == key), {})
    return [str(value).lower() for value in item.get("synonyms", []) + item.get("fallback_synonyms", [])]


def page_shape(text: str, synonyms: list[str]) -> str:
    """Only observable facts; this intentionally does not infer cells from plain text."""
    if not text:
        return "page text unavailable"
    years = sorted(set(YEAR.findall(text)))
    numeric_lines = sum(bool(re.search(r"\d", line)) for line in text.splitlines())
    facts = [f"numeric-lines={numeric_lines}"]
    if len(years) >= 2:
        facts.append("multi-year=" + "/".join(years[-2:]))
    if GROUP.search(text):
        facts.append("group-marker")
    if PARENT.search(text):
        facts.append("parent-marker")
    if any(term and term in text.lower() for term in synonyms):
        facts.append("schema-synonym")
    else:
        facts.append("no-schema-synonym")
    return ", ".join(facts)


def numeric_ratio(expected: Any, got: Any) -> float | None:
    try:
        expected_number = float(expected)
        got_number = float(got)
    except (TypeError, ValueError):
        return None
    if expected_number == 0:
        return None
    return abs(got_number / expected_number)


def wrong_value_reason(row: dict[str, Any], field: dict[str, Any] | None, source_text: str,
                       label_text: str, warnings: list[str]) -> str:
    """Conservative ordering: recognisable unit / entity cases precede a generic row-or-column flag."""
    ratio = numeric_ratio(row["expected_value"], row.get("got_value"))
    if ratio is not None and (abs(ratio - 1000) < 0.01 or abs(ratio - 0.001) < 0.00001):
        return "unit-scale candidate (×1000)"
    if PARENT.search(source_text) and not PARENT.search(label_text):
        return "parent-company column/page candidate"
    if row.get("got_value") is not None and value_printed(row["expected_value"], source_text) and \
            value_printed(row["got_value"], source_text):
        return "same-table prior-year/other-column or wrong-row candidate"
    evidence = set((field or {}).get("evidence") or [])
    if "label_known" not in evidence:
        return "row label is not schema-recognised (synonym gap candidate)"
    if warnings:
        return "stored-repair result differs; inspect listed warning"
    return "other value mismatch (row/column needs inspection)"


def citation_reason(expected: Any, label_page: int | None, got_page: int | None, label_text: str,
                    source_text: str, evidence: set[str]) -> str:
    on_label = value_printed(expected, label_text)
    on_source = value_printed(expected, source_text)
    if on_label and on_source:
        return "label scope: value is printed on both pages"
    if not on_source and evidence & BY_DESIGN:
        return "derived/translated citation: value is not printed on source page (by design)"
    if not on_source:
        return "citation defect candidate: value is absent from source page"
    if label_page is not None and got_page is not None and abs(label_page - got_page) == 1:
        return "adjacent table continuation/off-by-one candidate"
    return "other page difference; inspect page semantics"


def classify(row: dict[str, Any], field: dict[str, Any] | None, pages: dict[int, str],
             candidates: list[int], schema: dict[str, Any] | None,
             extraction: dict[str, Any] | None) -> dict[str, str]:
    """Return the requested A--D bucket plus the facts that make it auditable."""
    label_page = row.get("expected_page")
    try:
        label_page_int = int(float(label_page)) if label_page else None
    except (TypeError, ValueError):
        label_page_int = None
    got_page = row.get("got_page")
    got_page_int = got_page if isinstance(got_page, int) and not isinstance(got_page, bool) else None
    label_text = pages.get(label_page_int, "")
    source_text = pages.get(got_page_int, "")
    warnings = relevant_warnings(extraction, row["key"])
    evidence = set((field or {}).get("evidence") or [])
    expected_is_null = str(row["expected_value"]).strip().lower() == NULL
    value_pages = [] if expected_is_null else [str(page) for page, text in pages.items()
                                                if value_printed(row["expected_value"], text)]
    synonyms = schema_synonyms(schema, row["key"])
    locator = "label page is a candidate" if label_page_int in candidates else "label page is outside candidates"
    if not candidates:
        locator = "no deterministic candidate pages"

    if row["value_ok"] is False and not expected_is_null and not value_pages:
        bucket, reason = "D", "label candidate: expected value is absent from all stored report text"
    elif field is None or field.get("value") is None:
        # An absent stored extraction is unscored upstream and never reaches this function.
        bucket = "A"
        label_printed = value_printed(row["expected_value"], label_text)
        reason = ("not read; label value is printed on label page" if label_printed
                  else "not read; label value is not literal on label page")
        reason += f"; {locator}"
    elif row["value_ok"] is False:
        bucket = "B"
        reason = wrong_value_reason(row, field, source_text, label_text, warnings)
    else:
        bucket = "C"
        reason = citation_reason(row["expected_value"], label_page_int, got_page_int,
                                 label_text, source_text, evidence)

    return {
        "bucket": bucket,
        "reason": reason,
        "locator": locator,
        "label_shape": page_shape(label_text, synonyms),
        "source_shape": page_shape(source_text, synonyms),
        "writer": likely_writer(warnings),
        "evidence": ", ".join(sorted(evidence)) or "-",
        "warnings": " | ".join(warnings) or "-",
        "value_pages": ", ".join(value_pages) or "none",
    }


def detail_rows(rows: list[dict[str, Any]], kb_dir: Path) -> list[dict[str, Any]]:
    """Augment only crossed rows; scoring itself remains owned by eval/run.py."""
    cache: dict[tuple[str, str], tuple[dict[str, Any] | None, dict[int, str], list[int], dict[str, Any] | None]] = {}
    details: list[dict[str, Any]] = []
    for row in rows:
        if row["value_ok"] is not False and row["page_ok"] is not False:
            continue
        cache_key = (row["report_file"], row["section"])
        if cache_key not in cache:
            extraction = load_stored(kb_dir, row["report_file"], row["section"])
            pages = load_pages(kb_dir, row["report_file"])
            schema = load_schema(row["section"])
            cache[cache_key] = (extraction, pages, candidate_pages(pages, schema), schema)
        extraction, pages, candidates, schema = cache[cache_key]
        field = field_for(extraction, row["key"])
        details.append({**row, **classify(row, field, pages, candidates, schema, extraction)})
    return details


def score_line(rows: list[dict[str, Any]]) -> tuple[str, str, int]:
    scored_values = [row for row in rows if row["value_ok"] is not None]
    scored_pages = [row for row in rows if row["page_ok"] is not None]
    return (
        pct(sum(row["value_ok"] is True for row in scored_values), len(scored_values)),
        pct(sum(row["page_ok"] is True for row in scored_pages), len(scored_pages)),
        len(rows) - len(scored_values),
    )


def render(rows: list[dict[str, Any]], kb_dir: Path, selected_sections: list[str]) -> str:
    by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_section[row["section"]].append(row)
    lines = [
        "# Offline stored-KB eval breakdown",
        "",
        f"Source: `{cell(kb_dir)}`. The script imports `eval/run.py` for the value and page predicates; no API, network, PDF download, or model call is made.",
        "",
        "## Per-section hit rates",
        "",
        "| section | labels | value | page | unscored value |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    for section in selected_sections:
        value_rate, page_rate, unscored = score_line(by_section[section])
        lines.append(f"| `{cell(section)}` | {len(by_section[section])} | {value_rate} | {page_rate} | {unscored} |")

    income = by_section.get("income_statement", [])
    if income:
        lines += ["", "## Income statement by key", "", "| key | labels | value | page | unscored value |",
                  "| --- | ---: | --- | --- | ---: |"]
        by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in income:
            by_key[row["key"]].append(row)
        for key in sorted(by_key):
            value_rate, page_rate, unscored = score_line(by_key[key])
            lines.append(f"| `{cell(key)}` | {len(by_key[key])} | {value_rate} | {page_rate} | {unscored} |")

    details = detail_rows(rows, kb_dir)
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for detail in details:
        by_bucket[detail["bucket"]].append(detail)
    lines += ["", "## Miss buckets", "",
              "A = stored null / not read; B = value mismatch; C = value right, page wrong; D = label candidate (expected value absent from stored text).",
              "",
              "| bucket | rows | companies | company list |",
              "| --- | ---: | ---: | --- |"]
    for bucket in "ABCD":
        names = sorted({stem(row["report_file"]) for row in by_bucket[bucket]})
        lines.append(f"| {bucket} | {len(by_bucket[bucket])} | {len(names)} | {cell(', '.join(names) or '-')} |")

    lines += ["", "## ✗ rows", ""]
    if not details:
        lines.append("No scored value or page misses in the selected section(s). Rows without a stored extraction are unscored, not misses.")
    else:
        for detail in details:
            lines += [
                f"### `{cell(stem(detail['report_file']))}` / `{cell(detail['key'])}` — {detail['bucket']}",
                "",
                f"- Label: value `{cell(detail['expected_value'])}`, page `{cell(detail.get('expected_page'))}`; stored: value `{cell(detail.get('got_value'))}`, page `{cell(detail.get('got_page'))}`.",
                f"- Reason: {cell(detail['reason'])}.",
                f"- Locator: {cell(detail['locator'])}; expected value appears on stored text page(s): `{cell(detail['value_pages'])}`.",
                f"- Page shape (label / stored): {cell(detail['label_shape'])} / {cell(detail['source_shape'])}.",
                f"- Mechanism: `{cell(detail['writer'])}`; evidence: `{cell(detail['evidence'])}`; relevant warning(s): {cell(detail['warnings'])}.",
                "",
            ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stored-kb", action="append", required=True, metavar="DIR",
                        help="stored KB root; repeatable, matching eval/run.py")
    parser.add_argument("--section", action="append", default=[], metavar="NAME",
                        help="limit to a labelled section; repeatable (default: every labelled section)")
    parser.add_argument("--labels", default=str(ROOT / "eval" / "labels.csv"), metavar="CSV",
                        help="labels CSV to score (default: eval/labels.csv)")
    parser.add_argument("--out", help="write Markdown to this UTF-8/LF file instead of stdout")
    args = parser.parse_args()

    labels = ev_run.load_labels(args.labels)
    available = list(dict.fromkeys(row["section"] for row in labels))
    selected = args.section or available
    unknown = sorted(set(selected) - set(available))
    if unknown:
        parser.error("no labels for section(s): " + ", ".join(unknown))
    filtered = [row for row in labels if row["section"] in selected]
    reports: list[str] = []
    for kb in args.stored_kb:
        kb_dir = Path(kb)
        results = ev_run.evaluate_stored_kb(filtered, str(kb_dir))
        reports.append(render(results, kb_dir, selected))
    output = "\n---\n\n".join(reports)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(output, encoding="utf-8", newline="\n")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
