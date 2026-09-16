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
