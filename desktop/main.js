'use strict'
const { app, BrowserWindow, Menu, dialog, ipcMain } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const fsp = require('node:fs/promises')
const http = require('node:http')
const net = require('node:net')
const { spawn } = require('node:child_process')

const isDev = !app.isPackaged
const isWindows = process.platform === 'win32'
const DEV_PORT = 8000 // frontend/vite.config.ts hardcodes its /api proxy to :8000 and is outside
// this lane's territory (see desktop/README.md "Dev mode port"), so dev mode's backend binds
// that exact port instead of a random free one. Packaged mode has no such constraint (the
// backend serves the frontend itself, same origin, same port — see startBackend/loadShell).

let mainWindow = null
let backendProcess = null
let viteProcess = null
let backendLogStream = null

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
// Bundled data (companies.json, reports/index.json, kb/) -> userData, once.
// Same exclude list as the repo's own .gitignore for data/ (no PDFs, no
// derived KB embeddings/tmp files, no ad-hoc up-* uploads).
// ---------------------------------------------------------------------------
function shouldSkipDataEntry(relPath) {
  const p = relPath.replace(/\\/g, '/')
  return (
    /^reports\/.*\.pdf$/i.test(p) ||
    /^kb\/[^/]+\/embeddings\.jsonl$/.test(p) ||
    /^kb\/[^/]+\/.*\.tmp$/.test(p) ||
    /^kb\/up-/.test(p)
  )
}

async function copyDataDir(srcRoot, destRoot) {
  await fsp.cp(srcRoot, destRoot, {
    recursive: true,
    filter: (source) => {
      const rel = path.relative(srcRoot, source).replace(/\\/g, '/')
      return rel === '' || !shouldSkipDataEntry(rel)
    },
  })
}

async function ensureUserData(userDataDir, bundledDataDir) {
  const dest = path.join(userDataDir, 'data')
  if (fs.existsSync(dest)) return dest
  if (fs.existsSync(bundledDataDir)) {
    await copyDataDir(bundledDataDir, dest)
  } else {
    await fsp.mkdir(dest, { recursive: true })
  }
  return dest
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

async function startBackend(env) {
  if (isDev) {
    return startBackendFromVenv(path.join(findRepoRoot(), 'backend'), env, DEV_PORT)
  }

  const backendExeName = isWindows ? 'backend.exe' : 'backend'
  const backendExe = path.join(process.resourcesPath, 'backend', backendExeName)
  const port = await findFreePort()
  if (fs.existsSync(backendExe)) {
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
      // wrapping throws EINVAL when cwd contains a space (nodejs/node#21825) — true here on this
      // machine (`C:\Users\xingyi chen\...`). `shell: true` routes through a real shell instead,
      // which quotes correctly. Not needed for the backend spawns below: those target python.exe
      // directly (a real PE, no indirection), which CreateProcess handles natively.
      shell: isWindows,
    }),
    'vite',
  )
  return proc
}

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------
function toneOverlayOptions(tone) {
  return tone === 'light'
    ? { color: '#f7f7fa', symbolColor: '#16161a', height: 44 }
    : { color: '#14141b', symbolColor: '#f4f4f7', height: 44 }
}

function createWindow(acrylic) {
  const options = {
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    show: false,
    title: 'Annual Report Parser',
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
  if (acrylic) options.backgroundMaterial = 'acrylic'
  if (isWindows) {
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
  const logFile = path.join(logDir, 'backend.log')
  backendLogStream = fs.createWriteStream(logFile, { flags: 'a' })
  backendLogStream.write(`\n--- launch ${new Date().toISOString()} (isDev=${isDev}) ---\n`)

  const repoRoot = isDev ? findRepoRoot() : null
  const bundledDataDir = isDev ? path.join(repoRoot, 'data') : path.join(process.resourcesPath, 'data')
  const dataDir = await ensureUserData(userDataDir, bundledDataDir)
  const frontendDistDir = isDev ? path.join(repoRoot, 'frontend', 'dist') : path.join(process.resourcesPath, 'frontend-dist')

  const backendEnv = {
    ARP_DATA_DIR: dataDir,
    KB_DIR: path.join(dataDir, 'kb'),
    ...(fs.existsSync(frontendDistDir) ? { FRONTEND_DIST: frontendDistDir } : {}),
  }

  let backend
  try {
    backend = await startBackend(backendEnv)
  } catch (err) {
    dialog.showErrorBox('Annual Report Parser — backend failed to start', `${err.message}\n\nLog file: ${logFile}`)
    app.quit()
    return
  }
  backendProcess = backend.proc
  backendLogStream.write(`backend source: ${backend.source} (port ${backend.port})\n`)
  if (backend.proc) {
    backend.proc.stdout?.pipe(backendLogStream, { end: false })
    backend.proc.stderr?.pipe(backendLogStream, { end: false })
    backend.proc.on('exit', (code) => backendLogStream.write(`\nbackend exited with code ${code}\n`))
  }

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

  const acrylic = supportsAcrylic()
  mainWindow = createWindow(acrylic)

  ipcMain.on('arp:tone-changed', (_event, tone) => {
    if (!isWindows || !mainWindow || mainWindow.isDestroyed()) return
    if (typeof mainWindow.setTitleBarOverlay !== 'function') return
    mainWindow.setTitleBarOverlay(toneOverlayOptions(tone === 'light' ? 'light' : 'dark'))
  })

  const shellUrl = isDev ? 'http://127.0.0.1:5173' : `http://127.0.0.1:${backend.port}/`
  mainWindow.loadURL(shellUrl)
}
