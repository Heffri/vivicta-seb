'use strict'
// Stages electron-builder's extraResources under desktop/build-resources/ (gitignored) so
// electron-builder.yml can point at paths that always exist, even when v030's backend.exe
// (backend/dist/) has not been built yet — see README.md "Packaging without backend.exe".
const fs = require('node:fs')
const fsp = require('node:fs/promises')
const path = require('node:path')

const repoRoot = path.resolve(__dirname, '..', '..')
const desktopDir = path.resolve(__dirname, '..')
const stageDir = path.join(desktopDir, 'build-resources')
const tessdataFiles = ['eng.traineddata', 'swe.traineddata', 'LICENSE']
const tessdataBaseUrl = 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/'

function shouldSkipDataEntry(relPath) {
  const p = relPath.replace(/\\/g, '/')
  return (
    /^reports\/.*\.pdf$/i.test(p) ||
    /^uploads(?:\/|$)/.test(p) ||
    /^tessdata(?:\/|$)/.test(p) ||
    /\.log$/.test(p) ||
    /^kb\/[^/]+\/index\.json$/.test(p) ||
    /^kb\/[^/]+\/embeddings\.jsonl$/.test(p) ||
    /^kb\/[^/]+\/.*\.tmp$/.test(p) ||
    /^kb\/up-/.test(p)
  )
}

async function stageTessdata(dataDir) {
  const sourceDir = path.join(dataDir, 'tessdata')
  const destDir = path.join(stageDir, 'tessdata')
  await fsp.mkdir(destDir, { recursive: true })
  for (const name of tessdataFiles) {
    const source = path.join(sourceDir, name)
    const dest = path.join(destDir, name)
    if (fs.existsSync(source)) {
      // w214: these three files are committed to the repo, so this is the normal path on every
      // clone/CI machine and the build is deterministic and offline.
      await fsp.copyFile(source, dest)
      continue
    }
    // Fallback only for a damaged checkout missing a committed file.
    const response = await fetch(tessdataBaseUrl + name, { signal: AbortSignal.timeout(120_000) })
    if (!response.ok) throw new Error(`could not download OCR resource ${name}: HTTP ${response.status}`)
    const temp = `${dest}.tmp`
    await fsp.writeFile(temp, Buffer.from(await response.arrayBuffer()))
    await fsp.rename(temp, dest)
  }
}

async function main() {
  await fsp.rm(stageDir, { recursive: true, force: true })
  await fsp.mkdir(stageDir, { recursive: true })

  const frontendDist = path.join(repoRoot, 'frontend', 'dist')
  if (!fs.existsSync(frontendDist)) {
    throw new Error('frontend/dist missing — run: cd frontend && npm run build')
  }
  await fsp.cp(frontendDist, path.join(stageDir, 'frontend-dist'), { recursive: true })

  // v030's build_exe.py runs PyInstaller in onedir mode: output is dist/backend/backend.exe +
  // dist/backend/_internal/, so the staged copy source is dist/backend (not dist itself) or the
  // packaged resources/backend/ would end up nested one level too deep.
  const backendDist = path.join(repoRoot, 'backend', 'dist', 'backend')
  if (fs.existsSync(backendDist)) {
    await fsp.cp(backendDist, path.join(stageDir, 'backend'), { recursive: true })
  } else {
    await fsp.mkdir(path.join(stageDir, 'backend'), { recursive: true })
    console.warn(
      '[prepare-resources] backend/dist not found (v030 not landed yet) — packaging without backend.exe; ' +
        'the packaged app will need ARP_DEV_BACKEND_DIR to run (see README.md).',
    )
  }

  const dataDir = path.join(repoRoot, 'data')
  await fsp.cp(dataDir, path.join(stageDir, 'data'), {
    recursive: true,
    filter: (source) => {
      const rel = path.relative(dataDir, source).replace(/\\/g, '/')
      return rel === '' || !shouldSkipDataEntry(rel)
    },
  })
  // w204: every distributable carries the two languages the parser requests by default. Since
  // w214 they are committed under data/tessdata, so packaging copies the repo copy (offline,
  // deterministic); the download inside stageTessdata only covers a damaged checkout.
  await stageTessdata(dataDir)

  console.log(`[prepare-resources] staged resources at ${stageDir}`)
}

main().catch((err) => {
  console.error(err.message)
  process.exit(1)
})
