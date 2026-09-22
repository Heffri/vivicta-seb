#!/usr/bin/env python
"""Eval harness: replay hand-labelled fields against the extraction API and score accuracy.
Usage: python eval/run.py [--api URL] [--reports-dir DIR] [--labels CSV] [--dry-run] [--no-fail]
       python eval/run.py --stored-kb DIR [--stored-kb DIR ...]  # offline, no API/model calls"""
import argparse, csv, json, mimetypes, os, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_PATH = os.path.join(HERE, "..", "backend", "fixtures", "sample_extraction.json")
OK, BAD, NA = "✓", "✗", "-"

try:  # ponytail: Windows console defaults to cp1252; force utf-8 so the check/cross marks print cleanly.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def load_labels(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def upload_report(api, path):
    boundary = "evalharnessboundary"
    filename = os.path.basename(path)
    ctype = mimetypes.guess_type(filename)[0] or "application/pdf"
    with open(path, "rb") as f:
        content = f.read()
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n").encode()
    body = head + content + f"\r\n--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    req = urllib.request.Request(f"{api}/api/reports", data=body, method="POST", headers=headers)
    return json.load(urllib.request.urlopen(req))["report_id"]

def extract_section(api, report_id, section):
    data = json.dumps({"section": section}).encode()
    req = urllib.request.Request(f"{api}/api/reports/{report_id}/extract", data=data, method="POST",
                                  headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def values_match(expected, got):
    if str(expected).strip().lower() == "null":  # label says "this company does not report the line" => must be absent
        return got is None
    if got is None or expected in (None, ""):
        return False
    try:
        e, g = float(expected), float(got)
    except (TypeError, ValueError):
        return str(expected).strip().lower() == str(got).strip().lower()
    return abs(e - g) < 0.005  # printed numbers are exact: 11.70 (diluted) is not 11.77

def page_match(expected_page, got_page, expected_value=None, got_value=None):
    if not expected_page:
        return None  # not asserted for this row
    if str(expected_value).strip().lower() == "null" and got_value is None:
        # The label wants the value absent and it is absent -- no citation exists, so there is
        # no page to be right about (the label's expected_page names where the absence was verified).
        # Unscored, same treatment as a missing expected_page: out of the page denominator.
        return None
    if got_page is None:
        return False
    try:
        return int(float(expected_page)) == int(got_page)
    except (TypeError, ValueError):
        return False

def evaluate(rows, extractions):
    results = []
    for row in rows:
        extraction = extractions.get(row["section"]) or {}
        field = next((f for f in extraction.get("fields", []) if f.get("key") == row["key"]), None)
        got_value = field.get("value") if field else None
        got_page = (field.get("source") or {}).get("page") if field else None
        results.append(dict(row, got_value=got_value, got_page=got_page,
                             confidence=field.get("confidence") if field else None,
                             value_ok=values_match(row["expected_value"], got_value),
                             page_ok=page_match(row.get("expected_page"), got_page,
                                                row["expected_value"], got_value)))
    return results

def load_stored_extraction(kb_dir, report_file, section):
    stem = report_file[:-4] if report_file.lower().endswith(".pdf") else report_file
    path = os.path.join(kb_dir, stem, "extractions", f"{section}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def evaluate_stored_kb(rows, kb_dir):
    # ponytail: offline counterpart of evaluate() -- reads already-stored extractions/<section>.json
    # instead of calling the API. A label row whose (report_file, section) has no stored file at all
    # gets value_ok/page_ok=None ("-", not scored) rather than being counted as a miss.
    by_report = {}
    for row in rows:
        by_report.setdefault(row["report_file"], []).append(row)
    results = []
    for report_file, report_rows in by_report.items():
        sections = list(dict.fromkeys(r["section"] for r in report_rows))
        extractions = {}
        for section in sections:
            stored = load_stored_extraction(kb_dir, report_file, section)
            if stored is not None:
                extractions[section] = stored
        scorable = [r for r in report_rows if r["section"] in extractions]
        unscorable = [r for r in report_rows if r["section"] not in extractions]
        results.extend(evaluate(scorable, extractions))
        results.extend(dict(r, got_value=None, got_page=None, confidence=None,
                             value_ok=None, page_ok=None) for r in unscorable)
    return results

def mark(ok):
    return NA if ok is None else (OK if ok else BAD)

def print_report(results, no_fail):
    hdr = f'{"report":<28}{"key":<18}{"expected":>10}{"got":>10}{"val":^5}{"page":^5}{"conf":>6}'
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        conf = f'{r["confidence"]:.2f}' if r["confidence"] is not None else "-"
        print(f'{r["report_file"]:<28}{r["key"]:<18}{str(r["expected_value"]):>10}{str(r["got_value"]):>10}'
              f'{mark(r["value_ok"]):^5}{mark(r["page_ok"]):^5}{conf:>6}')

    total = len(results)
    if total == 0:
        print("\nNo rows evaluated (all reports skipped).")
        return 1
    # ponytail: value_ok is None for stored-kb rows with no extraction file at all ("-", unscored) --
    # excluded from the denominator here, same treatment page_ok already got for "no expected_page".
    value_rows = [r for r in results if r["value_ok"] is not None]
    value_correct = sum(r["value_ok"] for r in value_rows)
    page_rows = [r for r in results if r["page_ok"] is not None]
    page_correct = sum(r["page_ok"] for r in page_rows)
    avg = lambda xs: sum(xs) / len(xs) if xs else None
    ac = avg([r["confidence"] for r in results if r["value_ok"] and r["confidence"] is not None])
    aw = avg([r["confidence"] for r in results if r["value_ok"] is False and r["confidence"] is not None])

    if value_rows:
        print(f"\nvalue accuracy: {value_correct}/{len(value_rows)} ({100 * value_correct / len(value_rows):.1f}%)")
    else:
        print("\nvalue accuracy: n/a (no stored extractions to score)")
    if page_rows:
        print(f"page hit-rate: {page_correct}/{len(page_rows)} ({100 * page_correct / len(page_rows):.1f}%)")
    else:
        print("page hit-rate: n/a (no expected_page given)")
    ac_s = f"{ac:.2f}" if ac is not None else "n/a"
    aw_s = f"{aw:.2f}" if aw is not None else "n/a"
    print(f"mean confidence -- correct: {ac_s}  incorrect: {aw_s}")

    misses = [r for r in results if r["value_ok"] is False]
    if misses:
        print("\nmisses:")
        for r in misses:
            print(f'  {r["report_file"]} / {r["section"]} / {r["key"]}: '
                  f'expected {r["expected_value"]!r}, got {r["got_value"]!r}')
    return 0 if (value_correct == len(value_rows) or no_fail) else 1

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--reports-dir", default="data/reports")
    p.add_argument("--labels", default="eval/labels.csv")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-fail", action="store_true")
    p.add_argument("--stored-kb", action="append", default=[],
                    help="score against already-stored <dir>/<stem>/extractions/<section>.json "
                         "instead of the API; repeatable, one report printed per directory")
    args = p.parse_args()

    rows_all = load_labels(args.labels)

    if args.stored_kb:
        exit_code = 0
        for kb_dir in args.stored_kb:
            print(f"\n=== --stored-kb {kb_dir} ===")
            exit_code = print_report(evaluate_stored_kb(rows_all, kb_dir), args.no_fail) or exit_code
        sys.exit(exit_code)

    by_report = {}
    for row in rows_all:
        by_report.setdefault(row["report_file"], []).append(row)

    all_results = []
    for report_file, rows in by_report.items():
        sections = list(dict.fromkeys(r["section"] for r in rows))
        extractions = {}
        if args.dry_run:
            # ponytail: dry-run ignores --reports-dir entirely; it only proves the scoring logic works.
            with open(FIXTURE_PATH, encoding="utf-8") as f:
                fixture = json.load(f)
            extractions = {s: fixture for s in sections}
        else:
            report_path = os.path.join(args.reports_dir, report_file)
            if not os.path.isfile(report_path):
                print(f"WARNING: {report_path} not found, skipping {report_file}")
                continue
            try:
                report_id = upload_report(args.api, report_path)
                for s in sections:
                    extractions[s] = extract_section(args.api, report_id, s)
            except (urllib.error.URLError, OSError) as e:
                print(f"WARNING: API call failed for {report_file}: {e}")
                extractions = {s: {"fields": []} for s in sections}
        all_results.extend(evaluate(rows, extractions))

    sys.exit(print_report(all_results, args.no_fail))

if __name__ == "__main__":
    main()
