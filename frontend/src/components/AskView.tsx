import { useEffect, useState } from 'react'
import { getKb } from '@/api'
import { AskPanel } from '@/components/AskPanel'
import { CollectionPicker } from '@/components/CollectionPicker'
import { useCollection } from '@/hooks/useCollection'
import { Button } from '@/components/ui/button'
import { ErrorBlock, LoadingLine } from '@/components/ui/state'
import type { KbEntry } from '@/types'

type Props = { initialCompany?: string }

export function AskView({ initialCompany }: Props) {
  const [collection, setCollection] = useCollection()
  const [catalog, setCatalog] = useState<KbEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let alive = true
    getKb(collection).then((entries) => { if (alive) setCatalog(entries) }).catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [retry, collection])
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b pb-5"><div>
        <p className="text-xs text-muted-foreground uppercase tracking-wide">Ask</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Ask your saved reports</h1>
        <p className="mt-2 text-sm text-muted-foreground">Compare figures, explore risks, and follow every answer back to its source.</p>
        </div><CollectionPicker value={collection} onChange={value => { if (value !== collection) { setCatalog(null); setError(null); setCollection(value) } }} />
      </header>
      {error ? <div className="space-y-2"><ErrorBlock>Could not load saved reports: {error}</ErrorBlock><Button onClick={() => { setError(null); setCatalog(null); setRetry((n) => n + 1) }}>Retry</Button></div>
        : catalog === null ? <LoadingLine>Loading saved reports…</LoadingLine>
        : <AskPanel key={collection} reports={[]} catalog={catalog} initialCompany={initialCompany} />}
    </div>
  )
}
