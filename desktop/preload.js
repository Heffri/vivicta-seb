'use strict'
const { contextBridge, ipcRenderer } = require('electron')

function readArg(name) {
  const prefix = `--${name}=`
  const hit = process.argv.find((arg) => arg.startsWith(prefix))
  return hit ? hit.slice(prefix.length) : undefined
}

const material = readArg('arp-material') === 'acrylic' ? 'acrylic' : 'none'

contextBridge.exposeInMainWorld('arp', {
  material,
  platform: process.platform,
  version: process.versions.electron,
  // v033: the Settings view's only way to read/write <userData>/config.json and restart the
  // backend -- all four are ipcMain.handle()'d in main.js, invoke()/handle() (not send()/on()) since
  // every one of these is a request that needs an answer, unlike arp:tone-changed's fire-and-forget.
  settings: {
    get: () => ipcRenderer.invoke('arp:settings:get'),
    set: (cfg) => ipcRenderer.invoke('arp:settings:set', cfg),
    test: (cfg) => ipcRenderer.invoke('arp:settings:test', cfg),
    codexStatus: () => ipcRenderer.invoke('arp:settings:codex-status'),
    claudeStatus: () => ipcRenderer.invoke('arp:settings:claude-status'),
  },
})

// The native titleBarOverlay buttons are drawn by the OS outside the DOM, so main.js can only
// color them to match the app's own dark/light toggle (useTone.ts, <html data-tone>) if the
// renderer tells it when that attribute changes. Watched here instead of wiring an IPC call into
// useTone.ts itself, which is outside this lane's territory (material flag only).
window.addEventListener('DOMContentLoaded', () => {
  const root = document.documentElement
  const report = () => ipcRenderer.send('arp:tone-changed', root.dataset.tone === 'light' ? 'light' : 'dark')
  report()
  new MutationObserver(report).observe(root, { attributes: true, attributeFilter: ['data-tone'] })
})
