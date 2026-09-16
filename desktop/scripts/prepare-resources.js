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

function shouldSkipDataEntry(relPath) {
  const p = relPath.replace(/\\/g, '/')
  return (
    /^reports\/.*\.pdf$/i.test(p) ||
    /^kb\/[^/]+\/embeddings\.jsonl$/.test(p) ||
    /^kb\/[^/]+\/.*\.tmp$/.test(p) ||
    /^kb\/up-/.test(p)
  )
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

  console.log(`[prepare-resources] staged resources at ${stageDir}`)
}

main().catch((err) => {
  console.error(err.message)
  process.exit(1)
})
