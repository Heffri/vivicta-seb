'use strict'

function startUpdates(app, updater, log, portable = !!process.env.PORTABLE_EXECUTABLE_FILE) {
  if (!app.isPackaged || portable) return
  updater.logger = log
  // Download in the background and install on normal exit, never interrupt an extraction.
  updater.autoDownload = true
  updater.autoInstallOnAppQuit = true
  updater.allowDowngrade = false
  updater.on('error', (error) => log.warn(`Update failed: ${error.message}`))
  const check = () => updater.checkForUpdatesAndNotify().catch((error) => log.warn(`Update check failed: ${error.message}`))
  check()
  const timer = setInterval(check, 60 * 60 * 1000)
  timer.unref()
  app.once('before-quit', () => clearInterval(timer))
}

module.exports = { startUpdates }
