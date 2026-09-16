# frontend — Annual Report Parser UI

React 19 + Vite 8 + Tailwind 4 + shadcn/ui. No router, no state lib: `fetch` + `useState`.

- `npm install` — install
- `npm run dev` — dev server on http://localhost:5173, proxies `/api` → **backend must run on :8000**
- `npm run build` — production build to `dist/`

Where things live: `src/App.tsx` mounts the five tabs (Extract / Results / Compare / Ask / Knowledge base) through `src/components/shell/`;
`src/components/UploadView.tsx` (dropzone, section select, POST upload + extract);
`src/components/ResultsView.tsx` (fields table, checks/warnings, provenance pane with page image + quote);
`src/api.ts` (fetch wrappers + URL helpers); `src/types.ts` (copied from `docs/API.md` — change the contract there first).

## Acrylic UI

The app is skinned in the acrylic design language — one glass pane over a wallpaper gradient.
The design spec, token table and contrast numbers live in [`docs/acrylic/DESIGN.md`](../docs/acrylic/DESIGN.md);
per-lane walkthrough notes live in `docs/acrylic/evidence/`.

- **Tone**: dark is the default. The rail's Light/Dark button (or anything calling `useTone()` from
  `src/components/shell/useTone.ts`) sets `data-tone` on `<html>` and remembers the choice in
  localStorage key `acrylic-tone`. There is no `.dark` class — `:root` holds the dark tokens,
  `[data-tone="light"]` the light ones, both in `src/index.css`.
- **Tokens**: `src/index.css` maps the acrylic tokens (`--bg-0..4`, `--line-0..2`, `--fg-0..3`,
  `--glass-*`, status colors) onto the shadcn variables; what each is for is the table in
  `docs/acrylic/DESIGN.md`. Shared interaction primitives live in `src/components/ui/` — including
  `state.tsx` (`LoadingLine` = spinner + sentence, `ErrorBlock` = danger block with optional
  collapsible details; empty states are a muted sentence plus the next step).
- **Screenshots**: run the backend, then `npm run dev` against it (set `API_TARGET` and the shared
  lane vite override so `/api` proxies to your backend port). Capture with the shared Playwright
  helper over the local Edge channel (`shot.mjs` in the lanes' shared tools — pass
  `--tonekey acrylic-tone --tone dark|light`); it exists because tone and KB rows are awkward to
  drive otherwise. Screenshots go into `docs/acrylic/evidence/<lane>/` next to their notes.
