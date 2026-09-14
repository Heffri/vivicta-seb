import { useState } from 'react'
import { ResultsView } from './components/ResultsView'
import { UploadView } from './components/UploadView'
import type { Extraction } from './types'

type Result = { extraction: Extraction; sectionTitle: string }

export default function App() {
  const [view, setView] = useState<'upload' | 'results'>('upload')
  const [result, setResult] = useState<Result | null>(null)

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      {view === 'results' && result ? (
        <ResultsView
          key={result.extraction.report_id}
          extraction={result.extraction}
          sectionTitle={result.sectionTitle}
          onReset={() => setView('upload')}
        />
      ) : (
        <UploadView
          onDone={(extraction, sectionTitle) => {
            setResult({ extraction, sectionTitle })
            setView('results')
          }}
        />
      )}
    </main>
  )
}
