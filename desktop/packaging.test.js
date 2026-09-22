// Every local module main.js (and the modules it pulls in) requires must be in electron-builder.yml's
// `files` list, or the packaged app.asar lacks it and the shell dies on launch with
// "Cannot find module './data-sync'" (v107 shipped exactly that, 2026-09-19). Run: node packaging.test.js
const fs = require('fs')
const path = require('path')
const assert = require('assert')

const here = __dirname
const yml = fs.readFileSync(path.join(here, 'electron-builder.yml'), 'utf8').replace(/\r\n/g, '\n')
const filesBlock = yml.split('\nfiles:\n')[1].split(/\n(?=\S)/)[0]
const packaged = new Set(filesBlock.split('\n').map((l) => l.replace(/^\s*-\s*/, '').trim()).filter(Boolean))

const seen = new Set()
function walk(file) {
  if (seen.has(file)) return
  seen.add(file)
  const src = fs.readFileSync(path.join(here, file), 'utf8')
  for (const m of src.matchAll(/require\(\s*['"]\.\/([^'"]+)['"]\s*\)/g)) {
    const dep = m[1].endsWith('.js') ? m[1] : m[1] + '.js'
    assert.ok(packaged.has(dep), `${file} requires ./${dep} but electron-builder.yml's files list lacks it`)
    walk(dep)
  }
}
walk('main.js')
assert.ok(packaged.has('preload.js'), 'preload.js must be packaged')
assert.match(
  yml,
  /from: build-resources\/tessdata\s+to: tessdata/,
  'eng/swe OCR resources must be copied to resources/tessdata',
)
const prepare = fs.readFileSync(path.join(here, 'scripts', 'prepare-resources.js'), 'utf8')
for (const name of ['eng.traineddata', 'swe.traineddata', 'LICENSE']) {
  assert.ok(prepare.includes(name), `prepare-resources.js must stage ${name}`)
}
const main = fs.readFileSync(path.join(here, 'main.js'), 'utf8')
assert.match(main, /process\.resourcesPath, 'tessdata'/, 'the packaged backend must be pointed at resources/tessdata')
assert.match(main, /webContents\.on\(['"]render-process-gone['"]/, 'renderer crashes must be captured by the main process')
assert.match(main, /dialog\s*\.showMessageBox[\s\S]*webContents\.reload\(\)/, 'a renderer crash must offer a safe window reload instead of exiting the app')
console.log(`packaging: ${seen.size} shell modules all listed in electron-builder.yml (${[...seen].join(', ')})`)
