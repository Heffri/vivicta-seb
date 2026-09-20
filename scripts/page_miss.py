"""Offline page-miss analysis over the stored KB extractions. No model, no network, read-only.

    python scripts/page_miss.py --stored-kb data/kb
    python scripts/page_miss.py --stored-kb data/kb --csv docs/acrylic/evidence/v132/page_miss.csv

For every label row the eval harness scores value_ok=True / page_ok=False (the value the pipeline
returned matches the label, but the cited page is not the label page), the script reports, per row:

    stem / section / key            what row this is
    label_page / got_page / diff    expected_page vs source.page, and their distance
    value_on_got_page               is the label value printed verbatim on the PIPELINE page
                                    (data/kb/<stem>/pages.jsonl text, extract._value_in_quote)
    value_on_label_page             ... and on the label page
    quote_on_page                   does the stored source.quote verify on the stored page
                                    (parse.quote_on_page -- should always be true; a false is a bug)
    evidence / writer / warnings    the field's own evidence markers, the extraction warning that
                                    most likely wrote this source.page, and every warning naming the key
    bucket                          N / A / B / C / D, see below

Buckets (precedence top-down, so each row lands in exactly one):

    N  expected_value is "null" and the pipeline answers null: the value is correctly ABSENT, so no
       citation exists. Inert since the v132-b convention (eval's page_match leaves null/null rows
       unscored), kept so the bucket survives if that convention is ever revisited.
    A  the same number is printed on BOTH the pipeline page and the label page: two pages carry it,
       the label took the other one (labelling scope, not a wrong citation).
    B  the pipeline page does not print the number anywhere. Either a by-design derivation
       (value_derived / printed_nil / stated_zero evidence: the citation names the page the number
       was derived or translated on) or a TRUE defect (no such marker: the value is neither printed
       nor derived there -- the citation points at a page that never carries the number).
    C  the number is printed on the pipeline page but not on the label page, and the pages are one
       apart: a table spanning two pages, or an off-by-one page anchor.
    D  anything else (typically: printed on the pipeline page only, more than one page away).

Caveat carried in the output: _value_in_quote matches digits, not cells -- for |value| < 10 a page
match can come from an unrelated token ("0,4" contains a 0-match for value 0); such rows set the
small_value flag and deserve an eyeball before being believed.

Also counted: value_ok=False rows whose page_ok=True (value-wrong/page-right: the row/column was
misread on a correctly-cited page -- a different problem, not classified here).

Scoring is byte-identical to eval/run.py: the same load_labels / values_match / page_match /
evaluate_stored_kb are imported and reused, not re-implemented.
"""
import argparse, csv, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "eval"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import run as ev_run  # eval/run.py: the scoring this analysis must agree with
from pipeline import extract as cur  # noqa: E402  _value_in_quote
from pipeline.parse import quote_on_page  # noqa: E402

NULL = "null"
BY_DESIGN = {"value_derived", "printed_nil", "stated_zero", "identity_all_columns", "identity_kept"}


def load_pages(kb_dir: str, stem: str) -> dict[int, str]:
    """pages.jsonl as {page: text}; {} when the entry has none."""
    path = os.path.join(kb_dir, stem, "pages.jsonl")
    if not os.path.isfile(path):
        return {}
    pages = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                pages[rec["page"]] = rec.get("text") or ""
    return pages


def value_printed(value, text: str) -> bool | None:
    """The same match extract's provenance gates use, applied to a whole page. None when the value
    is not a number at all (the caller then falls back to a normalised substring)."""
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (int, float)):
        try:
            value = float(str(value).replace(" ", "").replace(",", "."))
        except ValueError:
            needle = re.sub(r"\s+", " ", str(value)).strip().lower()
            return bool(needle) and needle in re.sub(r"\s+", " ", text).lower()
    pat = cur._num_pattern(value)
    return pat is not None and re.search(pat, cur._FOOTNOTE.sub("", text)) is not None


def likely_writer(warnings: list[str]) -> str:
    """Which mechanism most plausibly wrote this source.page, from the warning vocabulary each
    write site uses. 'model' = the model's own answer (validation may have repaired it)."""
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
        ("filled from page", "statement-spread fill (pages[0])"),
        ("quote replaced by page", "quote repair"),
    ):
        if needle in joined:
            return name
    return "model"


