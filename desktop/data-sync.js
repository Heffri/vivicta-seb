'use strict'
// Bundled data (companies.json, reports/index.json, kb/) -> <userData>/data, merged on EVERY
// launch rather than copied once, so KB entries shipped with a new app version reach installs
// created by older versions. main.js calls syncBundledData() from ensureUserData.
//
// The merge is three-way. <userData>/data/.bundle-manifest.json records the sha256 of every file
// the bundle installed, so the next launch can tell "the user still has exactly the bundle version
// we put there" (-> follow the new bundle) from "the user changed it" (-> keep). Files installed
// before the manifest existed cannot be judged, so the first manifest-less run applies a
// conservative one-time rule to kb/<stem>/ only: an unreviewed file that differs from the new
// bundle is stale bundle data and is refreshed once. User uploads (kb/up-*), reviewed extractions
// and config.json always win, and nothing outside kb/ is touched by the one-time rule.
const path = require('node:path')
const fs = require('node:fs')
const fsp = require('node:fs/promises')
const crypto = require('node:crypto')

const MANIFEST_NAME = '.bundle-manifest.json'
const KB_STEM_RE = /^kb\/([^/]+)\//
const EXTRACTION_RE = /^kb\/[^/]+\/extractions\/[^/]+\.json$/

// Same exclude list as the repo's own .gitignore for data/ (no PDFs, no derived KB
// embeddings/tmp files, no ad-hoc up-* uploads).
function shouldSkipDataEntry(relPath) {
  const p = relPath.replace(/\\/g, '/')
  return (
    /^reports\/.*\.pdf$/i.test(p) ||
    /^kb\/[^/]+\/embeddings\.jsonl$/.test(p) ||
    /^kb\/[^/]+\/.*\.tmp$/.test(p) ||
    /^kb\/up-/.test(p)
  )
}

// Pure: union of two library-index arrays keyed by their `file` field. User entries keep their
// order and always win a key collision; bundled-only entries append in bundled order.
function mergeLibraryIndex(bundled, user) {
  const seen = new Map((user || []).map((entry) => [entry.file, true]))
  const out = (user || []).slice()
  for (const entry of bundled || []) {
    if (!seen.has(entry.file)) {
      seen.set(entry.file, true)
      out.push(entry)
    }
  }
  return out
}

