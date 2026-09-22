const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const crypto = require('node:crypto')
const { syncBundledData, syncLogLine } = require('./data-sync')

// The fixture scenario: userData/data already holds a user-reviewed extraction (content X,
// carrying the review markers the backend writes) and an upload stem; the bundled data ships a
// newer version of that same extraction (content Y), a brand-new stem, and a report index.
const ENT_A_BUNDLED = { file: 'a_2025.pdf', company: 'A', note: 'bundled' }
const ENT_B = { file: 'b_2025.pdf', company: 'B', note: 'bundled-only' }
const ENT_A_USER = { file: 'a_2025.pdf', company: 'A', note: 'user-reviewed' }
const USER_X = '{"fields":[{"key":"total_debt","value":1,"human_review":{"decision":"confirmed"}}]}'
const BUNDLED_Y = '{"fields":[{"key":"total_debt","value":2}]}'

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
  // 2. the user-reviewed extraction survives (bundled Y must not overwrite reviewed user X)
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
  // the startup log line for this run (the reviewed file is counted as kept)
  assert.equal(syncLogLine(first), 'data sync: +1 kb entries, +0 files, 1 kept (user-modified)')
})

test('second launch changes nothing (idempotent)', async () => {
  const { bundled, user } = makeFixture()
  await syncBundledData(bundled, user)
  const before = treeHash(user)

  const second = await syncBundledData(bundled, user)

  assert.deepEqual({ kbEntries: second.kbEntries, files: second.files, indexEntries: second.indexEntries, updated: second.updated }, { kbEntries: 0, files: 0, indexEntries: 0, updated: 0 })
  assert.equal(syncLogLine(second), 'data sync: +0 kb entries, +0 files, 1 kept (user-modified)')
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
  assert.equal(fs.existsSync(path.join(fresh, '.bundle-manifest.json')), true)
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

// Three-way sync against the bundle manifest recorded by the previous launch. A file the
// user never modified (hash still equal to what the manifest recorded) follows the new bundle;
// a file the user changed, and any reviewed extraction, are kept.
test('three-way sync: unmodified bundle entries follow the new bundle, modified and reviewed entries are kept', async () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'arp-data-sync-'))
  const bundled = path.join(base, 'bundled')
  const user = path.join(base, 'user', 'data')
  writeTree(bundled, {
    'kb/s_2025/meta.json': '{"company":"S","rev":1}',
    'kb/s_2025/extractions/debt_maturity.json': '{"fields":[{"key":"total_debt","value":1}]}',
    'kb/r_2025/extractions/debt_maturity.json': '{"fields":[{"key":"total_debt","value":1}]}',
  })
  // launch 1 (the install): the bundled v1 files land and the manifest records their hashes
  await syncBundledData(bundled, user)
  // a new app version bundles v2 of the same files
  writeTree(bundled, {
    'kb/s_2025/meta.json': '{"company":"S","rev":2}',
    'kb/s_2025/extractions/debt_maturity.json': '{"fields":[{"key":"total_debt","value":2}]}',
    'kb/r_2025/extractions/debt_maturity.json': '{"fields":[{"key":"total_debt","value":2}]}',
  })
  // meanwhile the user edited s_2025/meta.json by hand and reviewed r_2025 in the UI
  fs.writeFileSync(path.join(user, 'kb/s_2025/meta.json'), '{"company":"S","user-edit":true}')
  fs.writeFileSync(
    path.join(user, 'kb/r_2025/extractions/debt_maturity.json'),
    '{"fields":[{"key":"total_debt","value":1}],"basis_history":[{"at":"now"}]}',
  )

  const second = await syncBundledData(bundled, user)

  // (a) unmodified since install (hash == manifest) -> follows the new bundle
  assert.equal(fs.readFileSync(path.join(user, 'kb/s_2025/extractions/debt_maturity.json'), 'utf-8'), '{"fields":[{"key":"total_debt","value":2}]}')
  // (b) user-modified (hash differs from the manifest) -> kept
  assert.equal(fs.readFileSync(path.join(user, 'kb/s_2025/meta.json'), 'utf-8'), '{"company":"S","user-edit":true}')
  // (c) reviewed extraction -> kept even though its content changed after install
  assert.equal(JSON.parse(fs.readFileSync(path.join(user, 'kb/r_2025/extractions/debt_maturity.json'), 'utf-8')).basis_history.length, 1)
  assert.equal(second.updated, 1)
  assert.equal(second.kept, 2)

  // (e) third launch: everything is settled, nothing changes any more
  const before = treeHash(user)
  const third = await syncBundledData(bundled, user)
  assert.deepEqual({ kbEntries: third.kbEntries, files: third.files, updated: third.updated }, { kbEntries: 0, files: 0, updated: 0 })
  assert.equal(third.kept, 2)
  assert.equal(treeHash(user), before)
})

