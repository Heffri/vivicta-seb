'use strict'

const fs = require('node:fs/promises')
const path = require('node:path')
const { randomUUID } = require('node:crypto')
const { isIP } = require('node:net')
const LIMIT = 50 * 1024 * 1024

function publicUrl(value) {
  try {
    const url = new URL(value)
    const host = url.hostname.toLowerCase()
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password &&
      !isIP(host) && !host.startsWith('[') && host.includes('.') &&
      !['localhost', 'local', 'internal', 'test', 'invalid'].some(suffix => host === suffix || host.endsWith(`.${suffix}`))
  } catch { return false }
}

async function importPdf(file, request, port) {
  const size = (await fs.stat(file)).size
  if (size > LIMIT) throw new Error('Report exceeds the 50 MB browser import limit.')
  const bytes = await fs.readFile(file)
  if (!bytes.subarray(0, 5).equals(Buffer.from('%PDF-'))) throw new Error('The downloaded file is not a PDF.')
  const form = new FormData()
  form.append('file', new Blob([bytes], { type: 'application/pdf' }), 'report.pdf')
  form.append('company', request.company)
  form.append('year', String(request.fiscal_year))
  form.append('source_url', request.url)
  const response = await fetch(`http://127.0.0.1:${port}/api/reports/import-download`, {
    method: 'POST', body: form, signal: AbortSignal.timeout(120_000),
  })
  const body = await response.json()
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Report import failed.')
  return body
}

// Remote pages never receive our preload/IPC bridge. A private session keeps their
// cookies and permissions separate from the local application. The user operates
// the site's normal download flow; no CAPTCHA tokens or page scripts are injected.
function openReportBrowser({ BrowserWindow, session, tempDir, parent, request, port, importDownload = importPdf }) {
  if (!publicUrl(request?.url) || request.url.length > 2000 || typeof request.company !== 'string' ||
      !request.company.trim() || request.company.length > 100 ||
      !Number.isInteger(request.fiscal_year) || request.fiscal_year < 1990 || request.fiscal_year > 2100) {
    return Promise.resolve({ ok: false, error: 'Invalid report listing.' })
  }
  const partition = session.fromPartition(`report-download-${randomUUID()}`)
  partition.setPermissionRequestHandler((_wc, _permission, callback) => callback(false))
  partition.setPermissionCheckHandler(() => false)
  partition.webRequest.onBeforeRequest((details, callback) => {
    const url = details.url
    callback({ cancel: !publicUrl(url) && !url.startsWith('blob:') && !url.startsWith('data:') && url !== 'about:blank' })
  })
  const title = `${request.company} FY${request.fiscal_year} — Download the annual report to continue`
  const win = new BrowserWindow({
    width: 1100, height: 820, parent, show: true, title,
    webPreferences: { session: partition, contextIsolation: true, nodeIntegration: false, sandbox: true, plugins: false },
  })
  win.on('page-title-updated', event => event.preventDefault())
  win.webContents.on('will-navigate', (event, url) => { if (!publicUrl(url)) event.preventDefault() })
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (publicUrl(url)) win.loadURL(url).catch(() => {})
    return { action: 'deny' }
  })
  return new Promise(resolve => {
    let settled = false
    let active = null
    let importing = false
    const finish = result => {
      if (settled) return
      settled = true
      partition.removeListener('will-download', download)
      if (!win.isDestroyed()) win.destroy()
      if (parent && !parent.isDestroyed()) { parent.show(); parent.focus() }
      resolve(result)
    }
    const download = (event, item, contents) => {
      if (settled || active || contents !== win.webContents ||
          (!/\.pdf$/i.test(item.getFilename()) && item.getMimeType() !== 'application/pdf') || item.getTotalBytes() > LIMIT) {
        event.preventDefault()
        return
      }
      active = item
      // Never trust a remote filename or write into the saved-report library here.
      const file = path.join(tempDir, `arp-report-${randomUUID()}.pdf`)
      item.setSavePath(file)
      item.on('updated', () => { if (item.getReceivedBytes() > LIMIT) item.cancel() })
      item.once('done', async (_event, state) => {
        if (settled) { await fs.unlink(file).catch(() => {}); return }
        if (state !== 'completed') {
          await fs.unlink(file).catch(() => {})
          finish({ ok: false, error: 'The report download was interrupted. Open the listing to try again.' })
          return
        }
        importing = true
        win.setTitle(`${request.company} — Verifying downloaded PDF…`)
        try {
          const report = await importDownload(file, request, port)
          finish({ ok: true, report })
        } catch (error) {
          finish({ ok: false, error: error.message })
        } finally {
          await fs.unlink(file).catch(() => {})
        }
      })
    }
    partition.on('will-download', download)
    win.on('close', event => { if (importing) event.preventDefault() })
    win.on('closed', () => {
      if (active && !importing) active.cancel()
      if (!importing) finish({ ok: false, cancelled: true })
    })
    win.loadURL(request.url).catch(error => {
      // Navigation to a downloadable PDF aborts navigation after will-download.
      if (!active && !settled) finish({ ok: false, error: `Could not open the report listing: ${error.message}` })
    })
  })
}

module.exports = { openReportBrowser, publicUrl, importPdf }
