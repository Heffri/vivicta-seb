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
```

Contract: [`docs/API.md`](../docs/API.md). Add a section = drop a file in `schemas/`, no code.

Where to start hacking: `pipeline/parse.py` (PDF -> page texts, table-aware text would help),
`pipeline/locate.py` (keyword scoring -> which pages), `pipeline/extract.py` (prompt in
`SYSTEM_PROMPT_TEMPLATE`, provenance check, arithmetic checks). Each module's docstring says what to do next.
