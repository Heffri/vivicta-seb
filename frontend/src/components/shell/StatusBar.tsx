import { Cpu } from 'lucide-react'
import type { Config } from '../../api'

type StatusBarProps = { config: Config | null }

export function StatusBar({ config }: StatusBarProps) {
  return (
    <footer className="flex h-7 shrink-0 items-center gap-1.5 border-t border-border px-4 font-mono text-xs text-muted-foreground">
      <Cpu className="size-3.5" />
      {config ? (
        <span title={config.base_url ?? (config.llm ? 'no embeddings endpoint — keyword (BM25) retrieval' : 'no LLM configured')}>
          {config.model}
          <span className="opacity-60"> · {config.embed_model}</span>
        </span>
      ) : (
        <span className="opacity-60">no backend</span>
      )}
    </footer>
  )
}
