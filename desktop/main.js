'use strict'
const { app, BrowserWindow, Menu, dialog, ipcMain } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const fsp = require('node:fs/promises')
const http = require('node:http')
const net = require('node:net')
const { spawn, spawnSync, execFile } = require('node:child_process')
const settings = require('./settings')
const { syncBundledData, syncLogLine } = require('./data-sync')

const isDev = !app.isPackaged
const isWindows = process.platform === 'win32'
const DEV_PORT = 8000 // frontend/vite.config.ts hardcodes its /api proxy to :8000 and is outside
// this lane's territory (see desktop/README.md "Dev mode port"), so dev mode's backend binds
// that exact port instead of a random free one. Packaged mode has no such constraint (the
// backend serves the frontend itself, same origin, same port — see startBackend/loadShell).

let mainWindow = null
let overlayTone = 'dark' // v117: last tone the renderer reported over arp:tone-changed (drives glyph color)
let backendProcess = null
let viteProcess = null
let backendLogStream = null
let logFile = '' // set once in main(); read by applySettings()'s error messages too
let backendBaseEnv = {} // ARP_DATA_DIR/KB_DIR/FRONTEND_DIST -- fixed for the app's lifetime, merged
// with settings.envForConfig()'s LLM_* vars both at startup and on every settings-triggered restart
let currentBackend = { port: null, proc: null } // the backend this instance actually owns right now

function crashLog(label, err) {
  const line = `\n[${new Date().toISOString()}] ${label}: ${err && err.stack ? err.stack : err}\n`
  try {
    const logDir = path.join(app.getPath('userData'), 'logs')
    fs.mkdirSync(logDir, { recursive: true })
    fs.appendFileSync(path.join(logDir, 'crash.log'), line)
  } catch {
    /* best effort */
  }
  console.error(line)
}
process.on('uncaughtException', (err) => crashLog('uncaughtException', err))
process.on('unhandledRejection', (err) => crashLog('unhandledRejection', err))

// v138: honor --user-data-dir <dir> (or --user-data-dir=<dir>) by relocating userData before
// the single-instance lock below, which is keyed on app.getPath('userData') — without this the
// packaged exe ignored the switch end to end (v137: the run wrote into the default userData and
// a second launch died on the lock). Works the same for `electron .` dev launches and the
// packaged exe; the lock's semantics (one instance per userData) are unchanged.
const userDataArgIdx = process.argv.findIndex((a) => a === '--user-data-dir' || a.startsWith('--user-data-dir='))
if (userDataArgIdx !== -1) {
  const eq = process.argv[userDataArgIdx].indexOf('=')
  const dir = eq !== -1 ? process.argv[userDataArgIdx].slice(eq + 1) : process.argv[userDataArgIdx + 1]
  if (dir && !dir.startsWith('-')) app.setPath('userData', path.resolve(dir))
}

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  })
  app.whenReady().then(main).catch(fatalStartupError)
  app.on('window-all-closed', () => app.quit())
  app.on('before-quit', () => {
    killProcessTree(backendProcess)
    killProcessTree(viteProcess)
  })
}

// ---------------------------------------------------------------------------
// Windows acrylic material detection — same build-number gate UAW's main.ts
// uses (process.getSystemVersion() is "10.0.<build>" even on Windows 11).
// v029 shipped this unconditionally; v100 gates it behind the theme setting
// (Solid, the default, keeps the opaque window the 09-18 refresh chose).
// ---------------------------------------------------------------------------
function supportsAcrylic() {
  if (!isWindows || typeof BrowserWindow.prototype.setBackgroundMaterial !== 'function') return false
  try {
    const [major, , build] = process
      .getSystemVersion()
      .split('.')
      .map((part) => Number.parseInt(part, 10))
    return major !== undefined && build !== undefined && (major > 10 || (major === 10 && build >= 22_000))
  } catch {
    return false
  }
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.unref()
    srv.on('error', reject)
    srv.listen(0, '127.0.0.1', () => {
      const address = srv.address()
      srv.close(() => resolve(address.port))
    })
  })
}

