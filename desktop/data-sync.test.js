const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const crypto = require('node:crypto')
const { syncBundledData, syncLogLine } = require('./data-sync')

// Work order v107 scenario: userData/data already holds a user-reviewed extraction (content X)
// and an upload stem; the bundled data ships a newer version of that same extraction (content Y),
// a brand-new stem, and a report index. The old once-only copy never delivered any of it.
const ENT_A_BUNDLED = { file: 'a_2025.pdf', company: 'A', note: 'bundled' }
const ENT_B = { file: 'b_2025.pdf', company: 'B', note: 'bundled-only' }
const ENT_A_USER = { file: 'a_2025.pdf', company: 'A', note: 'user-reviewed' }
const USER_X = '{"rows":"user reviewed X"}'
const BUNDLED_Y = '{"rows":"bundled Y"}'

function writeTree(root, files) {
  for (const [rel, content] of Object.entries(files)) {
    fs.mkdirSync(path.join(root, rel, '..'), { recursive: true })
    fs.writeFileSync(path.join(root, rel), content)
  }
}

function readTree(root, rel = '') {
  const out = {}
  for (const entry of fs.readdirSync(path.join(root, rel), { withFileTypes: true })) {
    const child = path.join(rel, entry.name)
    if (entry.isDirectory()) Object.assign(out, readTree(root, child))
    else out[child.replace(/\\/g, '/')] = fs.readFileSync(path.join(root, child)).toString()
  }
  return out
}

function treeHash(root) {
  return JSON.stringify(readTree(root), (key, value) =>
    typeof value === 'string' ? crypto.createHash('sha256').update(value).digest('hex') : value)
}

function makeFixture() {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'arp-data-sync-'))
  const bundled = path.join(base, 'bundled')
  const user = path.join(base, 'user', 'data')
  writeTree(bundled, {
    'reports/index.json': JSON.stringify([ENT_A_BUNDLED, ENT_B]),
    'reports/atlas_2025.pdf': '%PDF never copied',
    'kb/a_2025/extractions/debt_maturity.json': BUNDLED_Y,
    'kb/b_2025/meta.json': '{"company":"B"}',
    'kb/b_2025/pages.jsonl': '{"page":1,"text":"x"}\n',
    'kb/b_2025/embeddings.jsonl': '[]',
    'kb/up-9/meta.json': '{}',
  })
  writeTree(user, {
    'reports/index.json': JSON.stringify([ENT_A_USER]),
    'kb/a_2025/extractions/debt_maturity.json': USER_X,
    'kb/up-1/meta.json': '{"upload":true}',
  })
  return { base, bundled, user }
}

test('merge fills what the user lacks and never touches what the user has', async () => {
  const { bundled, user } = makeFixture()

  const first = await syncBundledData(bundled, user)

  // 1. the new bundled stem arrives
  assert.equal(first.kbEntries, 1)
  assert.equal(fs.readFileSync(path.join(user, 'kb/b_2025/meta.json'), 'utf-8'), '{"company":"B"}')
  assert.equal(fs.existsSync(path.join(user, 'kb/b_2025/pages.jsonl')), true)
  // 2. the user-reviewed extraction survives (bundled Y must not overwrite user X)
  assert.equal(fs.readFileSync(path.join(user, 'kb/a_2025/extractions/debt_maturity.json'), 'utf-8'), USER_X)
  // 3. the user's upload stem is untouched
  assert.equal(fs.readFileSync(path.join(user, 'kb/up-1/meta.json'), 'utf-8'), '{"upload":true}')
  // 4. the report index merges by `file`, user entries win, bundled-only entries append
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(user, 'reports/index.json'), 'utf-8')), [ENT_A_USER, ENT_B])
  assert.equal(first.indexEntries, 1)
  // skip rules hold on the merge path, same as the old whole-copy filter
  assert.equal(fs.existsSync(path.join(user, 'kb/up-9')), false)
  assert.equal(fs.existsSync(path.join(user, 'kb/b_2025/embeddings.jsonl')), false)
  assert.equal(fs.existsSync(path.join(user, 'reports/atlas_2025.pdf')), false)
  // the startup log line for this run
  assert.equal(syncLogLine(first), 'data sync: +1 kb entries, +0 files')
})

test('second launch changes nothing (idempotent)', async () => {
  const { bundled, user } = makeFixture()
  await syncBundledData(bundled, user)
  const before = treeHash(user)

  const second = await syncBundledData(bundled, user)

  assert.deepEqual({ kbEntries: second.kbEntries, files: second.files, indexEntries: second.indexEntries }, { kbEntries: 0, files: 0, indexEntries: 0 })
  assert.equal(syncLogLine(second), 'data sync: +0 kb entries, +0 files')
  assert.equal(treeHash(user), before)
})

test('fresh install copies every non-skipped entry, like the old first-launch copy', async () => {
  const { base, bundled } = makeFixture()
  const fresh = path.join(base, 'fresh', 'data')

  const first = await syncBundledData(bundled, fresh)

  assert.equal(first.kbEntries, 2)
  assert.equal(fs.existsSync(path.join(fresh, 'kb/b_2025/meta.json')), true)
  assert.equal(fs.existsSync(path.join(fresh, 'kb/a_2025/extractions/debt_maturity.json')), true)
  assert.equal(JSON.parse(fs.readFileSync(path.join(fresh, 'reports/index.json'), 'utf-8')).length, 2)
  assert.equal(fs.existsSync(path.join(fresh, 'reports/atlas_2025.pdf')), false)
  assert.equal(fs.existsSync(path.join(fresh, 'kb/up-9')), false)
  assert.equal(syncLogLine(first), 'data sync: +2 kb entries, +0 files')
})

test('index copy and merge degrade correctly when either side is missing', async () => {
  const { base, bundled, user } = makeFixture()
  const noUserIndex = path.join(base, 'nouidx', 'data')
  fs.mkdirSync(path.join(noUserIndex, 'kb'), { recursive: true })

  // bundled index, no user index: the bundled file is copied, all its entries count as added
  const copied = await syncBundledData(bundled, noUserIndex)
  assert.equal(copied.indexEntries, 2)
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(noUserIndex, 'reports/index.json'), 'utf-8')), [ENT_A_BUNDLED, ENT_B])

  // user index, no bundled index: the user file is left byte-for-byte alone
  fs.rmSync(path.join(bundled, 'reports/index.json'))
  const untouched = await syncBundledData(bundled, user)
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(user, 'reports/index.json'), 'utf-8')), [ENT_A_USER])
  assert.equal(untouched.indexEntries, 0)
})
