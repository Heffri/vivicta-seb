import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import type { Config } from './api'
import type { ReportListing } from './api'
import type { Report } from './types'

// desktop/preload.js exposes this on Electron only; a browser tab never has `window.arp`, so
// dataset.material is simply never set and index.css's [data-material="on"] block never matches.
// `settings` (v033) is SettingsView.tsx's only way to read/write the desktop config and restart the
// backend — declared here, the one place `window.arp`'s shape exists, so it stays a single source of
// truth instead of a second `declare global` risking a conflicting re-declaration.
export type ArpSettingsApi = {
  get(): Promise<DesktopConfig>
  set(cfg: DesktopConfig): Promise<SetSettingsResult>
  test(cfg: DesktopConfig): Promise<TestConnectionResult>
  codexStatus(): Promise<TestConnectionResult>
  claudeStatus(): Promise<TestConnectionResult>
}

declare global {
  interface Window {
    arp?: {
      material: 'acrylic' | 'none'
      platform: string
      version: string
      settings: ArpSettingsApi
      downloadReport?: (listing: ReportListing) => Promise<{ ok: true; report: Report } | { ok: false; cancelled?: boolean; error?: string }>
      // v100: Settings' Theme select — persists config.json and switches the live window material
      // without the backend restart a settings Save would do (desktop only; a browser tab has no
      // window.arp and keeps the theme in localStorage alone). Optional so an older desktop build
      // serving a newer frontend degrades to the restart hint instead of a crash.
      setTheme?: (theme: 'solid' | 'acrylic') => Promise<{ appliedNow: boolean; material: 'acrylic' | 'none' }>
    }
  }
}

export type Provider = 'ollama' | 'openai' | 'codex' | 'claude' | 'fixture'

export type DesktopConfig = {
  provider: Provider
  baseUrl: string
  model: string
  apiKey: string
  embedModel: string
  codexModel: string
  claudeModel: string
  // EXTRACT_TWO_PASS passthrough (v047) -- ignored by desktop/settings.js's envForConfig() for
  // 'ollama' (always forced off, see its own comment) and 'fixture' (no model call either way).
  extractTwoPass: boolean
  // DEBT_BASIS passthrough (v089) -- unlike two-pass this is model-independent, so every provider
  // card shows the control and every non-fixture provider passes it through.
  maturityBasis: 'carrying' | 'undiscounted'
  // EXTRACT_MERGE_RUNS passthrough (v140) -- v133's second-run merge, model-independent like the
  // basis above (every non-fixture provider passes it through); unlike two-pass, /api/config
  // echoes the live value as `merge_runs`, which is what the status row shows.
  mergeRuns: 'off' | 'union' | 'majority'
  // EXTRACT_SECOND_PASS passthrough (w212) -- w197's bounded second pass + w198's full-text sweep
  // ("Deep search for missing figures"), model-independent like mergeRuns (every non-fixture
  // provider passes it through, Ollama included) and echoed by /api/config as `second_pass`.
  secondPass: boolean
  // v100: visual theme -- Solid (default, Sebastijan's 09-18 opaque surfaces) or Acrylic
  // (v001-v006b glass + the desktop shell's real Windows material). Persisted in config.json like
  // maturityBasis but never an env var: desktop/main.js reads it to build the window with the
  // right background material, the renderer keeps the live choice in localStorage `arp-theme`.
  theme: 'solid' | 'acrylic'
}

export type SetSettingsResult =
  // v056: the inline literal is now api.ts's Config — desktop main.js resolves this field from
  // /api/config's own JSON, which has carried `retrieval` since v034. No import cycle: api.ts
  // imports ./types only.
  | { ok: true; port: number; config?: Config }
  | { ok: false; error: string }

export type TestConnectionResult =
  | { ok: true; kind: 'models'; models: string[] }
  | { ok: true; kind: 'codex' | 'claude'; version: string; loggedIn: boolean }
  | { ok: false; error: string }

if (window.arp?.material === 'acrylic') {
  document.documentElement.dataset.material = 'on'
}

// v100: the theme choice from Settings' Theme select (Solid default / Acrylic glass), restored
// here before the first render so a reload never flashes the wrong skin. Solid is the absence of
// the attribute -- index.css's default tables are Solid, the Acrylic token scope only matches
// when this is set. Written by SettingsView's ThemeSelect, same localStorage as the tone.
if (localStorage.getItem('arp-theme') === 'acrylic') {
  document.documentElement.dataset.theme = 'acrylic'
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