function httpGetOk(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      res.resume()
      resolve(typeof res.statusCode === 'number' && res.statusCode < 500)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(2000, () => {
      req.destroy()
      resolve(false)
    })
  })
}

// `proc`, if given, ends the wait as soon as it exits instead of polling out the full timeout —
// found the hard way debugging this file: a port collision makes vite exit in ~1s, and without
// this the dialog blaming "did not respond" only appeared after the full 30s, which reads as a
// hang rather than the fast, clear failure it actually was.
async function waitForHealth(url, timeoutMs, proc) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (await httpGetOk(url)) return true
    if (proc && proc.exitCode !== null) return false
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  return false
}

function killProcessTree(proc) {
  if (!proc || proc.pid == null || proc.exitCode !== null) return
  if (isWindows) {
    spawn('taskkill', ['/pid', String(proc.pid), '/t', '/f'], { windowsHide: true })
  } else {
    try {
      process.kill(-proc.pid, 'SIGTERM')
    } catch {
      try {
        proc.kill('SIGTERM')
      } catch {
        /* already gone */
      }
    }
  }
}

function findRepoRoot() {
  // dev only: desktop/ is a sibling of backend/ and frontend/ in the repo checkout.
  return path.resolve(__dirname, '..')
}

// ---------------------------------------------------------------------------
// Bundled data (companies.json, reports/index.json, kb/) -> userData. v107:
// merged on every launch (desktop/data-sync.js) instead of copied once, so KB
// entries bundled with a new app version reach installs created by older
// versions — and nothing the user already has is ever overwritten (uploads,
// reviewed extractions and the user's own report index always win).
// ---------------------------------------------------------------------------
async function ensureUserData(userDataDir, bundledDataDir) {
  return syncBundledData(bundledDataDir, path.join(userDataDir, 'data'))
}

// ---------------------------------------------------------------------------
// Backend process
// ---------------------------------------------------------------------------
function attachProcLogging(proc, label) {
  // Node's EventEmitter rethrows 'error' as an uncaught exception when nothing is listening for
  // it — which is exactly what a bad spawn() (e.g. ENOENT on the command) emits. Without this,
  // a launch-time typo silently kills the whole app (crashLog's uncaughtException handler would
  // still catch it, but with no indication of *which* child process caused it).
  proc.on('error', (err) => crashLog(`${label} spawn error`, err))
  return proc
}

async function startBackendFromVenv(backendDir, env, port) {
  const venvDir = path.join(backendDir, '.venv')
  const pythonExe = isWindows ? path.join(venvDir, 'Scripts', 'python.exe') : path.join(venvDir, 'bin', 'python')
  if (!fs.existsSync(pythonExe)) {
    throw new Error(
      `no venv python at ${pythonExe} — run: cd backend && python -m venv .venv && ` +
        `.venv\\Scripts\\pip install -r requirements.txt`,
    )
  }
  if (await httpGetOk(`http://127.0.0.1:${port}/api/config`)) {
    return { port, proc: null, source: `${pythonExe} (reusing backend already listening on :${port})` }
  }
  const proc = attachProcLogging(
    spawn(pythonExe, ['-m', 'uvicorn', 'app:app', '--port', String(port)], {
      cwd: backendDir,
      env: { ...process.env, ...env },
      windowsHide: true,
    }),
    'backend',
  )
  return { port, proc, source: pythonExe }
}

