const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const crypto = require('node:crypto')
const { syncTeamData } = require('./sync-team-data')

const rel = 'kb/example_2025/extractions/income_statement.json'
const result = value => ({ section: 'income_statement', fields: [{ key: 'revenue', value, source: { page: 1, quote: `Revenue ${value}` } }] })
function write(root, name, value) {
  fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true })
  fs.writeFileSync(path.join(root, name), typeof value === 'string' ? value : JSON.stringify(value))
}
function report(root, stem = 'example_2025') {
  write(root, `kb/${stem}/meta.json`, { company: 'Example', fiscal_year: 2025, sha256: 'a'.repeat(64), source_url: 'https://example.com/report.pdf', pages: 1 })
  write(root, `kb/${stem}/pages.jsonl`, '{"page":1,"text":"Revenue 100"}\n')
  write(root, `kb/${stem}/extractions/income_statement.json`, result(100))
}
function fixture(t) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'team-data-'))
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }))
  const repoData = path.join(temp, 'repo'), appData = path.join(temp, 'app')
  fs.mkdirSync(path.join(repoData, 'kb'), { recursive: true }); fs.mkdirSync(path.join(appData, 'kb'), { recursive: true })
  report(repoData); report(appData)
  const opts = { repoData, appData }
  return { ...opts, sync: (extra = {}) => syncTeamData({ ...opts, ...extra }) }
}
const read = (root, name) => fs.readFileSync(path.join(root, name), 'utf8')

test('desktop extraction reaches a teammate without a model or private files', t => {
  const f = fixture(t)
  f.sync()
  write(f.appData, rel, result(120))
  write(f.appData, 'config.json', { apiKey: 'private' })
  write(f.appData, 'kb/example_2025/embeddings.jsonl', 'private derived data')
  write(f.appData, 'kb/example_2025/extractions/income_statement.run1.json', 'raw run')
  report(f.appData, 'up-private')
  assert.deepEqual(f.sync().toRepo, [rel])
  assert.equal(JSON.parse(read(f.repoData, rel)).fields[0].value, 120)
  assert.equal(fs.existsSync(path.join(f.repoData, 'config.json')), false)
  assert.equal(fs.existsSync(path.join(f.repoData, 'kb/up-private')), false)
  assert.equal(fs.existsSync(path.join(f.repoData, 'kb/example_2025/embeddings.jsonl')), false)
  assert.equal(fs.existsSync(path.join(f.repoData, 'kb/example_2025/extractions/income_statement.run1.json')), false)
  report(f.repoData, 'teammate_2024')
  assert.equal(f.sync().toApp.length, 3)
  assert.equal(f.sync().toRepo.length, 0)
  assert.equal(f.sync().toApp.length, 0)
})

test('initial sync uses the installed bundle baseline, then its own baseline', t => {
  const f = fixture(t)
  const original = read(f.appData, rel)
  write(f.appData, '.bundle-manifest.json', { files: { [rel]: crypto.createHash('sha256').update(original).digest('hex') } })
  write(f.appData, rel, result(120))
  assert.deepEqual(f.sync().toRepo, [rel])
  write(f.repoData, rel, result(130))
  assert.deepEqual(f.sync().toApp, [rel])
  assert.equal(JSON.parse(read(f.appData, rel)).fields[0].value, 130)
  assert.equal(JSON.parse(read(f.appData, '.bundle-manifest.json')).files[rel], crypto.createHash('sha256').update(original).digest('hex'))
})

test('conflicting reviews preserve the entire report on both sides', t => {
  const f = fixture(t); f.sync()
  const local = result(120); local.fields[0].human_review = { reviewer: 'A', decision: 'corrected' }
  const remote = result(130); remote.fields[0].human_review = { reviewer: 'B', decision: 'corrected' }
  write(f.appData, rel, local); write(f.repoData, rel, remote)
  write(f.repoData, 'kb/example_2025/extractions/debt_maturity.json', { section: 'debt_maturity', fields: [] })
  const outcome = f.sync()
  assert.equal(outcome.conflicts.length, 1)
  assert.equal(outcome.toApp.length, 0)
  assert.equal(read(f.appData, rel), JSON.stringify(local))
  assert.equal(read(f.repoData, rel), JSON.stringify(remote))
})

test('different PDF hashes and unknown baselines never overwrite data', t => {
  const f = fixture(t)
  write(f.appData, rel, result(200))
  assert.equal(f.sync().conflicts.length, 1)
  const metaPath = 'kb/example_2025/meta.json'
  write(f.appData, metaPath, { ...JSON.parse(read(f.appData, metaPath)), sha256: 'b'.repeat(64) })
  assert.match(f.sync().conflicts[0], /different source PDFs/)
  assert.equal(JSON.parse(read(f.repoData, rel)).fields[0].value, 100)
})

test('dry run writes neither reports nor sync state, malformed sources are skipped', t => {
  const f = fixture(t)
  report(f.appData, 'new_2025')
  write(f.appData, 'kb/broken_2025/meta.json', '{bad')
  const outcome = f.sync({ dryRun: true })
  assert.equal(outcome.toRepo.length, 3)
  assert.equal(outcome.skipped.length, 1)
  assert.equal(fs.existsSync(path.join(f.repoData, 'kb/new_2025')), false)
  assert.equal(fs.existsSync(path.join(f.appData, '.team-sync.json')), false)
})

test('identical sync is idempotent, and removed files are restored without deleting peers', t => {
  const f = fixture(t); f.sync()
  const state = fs.statSync(path.join(f.appData, '.team-sync.json')).mtimeMs
  f.sync()
  assert.equal(fs.statSync(path.join(f.appData, '.team-sync.json')).mtimeMs, state)
  fs.unlinkSync(path.join(f.appData, rel))
  assert.deepEqual(f.sync().toApp, [rel])
  assert.equal(read(f.appData, rel), read(f.repoData, rel))
  assert.throws(() => syncTeamData({ repoData: f.repoData, appData: f.repoData }), /separate directories/)
})

test('legacy shared sources sync, but new desktop-only reports need a public source URL', t => {
  const f = fixture(t)
  const metaPath = 'kb/example_2025/meta.json'
  const legacy = { ...JSON.parse(read(f.repoData, metaPath)), source_url: 'v051-local-copy' }
  write(f.repoData, metaPath, legacy); write(f.appData, metaPath, legacy)
  f.sync()
  write(f.appData, rel, result(120))
  assert.deepEqual(f.sync().toRepo, [rel])
  report(f.appData, 'local_2025')
  write(f.appData, 'kb/local_2025/meta.json', legacy)
  const outcome = f.sync()
  assert.equal(outcome.toRepo.length, 0)
  assert.equal(outcome.skipped.length, 1)
  assert.equal(fs.existsSync(path.join(f.repoData, 'kb/local_2025')), false)
})