def analyze(rows: list[dict], kb_dir: str) -> tuple[list[dict], dict]:
    """One detail record per value-right/page-wrong row, plus summary counters."""
    from collections import Counter

    by_report = {}
    for row in rows:
        by_report.setdefault(row["report_file"], []).append(row)
    details, counts = [], Counter()
    for report_file, report_rows in by_report.items():
        stem = report_file[:-4] if report_file.lower().endswith(".pdf") else report_file
        pages = load_pages(kb_dir, stem)
        for row in report_rows:
            section, key = row["section"], row["key"]
            stored = ev_run.load_stored_extraction(kb_dir, report_file, section)
            if stored is None:
                continue  # unscored ("-"), same as the harness
            field = next((f for f in stored.get("fields", []) if f.get("key") == key), None)
            got_value = field.get("value") if field else None
            got_page = (field.get("source") or {}).get("page") if field else None
            value_ok = ev_run.values_match(row["expected_value"], got_value)
            if value_ok is None:
                counts["unscored"] += 1
                continue
            counts["scored"] += 1
            page_ok = ev_run.page_match(row.get("expected_page"), got_page,
                                        row["expected_value"], got_value)
            if value_ok is False:  # value-wrong: a different problem, counted, not classified
                counts["value_wrong_page_right" if page_ok else "value_wrong_page_wrong"] += 1
                continue
            if page_ok is not False:
                continue  # value-right and page-right (or page not asserted)
            src = (field.get("source") or {}) if field else {}
            label_page = int(row["expected_page"]) if row.get("expected_page") else None
            is_null_label = str(row["expected_value"]).strip().lower() == NULL
            text_got = pages.get(got_page, "") if isinstance(got_page, int) else ""
            text_lbl = pages.get(label_page, "") if isinstance(label_page, int) else ""
            on_got, on_lbl = value_printed(row["expected_value"], text_got), value_printed(row["expected_value"], text_lbl)
            try:
                num = float(str(row["expected_value"]).replace(" ", "").replace(",", "."))
            except ValueError:
                num = None
            evidence = [e for e in (field.get("evidence") or []) if e in BY_DESIGN]
            key_warn = [w for w in stored.get("warnings", [])
                        if re.search(rf"(?<![\w/]){re.escape(row['key'])}(?![\w-])", w)]
            writer = likely_writer(key_warn) if key_warn else ("-" if is_null_label else "model")
            if is_null_label:
                bucket = "N"  # no citation exists to be wrong; the page assert itself is the convention question
            elif on_got and on_lbl:
                bucket = "A"
            elif not on_got:
                bucket = "B"
            elif isinstance(label_page, int) and isinstance(got_page, int) and abs(got_page - label_page) == 1:
                bucket = "C"
            else:
                bucket = "D"
            counts[f"bucket_{bucket}"] += 1
            counts["detail_rows"] += 1
            details.append({
                "stem": stem, "section": section, "key": row["key"],
                "label_page": label_page, "got_page": got_page,
                "diff": (got_page - label_page) if isinstance(label_page, int) and isinstance(got_page, int) else "",
                "value_on_got_page": "" if on_got is None else ("y" if on_got else "n"),
                "value_on_label_page": "" if on_lbl is None else ("y" if on_lbl else "n"),
                "quote_on_page": "y" if (isinstance(got_page, int) and src.get("quote")
                                         and quote_on_page(src["quote"], pages.get(got_page, ""))) else ("-" if is_null_label else "n"),
                "evidence": ",".join(evidence), "writer": writer,
                "small_value": "y" if num is not None and abs(num) < 10 else "",
                "bucket": bucket,
                "notes": (row.get("notes") or "")[:110],
                "warnings": " || ".join(key_warn)[:220],
            })
    return details, counts


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stored-kb", action="append", default=[],
                   help="score against already-stored <dir>/<stem>/extractions/<section>.json (repeatable)")
    p.add_argument("--labels", default=os.path.join(ROOT, "eval", "labels.csv"))
    p.add_argument("--csv", help="write the per-row detail table as CSV to this path")
    args = p.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    rows = ev_run.load_labels(args.labels)
    exit_code = 0
    for kb_dir in args.stored_kb:
        details, counts = analyze(rows, kb_dir)
        print(f"\n=== page_miss --stored-kb {kb_dir} ===")
        scored = counts["scored"]
        vw_pr, vw_pw = counts["value_wrong_page_right"], counts["value_wrong_page_wrong"]
        print(f"scored rows: {scored}  value-wrong: {vw_pr + vw_pw} (page-right {vw_pr} / page-wrong {vw_pw})")
        print(f"value-right/page-wrong: {counts['detail_rows']}  "
              f"N={counts['bucket_N']} A={counts['bucket_A']} B={counts['bucket_B']} "
              f"C={counts['bucket_C']} D={counts['bucket_D']}")
        for b in "NABCD":
            for d in [x for x in details if x["bucket"] == b]:
                print(f"  {b} {d['stem']:<38} {d['section'][:4]:<5} {d['key']:<20} "
                      f"lbl={d['label_page']:>4} got={str(d['got_page']):>4} diff={str(d['diff']):>4} "
                      f"got_pg={d['value_on_got_page'] or '-'} lbl_pg={d['value_on_label_page'] or '-'} "
                      f"qop={d['quote_on_page']:<2} ev={d['evidence'] or '-':<28} by={d['writer']}"
                      + ("  SMALL" if d["small_value"] else ""))
        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(details[0].keys()))
                w.writeheader()
                w.writerows(details)
            print(f"detail table: {args.csv}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
