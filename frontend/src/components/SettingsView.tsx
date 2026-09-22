import { Cpu, Loader2, Palette, SlidersHorizontal } from 'lucide-react'
import type { InputHTMLAttributes, ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { getConfig, type Config } from '@/api'
import type { ArpSettingsApi, DesktopConfig, Provider, TestConnectionResult } from '@/main'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageHeader, Workspace } from '@/components/ui/workspace'
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
  maturityBasis: 'carrying', // same -- the backend's own default
  mergeRuns: 'off', // same -- EXTRACT_MERGE_RUNS default off (the single-run route)
  secondPass: false, // same -- the bounded retry defaults off
  theme: 'solid', // same -- desktop/settings.js's own DEFAULTS; never reaches the backend
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
// carries this field, so that view has no source of
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
              // bm25 state (codex/claude with no base URL) embeds nothing, so the strip names the
              // retrieval mode instead of an embed model that is not in use; hybrid keeps the
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
            {status.maturity_basis && (
              // /api/config carries the backend's live DEBT_BASIS, so unlike two-pass (which
              // lives only in the desktop's config.json) this segment renders in the plain-browser
              // mirror too -- "Running now" showing what the backend would actually read.
              <span className="text-muted-foreground">
                basis <span className="text-foreground">{status.maturity_basis === 'undiscounted' ? 'contractual undiscounted' : 'carrying amount'}</span>
              </span>
            )}
            {status.merge_runs && (
              // Same deal as basis -- the merge mode lives in the backend's env (the desktop
              // passes EXTRACT_MERGE_RUNS on Save), and /api/config echoes the live value, so this
              // shows what the backend would actually run with, browser mirror included.
              <span className="text-muted-foreground">
                merge <span className="text-foreground">{status.merge_runs}</span>
              </span>
            )}
            {status.second_pass !== undefined && (
              // The deep-search switch is the same deal as merge -- /api/config echoes the
              // live EXTRACT_SECOND_PASS, so the strip shows what the backend would run with
              // (browser mirror included). `!== undefined`, not truthiness: a plain false is the
              // normal off state and must still render.
              <span className="text-muted-foreground">
                deep search <span className="text-foreground">{status.second_pass ? 'on' : 'off'}</span>
              </span>
            )}
            {status.scan_all !== undefined && (
              // The offline full-report scan, echoed for confirmation only (docs/DEMO.md's
              // checklist) -- it has no Settings control by design, so off is its expected state.
              <span className="text-muted-foreground">
                scan all <span className="text-foreground">{status.scan_all ? 'on' : 'off'}</span>
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

// Same checkbox styling as ProviderCard.tsx's own radio (`accent-ring`, `size-4`). Rendered on the
// Extraction page for Codex/Claude/API-endpoint only: Ollama has no two-pass evidence to recommend
// it, and fixture mode makes no model call at all.
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

// Which maturity table the debt_maturity section reads — the borrowings note's carrying amounts
// (the backend's default, total ties to the balance sheet) or the liquidity note's contractual
// undiscounted cash flows (future interest included, higher total). Unlike TwoPassToggle this is
// model-independent, so it renders on the Extraction page for every provider, Ollama included.
function MaturityBasisSelect({
  value,
  onChange,
}: {
  value: DesktopConfig['maturityBasis']
  onChange: (value: DesktopConfig['maturityBasis']) => void
}) {
  const options: Record<DesktopConfig['maturityBasis'], string> = {
    carrying: 'Carrying amount (default)',
    undiscounted: 'Contractual undiscounted',
  }
  return (
    <Field caption="Maturity basis">
      <Select
        value={value}
        onValueChange={(v) => {
          if (v === 'carrying' || v === 'undiscounted') onChange(v)
        }}
        items={options}
      >
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(Object.keys(options) as (keyof typeof options)[]).map((k) => (
            <SelectItem key={k} value={k}>
              {options[k]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}

// The second-run merge (`EXTRACT_MERGE_RUNS=off|union|majority`, default off) as a user option.
// Model-independent like MaturityBasisSelect -- the choice has nothing to do with which provider
// is picked, and every non-fixture provider passes it through, Ollama included. Same Segmented
// primitive as Results' PDF/Image toggle.
function MergeRunsControl({ value, onChange }: { value: DesktopConfig['mergeRuns']; onChange: (value: DesktopConfig['mergeRuns']) => void }) {
  return (
    <Card size="sm">
      <CardContent className="space-y-2">
        <Field caption="Two-run merge">
          <Segmented
            aria-label="Two-run merge"
            className="w-full sm:w-auto"
            value={value}
            onChange={onChange}
            options={[
              { value: 'off', label: 'Off' },
              { value: 'union', label: 'Union' },
              { value: 'majority', label: 'Majority' },
            ]}
          />
        </Field>
        <p className="text-xs text-muted-foreground">
          Union: run twice, keep the better-evidenced field. Majority: also count the saved extraction; skips the second run when the first matches it. Doubles model calls.
        </p>
      </CardContent>
    </Card>
  )
}

// The bounded second pass + full-text sweep (EXTRACT_SECOND_PASS) as a user option, modeled on
// MergeRunsControl (same card, same Segmented primitive, default off). Model-independent like the
// merge: the retry rides the same fixed_pages seam as the analyst fill, so every non-fixture
// provider passes it through, Ollama included.
function DeepSearchControl({ value, onChange }: { value: boolean; onChange: (value: boolean) => void }) {
  return (
    <Card size="sm">
      <CardContent className="space-y-2">
        <Field caption="Deep search for missing figures">
          <Segmented
            aria-label="Deep search for missing figures"
            className="w-full sm:w-auto"
            value={value ? 'on' : 'off'}
            onChange={(v) => onChange(v === 'on')}
            options={[
              { value: 'on', label: 'On' },
              { value: 'off', label: 'Off' },
            ]}
          />
        </Field>
        <p className="text-xs text-muted-foreground">
          When a required figure is still empty, scan the whole document for the figure&rsquo;s own wording and ask the model once more for just that field &mdash; the citation must be on the page. Costs a few extra model calls per report.
        </p>
      </CardContent>
    </Card>
  )
}

// The either/or between the app's two visual languages — Solid (default: opaque surfaces) and
// Acrylic (glass: wallpaper glow + backdrop blur in the browser, real Windows acrylic in the
// desktop app). Rendered on the Appearance page in *both* settings variants: in a plain browser
// tab localStorage is the whole persistence, the desktop additionally writes config.json and
// flips the live window material through window.arp.setTheme (main.tsx).
function ThemeSelect({ onThemeChange }: { onThemeChange?: (theme: DesktopConfig['theme']) => void }) {
  const [theme, setTheme] = useState<DesktopConfig['theme']>(() =>
    localStorage.getItem('arp-theme') === 'acrylic' ? 'acrylic' : 'solid',
  )
  const [restartHint, setRestartHint] = useState(false)

  const select = async (next: DesktopConfig['theme']) => {
    if (next === theme) return
    setTheme(next)
    setRestartHint(false)
    // The browser look is instant and local: <html data-theme> is what index.css's Acrylic scope
    // keys off, and localStorage is what main.tsx restores on the next load.
    if (next === 'acrylic') document.documentElement.dataset.theme = 'acrylic'
    else delete document.documentElement.dataset.theme
    localStorage.setItem('arp-theme', next)
    // Desktop only: keep the form's copy in step so a later Save (which writes the whole config)
    // persists the same theme the user just picked, never a stale one.
    onThemeChange?.(next)
    const setDesktopTheme = window.arp?.setTheme
    if (!setDesktopTheme) return
    const res = await setDesktopTheme(next).catch(() => null)
    if (!res) return // localStorage + data-theme already applied; config catches up on next launch
    if (!res.appliedNow) {
      setRestartHint(true) // no live setBackgroundMaterial on this window — restart to apply
      return
    }
    // Mirror main.tsx's startup rule: the OS-material branch goes on only when the desktop
    // actually switched the window to real acrylic (transparent ground, no painted wallpaper).
    if (res.material === 'acrylic') document.documentElement.dataset.material = 'on'
    else delete document.documentElement.dataset.material
  }

  const options: Record<DesktopConfig['theme'], string> = {
    solid: 'Solid (default)',
    acrylic: 'Acrylic',
  }
  return (
    <Card size="sm">
      <CardContent className="space-y-2">
        <Field caption="Theme">
          <Select
            value={theme}
            onValueChange={(v) => {
              if (v === 'solid' || v === 'acrylic') void select(v)
            }}
            items={options}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(options) as (keyof typeof options)[]).map((k) => (
                <SelectItem key={k} value={k}>
                  {options[k]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <p className="text-xs text-muted-foreground">
          Acrylic uses Windows&rsquo; translucent material in the desktop app and a wallpaper glow in the browser.
        </p>
        {restartHint && (
          <p className="text-xs text-warning">Restart the app to apply the window material.</p>
        )}
      </CardContent>
    </Card>
  )
}

// Shared by the Codex and Claude cards: a model dropdown, an optional base URL for embeddings/Ask
// with an optional key for it, and a status badge from the CLI-specific *Status() check. `info` is
// whatever that check last returned.
function SubscriptionCliFields({
  cliName,
  modelOptions,
  modelValue,
  onModelChange,
  baseUrl,
  apiKey,
  onBaseUrlChange,
  onApiKeyChange,
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
  const [view, setView] = useState<'provider' | 'appearance'>('provider')
  const [status, setStatus] = useState<Config | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getConfig()
      .then(setStatus)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Settings" title="Settings" description="Manage your model connection and workspace appearance." />
      <Workspace label="Settings workspace" value={view} onChange={setView} pages={[
        { value: 'provider', label: 'Model provider', icon: Cpu, content: <div className="max-w-2xl space-y-5">
          <p className="text-sm text-muted-foreground">Model settings are edited in the desktop app or via backend/.env.</p>
          {error && <ErrorBlock>{error}</ErrorBlock>}
          {!status && !error && <LoadingLine>Loading…</LoadingLine>}
          {status && <StatusRow status={status} error={error} />}
        </div> },
        { value: 'appearance', label: 'Appearance', icon: Palette, content: <div className="max-w-xl"><ThemeSelect /></div> },
      ]} />
    </div>
  )
}

// The only place that checks for window.arp — everything below takes `api` as a given, so there's
// no repeated optional-chaining (or a dead "not desktop" branch inside effects/handlers that only
// ever mount when it's already known to exist). `onConfigChange` forwards the post-save config to
// App so its StatusBar stops lagging behind a save until relaunch — the same fresh payload this
// view's own strip gets in DesktopSettings.save().
export function SettingsView({ onConfigChange }: { onConfigChange?: (config: Config) => void }) {
  const api = typeof window !== 'undefined' ? window.arp?.settings : undefined
  return api ? <DesktopSettings api={api} onConfigChange={onConfigChange} /> : <ReadOnlySettings />
}

function DesktopSettings({ api, onConfigChange }: { api: ArpSettingsApi; onConfigChange?: (config: Config) => void }) {
  const [view, setView] = useState<'provider' | 'extraction' | 'appearance'>('provider')
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
        return c // save()'s no-config branch forwards this same payload up to App
      })
      .catch((e: Error) => {
        setStatus(null)
        setStatusError(e.message)
        return null
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
      // App's StatusBar keeps the mount-time config until relaunch, so forward the post-restart
      // payload up the same way this strip gets it -- res.config when the shell resolved
      // it (desktop/main.js's nicety fetch; its failure path still resolves { ok: true } without a
      // config), a fresh /api/config fetch otherwise. Success only: the failure branch's
      // refreshStatus() below must leave App's footer showing whatever was live before the save.
      if (res.config) {
        setStatus(res.config)
        onConfigChange?.(res.config)
      } else {
        refreshStatus().then((fresh) => {
          if (fresh) onConfigChange?.(fresh)
        })
      }
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
    <div className="space-y-6">
      <PageHeader eyebrow="Settings" title="Settings" description="Manage your model connection, extraction preferences and workspace appearance." />

      {!loaded ? (
        <LoadingLine>Loading current settings…</LoadingLine>
      ) : (
        <>
          <Workspace label="Settings workspace" value={view} onChange={setView} pages={[
          { value: 'provider', label: 'Model provider', icon: Cpu, content: <div className="max-w-2xl space-y-5">
          <StatusRow status={status} error={statusError} twoPass={twoPassStatus} />
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

          </div> },
          { value: 'extraction', label: 'Extraction', icon: SlidersHorizontal, content: <div className="max-w-xl space-y-5">
            <div><h2 className="text-base font-semibold">Extraction preferences</h2><p className="mt-1 text-sm text-muted-foreground">These settings apply to new extractions. Save to restart the backend.</p></div>
            {form.provider !== 'fixture' && form.provider !== 'ollama' && <TwoPassToggle checked={form.extractTwoPass} onChange={v => update({ extractTwoPass: v })} />}
            <MaturityBasisSelect value={form.maturityBasis} onChange={v => update({ maturityBasis: v })} />
            <MergeRunsControl value={form.mergeRuns} onChange={v => update({ mergeRuns: v })} />
            <DeepSearchControl value={form.secondPass} onChange={v => update({ secondPass: v })} />
          </div> },
          { value: 'appearance', label: 'Appearance', icon: Palette, content: <div className="max-w-xl"><ThemeSelect onThemeChange={t => update({ theme: t })} /></div> },
          ]} footer={view !== 'appearance' && <>
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
          </>} />

          {testing && <LoadingLine>Testing…</LoadingLine>}
          {!testing && testResult && <TestOutcome result={testResult} />}
          {saveError && <ErrorBlock>{saveError}</ErrorBlock>}
        </>
      )}
    </div>
  )
}
