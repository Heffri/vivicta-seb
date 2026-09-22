# Conventions in this repo

The hackathon is over and nothing here is under active development. These are the conventions the
existing code follows, written down so that what you are reading makes sense.

- **`main` always runs.** Work was branched per task (`feat/locate-toc`, `ui/compare-view`) and
  squash-merged.
- **`docs/API.md` changes first**, before any response shape does. Frontend and backend both build
  against it.
- **Backend:** small, plain functions. No classes or abstractions until two callers exist.
- **`# ponytail: <ceiling>, <upgrade path>`** marks a deliberate shortcut: first the limit at which
  it stops working, then what would replace it. For example
  `reports: dict[str, dict] = {}  # ponytail: in-memory, add sqlite if restarts must survive` says
  the report store is a plain dict, that it is lost on restart, and that sqlite is the fix. These
  comments are scattered through `backend/` and `frontend/src/`; they are the known ceilings of
  this code, recorded rather than hidden.
- **Frontend:** React 19 + Tailwind 4 + shadcn. No router and no state library — no two views
  needed state that props could not carry.
- **`backend/schemas/*.json` is not a free edit.** The schema dict is hashed into the extraction
  cache key (`extraction_identity` in `backend/app.py`), so any change to a schema file
  invalidates every cached extraction for that section and changes what the locator matches.
- **PDFs** go in `data/reports/` (gitignored), named `<company>_<year>.pdf`, e.g.
  `atlas_copco_2025.pdf`.
- **Eval labels** live in `eval/labels.csv`. Edit it in a spreadsheet and save as CSV (UTF-8,
  comma).
- **Commit messages** are `area: what` — `backend: locate via TOC fallback`,
  `eval: add ABB 2025 labels`.
- **Tests** are plain scripts, not a framework. How to run them: the "Checks" section of
  [`README.md`](README.md).

Background reading: [`README.md`](README.md) for what this is and how to run it,
[`docs/CHALLENGE.md`](docs/CHALLENGE.md) for the brief, [`docs/meetings/`](docs/meetings) for the
SEB meeting notes.
