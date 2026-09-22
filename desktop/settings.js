'use strict'
// Desktop settings: <userData>/config.json <-> the backend's LLM_* env vars (backend/pipeline/llm.py,
// backend/.env.example). Kept separate from main.js so the translation table isn't buried in
// process-management code.
const fs = require('node:fs')
const path = require('node:path')

const PROVIDERS = ['ollama', 'openai', 'codex', 'claude', 'fixture']
const CODEX_MODELS = ['gpt-5.6-terra', 'gpt-5.6-sol'] // owner rule: no higher tier than sol
const CLAUDE_MODELS = ['claude-sonnet-5', 'claude-opus-5', 'claude-haiku-4-5-20251001']

const DEFAULTS = {
  provider: 'fixture', // first launch: demo mode, matches backend/app.py's own fixture fallback
  baseUrl: '',
  model: '',
  apiKey: '',
  embedModel: '',
  codexModel: CODEX_MODELS[0],
  claudeModel: CLAUDE_MODELS[0],
  // Measured net positive on a 30-company debt_maturity before/after against Codex
  // (docs/acrylic/evidence/v045.md), so it defaults on for the three hosted-model cards (Codex,
  // Claude, API endpoint). It was never measured against a local model, so envForConfig's 'ollama'
  // case below forces it off regardless of this default.
  extractTwoPass: true,
  // Which maturity table debt_maturity reads -- the borrowings note's carrying amounts (the
  // backend default) or the liquidity note's contractual undiscounted cash flows. Unlike two-pass
  // this is model-independent, so every provider card carries the control and every non-fixture
  // provider passes DEBT_BASIS through (backend/pipeline/extract.py's debt_basis()).
  maturityBasis: 'carrying',
  // EXTRACT_MERGE_RUNS, the second-run merge (off|union|majority; backend/pipeline/merge.py).
  // Model-independent like maturityBasis, so every non-fixture provider passes it through, Ollama
  // included. Cost, which SettingsView's copy repeats: 'union' makes every extraction cost TWO
  // model calls (the second run and the per-field merge); 'majority' additionally counts the saved
  // extraction and skips the second run entirely when the first matches it; 'off' (the default) is
  // the single-run route.
  mergeRuns: 'off',
  // EXTRACT_SECOND_PASS: a bounded second pass plus a full-text sweep, exposed as "Deep search for
  // missing figures". Default off because the live measurement did not justify an always-on cost
  // (docs/acrylic/evidence/w197.md). Unlike two-pass there is no hosted-only caveat: the retry
  // rides the same fixed_pages seam as the analyst fill, so every non-fixture provider passes it
  // through, Ollama included.
  secondPass: false,
  // Visual theme for the whole app -- 'solid' (the default: opaque surfaces) or 'acrylic' (the
  // app's glass styling over this shell's real Windows material). A plain config key that is never
  // an env var: main.js reads it when building the window and the renderer keeps the live choice
  // in localStorage 'arp-theme'. envForConfig ignores it.
  theme: 'solid',
}

function sanitize(raw) {
  const cfg = raw && typeof raw === 'object' ? raw : {}
  return {
    provider: PROVIDERS.includes(cfg.provider) ? cfg.provider : DEFAULTS.provider,
    baseUrl: typeof cfg.baseUrl === 'string' ? cfg.baseUrl.trim() : '',
    model: typeof cfg.model === 'string' ? cfg.model.trim() : '',
    apiKey: typeof cfg.apiKey === 'string' ? cfg.apiKey : '', // not trimmed or logged anywhere -- see saveConfig
    embedModel: typeof cfg.embedModel === 'string' ? cfg.embedModel.trim() : '',
    codexModel: CODEX_MODELS.includes(cfg.codexModel) ? cfg.codexModel : DEFAULTS.codexModel,
    claudeModel: CLAUDE_MODELS.includes(cfg.claudeModel) ? cfg.claudeModel : DEFAULTS.claudeModel,
    extractTwoPass: typeof cfg.extractTwoPass === 'boolean' ? cfg.extractTwoPass : DEFAULTS.extractTwoPass,
    maturityBasis: ['carrying', 'undiscounted'].includes(cfg.maturityBasis) ? cfg.maturityBasis : DEFAULTS.maturityBasis,
    // Only the three values merge.mode() reads; anything else (a typo, an older config) falls back
    // to off -- the same "a typo can never silently turn the second run on" rule as the backend's.
    mergeRuns: ['off', 'union', 'majority'].includes(cfg.mergeRuns) ? cfg.mergeRuns : DEFAULTS.mergeRuns,
    secondPass: typeof cfg.secondPass === 'boolean' ? cfg.secondPass : DEFAULTS.secondPass,
    theme: ['solid', 'acrylic'].includes(cfg.theme) ? cfg.theme : DEFAULTS.theme,
  }
}

function configPath(userDataDir) {
  return path.join(userDataDir, 'config.json')
}

function loadConfig(userDataDir) {
  try {
    return sanitize(JSON.parse(fs.readFileSync(configPath(userDataDir), 'utf-8')))
  } catch {
    return { ...DEFAULTS } // first launch, or a missing/corrupt file
  }
}

