import { Cpu, Loader2 } from 'lucide-react'
import type { Config } from '../../api'
import type { Batch } from '../../hooks/useBatch'

type StatusBarProps = { config: Config | null; batch?: Batch; onOpenBatch?: () => void }

// Minimal cross-tab visibility for a running batch (v171): a small "n/m" pill so leaving the
// Extract tab doesn't make the batch feel like it vanished — the fuller per-report breakdown
// stays in BatchProgress, this is just a pointer back to it.
export function StatusBar({ config, batch, onOpenBatch }: StatusBarProps) {
  const settled = batch?.items.filter((it) => it.stage === 'done' || it.stage === 'failed').length ?? 0
  return (
    <footer className="flex h-7 shrink-0 items-center gap-1.5 border-t border-border px-4 font-mono text-xs text-muted-foreground">
      <Cpu className="size-3.5" />
      {batch?.busy && (
        <button
          type="button"
          onClick={onOpenBatch}
          className="flex items-center gap-1 rounded-sm border-l border-border pl-1.5 hover:text-foreground"
        >
          <Loader2 className="size-3 animate-spin" aria-hidden />
          Batch {settled}/{batch.items.length}
        </button>
      )}
      {config ? (
        <span title={config.base_url ?? (config.llm ? 'no embeddings endpoint — keyword (BM25) retrieval' : 'no LLM configured')}>
          {config.model}
          {config.retrieval === 'bm25' ? (
            // v034's bm25 state embeds nothing — same swap as SettingsView's StatusRow (v056);
            // hybrid/fixture keep the embed model name.
            <span className="opacity-60"> · retrieval BM25</span>
          ) : (
            <span className="opacity-60"> · {config.embed_model}</span>
          )}
        </span>
      ) : (
        <span className="opacity-60">no backend</span>
      )}
    </footer>
  )
}