// Spawns on a *specific* port, given -- the piece startBackend() and applySettings() (v033, settings
// restart) both need, factored out so a restart can reuse the exact port the window already loaded
// instead of re-deriving one (dev mode's is fixed anyway; packaged mode's window has already loaded
// http://127.0.0.1:<port>/, so a restart must keep serving that same origin).
async function launchBackendOnPort(env, port) {
  if (isDev) {
    return startBackendFromVenv(path.join(findRepoRoot(), 'backend'), env, port)
  }

  const backendExeName = isWindows ? 'backend.exe' : 'backend'
  const backendExe = path.join(process.resourcesPath, 'backend', backendExeName)
  if (fs.existsSync(backendExe)) {
    if (await httpGetOk(`http://127.0.0.1:${port}/api/config`)) {
      return { port, proc: null, source: `${backendExe} (reusing backend already listening on :${port})` }
    }
    const proc = attachProcLogging(
      spawn(backendExe, ['--port', String(port)], {
        env: { ...process.env, ...env },
        windowsHide: true,
      }),
      'backend',
    )
    return { port, proc, source: backendExe }
  }

  // v030 (PyInstaller packaging) had not shipped backend.exe yet when this lane ran. Dev-machine
  // smoke test only: point ARP_DEV_BACKEND_DIR at a backend/ checkout with its own .venv and the
  // packaged app will run it with python instead of failing outright. Real end-user installs have
  // no such checkout and must ship backend.exe.
  const devBackendDir = process.env.ARP_DEV_BACKEND_DIR
  if (devBackendDir && fs.existsSync(devBackendDir)) {
    return startBackendFromVenv(devBackendDir, env, port)
  }

  throw new Error(
    `packaged backend not found at ${backendExe} (v030 build artifact not bundled).\n` +
      `Dev-machine smoke test: set ARP_DEV_BACKEND_DIR to a backend/ checkout with its own .venv, then relaunch.`,
  )
}

async function startBackend(env) {
  const port = isDev ? DEV_PORT : await findFreePort()
  return launchBackendOnPort(env, port)
}

function wireBackendLogging(backend) {
  if (!backend.proc) return
  backend.proc.stdout?.pipe(backendLogStream, { end: false })
  backend.proc.stderr?.pipe(backendLogStream, { end: false })
  backend.proc.on('exit', (code) => backendLogStream.write(`\nbackend exited with code ${code}\n`))
}

function waitForExit(proc, timeoutMs = 5000) {
  if (!proc || proc.exitCode !== null) return Promise.resolve()
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, timeoutMs) // taskkill is fire-and-forget (killProcessTree); don't hang Save forever if it never lands
    proc.once('exit', () => {
      clearTimeout(timer)
      resolve()
    })
  })
}

async function stopProcess(proc) {
  killProcessTree(proc)
  await waitForExit(proc)
}

// ---------------------------------------------------------------------------
// Settings (v033): <userData>/config.json, save-triggers-restart, test connection.
// ---------------------------------------------------------------------------

/** Save + kill the owned backend + respawn on the *same* port with the new env + health check.
 *  Resolves only once the new backend answers /api/config, which is also what tells the renderer
 *  (awaiting window.arp.settings.set()) it's safe to stop showing "Restarting..." -- no separate
 *  onBackendRestart event or renderer-side poll loop needed. */
async function applySettings(cfg) {
  if (!currentBackend.proc) {
    return {
      ok: false,
      error:
        'Backend is running outside this app (dev mode reused an already-listening server on this port) — ' +
        'stop it by hand, then relaunch the app so it can apply new settings.',
    }
  }
  const clean = settings.saveConfig(app.getPath('userData'), cfg)
  const port = currentBackend.port
  await stopProcess(currentBackend.proc)
  const env = { ...backendBaseEnv, ...settings.envForConfig(clean) }
  let launched
  try {
    launched = await launchBackendOnPort(env, port)
  } catch (err) {
    return { ok: false, error: err.message }
  }
  currentBackend = launched
  backendProcess = launched.proc
  // EXTRACT_TWO_PASS logged here (not in /api/config -- that endpoint stays backend territory,
  // v047 work order) so a settings save's actual env is provable from this file alone.
  backendLogStream.write(`\nrestarting backend (settings save): ${launched.source} (port ${port}); two-pass: ${env.EXTRACT_TWO_PASS ?? 'unset'}; basis: ${env.DEBT_BASIS ?? 'unset'}\n`)
  wireBackendLogging(launched)
  const healthy = await waitForHealth(`http://127.0.0.1:${port}/api/config`, 30_000, launched.proc)
  if (!healthy) {
    return { ok: false, error: `backend did not respond on :${port} within 30s after restart (log: ${logFile})` }
  }
  try {
    const res = await fetch(`http://127.0.0.1:${port}/api/config`)
    return { ok: true, port, config: await res.json() }
  } catch {
    return { ok: true, port } // healthy per waitForHealth; this second fetch is just a nicety
  }
}

