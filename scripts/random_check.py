"""Fetch N random listed companies' annual reports and extract a section; report how many parse at full confidence.

    python scripts/random_check.py [--n 10] [--seed 1] [--year 2025] [--section income_statement] [--market "Large Cap"] [--exclude-sector "Real Estate"]

"Full confidence" = every non-null field at confidence 1.0 and every arithmetic check passed (docs/CONFIDENCE.md).
No labels involved: this is the backend's own evidence on companies nobody tuned the parser on. The labelled eval set
(eval/labels.csv) is skipped; the same seed always draws the same companies. Needs the backend on :8000 with Ollama; ~2 min per company.
"""
import argparse
import json
import pathlib
import random
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def call(method, path, body=None, api="http://localhost:8000"):
    req = urllib.request.Request(api + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--section", default="income_statement")
    ap.add_argument("--market", default="Large Cap", help="substring of the market field; '' for all")
    ap.add_argument("--exclude-sector", action="append", default=[],
                    help="drop companies whose sector contains this substring, e.g. 'Real Estate'; repeatable")
    ap.add_argument("--sector", action="append", default=[],
                    help="keep only companies whose sector contains this substring, e.g. 'Financials'; repeatable")
    ap.add_argument("--only", nargs="*", default=[], help="re-check only companies whose name contains one of these")
    ap.add_argument("--api", default="http://localhost:8000", help="backend base URL")
    a = ap.parse_args()

    companies = json.loads((ROOT / "data" / "companies.json").read_text("utf-8"))
    known = {line.split("_")[0] for line in (ROOT / "eval" / "labels.csv").read_text("utf-8").splitlines()[1:]}
    pool = [c for c in companies if a.market.lower() in c.get("market", "").lower()
            and not any(s.lower() in c.get("sector", "").lower() for s in a.exclude_sector)
            and (not a.sector or any(s.lower() in c.get("sector", "").lower() for s in a.sector))
            and c["name"].split()[0].lower() not in known]
    random.Random(a.seed).shuffle(pool)
    if a.only:
        pool = [c for c in pool if any(o.lower() in c["name"].lower() for o in a.only)]

    results, tried = [], 0
    for c in pool:
        if len(results) >= a.n:
            break
        tried += 1
        t0 = time.time()
        st, r = call("POST", "/api/reports/fetch", {"company": c["name"], "year": a.year}, api=a.api)
        if st != 200:
            print(f"skip  {c['name']:<28} fetch {st}: {str(r)[:90]}", flush=True)
            continue
        st, x = call("POST", f"/api/reports/{r['report_id']}/extract", {"section": a.section}, api=a.api)
        if st != 200:
            print(f"fail  {c['name']:<28} extract {st}: {str(x)[:90]}", flush=True)
            results.append((c["name"], 0, 0, False))
            continue
        fields = [f for f in x["fields"] if f["value"] is not None]
        full = sum(f["confidence"] >= 1.0 for f in fields)
        checks_ok = all(ch["passed"] or ch["detail"].startswith("missing:") for ch in x["checks"])
        perfect = bool(fields) and full == len(fields) and checks_ok
        results.append((c["name"], full, len(fields), perfect))
        low = [f"{f['key']}={f['value']}@{f['confidence']}" for f in fields if f["confidence"] < 1.0]
        print(f"{'ok   ' if perfect else 'low  '} {c['name']:<28} {full}/{len(fields)} fields at 1.0, checks {'ok' if checks_ok else 'FAIL'},"
              f" {time.time() - t0:.0f}s  {' '.join(low)}  {[w for w in x['warnings'] if 'llm' in w]}", flush=True)

    perfect = sum(p for *_, p in results)
    cut = ", ".join(a.exclude_sector) if a.exclude_sector else "no sector excluded"
    print(f"\n{perfect}/{len(results)} companies at full confidence ({tried} tried, seed {a.seed}, {a.market or 'all markets'}, {cut})")
    sys.exit(0 if perfect == len(results) else 1)


if __name__ == "__main__":
    main()
