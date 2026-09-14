# frontend — Annual Report Parser UI

React 19 + Vite 8 + Tailwind 4 + shadcn/ui. No router, no state lib: `fetch` + `useState`.

- `npm install` — install
- `npm run dev` — dev server on http://localhost:5173, proxies `/api` → **backend must run on :8000**
- `npm run build` — production build to `dist/`

Where things live: `src/App.tsx` toggles `'upload' | 'results'`; `src/components/UploadView.tsx` (dropzone, section select, POST upload + extract);
`src/components/ResultsView.tsx` (fields table, checks/warnings, provenance pane with page image + quote);
`src/api.ts` (3 fetch wrappers + URL helpers); `src/types.ts` (copied from `docs/API.md` — change the contract there first).
