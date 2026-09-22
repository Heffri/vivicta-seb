"""Exercise every Extract > Wallenberg directory option against a running backend.

Downloads reports and checks deterministic candidate-page retrieval; does not run
model extraction or overwrite reviews. Writes resumable JSON evidence after each result.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    def call(path, body=None):
        request = urllib.request.Request(args.base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"detail": raw[:2000] or str(error)}
            return error.code, body

    _, companies = call("/api/companies?collection_name=wallenberg")
    results = json.loads(args.output.read_text(encoding="utf-8"))["results"] if args.retry_failed and args.output.exists() else []
    completed = {r["company"] for r in results if r.get("pdf_available") and r.get("candidate_status") == 200}
    results = [r for r in results if r["company"] in completed]

    def check(company):
        started = time.monotonic()
        result = {"company": company["name"], "group": company["collection_group"]}
        try:
            status, body = call("/api/reports/fetch", {"company": company["name"], "year": args.year})
            result.update(status=status, response=body)
            if status == 200:
                rid = body["report_id"]
                status, candidates = call(f"/api/reports/{rid}/candidates?section=debt_maturity")
                result.update(candidate_status=status, candidate_pages=[p["page"] for p in candidates] if status == 200 else [], candidate_error=candidates if status != 200 else None)
                _, catalog = call("/api/kb?collection_name=wallenberg")
                result["pdf_available"] = next((e["pdf_available"] for e in catalog if e["report_id"] == rid), False)
            else:
                result["pdf_available"] = False
        except Exception as error:
            result.update(status=0, error=str(error), pdf_available=False)
        result["seconds"] = round(time.monotonic() - started, 1)
        return result

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(check, c) for c in companies if c["name"] not in completed]
        for job in as_completed(jobs):
            result = job.result()
            results.append(result)
            args.output.write_text(json.dumps({"checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "year": args.year, "total": len(companies), "results": sorted(results, key=lambda r: r["company"])}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({k: result.get(k) for k in ("company", "status", "pdf_available", "candidate_status", "seconds")}), flush=True)


if __name__ == "__main__":
    main()
