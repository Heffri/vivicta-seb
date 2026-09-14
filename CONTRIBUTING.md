# Working in this repo

- `main` must always run. Branch per task (`feat/locate-toc`, `ui/compare-view`), PR, one teammate reviews, squash-merge.
- Change `docs/API.md` **before** changing a response shape. Frontend and backend build against it.
- Backend: keep functions small and plain; no classes/abstractions until two callers exist. Mark shortcuts with `# ponytail: <ceiling>, <upgrade path>`.
- Frontend: React 19 + Tailwind 4 + shadcn. No router/state lib until two views can't share state with props.
- PDFs go in `data/reports/` (gitignored). Name them `<company>_<year>.pdf`, e.g. `atlas_copco_2025.pdf`.
- New labels for eval: edit `eval/labels.csv` in Excel/Numbers, save as CSV (UTF-8, comma).
- Commit messages: `area: what` — `backend: locate via TOC fallback`, `eval: add ABB 2025 labels`.
- Discord for questions. Meeting notes in `docs/`.
