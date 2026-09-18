import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import type { Config } from './api'

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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
