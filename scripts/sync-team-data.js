#!/usr/bin/env node
'use strict'

// Git is the hackathon team's shared store. This bridges a desktop install's
// private data directory and the checkout; committing/pulling stays normal Git.
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const crypto = require('node:crypto')
const { parseArgs } = require('node:util')

const STATE = '.team-sync.json'
const hash = (bytes) => bytes == null ? null : crypto.createHash('sha256').update(bytes).digest('hex')
const json = (bytes) => JSON.parse(bytes.toString('utf8'))

function read(file) {
  try {
    if (!fs.lstatSync(file).isFile()) throw new Error(`Not a regular file: ${file}`)
    return fs.readFileSync(file)
  } catch (error) {
    if (error.code === 'ENOENT') return null
    throw error
  }
}

function directories(root) {
  if (!fs.lstatSync(root).isDirectory()) throw new Error(`Not a regular directory: ${root}`)
  return fs.readdirSync(root, { withFileTypes: true })
}

function publicSource(meta) {
  try {
    const url = new URL(meta.source_url)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password
  } catch { return false }
}

function reportFiles(root, stem) {
  const folder = path.join(root, 'kb', stem)
  if (!fs.existsSync(folder)) return null
  directories(folder) // Reject symlinks/junctions, including extraction directories below.
  const files = new Map()
  for (const name of ['meta.json', 'pages.jsonl']) {
    const bytes = read(path.join(folder, name))
    if (!bytes) throw new Error(`${stem}: missing ${name}`)
    files.set(`kb/${stem}/${name}`, bytes)
  }
  const meta = json(files.get(`kb/${stem}/meta.json`))
  if (!meta || typeof meta.sha256 !== 'string' || !meta.sha256) {
    throw new Error(`${stem}: needs a PDF hash`)
  }
  const pages = files.get(`kb/${stem}/pages.jsonl`).toString('utf8').split('\n').filter(line => line.trim()).map(JSON.parse)
  if (!pages.length || pages.some(p => !Number.isInteger(p.page) || p.page < 1 || typeof p.text !== 'string')) {
    throw new Error(`${stem}: invalid saved page text`)
  }
  const extractionDir = path.join(folder, 'extractions')
  if (fs.existsSync(extractionDir)) {
    for (const entry of directories(extractionDir)) {
      if (!entry.isFile() || !/^[a-z0-9_]+\.json$/.test(entry.name)) continue
      const bytes = read(path.join(extractionDir, entry.name))
      const result = json(bytes)
      if (!result || result.section !== entry.name.slice(0, -5) || !Array.isArray(result.fields) || result.provider === 'fixture') {
        throw new Error(`${stem}/${entry.name}: invalid or demo extraction`)
      }
      files.set(`kb/${stem}/extractions/${entry.name}`, bytes)
    }
  }
  return { meta, files }
}

function manifest(root, name) {
  const bytes = read(path.join(root, name))
  if (!bytes) return null
  const value = json(bytes)
  if (!value || !value.files || typeof value.files !== 'object' || Array.isArray(value.files)) {
    throw new Error(`Invalid ${name}; preserve it and resolve the sync state before retrying`)
  }
  return value
}

function writeAtomic(file, bytes) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const temporary = `${file}.${crypto.randomUUID()}.tmp`
  try {
    fs.writeFileSync(temporary, bytes, { flag: 'wx' })
    fs.renameSync(temporary, file)
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary)
  }
}