/** Plaintext by design: this file is the only place an API key is ever persisted. Never write
 *  `cfg`/`clean` to a log -- envForConfig() below only ever hands the key to the backend child
 *  process's own env, never to backendLogStream. */
function saveConfig(userDataDir, cfg) {
  const clean = sanitize(cfg)
  fs.mkdirSync(userDataDir, { recursive: true })
  fs.writeFileSync(configPath(userDataDir), JSON.stringify(clean, null, 2), 'utf-8')
  return clean
}

/** `clean` must already be sanitize()'d (saveConfig's return value) -- every call site here goes
 *  through saveConfig first, so this stays a pure lookup table instead of re-validating. */
function envForConfig(clean) {
  switch (clean.provider) {
    case 'ollama':
      // Defaults match backend/.env.example's own Ollama block; EMBED_MODEL default also matches
      // kb.embed_model()'s fallback, set explicitly anyway so /api/config always shows the real value.
      // EXTRACT_TWO_PASS is hardcoded off here (not `clean.extractTwoPass`, which this card has no
      // toggle for and may still hold a stale hosted-provider value) -- the two-pass measurement
      // never ran against a local model, see docs/acrylic/README.md's "Model providers".
      return {
        LLM_BASE_URL: clean.baseUrl || 'http://127.0.0.1:11434/v1',
        LLM_MODEL: clean.model || 'qwen3:8b',
        EMBED_MODEL: clean.embedModel || 'bge-m3',
        EXTRACT_TWO_PASS: '0',
        DEBT_BASIS: clean.maturityBasis, // basis is model-independent -- Ollama passes it through, unlike two-pass
        EXTRACT_MERGE_RUNS: clean.mergeRuns, // the merge runs are rules over the two answers, not model work -- Ollama passes them through too
        EXTRACT_SECOND_PASS: clean.secondPass ? '1' : '0', // the bounded retry rides the fixed_pages seam -- Ollama passes it through too
      }
    case 'openai': {
      const env = { EXTRACT_TWO_PASS: clean.extractTwoPass ? '1' : '0', DEBT_BASIS: clean.maturityBasis, EXTRACT_MERGE_RUNS: clean.mergeRuns, EXTRACT_SECOND_PASS: clean.secondPass ? '1' : '0' }
      if (clean.baseUrl) env.LLM_BASE_URL = clean.baseUrl
      if (clean.model) env.LLM_MODEL = clean.model
      if (clean.apiKey) env.LLM_API_KEY = clean.apiKey
      if (clean.embedModel) env.EMBED_MODEL = clean.embedModel
      return env
    }
    case 'codex': {
      // LLM_BASE_URL is optional here (embeddings/hybrid retrieval only -- backend/app.py gates
      // /extract, /index and /ask on _llm_configured(), true for provider=="codex" with no base URL
      // at all; Ask retrieves with pure BM25 without it, hybrid cosine+BM25 with it). See
      // docs/acrylic/evidence/v033.md and docs/acrylic/evidence/v034.md.
      // An API key here is optional and only ever reaches that same base URL (embeddings/Ask) --
      // never the codex CLI call itself, which authenticates via `codex login`, not an env var.
      const env = { LLM_PROVIDER: 'codex', LLM_MODEL: clean.codexModel, EXTRACT_TWO_PASS: clean.extractTwoPass ? '1' : '0', DEBT_BASIS: clean.maturityBasis, EXTRACT_MERGE_RUNS: clean.mergeRuns, EXTRACT_SECOND_PASS: clean.secondPass ? '1' : '0' }
      if (clean.baseUrl) env.LLM_BASE_URL = clean.baseUrl
      if (clean.apiKey) env.LLM_API_KEY = clean.apiKey
      if (clean.embedModel) env.EMBED_MODEL = clean.embedModel
      return env
    }
    case 'claude': {
      // Mirrors 'codex' exactly -- same optional base-URL-for-embeddings shape, same "API key only
      // ever reaches that base URL, never the CLI call" rule (Claude Code CLI authenticates via
      // `claude login`/an already-signed-in CLI). backend/pipeline/llm.py handles
      // LLM_PROVIDER=claude; see docs/acrylic/evidence/v033.md.
      const env = { LLM_PROVIDER: 'claude', LLM_MODEL: clean.claudeModel, EXTRACT_TWO_PASS: clean.extractTwoPass ? '1' : '0', DEBT_BASIS: clean.maturityBasis, EXTRACT_MERGE_RUNS: clean.mergeRuns, EXTRACT_SECOND_PASS: clean.secondPass ? '1' : '0' }
      if (clean.baseUrl) env.LLM_BASE_URL = clean.baseUrl
      if (clean.apiKey) env.LLM_API_KEY = clean.apiKey
      if (clean.embedModel) env.EMBED_MODEL = clean.embedModel
      return env
    }
    default: // fixture: nothing set, demo mode
      return {}
  }
}

module.exports = { PROVIDERS, CODEX_MODELS, CLAUDE_MODELS, DEFAULTS, configPath, loadConfig, saveConfig, envForConfig }