/** v100: a theme switch from Settings' Theme select — deliberately NOT the applySettings path
 *  (that one restarts the backend, which a visual change doesn't need). Persists theme into
 *  config.json immediately — merged over the stored file, so apiKey & friends survive and a
 *  later Save writes the same value the user already picked — then switches the live window's
 *  material when the platform can, so the change lands without a relaunch. `appliedNow: false`
 *  tells the renderer to show the restart hint instead; `material` tells it whether to flip
 *  <html data-material> (the CSS branch that swaps painted wallpaper for the OS blur). */
function applyTheme(theme) {
  const wanted = theme === 'acrylic' ? 'acrylic' : 'solid'
  const wantAcrylic = wanted === 'acrylic' && supportsAcrylic()
  const userDataDir = app.getPath('userData')
  const clean = settings.saveConfig(userDataDir, { ...settings.loadConfig(userDataDir), theme: wanted })
  let appliedNow = false
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (typeof mainWindow.setBackgroundMaterial === 'function') {
      try {
        mainWindow.setBackgroundColor(wantAcrylic ? '#00000000' : '#0a0a12')
        mainWindow.setBackgroundMaterial(wantAcrylic ? 'acrylic' : 'none')
        appliedNow = true
      } catch (err) {
        backendLogStream.write(`theme switch to ${wanted}: live material change failed: ${err.message}\n`)
      }
    }
  }
  backendLogStream.write(`theme set: ${clean.theme}; live material switch: ${appliedNow}\n`)
  return { appliedNow, material: wantAcrylic ? 'acrylic' : 'none' }
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

async function testOpenAiCompatible(cfg) {
  const base = (cfg.baseUrl || (cfg.provider === 'ollama' ? 'http://127.0.0.1:11434/v1' : '')).replace(/\/+$/, '')
  if (!base) return { ok: false, error: 'Base URL is required.' }
  try {
    const res = await fetchWithTimeout(
      `${base}/models`,
      { headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {} },
      5000,
    )
    if (!res.ok) return { ok: false, error: `${res.status} ${res.statusText}` }
    const body = await res.json().catch(() => ({}))
    const list = Array.isArray(body.data) ? body.data : Array.isArray(body.models) ? body.models : []
    const models = list.map((m) => (typeof m === 'string' ? m : m.id || m.name)).filter(Boolean)
    return { ok: true, kind: 'models', models }
  } catch (err) {
    // Node's fetch collapses every network failure to the one message "fetch failed" and puts the
    // actual reason (ECONNREFUSED, a blocked port, DNS failure, ...) on `.cause` instead -- verified
    // live against an unreachable port, which is not a generic "connection refused" case here but
    // undici's own blocked-port list ("bad port"). Surface `.cause` too, or a financial user sees only
    // the unhelpful top-level message.
    const detail = err.cause && err.cause.message ? `: ${err.cause.message}` : ''
    return { ok: false, error: err.name === 'AbortError' ? 'Timed out after 5s' : `${String(err.message || err)}${detail}` }
  }
}

function findOnPath(name) {
  try {
    const res = spawnSync(isWindows ? 'where' : 'which', [name], { encoding: 'utf-8', windowsHide: true })
    if (res.status === 0 && res.stdout) {
      const first = res.stdout.split(/\r?\n/).find(Boolean)
      if (first) return first.trim()
    }
  } catch {
    /* not found */
  }
  return null
}

