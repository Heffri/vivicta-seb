# desktop — Electron shell for the Annual Report Parser

Double-click app, not a browser tab. Launches the backend itself, loads the frontend, and on
Windows 11 paints the window with real OS acrylic material (the desktop shows through, blurred)
instead of the browser's painted wallpaper-and-glass fallback.

## Dev mode

```powershell
cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt   # once
cd ..\desktop; npm install                                                          # once
npm run dev
```

One command brings up the backend (venv `uvicorn`), the frontend (`frontend`'s own `npm run dev`),
and the Electron window, in that order, each gated on a health check. If you already have either
one running by hand (e.g. `cd frontend && npm run dev` in another terminal), `npm run dev` here
detects and reuses it instead of starting a second copy.

### Dev mode port is fixed at 8000, not random

`frontend/vite.config.ts` hardcodes its `/api` dev proxy to `http://localhost:8000` — that file is
outside this package's territory, so it can't be made to follow whatever port the backend picks.
Dev mode's backend therefore always binds `:8000` (reusing it if already listening, per above);
only **packaged** mode picks a random free port, because there the backend serves the frontend
itself on that same port (same origin, no proxy involved — see "Packaged mode" below).

Reload (`Ctrl+R`) and DevTools (`F12`) only work in dev mode; the packaged app has no menu and no
devtools access, for a clean end-user window.

## Packaged mode

```powershell
cd frontend; npm run build      # produces frontend/dist
cd ..\desktop; npm install      # once
npm run dist                    # nsis installer + portable exe, in desktop/dist/
```

The packaged app loads `http://127.0.0.1:<random free port>/` — the backend itself serves
`frontend/dist` as a static site at `/` and the API at `/api` (same origin, zero CORS). First
launch copies the bundled `data/` (companies, report index, knowledge base — no PDFs) into
`app.getPath('userData')/data`; later launches reuse it, so a user's uploads/index rebuilds
survive an upgrade.

### Packaging without backend.exe

The backend packaging lane (v030, PyInstaller) may not have shipped `backend/dist/backend.exe`
yet. `npm run dist` packages fine regardless (`scripts/prepare-resources.js` stages whatever
`backend/dist` has, or nothing). At runtime the app looks for `resources/backend/backend.exe`; if
it's missing, that's a normal end-user-facing failure (clear dialog, log file path) **unless** you
set `ARP_DEV_BACKEND_DIR` to a `backend/` checkout that has its own `.venv` — then the packaged
exe runs that with `python -m uvicorn` instead, exactly like dev mode. This is a dev-machine
smoke-test escape hatch, not a shipped feature: a real end-user install has no such checkout.

```powershell
$env:ARP_DEV_BACKEND_DIR = "C:\path\to\backend"
.\dist\win-unpacked\"Annual Report Parser.exe"
```

## Settings

The Settings tab (desktop only — a browser tab gets a read-only mirror, see `frontend/README.md`)
picks a model provider from four cards — **Ollama** (a local server, defaults to
`http://127.0.0.1:11434/v1` + `qwen3:8b`), an **API endpoint** (any OpenAI-compatible `/v1` host —
OpenAI itself, or an Anthropic-compatible one), **Codex** (subscription: the local Codex CLI login,
model `gpt-5.6-terra`/`gpt-5.6-sol`), and **Claude** (subscription: the local Claude Code CLI login,
model `claude-sonnet-5`/`claude-opus-5`/`claude-haiku-4-5-20251001`) — plus a demo-mode link back to
the fixture default. "Test" checks reachability (`GET <base>/models`) or, for Codex/Claude, runs
`codex --version`/`claude --version` + a login-status check, never a real model call. "Save" writes
`<userData>/config.json` (API key in plaintext — this file is the only place it's ever stored, and
it never reaches a log) and restarts the backend on the same port with the matching `LLM_*` env
(`desktop/settings.js` has the full translation table); if the restart fails the window shows the
error and keeps running (no backend, not a crash) rather than reverting to what was there before —
see `docs/acrylic/evidence/v033.md` for why a revert-on-failure wasn't added.

## Not signed

`npm run dist` does not code-sign anything (no certificate configured). Windows SmartScreen will
show an "unknown publisher" warning on first run of the installer and the portable exe — click
"More info" → "Run anyway". Fine for internal/demo use; a real release needs a code-signing
certificate, which is out of scope here.

## Not done (left for later)

- Code signing / SmartScreen suppression.
- Auto-update.
- Data directory override in the Settings UI (still only via `ARP_DEV_BACKEND_DIR`, a testing escape
  hatch — see "Settings" above for what the UI does cover: provider/model, not paths).
- macOS/Linux packaging targets (`win` only in `electron-builder.yml`; the acrylic material itself
  is Windows-11-only regardless — `supportsAcrylic()` in `main.js` degrades to an opaque window
  everywhere else, including Windows 10).

## Files

- `main.js` — main process: single-instance lock, backend launch + health check, window creation,
  acrylic detection, titlebar-overlay tone sync, Settings IPC (get/set/test/codexStatus/claudeStatus)
  and the backend-restart-on-save logic.
- `settings.js` — `<userData>/config.json` load/save and its translation to the backend's `LLM_*` env
  vars; see "Settings" above.
- `preload.js` — exposes `window.arp = { material, platform, version, settings }` to the renderer
  (read by `frontend/src/main.tsx` and `frontend/src/components/SettingsView.tsx`) and mirrors
  `<html data-tone>` back to the main process over IPC so the native titlebar-overlay buttons can
  match the app's dark/light toggle.
- `electron-builder.yml` — nsis + portable targets, `extraResources` from `build-resources/`
  (staged by `scripts/prepare-resources.js`, gitignored).
- `icons/icon.ico` (+ `make-icon.js`, its generator) — placeholder mark, "AR" in a 5x7 dot-matrix
  font on a dark rounded square, hand-drawn with a ~130-line PNG/ICO encoder (no image-library
  dependency for one static asset). Colors from `docs/acrylic/DESIGN.md`'s dark wallpaper/accent.
