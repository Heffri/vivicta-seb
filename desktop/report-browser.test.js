const { test } = require('node:test')
const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const { openReportBrowser, publicUrl } = require('./report-browser')
const os = require('node:os')

const request = { company: 'Example AB', fiscal_year: 2025, url: 'https://registry.example/company/1' }
function harness(importDownload = async () => ({ report_id: 'lib-verified', company: request.company })) {
  const partition = new EventEmitter()
  partition.setPermissionRequestHandler = fn => { partition.permission = fn }
  partition.setPermissionCheckHandler = fn => { partition.check = fn }
  partition.webRequest = { onBeforeRequest: fn => { partition.request = fn } }
  let win
  class Window extends EventEmitter {
    constructor(options) {
      super(); win = this; this.options = options; this.webContents = new EventEmitter()
      this.webContents.setWindowOpenHandler = fn => { this.popup = fn }
    }
    loadURL(url) { this.url = url; return Promise.resolve() }
    isDestroyed() { return !!this.destroyed }
    destroy() { this.destroyed = true; this.emit('closed') }
    setTitle(title) { this.title = title }
  }
  const result = openReportBrowser({ BrowserWindow: Window, session: { fromPartition: () => partition },
    tempDir: os.tmpdir(), request, port: 8000, importDownload })
  const item = new EventEmitter()
  Object.assign(item, { getFilename: () => '../../report.pdf', getMimeType: () => 'application/pdf',
    getTotalBytes: () => 10, getReceivedBytes: () => 10, setSavePath: file => { item.file = file },
    cancel: () => { item.cancelled = true } })
  const event = { preventDefault() { this.prevented = true } }
  return { result, win, partition, item, event }
}

test('rejects unsafe URLs and keeps the remote browser isolated', async () => {
  for (const url of ['file:///tmp/a', 'javascript:alert(1)', 'https://user:pass@host.com', 'http://localhost:8000', 'http://127.0.0.1', 'http://[::1]', 'http://thing.local']) assert.equal(publicUrl(url), false)
  assert.equal(publicUrl(request.url), true)
  const h = harness()
  assert.equal(h.win.options.webPreferences.preload, undefined)
  assert.equal(h.win.options.webPreferences.nodeIntegration, false)
  assert.equal(h.win.options.webPreferences.sandbox, true)
  assert.equal(h.partition.check(), false)
  let decision
  h.partition.request({ url: 'http://127.0.0.1:8000/api/config' }, d => { decision = d })
  assert.equal(decision.cancel, true)
  h.win.destroy()
  assert.deepEqual(await h.result, { ok: false, cancelled: true })
})

test('imports completed PDF with the selected issuer/year, then returns report for extraction', async () => {
  let imported
  const h = harness(async (file, req, port) => { imported = { file, req, port }; return { report_id: 'lib-verified' } })
  h.partition.emit('will-download', h.event, h.item, h.win.webContents)
  assert.ok(h.item.file.startsWith(os.tmpdir()))
  assert.ok(!h.item.file.includes('..'))
  h.item.emit('done', {}, 'completed')
  assert.deepEqual(await h.result, { ok: true, report: { report_id: 'lib-verified' } })
  assert.deepEqual(imported.req, request)
  assert.equal(imported.port, 8000)
  assert.equal(h.partition.listenerCount('will-download'), 0)
})

test('validation failure does not return a report; user can retry', async () => {
  const h = harness(async () => { throw new Error('issuer mismatch') })
  h.partition.emit('will-download', h.event, h.item, h.win.webContents)
  h.item.emit('done', {}, 'completed')
  assert.deepEqual(await h.result, { ok: false, error: 'issuer mismatch' })
})

test('closing the browser cancels an active download and never imports it', async () => {
  let imported = false
  const h = harness(async () => { imported = true })
  h.partition.emit('will-download', h.event, h.item, h.win.webContents)
  h.win.destroy()
  assert.equal(h.item.cancelled, true)
  h.item.emit('done', {}, 'cancelled')
  assert.equal((await h.result).cancelled, true)
  assert.equal(imported, false)
})

test('unrelated downloads, executables and oversized files are refused', async () => {
  for (const mode of ['other-window', 'executable', 'oversize']) {
    const h = harness()
    if (mode === 'executable') { h.item.getFilename = () => 'setup.exe'; h.item.getMimeType = () => 'application/octet-stream' }
    if (mode === 'oversize') h.item.getTotalBytes = () => 51 * 1024 * 1024
    h.partition.emit('will-download', h.event, h.item, mode === 'other-window' ? {} : h.win.webContents)
    assert.equal(h.event.prevented, true)
    h.win.destroy()
    await h.result
  }
})

test('interrupted download returns a concrete error, never an extraction result', async () => {
  const h = harness()
  h.partition.emit('will-download', h.event, h.item, h.win.webContents)
  h.item.emit('done', {}, 'interrupted')
  assert.match((await h.result).error, /interrupted/)
})
