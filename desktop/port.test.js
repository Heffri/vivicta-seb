const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const vm = require('node:vm')

function loadPortSelection() {
  const source = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8') +
    '\nmodule.exports.__portTest = { PACKAGED_BACKEND_PORTS, choosePackagedPort, loadRememberedBackendPort, rememberBackendPort };\n'
  const fakeApp = {
    isPackaged: true,
    requestSingleInstanceLock: () => false,
    quit: () => {},
    on: () => {},
  }
  const sandbox = {
    require: (id) => id === 'electron'
      ? { app: fakeApp, BrowserWindow: function BrowserWindow() {}, Menu: {}, dialog: {}, ipcMain: {} }
      : require(id),
    module: { exports: {} },
    exports: {},
    __dirname,
    console,
    process: { argv: [], env: {}, platform: 'win32', on: () => {} },
    setTimeout,
    clearTimeout,
    fetch,
  }
  vm.runInNewContext(source, sandbox, { filename: 'desktop/main.js' })
  return sandbox.module.exports.__portTest
}

test('packaged startup prioritizes its fixed stable port', async () => {
  const { PACKAGED_BACKEND_PORTS, choosePackagedPort, loadRememberedBackendPort, rememberBackendPort } = loadPortSelection()
  const selected = await choosePackagedPort(undefined, {
    isPortAvailable: async () => true,
    findRandomPort: async () => 60_000,
  })
  assert.equal(selected, PACKAGED_BACKEND_PORTS[0])
})

test('an occupied fixed port falls through to the next stable port', async () => {
  const { PACKAGED_BACKEND_PORTS, choosePackagedPort, loadRememberedBackendPort, rememberBackendPort } = loadPortSelection()
  const selected = await choosePackagedPort(undefined, {
    isPortAvailable: async (port) => port !== PACKAGED_BACKEND_PORTS[0],
    findRandomPort: async () => 60_000,
  })
  assert.equal(selected, PACKAGED_BACKEND_PORTS[1])
})

test('when every stable port is occupied, startup uses a random free port', async () => {
  const { PACKAGED_BACKEND_PORTS, choosePackagedPort, loadRememberedBackendPort, rememberBackendPort } = loadPortSelection()
  const selected = await choosePackagedPort(undefined, {
    isPortAvailable: async () => false,
    findRandomPort: async () => 60_000,
  })
  assert.equal(selected, 60_000)
  assert.equal(PACKAGED_BACKEND_PORTS.length, 16)
})
test('the selected packaged port is recorded in config for the next launch', () => {
  const { PACKAGED_BACKEND_PORTS, loadRememberedBackendPort, rememberBackendPort } = loadPortSelection()
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'arp-port-'))
  try {
    rememberBackendPort(userData, PACKAGED_BACKEND_PORTS[1])
    assert.equal(loadRememberedBackendPort(userData), PACKAGED_BACKEND_PORTS[1])
  } finally {
    fs.rmSync(userData, { recursive: true, force: true })
  }
})