// Ports backend/pipeline/llm.py's _codex_executable() discovery order to the main process, so Test
// (and a future restart) find the same `codex` the backend itself would: CODEX_BIN overrides, else
// PATH (bare "codex" so Windows' PATHEXT picks up the .cmd/.ps1 shim `npm install -g` writes), else
// the two Windows install roots llm.py already knows about.
function codexExecutable() {
  if (process.env.CODEX_BIN) return process.env.CODEX_BIN
  const onPath = findOnPath('codex')
  if (onPath) return onPath
  const home = app.getPath('home')
  const roots = isWindows
    ? [
        path.join(home, 'AppData', 'Local', 'OpenAI', 'Codex', 'bin', 'codex.exe'),
        path.join(home, 'AppData', 'Local', 'Programs', 'OpenAI', 'Codex', 'bin', 'codex.exe'),
      ]
    : [path.join(home, '.codex', 'bin', 'codex')]
  const found = roots.find((candidate) => fs.existsSync(candidate))
  if (found) return found
  // The desktop installer keeps the CLI in bin/<version>/codex.exe.
  if (isWindows) {
    for (const candidate of roots) {
      const dir = path.dirname(candidate)
      if (!fs.existsSync(dir)) continue
      const versions = fs.readdirSync(dir, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .map((entry) => path.join(dir, entry.name, 'codex.exe'))
        .filter((file) => fs.existsSync(file) && fs.statSync(file).isFile())
        .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)
      if (versions.length) return versions[0]
    }
  }
  throw new Error('codex executable not found (PATH, or the usual OpenAI Codex install dirs); set CODEX_BIN to override')
}

function runCapture(exe, args, timeoutMs = 5000) {
  return new Promise((resolve) => {
    execFile(exe, args, { timeout: timeoutMs, windowsHide: true }, (err, stdout, stderr) => {
      if (err) resolve({ ok: false, error: String(err.killed ? 'Timed out' : stderr || err.message).trim() })
      else resolve({ ok: true, stdout: stdout.trim(), stderr: stderr.trim() })
    })
  })
}

// `codex login status` is a real subcommand (verified: `codex login --help` lists it, this machine's
// 0.153.4 runs it in well under a second, read-only, no model call). Fall back to the auth.json file
// per the work order if some other Codex version lacks it -- don't guess any other subcommand.
// Its "Logged in using ChatGPT" line comes out on *stderr*, not stdout -- confirmed by running the
// exact execFile call standalone and printing both streams separately; missed on first pass because
// a plain `codex login status` in a terminal merges both onto the screen with no visible distinction.
// Checking both streams is the fix rather than hardcoding stderr, in case a future version moves it.
async function testCodex() {
  let exe
  try {
    exe = codexExecutable()
  } catch (err) {
    return { ok: false, error: err.message }
  }
  const version = await runCapture(exe, ['--version'])
  if (!version.ok) return { ok: false, error: version.error }
  const status = await runCapture(exe, ['login', 'status'])
  const loggedIn = status.ok
    ? /logged in/i.test(`${status.stdout}\n${status.stderr}`)
    : fs.existsSync(path.join(app.getPath('home'), '.codex', 'auth.json'))
  return { ok: true, kind: 'codex', version: version.stdout, loggedIn }
}

// Claude Code CLI discovery. `CLAUDE_BIN` matches backend/pipeline/llm.py's own _claude_executable()
// (v039, landed after this lane started -- merged in), so a user's override works the same way for
// both the backend's real calls and this Test button. The rest is scaled down from UAW's own
// src/agent-runtime/claude/process-transport.ts (discoverClaudeLaunch): that version also scans an
// npm global prefix and a "managed version" root (itself a fallback-of-a-fallback by UAW's own
// account) neither this app nor backend/llm.py's port of it bothers with; kept here are the two steps
// that matter for a normal install -- PATH, then the official non-npm Windows installer's target --
// verified live on this machine (`where claude` already resolves to the second one, ~/.local/bin/claude.exe).
function claudeExecutable() {
  if (process.env.CLAUDE_BIN) return process.env.CLAUDE_BIN
  const onPath = findOnPath('claude')
  if (onPath) return onPath
  const officialCandidate = path.join(app.getPath('home'), '.local', 'bin', isWindows ? 'claude.exe' : 'claude')
  if (fs.existsSync(officialCandidate)) return officialCandidate
  throw new Error('claude executable not found (PATH, or ~/.local/bin); set CLAUDE_BIN to override')
}

