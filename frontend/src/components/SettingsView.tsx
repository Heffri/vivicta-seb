import { Loader2 } from 'lucide-react'
import type { InputHTMLAttributes, ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { getConfig, type Config } from '@/api'
import type { ArpSettingsApi, DesktopConfig, Provider, TestConnectionResult } from '@/main'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import { ProviderCard } from '@/components/settings/ProviderCard'

const DEFAULT_CONFIG: DesktopConfig = {
  provider: 'fixture',
  baseUrl: '',
  model: '',
  apiKey: '',
  embedModel: '',
  codexModel: 'gpt-5.6-terra',
  claudeModel: 'claude-sonnet-5',
  extractTwoPass: true, // matches desktop/settings.js's own DEFAULTS -- see its comment for why
}

// Ollama has no toggle for this (see the Local (Ollama) card below) and desktop/settings.js's
// envForConfig() hardcodes it off for that provider regardless of what's stored -- mirrored here so
// the status row reads the same "actually applies on Save" value the backend will run with, not
// just whatever the checkbox last showed while a different card was selected.
function effectiveTwoPass(cfg: DesktopConfig): boolean | undefined {
  if (cfg.provider === 'ollama') return false
  if (cfg.provider === 'fixture') return undefined // no model call either way
  return cfg.extractTwoPass
}
const CODEX_MODELS = ['gpt-5.6-terra', 'gpt-5.6-sol'] // owner rule: no tier above sol
const CLAUDE_MODELS = ['claude-sonnet-5', 'claude-opus-5', 'claude-haiku-4-5-20251001']

function Field({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <span className="block text-xs text-muted-foreground">{caption}</span>
      {children}
    </div>
  )
}

function TextField({ caption, ...props }: { caption: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <Field caption={caption}>
      <Input aria-label={caption} {...props} />
    </Field>
  )
}

// `twoPass` is left undefined by ReadOnlySettings (the plain-browser mirror): GET /api/config never
// carries this field (v047 work order -- backend stays untouched), so that view has no source of
// truth for it at all and shows nothing rather than guess. DesktopSettings passes its own
// last-saved config.json value instead, which is where this actually lives.
function StatusRow({ status, error, twoPass }: { status: Config | null; error: string | null; twoPass?: boolean }) {
  return (
    <Card size="sm">
      <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <span className="font-medium text-foreground">Running now</span>
        {status ? (
          <>
            <span className="text-muted-foreground">
              provider <span className="text-foreground">{status.provider}</span>
            </span>
            <span className="text-muted-foreground">
              model <span className="text-foreground">{status.model}</span>
            </span>
            {status.retrieval === 'bm25' ? (
              // bm25 state (v034: codex/claude, no base URL) embeds nothing, so the strip names the
              // retrieval mode instead of an embed model that is not in use (v056); hybrid keeps the
              // embed model name, fixture mode unchanged.
              <span className="text-muted-foreground">
                retrieval <span className="text-foreground">BM25</span>
              </span>
            ) : (
              <span className="text-muted-foreground">
                embed <span className="text-foreground">{status.embed_model}</span>
              </span>
            )}
            {twoPass !== undefined && (
              <span className="text-muted-foreground">
                two-pass <span className="text-foreground">{twoPass ? 'on' : 'off'}</span>
              </span>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">{error ?? 'loading…'}</span>
        )}
      </CardContent>
    </Card>
  )
}

const CLI_LOGIN_HINT: Record<'codex' | 'claude', string> = { codex: 'codex login', claude: 'claude auth login' }

function TestOutcome({ result }: { result: TestConnectionResult }) {
  if (!result.ok) return <ErrorBlock className="px-3 py-2 text-xs">{result.error}</ErrorBlock>
  const text =
    result.kind === 'models'
      ? result.models.length > 0
        ? `Reachable — ${result.models.length} model${result.models.length === 1 ? '' : 's'}: ${result.models.slice(0, 5).join(', ')}${result.models.length > 5 ? ', …' : ''}`
        : 'Reachable — the endpoint returned no model list'
      : `${result.version} · ${result.loggedIn ? 'logged in' : `not logged in — run "${CLI_LOGIN_HINT[result.kind]}"`}`
  const warn = result.kind !== 'models' && !result.loggedIn
  return (
    <div
      className={`rounded-lg border px-3 py-2 text-xs ${warn ? 'border-warning/30 bg-warning-muted text-warning' : 'border-success/30 bg-success-muted text-success'}`}
    >
      {text}
    </div>
  )
}

// v047: same checkbox styling as ProviderCard.tsx's own radio (`accent-ring`, `size-4`) -- shown on
// the Codex/Claude/API-endpoint cards only (Ollama has no two-pass evidence to recommend it, Local
// (Ollama) card below never renders this; fixture mode makes no model call at all).
function TwoPassToggle({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-start gap-2 text-xs">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-0.5 size-4 accent-ring" />
      <span>
        Two-pass page selection <span className="text-muted-foreground">(recommended for hosted models)</span>
      </span>
    </label>
  )
}

// Shared by the Codex and Claude cards (v033 owner follow-up added Claude, same shape as Codex): a
// model dropdown, an optional base URL for embeddings/Ask with an optional key for it, and a status
// badge from the CLI-specific *Status() check. `info` is whatever that check last returned.
function SubscriptionCliFields({
  cliName,
  modelOptions,
  modelValue,
  onModelChange,
  baseUrl,
  apiKey,
  onBaseUrlChange,
  onApiKeyChange,
  twoPass,
  onTwoPassChange,
  info,
}: {
  cliName: string
  modelOptions: readonly string[]
  modelValue: string
  onModelChange: (value: string) => void
  baseUrl: string
  apiKey: string
  onBaseUrlChange: (value: string) => void
  onApiKeyChange: (value: string) => void
  twoPass: boolean
  onTwoPassChange: (value: boolean) => void
  info: TestConnectionResult | null
}) {
  return (
    <>
      <Field caption="Model">
        <Select value={modelValue} onValueChange={(v) => v && onModelChange(v)} items={Object.fromEntries(modelOptions.map((m) => [m, m]))}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {modelOptions.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <TwoPassToggle checked={twoPass} onChange={onTwoPassChange} />
      <TextField caption="Base URL (optional)" value={baseUrl} onChange={(e) => onBaseUrlChange(e.target.value)} placeholder="http://127.0.0.1:11434/v1" />
      <p className="text-xs text-muted-foreground">Without a base URL, Ask retrieves with keyword search (BM25) instead of embeddings — Extract still works.</p>
      {baseUrl.trim() && (
        <TextField caption="API key (optional, for the base URL above)" type="password" autoComplete="off" value={apiKey} onChange={(e) => onApiKeyChange(e.target.value)} />
      )}
      {info === null ? (
        <LoadingLine className="text-xs">Checking {cliName}…</LoadingLine>
      ) : !info.ok ? (
        <Badge variant="danger">{info.error}</Badge>
      ) : info.kind === 'models' ? (
        <Badge variant="danger">unexpected response</Badge>
      ) : (
        <Badge variant={info.loggedIn ? 'success' : 'warning'}>
          {info.version} · {info.loggedIn ? 'logged in' : 'not logged in'}
        </Badge>
      )}
    </>
  )
}

// Read-only mirror of GET /api/config for a plain browser tab — no window.arp there (main.tsx), so
// nothing is editable; a desktop double-click is the only way to change provider/model.
function ReadOnlySettings() {
  const [status, setStatus] = useState<Config | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getConfig()
      .then(setStatus)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <div className="max-w-xl space-y-5">
      <header className="border-b border-border pb-5">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">Settings</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Model provider</h1>
        <p className="mt-1 text-sm text-muted-foreground">Settings are edited in the desktop app or via backend/.env.</p>
      </header>
      {error && <ErrorBlock>{error}</ErrorBlock>}
      {!status && !error && <LoadingLine>Loading…</LoadingLine>}
      {status && <StatusRow status={status} error={error} />}
    </div>
  )
}

// The only place that checks for window.arp — everything below takes `api` as a given, so there's
// no repeated optional-chaining (or a dead "not desktop" branch inside effects/handlers that only
// ever mount when it's already known to exist).
export function SettingsView() {
  const api = typeof window !== 'undefined' ? window.arp?.settings : undefined
  return api ? <DesktopSettings api={api} /> : <ReadOnlySettings />
}

function DesktopSettings({ api }: { api: ArpSettingsApi }) {
  const [loaded, setLoaded] = useState(false)
  const [form, setForm] = useState<DesktopConfig>(DEFAULT_CONFIG)
  const [status, setStatus] = useState<Config | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [codexInfo, setCodexInfo] = useState<TestConnectionResult | null>(null)
  const [claudeInfo, setClaudeInfo] = useState<TestConnectionResult | null>(null)
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  // The status row's own "two-pass on/off" -- the *last saved* value (config.json via api.get(),
  // then whatever api.set() just persisted), never the in-progress `form` -- same "confirmed, not
  // edited" contract StatusRow's `status`/`statusError` already keep for provider/model/embed.
  const [twoPassStatus, setTwoPassStatus] = useState<boolean | undefined>(undefined)

  // Clears `status` on failure too (not just setting `statusError`) -- found live: after a failed
  // save leaves the backend answering 500 (LLM_PROVIDER=claude, no backend support yet), a stale
  // `status` from the last successful fetch otherwise wins StatusRow's `status ? ... : error` branch
  // forever, silently showing the old provider as if it were still the truth.
  const refreshStatus = () =>
    getConfig()
      .then((c) => {
        setStatus(c)
        setStatusError(null)
      })
      .catch((e: Error) => {
        setStatus(null)
        setStatusError(e.message)
      })

  useEffect(() => {
    refreshStatus()
    api.get().then((cfg) => {
      const merged = { ...DEFAULT_CONFIG, ...cfg }
      setForm(merged)
      setTwoPassStatus(effectiveTwoPass(merged))
      setLoaded(true)
      if (merged.provider === 'codex') api.codexStatus().then(setCodexInfo)
      if (merged.provider === 'claude') api.claudeStatus().then(setClaudeInfo)
    })
  }, [api])

  const update = (patch: Partial<DesktopConfig>) => {
    setForm((f) => ({ ...f, ...patch }))
    setTestResult(null)
    setSaved(false)
  }

  const selectProvider = (provider: Provider) => {
    update({ provider })
    if (provider === 'codex') {
      setCodexInfo(null)
      api.codexStatus().then(setCodexInfo)
    }
    if (provider === 'claude') {
      setClaudeInfo(null)
      api.claudeStatus().then(setClaudeInfo)
    }
  }

  const canSave = form.provider !== 'openai' || (form.baseUrl.trim() !== '' && form.model.trim() !== '')

  const test = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await api.test(form))
    } finally {
      setTesting(false)
    }
  }

  const save = async () => {
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    const res = await api.set(form)
    setSaving(false)
    if (res.ok) {
      setSaved(true)
      setTwoPassStatus(effectiveTwoPass(form))
      if (res.config) setStatus(res.config)
      else refreshStatus()
    } else {
      setSaveError(res.error)
      // The old backend was already killed before the new one failed its health check (main.js's
      // applySettings) -- "Running now" would otherwise keep showing the pre-save provider as if it
      // were still live. Refresh even on failure so it reflects whatever the new (broken) process
      // actually answers, confirmed live: a claude save with no backend support yet shows this as a
      // 500, not a silent stale success.
      refreshStatus()
    }
  }

  return (
    <div className="max-w-2xl space-y-5">
      <header className="border-b border-border pb-5">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">Settings</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Model provider</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Pick where Extract and Ask get their answers from. Saving restarts the backend with the new settings.
        </p>
      </header>

      <StatusRow status={status} error={statusError} twoPass={twoPassStatus} />

      {!loaded ? (
        <LoadingLine>Loading current settings…</LoadingLine>
      ) : (
        <>
          <div className="space-y-3">
            <ProviderCard
              value="ollama"
              title="Local (Ollama)"
              description="Runs on this machine. No API key, nothing leaves the machine."
              selected={form.provider === 'ollama'}
              onSelect={() => selectProvider('ollama')}
            >
              <TextField caption="Base URL" value={form.baseUrl} onChange={(e) => update({ baseUrl: e.target.value })} placeholder="http://127.0.0.1:11434/v1" />
              <TextField caption="Model" value={form.model} onChange={(e) => update({ model: e.target.value })} placeholder="qwen3:8b" />
              <TextField caption="Embed model" value={form.embedModel} onChange={(e) => update({ embedModel: e.target.value })} placeholder="bge-m3" />
            </ProviderCard>

            <ProviderCard
              value="openai"
              title="API endpoint"
              description="Any OpenAI-compatible /v1 host — e.g. https://api.openai.com/v1 (OpenAI) or https://api.anthropic.com/v1/ (Anthropic-compatible)."
              selected={form.provider === 'openai'}
              onSelect={() => selectProvider('openai')}
            >
              <TextField caption="Base URL" value={form.baseUrl} onChange={(e) => update({ baseUrl: e.target.value })} placeholder="https://api.openai.com/v1" />
              <TextField caption="Model" value={form.model} onChange={(e) => update({ model: e.target.value })} placeholder="gpt-4o-mini" />
              <TextField caption="API key" type="password" autoComplete="off" value={form.apiKey} onChange={(e) => update({ apiKey: e.target.value })} placeholder="sk-…" />
              <TextField caption="Embed model (optional, for Ask)" value={form.embedModel} onChange={(e) => update({ embedModel: e.target.value })} placeholder="bge-m3" />
              <TwoPassToggle checked={form.extractTwoPass} onChange={(v) => update({ extractTwoPass: v })} />
            </ProviderCard>

            <ProviderCard
              value="codex"
              title="Codex"
              description="Subscription: uses your local Codex CLI login. No local model required for Extract."
              selected={form.provider === 'codex'}
              onSelect={() => selectProvider('codex')}
            >
              <SubscriptionCliFields
                cliName="Codex CLI"
                modelOptions={CODEX_MODELS}
                modelValue={form.codexModel}
                onModelChange={(v) => update({ codexModel: v })}
                baseUrl={form.baseUrl}
                apiKey={form.apiKey}
                onBaseUrlChange={(v) => update({ baseUrl: v })}
                onApiKeyChange={(v) => update({ apiKey: v })}
                twoPass={form.extractTwoPass}
                onTwoPassChange={(v) => update({ extractTwoPass: v })}
                info={codexInfo}
              />
            </ProviderCard>

            <ProviderCard
              value="claude"
              title="Claude"
              description="Subscription: uses your local Claude Code CLI login. No local model required for Extract."
              selected={form.provider === 'claude'}
              onSelect={() => selectProvider('claude')}
            >
              <SubscriptionCliFields
                cliName="Claude Code CLI"
                modelOptions={CLAUDE_MODELS}
                modelValue={form.claudeModel}
                onModelChange={(v) => update({ claudeModel: v })}
                baseUrl={form.baseUrl}
                apiKey={form.apiKey}
                onBaseUrlChange={(v) => update({ baseUrl: v })}
                onApiKeyChange={(v) => update({ apiKey: v })}
                twoPass={form.extractTwoPass}
                onTwoPassChange={(v) => update({ extractTwoPass: v })}
                info={claudeInfo}
              />
            </ProviderCard>
          </div>

          <p className="text-xs text-muted-foreground">
            {form.provider === 'fixture' ? (
              'Demo mode is active — no model configured, canned fixture answers only.'
            ) : (
              <button type="button" onClick={() => selectProvider('fixture')} className="underline underline-offset-2 hover:text-foreground">
                Use demo mode instead (no model, canned fixture answers)
              </button>
            )}
          </p>

          <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
            <Button variant="outline" onClick={test} disabled={testing || saving || form.provider === 'fixture'}>
              {testing && <Loader2 className="animate-spin" />}
              Test connection
            </Button>
            <Button onClick={save} disabled={saving || testing || !canSave}>
              {saving && <Loader2 className="animate-spin" />}
              {saving ? 'Restarting…' : 'Save'}
            </Button>
            {saved && !saving && (
              <p role="status" className="text-xs text-success">
                Saved — backend restarted.
              </p>
            )}
          </div>

          {testing && <LoadingLine>Testing…</LoadingLine>}
          {!testing && testResult && <TestOutcome result={testResult} />}
          {saveError && <ErrorBlock>{saveError}</ErrorBlock>}
        </>
      )}
    </div>
  )
}
