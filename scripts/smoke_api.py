#!/usr/bin/env python
"""Hit every endpoint in docs/API.md against a running backend; print PASS/FAIL per call.

    python scripts/smoke_api.py [--api http://localhost:8000] [--llm] [--fetch "Company Name"]

--llm    also run /extract, /index, /ask (needs Ollama; ~2 min)
--fetch  also run POST /api/reports/fetch for an uncached company (web access; ~1 min)
Exit 1 if anything failed. stdlib only.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
fails = 0
API = "http://localhost:8000"


def call(method, path, body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = {"Content-Type": "application/json"} if body is not None else {}
    h.update(headers or {})
    req = urllib.request.Request(API + path, data=data, method=method, headers=h)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read(), time.time() - t


def check(name, cond, detail=""):
    global fails
    fails += not cond
    print(("PASS  " if cond else "FAIL  ") + name + ("  -- " + str(detail) if detail else ""), flush=True)


def js(b):
    try:
        return json.loads(b)
    except Exception:
        return None


def multipart(filename, content):
    bnd = "smokeboundary"
    head = ('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
            'Content-Type: application/pdf\r\n\r\n' % (bnd, filename)).encode()
    return head + content + ("\r\n--%s--\r\n" % bnd).encode(), {"Content-Type": "multipart/form-data; boundary=" + bnd}


def main():
    global API
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=API)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--fetch", default=None, help="company name to fetch live, e.g. 'Alfa Laval'")
    a = ap.parse_args()
    API = a.api

    st, _, b, _ = call("GET", "/api/schemas")
    schemas = js(b) or []
    check("GET /api/schemas", st == 200 and schemas and schemas[0].get("name"), "%d schemas" % len(schemas))
    section = schemas[0]["name"] if schemas else "income_statement"

    st, _, b, _ = call("GET", "/api/companies?q=sand")
    comps = js(b)
    ok = st == 200 and isinstance(comps, list) and comps and "ticker" in comps[0] and "cached_years" in comps[0]
    check("GET /api/companies?q=sand", ok, "%d hits, first=%s" % (len(comps or []), comps[0]["name"] if comps else None))
    st, _, b, _ = call("GET", "/api/companies?q=")
    check("GET /api/companies?q= (max 50)", st == 200 and isinstance(js(b), list) and len(js(b)) <= 50, len(js(b) or []))

    st, _, b, _ = call("GET", "/api/library")
    lib = js(b) or []
    check("GET /api/library", st == 200 and isinstance(lib, list), "%d cached reports" % len(lib))
    if not lib:
        print("no cached reports; skipping report endpoints")
        return finish()
    entry = next((e for e in lib if e["file"].startswith("atlas")), lib[0])

    st, _, b, dt = call("POST", "/api/reports/from-library", {"file": entry["file"]})
    rep = js(b) or {}
    rid = rep.get("report_id")
    check("POST /api/reports/from-library", st == 200 and rid and rep.get("pages") == entry["pages"],
          "%s %s %sp %.1fs" % (rid, rep.get("company"), rep.get("pages"), dt))
    st, _, b, _ = call("POST", "/api/reports/from-library", {"file": entry["file"]})
    check("  same file twice -> same id", (js(b) or {}).get("report_id") == rid)
    st, _, b, _ = call("POST", "/api/reports/from-library", {"file": "../../backend/app.py"})
    check("  path traversal -> 404", st == 404, st)

    st, _, b, _ = call("GET", "/api/reports/" + rid)
    check("GET /api/reports/{id}", st == 200 and (js(b) or {}).get("report_id") == rid)
    st, _, b, _ = call("GET", "/api/reports/nope")
    check("  unknown id -> 404", st == 404, st)

    st, h, b, _ = call("GET", "/api/reports/%s/pdf" % rid, headers={"Range": "bytes=0-1023"})
    ok = st in (200, 206) and h.get("content-type", "").startswith("application/pdf") and b[:4] == b"%PDF" \
        and "inline" in h.get("content-disposition", "")
    check("GET /api/reports/{id}/pdf (Range)", ok, "%s %dB %s" % (st, len(b), h.get("content-disposition")))
    st, h, b, _ = call("GET", "/api/reports/%s/pages/1.png" % rid)
    check("GET /api/reports/{id}/pages/1.png", st == 200 and h.get("content-type") == "image/png" and b[:4] == b"\x89PNG",
          "%d KB" % (len(b) // 1024))
    st, _, b, _ = call("GET", "/api/reports/%s/pages/99999.png" % rid)
    check("  page out of range -> 404", st == 404, st)

    pdf = os.path.join(ROOT, "data", "reports", entry["file"])
    if os.path.exists(pdf):
        raw, hdr = multipart(entry["file"], open(pdf, "rb").read())
        st, _, b, dt = call("POST", "/api/reports", raw=raw, headers=hdr)
        up = js(b) or {}
        check("POST /api/reports (upload)", st == 200 and up.get("pages") == entry["pages"], "%s %.1fs" % (up.get("report_id"), dt))
        raw, hdr = multipart("x.pdf", b"not a pdf")
        st, _, b, _ = call("POST", "/api/reports", raw=raw, headers=hdr)
        check("  non-PDF upload -> 400", st == 400, st)

    st, _, b, _ = call("POST", "/api/reports/%s/extract" % rid, {"section": "no_such_section"})
    check("POST /extract unknown section -> 404", st == 404, st)
    st, _, b, _ = call("GET", "/api/kb")
    kb = js(b)
    check("GET /api/kb", st == 200 and isinstance(kb, list), "%d kb entries" % len(kb or []))
    st, _, b, _ = call("POST", "/api/ask", {"question": "x", "report_ids": []})
    check("POST /api/ask empty report_ids -> 400", st == 400, st)
    st, _, b, _ = call("POST", "/api/ask", {"question": "x", "report_ids": ["nope"]})
    check("POST /api/ask unknown id -> 404", st == 404, st)

    if a.llm:
        st, _, b, dt = call("POST", "/api/reports/%s/extract" % rid, {"section": section})
        x = js(b) or {}
        fields = x.get("fields", [])
        vals = [f for f in fields if f.get("value") is not None]
        ok = st == 200 and len(vals) >= 6 and all(f.get("source") for f in vals) and all("evidence" in f for f in fields)
        checks = x.get("checks", [])
        check("POST /extract (LLM)", ok, "%d/%d values, checks %d/%d, warnings %d, %.0fs" % (
            len(vals), len(fields), sum(c["passed"] for c in checks), len(checks), len(x.get("warnings", [])), dt))
        for f in fields:
            print("        %-20s %-14s %-6s conf=%.2f  %s" % (f["key"], f.get("value"), f.get("unit"), f.get("confidence", 0),
                                                            ",".join(f.get("evidence", []))))
        st, h, b, _ = call("GET", "/api/reports/%s/extraction.csv" % rid)
        check("GET /extraction.csv", st == 200 and b.decode("utf-8").startswith("report_id,company,fiscal_year,section,key"),
              "%d lines" % b.count(b"\n"))
        st, _, b, dt = call("POST", "/api/reports/%s/index" % rid)
        ix = js(b) or {}
        check("POST /index", st == 200 and ix.get("chunks", 0) > 0, "%s chunks, cached=%s, %.0fs" % (ix.get("chunks"), ix.get("cached"), dt))
        st, _, b, dt = call("POST", "/api/ask", {"question": "What was the revenue and on which page?", "report_ids": [rid]})
        an = js(b) or {}
        check("POST /api/ask (LLM)", st == 200 and an.get("answer") and an.get("citations"),
              "%d citations, warnings %s, %.0fs\n        %s" % (len(an.get("citations", [])), an.get("warnings"), dt, str(an.get("answer"))[:200]))
    else:
        print("skip  /extract /index /ask (LLM) -- pass --llm")

    if a.fetch:
        st, _, b, dt = call("POST", "/api/reports/fetch", {"company": a.fetch, "year": 2025})
        r = js(b) or {}
        check("POST /api/reports/fetch %r" % a.fetch, st == 200 and r.get("report_id") and r.get("pages", 0) > 40,
              "%s %s %sp %.0fs %s" % (st, r.get("report_id"), r.get("pages"), dt, r.get("detail", "")))
    else:
        cached = next((e for e in lib if e.get("company")), None)
        if cached:
            st, _, b, dt = call("POST", "/api/reports/fetch", {"company": cached["company"], "year": cached["fiscal_year"]})
            r = js(b) or {}
            check("POST /api/reports/fetch (cached -> instant)", st == 200 and r.get("report_id"), "%s %s %.1fs" % (st, cached["company"], dt))
        st, _, b, dt = call("POST", "/api/reports/fetch", {"company": "Definitely Not A Company XYZ", "year": 1999})
        check("  unknown company -> 404 with tried[]", st == 404 and isinstance((js(b) or {}).get("tried"), list), "%s %.0fs" % (st, dt))
    return finish()


def finish():
    print("\n" + ("ALL PASS" if not fails else "%d FAILED" % fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