// `claude auth status --json` (verified live: this machine's 2.1.270 answers in well under a second,
// read-only, no model call) -- the exact subcommand UAW's authentication-status.ts uses, not a guess.
// Its JSON also carries email/orgId/orgName/subscriptionType; UAW's own ClaudeAuthenticationStatus type
// deliberately keeps only {loggedIn, authMethod, apiProvider} and documents why ("no account, email,
// organization, or token value is read here"). Same cut here: `loggedIn` is the only field that leaves
// this function, so that account information never reaches the renderer, an IPC log, or evidence.
async function testClaude() {
  let exe
  try {
    exe = claudeExecutable()
  } catch (err) {
    return { ok: false, error: err.message }
  }
  const version = await runCapture(exe, ['--version'])
  if (!version.ok) return { ok: false, error: version.error }
  const status = await runCapture(exe, ['auth', 'status', '--json'])
  let loggedIn = false
  if (status.ok) {
    try {
      loggedIn = JSON.parse(status.stdout).loggedIn === true
    } catch {
      /* leave loggedIn false -- unparsable output is not a logged-in signal */
    }
  }
  return { ok: true, kind: 'claude', version: version.stdout, loggedIn }
}

function testConnection(cfg) {
  if (cfg?.provider === 'codex') return testCodex()
  if (cfg?.provider === 'claude') return testClaude()
  return testOpenAiCompatible(cfg || {})
}

// ---------------------------------------------------------------------------
// Dev-mode vite dev server (desktop's "one command" dev bring-up). Packaged
// mode never runs this — it loads the backend-served static frontend instead.
// ---------------------------------------------------------------------------
async function startViteDevServer(repoRoot) {
  const frontendDir = path.join(repoRoot, 'frontend')
  if (await httpGetOk('http://127.0.0.1:5173/')) {
    return null // developer already has `npm run dev` running in frontend/
  }
  if (!fs.existsSync(path.join(frontendDir, 'node_modules'))) {
    throw new Error(`frontend/node_modules missing — run: cd frontend && npm install`)
  }
  const npmCmd = isWindows ? 'npm.cmd' : 'npm'
  const proc = attachProcLogging(
    // --host 127.0.0.1, not vite's default: on this machine "localhost" resolves to ::1 only for
    // bind purposes, so an unqualified `vite --port 5173` is unreachable at the 127.0.0.1 URL
    // below and everywhere else in this file — found by comparing `curl localhost:5173` (200)
    // against `curl 127.0.0.1:5173` (connection refused) while vite's own banner said ready.
    spawn(npmCmd, ['run', 'dev', '--', '--port', '5173', '--strictPort', '--host', '127.0.0.1'], {
      cwd: frontendDir,
      env: process.env,
      windowsHide: true,
      // Node's spawn() wraps a .cmd target in its own cmd.exe invocation on Windows, and that
      // wrapping throws EINVAL when cwd contains a space (nodejs/node#21825) — true whenever the
      // checkout sits under a user profile path with a space in the account name. `shell: true`
      // routes through a real shell instead, which quotes correctly. Not needed for the backend
      // spawns below: those target python.exe directly (a real PE, no indirection), which
      // CreateProcess handles natively.
      shell: isWindows,
    }),
    'vite',
  )
  return proc
}

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------
// v117: the overlay ground is always fully transparent. The caption region composites over the
// page itself, and the page already paints the right thing under the buttons in every theme×tone
// (Solid dark: the painted-wallpaper glass the default tone kept through v100; Solid light: the
// opaque painted titlebar strip; Acrylic: the one glass pane over the OS material) — so a
// transparent overlay lets the window's own titlebar continue under the OS glyphs instead of
// showing the old flat #14141b/#f7f7fa block that matched neither theme. Only the glyph color
// follows the tone. (Measured on the pre-fix build, 2026-09-19: an opaque overlay reads
// (10,10,18) where the Solid dark glass titlebar reads (14,23,51) beside it — the block the
// owner reported; transparent reads identical to the neighbouring titlebar in all four combos.)
function toneOverlayOptions(tone) {
  return { color: '#00000000', symbolColor: tone === 'light' ? '#16161a' : '#f4f4f7', height: 44 }
}

