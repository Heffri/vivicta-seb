# desktop — Electron shell for the Annual Report Parser

Double-click app, not a browser tab. Launches the backend itself and loads the frontend.
The window's background follows the Theme setting: **Solid** (the default) paints the app's own
light/dark background, which does not change when focus moves to another app; **Acrylic** asks
Windows 11 for the real material, so the desktop shows through. See "Settings" below.

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

### Dev mode port is fixed at 8000

`frontend/vite.config.ts` hardcodes its `/api` dev proxy to `http://localhost:8000`, so dev mode's
backend always binds that exact port (reusing it if already listening, per above). Packaged mode
chooses its own port instead, because there the backend serves the frontend itself on that same
port — same origin, no proxy involved. See "Packaged mode" below.

Reload (`Ctrl+R`) and DevTools (`F12`) only work in dev mode; the packaged app has no menu and no
devtools access, for a clean end-user window.

## Packaged mode

```powershell
cd frontend; npm run build      # produces frontend/dist
cd ..\desktop; npm install      # once
npm run dist                    # nsis installer + portable exe, in desktop/dist/
```

The packaged app loads `http://127.0.0.1:<port>/` — the backend itself serves `frontend/dist` as a
static site at `/` and the API at `/api` (same origin, zero CORS).

That port is stable, not random. The app tries the port it used last (`backendPort` in
`<userData>/config.json`), then 47311–47326 in order, and only falls back to a random free port if
every one of those is taken. Keeping the same port keeps one userData directory on one browser
origin, so the renderer's `localStorage` (theme, viewer and chart preferences) survives a relaunch.

The bundled `data/` (companies, report index, knowledge base — no PDFs) is synced into
`app.getPath('userData')/data` on every launch: files the user never modified follow the app's
bundled copy (tracked by a `.bundle-manifest.json` hash manifest), while user uploads (`kb/up-*`),
reviewed extractions and anything the user changed are kept. Launch with `--user-data-dir <dir>`
(or `--user-data-dir=<dir>`) to relocate the whole userData directory — logs, data, single-instance
lock — for isolated test runs; both the packaged exe and `npm run dev` honor it.

### Running a packaged build without backend.exe

CI builds `backend/dist/backend.exe` (`backend/build_exe.py`, PyInstaller) and
`scripts/prepare-resources.js` stages it into the installer, so a normal build has it. Packaging
from a checkout that never ran `build_exe.py` still succeeds — `prepare-resources.js` stages
whatever `backend/dist` has, or nothing. At runtime the app then fails to find
`resources/backend/backend.exe` and shows an end-user-facing dialog with the log file path,
**unless** you set `ARP_DEV_BACKEND_DIR` to a `backend/` checkout that has its own `.venv` — then
the packaged exe runs that with `python -m uvicorn` instead, exactly like dev mode. This is a
dev-machine smoke-test escape hatch, not a shipped feature: a real end-user install has no such
checkout.

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

The Appearance tab carries the Theme select (Solid/Acrylic). It writes the same `config.json` and
switches the live window material without restarting the backend; on a platform that cannot switch
a live window it persists the choice and the UI asks for a relaunch.

## Limitations

- `npm run dist` does not code-sign anything (no certificate configured). Windows SmartScreen will
  show an "unknown publisher" warning on first run of the installer and the portable exe — click
  "More info" → "Run anyway". Fine for internal/demo use; a real release needs a code-signing
  certificate, which is out of scope here.
- Windows only: `win` is the sole target in `electron-builder.yml`. No macOS or Linux build.

## Files

- `main.js` — main process: single-instance lock, backend launch + health check, window creation,
  stable window background, titlebar-overlay tone sync, Settings IPC (get/set/test/codexStatus/claudeStatus)
  and the backend-restart-on-save logic.
- `settings.js` — `<userData>/config.json` load/save and its translation to the backend's `LLM_*` env
  vars; see "Settings" above.
- `preload.js` — exposes `window.arp = { material, platform, version, settings }` to the renderer
  (read by `frontend/src/main.tsx` and `frontend/src/components/SettingsView.tsx`) and mirrors
  `<html data-tone>` back to the main process over IPC so the native titlebar-overlay buttons can
  match the app's dark/light toggle.
- `data-sync.js` — the bundled-data merge described under "Packaged mode".
- `report-browser.js` — the isolated window used to download a report PDF from a public listing.
- `updates.js` — the auto-update wiring described below.
- `electron-builder.yml` — nsis + portable targets, `extraResources` from `build-resources/`
  (staged by `scripts/prepare-resources.js`, gitignored).
- `icons/icon.ico` (+ `make-icon.js`, its generator) — placeholder mark, "AR" in a 5x7 dot-matrix
  font on a dark rounded square, hand-drawn with a ~130-line PNG/ICO encoder (no image-library
  dependency for one static asset). Colors from `docs/acrylic/DESIGN.md`'s dark wallpaper/accent.

## Automatic updates

Pushes to `main` and `demo` build the frontend, Python backend and Windows NSIS installer in
GitHub Actions. Each branch publishes its own update feed:

- [Main installer releases](https://github.com/Heffri/vivicta-seb/releases/latest) — the public
  download, always the current `main`. One installer, under a stable filename that each build
  replaces; `latest.yml` beside it carries the version the updater compares against.
- [Demo installer releases](https://github.com/Heffri/vivicta-seb/releases/tag/desktop-demo) —
  kept a prerelease, so it never takes the "Latest" slot from main.

Install the Setup executable once. Only the installed app updates itself; the portable exe does
not. Installed copies check on startup and hourly, download in the background, and apply on normal
exit. Restart to use the new build. A failed build leaves the previous update available. Offline
update checks do not prevent using the app. Main and demo install separately and keep separate
settings and data.

Versions are generated as `1.<workflow run number>.<attempt>`, so no commit ever bumps a version.
The workflow uploads the installer and blockmap before `latest.yml`, and the feed retains older
versioned installers, so a client finishing an earlier download can still retrieve it.

Sharing saved reports between checkouts is a separate, Git-based flow that needs no new build and
never reads model settings: `node scripts/sync-team-data.js`, documented in
[the root README](../README.md#sharing-saved-reports-with-the-hackathon-team).

## Checks

```powershell
node --test desktop/data-sync.test.js desktop/port.test.js desktop/report-browser.test.js desktop/updates.test.js
node desktop/packaging.test.js          # a plain script, not a `node --test` suite
python scripts/check_codex_discovery.py
```
