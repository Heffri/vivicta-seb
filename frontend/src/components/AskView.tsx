import { AskPanel } from '@/components/AskPanel'

type Props = { reports: { report_id: string; label: string }[] }

export function AskView({ reports }: Props) {
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <header className="border-b pb-5">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">Ask</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">
          {reports.length === 1 ? reports[0].label : `${reports.length} reports`}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">Answers cite pages of the loaded reports; citations open the PDF.</p>
      </header>
      <AskPanel reports={reports} />
    </div>
  )
}
