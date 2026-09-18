import { useEffect, useState } from 'react'
import { getKb } from '@/api'
import { AskPanel } from '@/components/AskPanel'
import { Button } from '@/components/ui/button'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { KbEntry } from '@/types'

type Props = { initialCompany?: string }

export function AskView({ initialCompany }: Props) {
  const [catalog, setCatalog] = useState<KbEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let alive = true
    getKb().then((entries) => { if (alive) setCatalog(entries) }).catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [retry])
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <header className="border-b pb-5">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">Ask</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Ask your saved reports</h1>
        <p className="mt-1 text-sm text-muted-foreground">Search all saved reports, or type @ and choose companies to narrow your question. Answers link to their sources.</p>
      </header>
      {error ? <div className="space-y-2"><ErrorBlock>Could not load saved reports: {error}</ErrorBlock><Button onClick={() => { setError(null); setCatalog(null); setRetry((n) => n + 1) }}>Retry</Button></div>
        : catalog === null ? <LoadingLine>Loading saved reports…</LoadingLine>
        : <AskPanel reports={[]} catalog={catalog} initialCompany={initialCompany} />}
    </div>
  )
}
