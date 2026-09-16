# backend

```sh
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # mac/linux: .venv/bin/pip
cp .env.example .env         # leave the LLM_* lines commented to get fixture responses (frontend dev mode)
.venv/Scripts/uvicorn app:app --reload --port 8000

python ../data/fetch.py                                                                          # once: download the bundled reports (data/reports/index.json)
curl http://localhost:8000/api/library                                                           # -> LibraryEntry[] (only files on disk)
curl -X POST -H 'content-type: application/json' -d '{"file":"atlas_copco_2025.pdf"}' http://localhost:8000/api/reports/from-library  # -> same Report shape as an upload, id "lib-atlas_copco_2025"
curl -F file=@report.pdf http://localhost:8000/api/reports                                       # -> {"report_id": "...", ...}
curl -X POST -H 'content-type: application/json' -d '{"section":"income_statement"}' http://localhost:8000/api/reports/<id>/extract
curl http://localhost:8000/api/reports/<id>/extraction.csv
curl -o out.pdf http://localhost:8000/api/reports/<id>/pdf                                       # inline PDF, Range-capable (browser viewer, #page=N)
curl -X POST http://localhost:8000/api/reports/<id>/index                                        # chunk + embed into the KB (cached; /ask does it on demand)
curl -X POST -H 'content-type: application/json' -d '{"question":"Revenue 2025?","report_ids":["<id>"]}' http://localhost:8000/api/ask  # -> Answer with verified citations
curl http://localhost:8000/api/kb                                                                # what is in data/kb/
python -m pipeline.kb build                                                                      # once: meta + pages + embeddings for every bundled report on disk
```

Knowledge base (`pipeline/kb.py`, layout in `docs/API.md`): every parsed report lands in `data/kb/<stem>/` as
`meta.json` + `pages.jsonl` (committed), `/extract` adds `extractions/<section>.json` (committed), `/index` derives
`embeddings.jsonl` (gitignored, `EMBED_MODEL`, default `bge-m3`) from ~800-char page windows plus one fact chunk per
extracted field. `/ask` = cosine + keyword rerank over the selected reports, then `LLM_MODEL` answers with `[Company p.N]`
citations whose quotes are verified against the page text (unverified ones are dropped with a warning). `/extract` shows
the model up to `FEWSHOT` (default 2) checks-passed extractions of the same section from *other* reports, so the mapping
"Skatt" -> `income_tax` improves as the KB grows; `FEWSHOT=0` turns that off.

Contract: [`docs/API.md`](../docs/API.md). Add a section = drop a file in `schemas/`, no code.

Where to start hacking: `pipeline/parse.py` (PDF -> page texts, table-aware text would help),
`pipeline/locate.py` (keyword scoring -> which pages), `pipeline/extract.py` (prompt in
`SYSTEM_PROMPT_TEMPLATE`, provenance check, arithmetic checks), `pipeline/kb.py` (chunking, retrieval, /ask prompt).
Each module's docstring says what to do next.

## Checks

- `python ../scripts/smoke_api.py` — every endpoint in `docs/API.md` against a running backend (`--llm` adds extract/index/ask,
  `--fetch "Alfa Laval"` fetches a report live). Run before pushing backend changes.
- `python -m pipeline.test_confidence` — the evidence scoring in [`docs/CONFIDENCE.md`](../docs/CONFIDENCE.md).
- `python -m pipeline.test_parse`, `python -m pipeline.test_kb`, `python -m pipeline.test_paths` — table-row
  reconstruction, KB save idempotency, and dev-tree-vs-frozen path resolution self-checks.
- `python ../eval/run.py` — accuracy + mean confidence against `eval/labels.csv` (needs Ollama; ~1 min per report).
- Company + year in the UI calls `POST /api/reports/fetch`: MFN news feed first, DuckDuckGo PDF search as fallback; the PDF must
  be > 40 pages, have a text layer, and mention the company and the year in its first 20 pages. Cached in `data/reports/`.

## Desktop build (PyInstaller)

All filesystem paths go through `pipeline/paths.py` (dev tree vs. frozen onedir build, see its module docstring).
Two roots: `resource_dir()` (read-only, bundled: `schemas/`, `fixtures/`) and `data_dir()` (read-write: reports
cache, KB, uploads, `backend.log` — `ARP_DATA_DIR` if set, else `data/` next to the repo root in dev or next to
the exe when frozen).

```sh
pip install -r requirements-build.txt        # adds pyinstaller on top of requirements.txt
python build_exe.py                          # -> dist/backend/backend.exe (onedir; ~106 MB, ~2-6 s cold start)

set ARP_DATA_DIR=C:\path\to\user\data        # companies.json, reports/, kb/, uploads/, backend.log all live here
set FRONTEND_DIST=C:\path\to\frontend\dist   # optional: serve the built frontend from / (SPA fallback to index.html); unset -> no static route at all
dist\backend\backend.exe --port 8000 --host 127.0.0.1
```

- `ARP_DATA_DIR` unset in the packaged exe defaults to a `data/` folder next to `backend.exe` (portable-app style);
  in the dev tree it defaults to `<repo>/data`, unchanged from before this existed.
- `KB_DIR` keeps its pre-existing standalone meaning (resolved against `resource_dir()`, independent of
  `ARP_DATA_DIR`) for backward compatibility with the documented `.env` override.
- The desktop shell is expected to copy `data/companies.json`, `data/reports/index.json`, and `data/kb/` into
  `ARP_DATA_DIR` once (and any cached report PDFs it wants pre-seeded) — `backend.exe` never bundles `data/` itself.
- Logs go to stdout and `<data_dir>/backend.log` (rotated at 5 MB, 3 backups); this mirrors the existing
  `print()`-based diagnostics too, not just uvicorn's own request log, so a console-less run still leaves a trail.
- `backend.spec` bundles `schemas/` + `fixtures/` as data and pins hidden imports uvicorn needs for its dynamic
  loop/protocol imports (`app.py` forces `loop="asyncio", http="h11", ws="none"` so only those concrete
  implementations need to be listed), plus `pymupdf`/`pptx` package data PyInstaller's static analysis can't see
  on its own. A PyInstaller `tzdata` hidden-import warning is expected and harmless (nothing here does named-zone
  `zoneinfo` conversion).