// First run on an install created before the manifest existed: there is no recorded bundle
// version to compare against, so unreviewed kb entries that differ
// from the new bundle are treated as stale bundle data and refreshed once; uploads, reviewed
// extractions and non-kb user files are outside the rule. Every later launch is three-way.
test('first run without a manifest: stale bundle-era kb entries are refreshed once; reviewed and user files are kept', async () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'arp-data-sync-'))
  const bundled = path.join(base, 'bundled')
  const user = path.join(base, 'user', 'data')
  writeTree(bundled, {
    'companies.json': '{"companies":"bundled-v2"}',
    'kb/old_2025/meta.json': '{"company":"Old","rev":2}',
    'kb/old_2025/extractions/debt_maturity.json': '{"fields":[{"key":"total_debt","value":305555}]}',
    'kb/new_2025/meta.json': '{"company":"New"}',
  })
  writeTree(user, {
    'companies.json': '{"companies":"user-edited"}',
    'kb/old_2025/meta.json': '{"company":"Old","rev":1}',
    'kb/old_2025/extractions/debt_maturity.json': '{"fields":[{"key":"total_debt","value":null}]}',
    'kb/old_2025/extractions/income_statement.json': '{"fields":[{"key":"revenue","value":9,"human_review":{"decision":"confirmed"}}]}',
    'kb/up-1/meta.json': '{"upload":true}',
  })

  const first = await syncBundledData(bundled, user)

  // stale, unreviewed, not an upload -> refreshed (the one-time rule)
  assert.equal(fs.readFileSync(path.join(user, 'kb/old_2025/extractions/debt_maturity.json'), 'utf-8'), '{"fields":[{"key":"total_debt","value":305555}]}')
  assert.equal(fs.readFileSync(path.join(user, 'kb/old_2025/meta.json'), 'utf-8'), '{"company":"Old","rev":2}')
  assert.deepEqual(first.staleStems, ['old_2025'])
  // a reviewed extraction survives the one-time rule
  assert.equal(JSON.parse(fs.readFileSync(path.join(user, 'kb/old_2025/extractions/income_statement.json'), 'utf-8')).fields[0].human_review.decision, 'confirmed')
  // uploads and non-kb user files are outside the rule
  assert.equal(fs.readFileSync(path.join(user, 'kb/up-1/meta.json'), 'utf-8'), '{"upload":true}')
  assert.equal(fs.readFileSync(path.join(user, 'companies.json'), 'utf-8'), '{"companies":"user-edited"}')
  // the brand-new stem still lands, and the log names the refreshed stems
  assert.equal(first.kbEntries, 1)
  assert.ok(fs.existsSync(path.join(user, 'kb/new_2025/meta.json')))
  assert.match(syncLogLine(first), /1 stale stem refreshed \(first run, no manifest\): old_2025/)
  assert.equal(first.updated, 2)

  // from the second launch on everything is three-way: no further changes
  const before = treeHash(user)
  const second = await syncBundledData(bundled, user)
  assert.equal(second.updated, 0)
  assert.equal(second.kbEntries, 0)
  assert.equal(treeHash(user), before)
})