function syncTeamData({ repoData, appData, dryRun = false }) {
  repoData = fs.realpathSync(repoData)
  appData = fs.realpathSync(appData)
  const within = (a, b) => { const rel = path.relative(a, b); return !rel || (!rel.startsWith('..') && !path.isAbsolute(rel)) }
  if (within(repoData, appData) || within(appData, repoData)) throw new Error('Repo and app data must be separate directories')
  const previous = manifest(appData, STATE)
  if (previous && previous.repo !== repoData) throw new Error('This app data was synced with another checkout; use that checkout')
  const bundle = manifest(appData, '.bundle-manifest.json')
  const baseline = { ...bundle?.files, ...previous?.files }
  const next = { ...previous?.files }
  const result = { reports: 0, toRepo: [], toApp: [], conflicts: [], skipped: [], dryRun }
  const stems = new Set([repoData, appData].flatMap(root => directories(path.join(root, 'kb'))
    .filter(entry => entry.isDirectory() && /^[a-z0-9_-]+$/.test(entry.name) && !entry.name.startsWith('up-'))
    .map(entry => entry.name)))

  for (const stem of [...stems].sort()) {
    let repo, local
    try {
      repo = reportFiles(repoData, stem)
      local = reportFiles(appData, stem)
      // A few already-shared reports predate source URLs. Keep supporting those,
      // but require a public source URL before adding a new desktop-only report.
      if (!repo && !publicSource(local.meta)) throw new Error(`${stem}: new reports need a source URL; uploads stay local`)
    } catch (error) {
      result.skipped.push(error.message)
      continue
    }
    if (repo && local && repo.meta.sha256 !== local.meta.sha256) {
      result.conflicts.push(`${stem}: different source PDFs; both copies kept`)
      continue
    }
    const copies = []
    const common = {}
    const conflicts = []
    for (const rel of new Set([...(repo?.files.keys() || []), ...(local?.files.keys() || [])])) {
      const repoBytes = repo?.files.get(rel), localBytes = local?.files.get(rel)
      const r = hash(repoBytes), l = hash(localBytes)
      if (r === l) { common[rel] = r; continue }
      let direction
      if (r === null) direction = 'toRepo'
      else if (l === null) direction = 'toApp'
      else if (r === baseline[rel]) direction = 'toRepo'
      else if (l === baseline[rel]) direction = 'toApp'
      else { conflicts.push(`${rel}: changed in both places or no shared baseline`); continue }
      const bytes = direction === 'toRepo' ? localBytes : repoBytes
      // Deletions never propagate, even when one side equals the previous baseline.
      if (!bytes) { conflicts.push(`${rel}: removed on one side; both copies kept`); continue }
      copies.push({ rel, direction, bytes })
      common[rel] = hash(bytes)
    }
    if (conflicts.length) {
      result.conflicts.push(...conflicts)
      continue // Keep a report's pages, metadata and extractions together on conflict.
    }
    if (!dryRun) {
      // Catch a running extraction/review or concurrent pull before replacing any files.
      for (const [root, report] of [[repoData, repo], [appData, local]]) {
        const current = reportFiles(root, stem)
        const signature = value => JSON.stringify([...(value?.files || [])].map(([rel, bytes]) => [rel, hash(bytes)]).sort())
        if (signature(current) !== signature(report)) throw new Error(`${stem} changed during sync. Close the app and retry.`)
      }
      for (const copy of copies) writeAtomic(path.join(copy.direction === 'toRepo' ? repoData : appData, copy.rel), copy.bytes)
    }
    for (const copy of copies) result[copy.direction].push(copy.rel)
    Object.assign(next, common)
    result.reports++
  }
  if (!dryRun) {
    const state = Buffer.from(JSON.stringify({ version: 1, repo: repoData, files: Object.fromEntries(Object.entries(next).sort()) }, null, 2) + '\n')
    if (hash(state) !== hash(read(path.join(appData, STATE)))) writeAtomic(path.join(appData, STATE), state)
    // Do not change .bundle-manifest.json: it must still identify the installed
    // release, so launching an older app cannot roll back data pulled from Git.
  }
  return result
}

function defaultAppData() {
  const base = process.platform === 'win32' ? process.env.APPDATA
    : process.platform === 'darwin' ? path.join(os.homedir(), 'Library', 'Application Support')
      : process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config')
  if (!base) throw new Error('Specify the installed app data folder with --app-data')
  return path.join(base, 'annual-report-parser-desktop-main', 'data')
}

if (require.main === module) {
  try {
    const { values } = parseArgs({ options: { 'app-data': { type: 'string' }, 'dry-run': { type: 'boolean' }, help: { type: 'boolean', short: 'h' } } })
    if (values.help) {
      console.log('Usage: node scripts/sync-team-data.js [--dry-run] [--app-data <installed data folder>]\nClose the desktop app first. Sync public saved reports with this checkout, then commit/pull data/kb with normal Git. No model calls or network access.')
    } else {
      const result = syncTeamData({ repoData: path.resolve(__dirname, '..', 'data'), appData: values['app-data'] || defaultAppData(), dryRun: values['dry-run'] })
      console.log(`${result.dryRun ? 'Preview' : 'Sync'}: ${result.reports} reports; ${result.toRepo.length} files to repo; ${result.toApp.length} files to app.`)
      for (const direction of ['toRepo', 'toApp']) for (const rel of result[direction]) console.log(`${direction}: ${rel}`)
      for (const message of result.conflicts) console.error(`Conflict (report kept unchanged): ${message}`)
      for (const message of result.skipped) console.error(`Skipped: ${message}`)
      if (result.conflicts.length || result.skipped.length) process.exitCode = 1
      else if (!result.dryRun) console.log('Reopen the app. Commit changes under data/kb to share them; after pulling teammates\' commits, run this command again.')
    }
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}

module.exports = { syncTeamData }
