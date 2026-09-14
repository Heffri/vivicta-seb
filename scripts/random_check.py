"""Fetch N random listed companies' annual reports and extract a section; report how many parse at full confidence.

    python scripts/random_check.py [--n 10] [--seed 1] [--year 2025] [--section income_statement] [--market "Large Cap"]

"Full confidence" = every non-null field at confidence 1.0 and every arithmetic check passed (docs/CONFIDENCE.md).
No labels involved: this is the backend's own evidence on companies nobody tuned the parser on. Companies already
in data/kb (the tuning set) are skipped. Needs the backend on :8000 with Ollama; ~2 min per company.
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
    a = ap.parse_args()

    companies = json.loads((ROOT / "data" / "companies.json").read_text("utf-8"))
    known = {p.name.split("_")[0] for p in (ROOT / "data" / "kb").iterdir() if p.is_dir()}
    pool = [c for c in companies if a.market.lower() in c.get("market", "").lower()
            and c["name"].split()[0].lower() not in known]
    random.Random(a.seed).shuffle(pool)

    results, tried = [], 0
    for c in pool:
        if len(results) >= a.n:
            break
        tried += 1
        t0 = time.time()
        st, r = call("POST", "/api/reports/fetch", {"company": c["name"], "year": a.year})
        if st != 200:
            print(f"skip  {c['name']:<28} fetch {st}: {str(r)[:90]}", flush=True)
            continue
        st, x = call("POST", f"/api/reports/{r['report_id']}/extract", {"section": a.section})
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
    print(f"\n{perfect}/{len(results)} companies at full confidence ({tried} tried, seed {a.seed}, {a.market or 'all markets'})")
    sys.exit(0 if perfect == len(results) else 1)


if __name__ == "__main__":
    main()
