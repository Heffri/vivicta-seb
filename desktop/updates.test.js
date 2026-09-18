const { test } = require('node:test')
const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const { startUpdates } = require('./updates')

test('installed apps check updates, tolerate offline errors, and do not force restarts', async () => {
  const app = Object.assign(new EventEmitter(), { isPackaged: true })
  const updater = new EventEmitter()
  let checks = 0
  const warnings = []
  updater.checkForUpdatesAndNotify = async () => { checks++; throw new Error('offline') }
  const log = { warn: message => warnings.push(message) }
  startUpdates({ isPackaged: false }, updater, log, false)
  startUpdates(app, updater, log, true)
  assert.equal(checks, 0)
  startUpdates(app, updater, log, false)
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(checks, 1)
  assert.equal(updater.autoDownload, true)
  assert.equal(updater.autoInstallOnAppQuit, true)
  assert.equal(updater.allowDowngrade, false)
  assert.match(warnings[0], /offline/)
  updater.emit('error', new Error('download failed'))
  assert.match(warnings[1], /download failed/)
  app.emit('before-quit')
})

test('main and demo have separate update feeds and installed identities', () => {
  const config = (channel) => {
    process.env.RELEASE_CHANNEL = channel
    process.env.RELEASE_VERSION = '1.5.1'
    delete require.cache[require.resolve('./release-config.cjs')]
    return require('./release-config.cjs')
  }
  const main = config('main'), demo = config('demo')
  assert.notEqual(main.appId, demo.appId)
  assert.notEqual(main.extraMetadata.name, demo.extraMetadata.name)
  assert.match(main.publish[0].url, /desktop-main\/$/)
  assert.match(demo.publish[0].url, /desktop-demo\/$/)
  assert.throws(() => config('other'), /RELEASE_CHANNEL/)
})