// v117: push the current tone onto the live overlay without a restart (glyph color; the caption
// ground stays transparent in every theme).
function applyOverlay() {
  if (!isWindows || !mainWindow || mainWindow.isDestroyed()) return
  if (typeof mainWindow.setTitleBarOverlay !== 'function') return
  mainWindow.setTitleBarOverlay(toneOverlayOptions(overlayTone))
}

function createWindow(acrylic) {
  const options = {
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    show: false,
    title: 'Annual Report Parser',
    // Solid keeps the renderer's stable painted background (native acrylic changes on focus
    // loss); Acrylic asks for the real OS material and clears the native fill behind it so the
    // desktop itself shows through -- the v029/v100 trade-off the theme setting exposes.
    backgroundColor: acrylic ? '#00000000' : '#0a0a12',
    icon: path.join(__dirname, 'icons', 'icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [`--arp-material=${acrylic ? 'acrylic' : 'none'}`],
    },
  }
  if (isWindows) {
    options.backgroundMaterial = acrylic ? 'acrylic' : 'none'
    options.titleBarStyle = 'hidden'
    options.titleBarOverlay = toneOverlayOptions('dark') // useTone.ts's own default before the renderer reports in
  }

  const win = new BrowserWindow(options)
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('before-input-event', (event, input) => {
    if (!isDev || input.type !== 'keyDown') return
    if (input.key === 'F12') {
      win.webContents.toggleDevTools()
      event.preventDefault()
    } else if (input.control && input.key.toLowerCase() === 'r') {
      win.webContents.reload()
      event.preventDefault()
    }
  })
  win.once('ready-to-show', () => win.show())
  win.on('closed', () => {
    mainWindow = null
  })
  return win
}

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------
function fatalStartupError(err) {
  dialog.showErrorBox('Annual Report Parser — failed to start', String(err && err.stack ? err.stack : err))
  app.quit()
}