function sha256File(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

// The review markers the backend writes (backend/app.py's has_reviews() plus the human_review
// object its review endpoint stores on fields): a non-empty top-level basis_history/reviews, or
// any field carrying a non-empty human_review/review_history. Bundled extractions carry none of
// these, so a file that does is a human-reviewed document and is never overwritten.
function resultHasReviews(result) {
  if (!result || typeof result !== 'object') return false
  const nonEmpty = (v) =>
    (Array.isArray(v) && v.length > 0) ||
    (v != null && typeof v === 'object' && Object.keys(v).length > 0)
  if (nonEmpty(result.basis_history) || nonEmpty(result.reviews)) return true
  return (
    Array.isArray(result.fields) &&
    result.fields.some((f) => f && typeof f === 'object' && (nonEmpty(f.human_review) || nonEmpty(f.review_history)))
  )
}

// null = no manifest on disk (an install predating the manifest; see the one-time rule in
// syncBundledData).
// A manifest that exists but cannot be parsed counts as present-but-empty: without trustworthy
// hashes we cannot tell user-modified from bundle-installed, so the safe answer is keep.
async function loadManifest(destRoot) {
  try {
    const raw = JSON.parse(await fsp.readFile(path.join(destRoot, MANIFEST_NAME), 'utf-8'))
    return raw && typeof raw.files === 'object' && raw.files ? { files: raw.files } : { files: {} }
  } catch (err) {
    if (err && err.code === 'ENOENT') return null
    return { files: {} }
  }
}

async function syncBundledData(bundledRoot, destRoot) {
  const counts = { dataDir: destRoot, kbEntries: 0, files: 0, indexEntries: 0, updated: 0, kept: 0, staleStems: [] }
  await fsp.mkdir(destRoot, { recursive: true })
  if (!fs.existsSync(bundledRoot)) return counts
  const oldManifest = await loadManifest(destRoot)
  const manifest = {} // rel -> sha256 of the bundled content, rebuilt on every launch
  const plan = { stemCopies: [], fileCopies: [], overwrites: [], kept: 0, staleStems: new Set(), index: { action: 'none', added: 0, merged: null } }
  const relOf = (root, p) => path.relative(root, p).replace(/\\/g, '/')

  // Three-way decision for one bundled rel path whose user copy exists. Manifest is updated in
  // every branch: it always describes the bundled content seen at this launch, so the next
  // launch compares against exactly that.
  function decide(rel) {
    const bundleHash = sha256File(path.join(bundledRoot, rel))
    manifest[rel] = bundleHash
    const userPath = path.join(destRoot, rel)
    if (!fs.existsSync(userPath)) {
      plan.fileCopies.push(rel)
      return
    }
    let userHash
    try {
      userHash = sha256File(userPath)
    } catch {
      plan.kept++ // unreadable user file: keep it, never risk destroying what we cannot read
      return
    }
    if (EXTRACTION_RE.test(rel)) {
      try {
        if (resultHasReviews(JSON.parse(fs.readFileSync(userPath, 'utf-8')))) {
          plan.kept++
          return
        }
      } catch {
        /* unparsable user extraction: fall through to the hash comparison */
      }
    }
    if (userHash === bundleHash) return // already the current bundle content
    if (oldManifest === null) {
      // First run on a pre-manifest install: the one-time rule covers kb/<stem>/ only.
      const stem = KB_STEM_RE.exec(rel)
      if (stem) {
        plan.overwrites.push(rel)
        plan.staleStems.add(stem[1])
      } else {
        plan.kept++
      }
      return
    }
    if (oldManifest.files[rel] === undefined) {
      plan.kept++ // present in the manifest era but never installed by a bundle
      return
    }
    if (userHash === oldManifest.files[rel]) {
      plan.overwrites.push(rel) // still the recorded bundle version -> user never modified it
      return
    }
    plan.kept++
  }

  // Manifest entries for every non-skipped file a whole-stem copy installs.
  async function recordStemFiles(srcDir, root) {
    for (const entry of await fsp.readdir(srcDir, { withFileTypes: true })) {
      const src = path.join(srcDir, entry.name)
      const rel = relOf(root, src)
      if (shouldSkipDataEntry(rel)) continue
      if (entry.isDirectory()) await recordStemFiles(src, root)
      else manifest[rel] = sha256File(src)
    }
  }

  async function walk(srcDir, destDir, root, skip = shouldSkipDataEntry) {
    for (const entry of await fsp.readdir(srcDir, { withFileTypes: true })) {
      const src = path.join(srcDir, entry.name)
      const rel = relOf(root, src)
      if (skip(rel)) continue
      const dest = path.join(destDir, entry.name)
      if (entry.isDirectory()) {
        if (rel === 'kb') {
          // kb/<stem> is the unit the backend treats as one report: a stem the user lacks is
          // copied whole (still filtered); a stem they have is decided file by file.
          for (const stem of await fsp.readdir(src, { withFileTypes: true })) {
            if (!stem.isDirectory()) continue
            const stemRel = `kb/${stem.name}`
            if (skip(stemRel)) continue
            if (!fs.existsSync(path.join(dest, stem.name))) {
              plan.stemCopies.push(stem.name)
              await recordStemFiles(path.join(src, stem.name), root)
            } else {
              await walk(path.join(src, stem.name), path.join(dest, stem.name), root)
            }
          }
        } else {
          await walk(src, dest, root)
        }
      } else if (rel === 'reports/index.json') {
        // The report index is merged, not replaced: the user's copy may carry their own
        // fetch results that the bundled file does not know about. (Never manifest-tracked:
        // its content is a merge, not a bundle-installed file.)
        if (!fs.existsSync(dest)) {
          plan.index = { action: 'copy', added: JSON.parse(await fsp.readFile(src, 'utf-8')).length }
        } else {
          const merged = mergeLibraryIndex(
            JSON.parse(await fsp.readFile(src, 'utf-8')),
            JSON.parse(await fsp.readFile(dest, 'utf-8')),
          )
          const added = merged.length - JSON.parse(await fsp.readFile(dest, 'utf-8')).length
          if (added > 0) plan.index = { action: 'merge', added, merged }
        }
      } else {
        decide(rel)
      }
    }
  }

  await walk(bundledRoot, destRoot, bundledRoot)

  for (const stem of plan.stemCopies) {
    const src = path.join(bundledRoot, 'kb', stem)
    await fsp.cp(src, path.join(destRoot, 'kb', stem), {
      recursive: true,
      filter: (source) => {
        // rel paths below bundledRoot, the same shape walk()/shouldSkipDataEntry use (e.g. kb/b_2025/pages.jsonl)
        const rel = path.relative(bundledRoot, source).replace(/\\/g, '/')
        return rel === '' || !shouldSkipDataEntry(rel)
      },
    })
    counts.kbEntries++
  }
  for (const rel of plan.fileCopies) {
    const dest = path.join(destRoot, rel)
    await fsp.mkdir(path.dirname(dest), { recursive: true })
    await fsp.copyFile(path.join(bundledRoot, rel), dest)
    counts.files++
  }
  for (const rel of plan.overwrites) {
    const dest = path.join(destRoot, rel)
    await fsp.mkdir(path.dirname(dest), { recursive: true })
    await fsp.copyFile(path.join(bundledRoot, rel), dest)
    counts.updated++
  }
  counts.kept = plan.kept
  counts.staleStems = [...plan.staleStems]
  if (plan.index.action === 'copy') {
    const dest = path.join(destRoot, 'reports', 'index.json')
    await fsp.mkdir(path.dirname(dest), { recursive: true })
    await fsp.copyFile(path.join(bundledRoot, 'reports', 'index.json'), dest)
    counts.indexEntries = plan.index.added
  } else if (plan.index.action === 'merge') {
    // Same shape the backend's fetch writes (indent=2, no ASCII escaping, trailing newline);
    // only the tags-on-one-line cosmetic pass is not replicated. tmp+rename like kb.py's
    // save_extraction, so a crash mid-write cannot truncate the user's index.
    const dest = path.join(destRoot, 'reports', 'index.json')
    const tmp = `${dest}.tmp`
    await fsp.writeFile(tmp, JSON.stringify(plan.index.merged, null, 2) + '\n', 'utf-8')
    await fsp.rename(tmp, dest)
    counts.indexEntries = plan.index.added
  }
  // Persist the manifest (sorted keys so byte comparison is stable); skip the write when
  // nothing changed — a launch that touches nothing must not touch the file either.
  const ordered = {}
  for (const k of Object.keys(manifest).sort()) ordered[k] = manifest[k]
  const unchanged = oldManifest !== null && JSON.stringify(oldManifest.files) === JSON.stringify(ordered)
  if (!unchanged) {
    const dest = path.join(destRoot, MANIFEST_NAME)
    const tmp = `${dest}.tmp`
    await fsp.writeFile(tmp, JSON.stringify({ version: 1, files: ordered }, null, 2) + '\n', 'utf-8')
    await fsp.rename(tmp, dest)
  }
  return counts
}

function syncLogLine(counts) {
  let line = `data sync: +${counts.kbEntries} kb entries, +${counts.files} files`
  if (counts.updated) line += `, ${counts.updated} updated`
  if (counts.kept) line += `, ${counts.kept} kept (user-modified)`
  if (counts.staleStems && counts.staleStems.length) {
    const n = counts.staleStems.length
    line += `, ${n} stale stem${n === 1 ? '' : 's'} refreshed (first run, no manifest): ${counts.staleStems.join(', ')}`
  }
  return line
}

module.exports = { syncBundledData, syncLogLine, mergeLibraryIndex, shouldSkipDataEntry }
