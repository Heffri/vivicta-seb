'use strict'
// Desktop settings: <userData>/config.json <-> the backend's LLM_* env vars (backend/pipeline/llm.py,
// backend/.env.example). Kept separate from main.js so the translation table (the one piece a teammate
// changing model defaults would touch) isn't buried in process-management code.
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
  // v045's own "for the group" recommendation (docs/acrylic/evidence/v045.md): net positive on a
  // 30-company debt_maturity before/after against Codex -- default on for the three hosted-model
  // cards (Codex, Claude, API endpoint). Never run against a local model, so irrelevant for Ollama,
  // which envForConfig's 'ollama' case below always forces off regardless of this default.
  extractTwoPass: true,
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

/** Plaintext by design (owner call, v033 work order): this file is the only place an API key is
 *  ever persisted. Never write `cfg`/`clean` to a log -- envForConfig() below only ever hands the
 *  key to the backend child process's own env, never to backendLogStream. */
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
      // toggle for and may still hold a stale hosted-provider value) -- v045's evidence never ran
      // two-pass against a local model, see docs/acrylic/README.md's "Model providers".
      return {
        LLM_BASE_URL: clean.baseUrl || 'http://127.0.0.1:11434/v1',
        LLM_MODEL: clean.model || 'qwen3:8b',
        EMBED_MODEL: clean.embedModel || 'bge-m3',
        EXTRACT_TWO_PASS: '0',
      }
    case 'openai': {
      const env = { EXTRACT_TWO_PASS: clean.extractTwoPass ? '1' : '0' }
      if (clean.baseUrl) env.LLM_BASE_URL = clean.baseUrl
      if (clean.model) env.LLM_MODEL = clean.model
      if (clean.apiKey) env.LLM_API_KEY = clean.apiKey
      if (clean.embedModel) env.EMBED_MODEL = clean.embedModel
      return env
    }
    case 'codex': {
      // LLM_BASE_URL is optional here (embeddings/hybrid retrieval only -- backend/app.py gates
      // /extract, /index and /ask on _llm_configured(), true for provider=="codex" with no base URL
      // at all; since v034 Ask retrieves with pure BM25 without it, hybrid cosine+BM25 with it).
      // See docs/acrylic/evidence/v033.md, v034.md.
      // An API key here is optional and only ever reaches that same base URL (embeddings/Ask) --
      // never the codex CLI call itself, which authenticates via `codex login`, not an env var.
      const env = { LLM_PROVIDER: 'codex', LLM_MODEL: clean.codexModel, EXTRACT_TWO_PASS: clean.extractTwoPass ? '1' : '0' }
      if (clean.baseUrl) env.LLM_BASE_URL = clean.baseUrl
      if (clean.apiKey) env.LLM_API_KEY = clean.apiKey
      if (clean.embedModel) env.EMBED_MODEL = clean.embedModel
      return env
    }
    case 'claude': {
      // Mirrors 'codex' exactly -- same optional base-URL-for-embeddings shape, same "API key only
      // ever reaches that base URL, never the CLI call" rule (Claude Code CLI authenticates via
      // `claude login`/an already-signed-in CLI). LLM_PROVIDER=claude landed in backend/pipeline/llm.py
      // (v039) while this lane was in flight -- merged in, see docs/acrylic/evidence/v033.md.
      const env = { LLM_PROVIDER: 'claude', LLM_MODEL: clean.claudeModel, EXTRACT_TWO_PASS: clean.extractTwoPass ? '1' : '0' }
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
