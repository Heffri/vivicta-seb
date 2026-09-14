import { useState } from 'react'
import { CompareView } from './components/CompareView'
import { ResultsView } from './components/ResultsView'
import { UploadView } from './components/UploadView'
import type { Result } from './types'

export default function App() {
  const [results, setResults] = useState<Result[]>([])
  const [detail, setDetail] = useState<number | null>(null) // index into results when drilling down from compare
  const [detailPage, setDetailPage] = useState<number | null>(null) // page a citation chip asked for, if any
  const reset = () => {
    setResults([])
    setDetail(null)
  }

  const single = results.length === 1 ? results[0] : null
  const shown = single ?? (detail !== null ? results[detail] : null)

  if (shown?.extraction) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10">
        <ResultsView
          key={shown.extraction.report_id}
          extraction={shown.extraction}
          sectionTitle={shown.sectionTitle}
          onReset={reset}
          onBack={single ? undefined : () => setDetail(null)}
          initialPage={detailPage}
        />
      </main>
    )
  }
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      {results.length > 1 ? (
        <CompareView
          results={results}
          onSelect={(i, page) => {
            setDetail(i)
            setDetailPage(page ?? null)
          }}
          onReset={reset}
        />
      ) : (
        <UploadView onDone={setResults} />
      )}
    </main>
  )
}
