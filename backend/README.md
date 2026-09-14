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
- `python ../eval/run.py` — accuracy + mean confidence against `eval/labels.csv` (needs Ollama; ~1 min per report).
- Company + year in the UI calls `POST /api/reports/fetch`: MFN news feed first, DuckDuckGo PDF search as fallback; the PDF must
  be > 40 pages, have a text layer, and mention the company and the year in its first 20 pages. Cached in `data/reports/`.