async function main() {
  Menu.setApplicationMenu(null)

  const userDataDir = app.getPath('userData')
  const logDir = path.join(userDataDir, 'logs')
  await fsp.mkdir(logDir, { recursive: true })
  logFile = path.join(logDir, 'backend.log')
  backendLogStream = fs.createWriteStream(logFile, { flags: 'a' })
  backendLogStream.write(`\n--- launch ${new Date().toISOString()} (isDev=${isDev}) ---\n`)

  const repoRoot = isDev ? findRepoRoot() : null
  const bundledDataDir = isDev ? path.join(repoRoot, 'data') : path.join(process.resourcesPath, 'data')
  const sync = await ensureUserData(userDataDir, bundledDataDir)
  backendLogStream.write(`${syncLogLine(sync)}\n`)
  const dataDir = sync.dataDir
  const frontendDistDir = isDev ? path.join(repoRoot, 'frontend', 'dist') : path.join(process.resourcesPath, 'frontend-dist')

  backendBaseEnv = {
    ARP_DATA_DIR: dataDir,
    TESSDATA_PREFIX: process.env.TESSDATA_PREFIX || path.join(bundledDataDir, 'tessdata'),
    KB_DIR: path.join(dataDir, 'kb'),
    ...(fs.existsSync(frontendDistDir) ? { FRONTEND_DIST: frontendDistDir } : {}),
  }
  const llmConfig = settings.loadConfig(userDataDir) // v033: provider/model/etc. saved by a previous Settings save
  const backendEnv = { ...backendBaseEnv, ...settings.envForConfig(llmConfig) }

  let backend
  try {
    backend = await startBackend(backendEnv)
  } catch (err) {
    dialog.showErrorBox('Annual Report Parser — backend failed to start', `${err.message}\n\nLog file: ${logFile}`)
    app.quit()
    return
  }
  currentBackend = backend
  backendProcess = backend.proc
  backendLogStream.write(`backend source: ${backend.source} (port ${backend.port}); llm provider: ${llmConfig.provider}; two-pass: ${backendEnv.EXTRACT_TWO_PASS ?? 'unset'}; basis: ${backendEnv.DEBT_BASIS ?? 'unset'}\n`)
  wireBackendLogging(backend)

  const backendHealthy = await waitForHealth(`http://127.0.0.1:${backend.port}/api/config`, 30_000, backend.proc)
  if (!backendHealthy) {
    dialog.showErrorBox(
      'Annual Report Parser — backend did not respond',
      `No response from http://127.0.0.1:${backend.port}/api/config within 30s.\n\nLog file: ${logFile}`,
    )
    app.quit()
    return
  }

  if (isDev) {
    try {
      viteProcess = await startViteDevServer(repoRoot)
    } catch (err) {
      dialog.showErrorBox('Annual Report Parser — frontend dev server failed to start', `${err.message}\n\nLog file: ${logFile}`)
      app.quit()
      return
    }
    if (viteProcess) {
      viteProcess.stdout?.pipe(backendLogStream, { end: false })
      viteProcess.stderr?.pipe(backendLogStream, { end: false })
      viteProcess.on('exit', (code) => backendLogStream.write(`\nvite dev server exited with code ${code}\n`))
    }
    const viteReady = await waitForHealth('http://127.0.0.1:5173/', 30_000, viteProcess)
    if (!viteReady) {
      dialog.showErrorBox(
        'Annual Report Parser — frontend dev server did not respond',
        `No response from http://127.0.0.1:5173/ within 30s.\n\nLog file: ${logFile}`,
      )
      app.quit()
      return
    }
  }

  // v100: the window is built for the configured theme — only Acrylic asks for the real OS
  // material (v029's detection + transparent fill, restored from 263f8eb); Solid keeps the
  // 09-18 opaque window. The log line is the evidence trail for which one this launch used.
  const acrylic = llmConfig.theme === 'acrylic' && supportsAcrylic()
  backendLogStream.write(
    `windows version: ${isWindows ? process.getSystemVersion() : 'n/a'}; theme: ${llmConfig.theme}; acrylic material: ${acrylic}\n`,
  )
  mainWindow = createWindow(acrylic)

  // v117: tone arrives from the renderer's <html data-tone> observer (preload.js) and drives the
  // overlay glyph color; the caption ground itself is transparent, so theme needs no IPC here.
  ipcMain.on('arp:tone-changed', (_event, tone) => {
    overlayTone = tone === 'light' ? 'light' : 'dark'
    applyOverlay()
  })

  ipcMain.handle('arp:settings:get', () => settings.loadConfig(app.getPath('userData')))
  ipcMain.handle('arp:settings:set', (_event, cfg) => applySettings(cfg))
  ipcMain.handle('arp:theme:set', (_event, theme) => applyTheme(theme)) // v100, see applyTheme
  ipcMain.handle('arp:settings:test', (_event, cfg) => testConnection(cfg))
  ipcMain.handle('arp:settings:codex-status', () => testCodex())
  ipcMain.handle('arp:settings:claude-status', () => testClaude())

  const shellUrl = isDev ? 'http://127.0.0.1:5173' : `http://127.0.0.1:${backend.port}/`
  mainWindow.loadURL(shellUrl)
  require('./updates').startUpdates(app, require('electron-updater').autoUpdater, {
    info: (message) => backendLogStream.write(`[update] ${message}\n`),
    warn: (message) => backendLogStream.write(`[update] ${message}\n`),
    error: (message) => backendLogStream.write(`[update] ${message}\n`),
  })
}
