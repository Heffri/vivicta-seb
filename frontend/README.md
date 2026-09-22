# frontend — Annual Report Parser UI

React 19 + Vite 8 + Tailwind 4 + shadcn/ui. No router, no state lib: `fetch` + `useState`.

- `npm install` — install
- `npm run dev` — dev server on http://localhost:5173, proxies `/api` → **backend must run on :8000**
- `npm run build` — production build to `dist/`

Where things live: `src/App.tsx` mounts the tabs listed in `src/components/shell/tabs.ts` —
Extract, Results, Compare, Ask, Review, Knowledge base, Company map, Settings — through
`src/components/shell/`;
`src/components/UploadView.tsx` (dropzone, section select, POST upload + extract);
`src/components/ResultsView.tsx` (fields table, checks/warnings, provenance pane with page image + quote);
`src/api.ts` (fetch wrappers + URL helpers); `src/types.ts` (copied from `docs/API.md` — change the contract there first).

`src/components/SettingsView.tsx` (+ `src/components/settings/ProviderCard.tsx`) is read-only here: it
mirrors `GET /api/config` (provider/model/embed model) with a note that settings are edited in the
desktop app or `backend/.env`, since a browser tab has no `window.arp` to read or write
`<userData>/config.json` or restart the backend. The desktop app's editable version — four
provider cards (Ollama, an OpenAI-compatible API endpoint, Codex, Claude), Test and Save — is
documented in `desktop/README.md`.

## Acrylic UI

The app is skinned in the acrylic design language — one glass pane over a wallpaper gradient.
The design spec, token table and contrast numbers live in [`docs/acrylic/DESIGN.md`](../docs/acrylic/DESIGN.md);
walkthrough notes live in `docs/acrylic/evidence/`.

- **Tone**: dark is the default. The rail's Light/Dark button (or anything calling `useTone()` from
  `src/components/shell/useTone.ts`) sets `data-tone` on `<html>` and remembers the choice in
  localStorage key `acrylic-tone`. There is no `.dark` class — `:root` holds the dark tokens,
  `[data-tone="light"]` the light ones, both in `src/index.css`.
- **Tokens**: `src/index.css` maps the acrylic tokens (`--bg-0..4`, `--line-0..2`, `--fg-0..3`,
  `--glass-*`, status colors) onto the shadcn variables; what each is for is the table in
  `docs/acrylic/DESIGN.md`. Shared interaction primitives live in `src/components/ui/` — including
  `state.tsx` (`LoadingLine` = spinner + sentence, `ErrorBlock` = danger block with optional
  collapsible details; empty states are a muted sentence plus the next step).

## Playwright e2e smoke

`e2e/tests/` holds 26 specs over local Microsoft Edge (`channel: 'msedge'` — no browser download),
run serially against one long-lived backend. Six of them (cached-report extract, multi-PDF upload →
Compare, Knowledge base open → Results, the embedded Ask citation flow, candidate pages and source
citation locating) run in both tones; the rest run once. The suite never starts a server itself:

```
# 1. backend, fixture mode (no LLM_* set)
cd backend && uvicorn app:app --port 8000

# 2. frontend dev server, in another shell
cd frontend && npm run dev

# 3. the suite, in a third shell
cd frontend && npm run e2e
```

`E2E_BASE_URL` overrides the default `http://127.0.0.1:5173`. Most specs mock the API routes they
need; seven generate throwaway PDFs at run time (`e2e/fixtures/make-pdf.ts`, no fixture binaries
committed). Only `extract-cached.spec.ts` needs the real PDF at `data/reports/atlas_copco_2025.pdf`
(gitignored, not in this repo — copy it in, or the case `test.skip()`s with a reason instead of
failing).

## Unit tests

Three pure-function suites run on `node:test` with no test framework installed:

```
node --experimental-strip-types --test src/components/ask/renderAnswer.test.ts \
  src/components/ask/sourceDocument.test.ts src/components/results/statusCopy.test.ts
```

21 tests, ~0.1 s. The flag is only needed below Node 24, which strips types on its own.
