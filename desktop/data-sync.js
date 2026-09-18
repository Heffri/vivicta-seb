'use strict'
// Bundled data (companies.json, reports/index.json, kb/) -> <userData>/data, merged on EVERY
// launch (v107). The old behavior copied the whole tree once and never again, so KB entries
// shipped with a new app version never reached existing installs. Now every launch re-plans the
// merge; only files the user does not have are copied, so user uploads (kb/up-*), reviewed
// extractions and config.json always win. main.js calls syncBundledData() from ensureUserData.
const path = require('node:path')
const fs = require('node:fs')
const fsp = require('node:fs/promises')

// Same exclude list as the repo's own .gitignore for data/ (no PDFs, no derived KB
// embeddings/tmp files, no ad-hoc up-* uploads). Moved here from main.js so the once-copy
// and the every-launch merge share one rule set.
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

// Walk the bundled tree and decide what the user's data dir is missing. Never looks at file
// *contents* — an existing destination file is never overwritten, whatever it says.
async function planDataSync(bundledRoot, destRoot, skip = shouldSkipDataEntry) {
  const plan = { kbStems: [], files: [], index: { action: 'none', added: 0 } }
  const relOf = (root, p) => path.relative(root, p).replace(/\\/g, '/')

  async function backfill(srcDir, destDir, root) {
    for (const entry of await fsp.readdir(srcDir, { withFileTypes: true })) {
      const src = path.join(srcDir, entry.name)
      const rel = relOf(root, src)
      if (skip(rel)) continue
      const dest = path.join(destDir, entry.name)
      if (entry.isDirectory()) await backfill(src, dest, root)
      else if (!fs.existsSync(dest)) plan.files.push(rel)
    }
  }

  async function walk(srcDir, destDir, root) {
    for (const entry of await fsp.readdir(srcDir, { withFileTypes: true })) {
      const src = path.join(srcDir, entry.name)
      const rel = relOf(root, src)
      if (skip(rel)) continue
      const dest = path.join(destDir, entry.name)
      if (entry.isDirectory()) {
        if (rel === 'kb') {
          // kb/<stem> is the unit the backend treats as one report: a stem the user lacks is
          // copied whole (still filtered); a stem they have only gets missing files backfilled.
          for (const stem of await fsp.readdir(src, { withFileTypes: true })) {
            if (!stem.isDirectory()) continue
            const stemRel = `kb/${stem.name}`
            if (skip(stemRel)) continue
            if (!fs.existsSync(path.join(dest, stem.name))) plan.kbStems.push(stem.name)
            else await backfill(path.join(src, stem.name), path.join(dest, stem.name), root)
          }
        } else {
          await walk(src, dest, root)
        }
      } else if (rel === 'reports/index.json') {
        // The report index is merged, not replaced: the user's copy may carry their own
        // fetch results that the bundled file does not know about.
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
      } else if (!fs.existsSync(dest)) {
        plan.files.push(rel)
      }
    }
  }

  if (fs.existsSync(bundledRoot)) await walk(bundledRoot, destRoot, bundledRoot)
  return plan
}

async function syncBundledData(bundledRoot, destRoot) {
  const counts = { dataDir: destRoot, kbEntries: 0, files: 0, indexEntries: 0 }
  await fsp.mkdir(destRoot, { recursive: true })
  if (!fs.existsSync(bundledRoot)) return counts
  const plan = await planDataSync(bundledRoot, destRoot)

  for (const stem of plan.kbStems) {
    const src = path.join(bundledRoot, 'kb', stem)
    await fsp.cp(src, path.join(destRoot, 'kb', stem), {
      recursive: true,
      filter: (source) => {
        // rel paths below bundledRoot, same shape planDataSync/skip use (e.g. kb/b_2025/pages.jsonl)
        const rel = path.relative(bundledRoot, source).replace(/\\/g, '/')
        return rel === '' || !shouldSkipDataEntry(rel)
      },
    })
    counts.kbEntries++
  }
  for (const rel of plan.files) {
    const src = path.join(bundledRoot, rel)
    const dest = path.join(destRoot, rel)
    await fsp.mkdir(path.dirname(dest), { recursive: true })
    await fsp.copyFile(src, dest)
    counts.files++
  }
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
  return counts
}

function syncLogLine(counts) {
  return `data sync: +${counts.kbEntries} kb entries, +${counts.files} files`
}

module.exports = { syncBundledData, syncLogLine, mergeLibraryIndex, shouldSkipDataEntry }
