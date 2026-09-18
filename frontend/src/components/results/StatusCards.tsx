import { Check, Info, TriangleAlert, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Check as CheckType, Field } from '@/types'
import { explainCheck, explainWarning } from './statusCopy'
import { fieldVerification } from './verification'

type StatusCardsProps = {
  checks: CheckType[]
  warnings: string[]
  fields: Field[]
  onSelect?: (key: string) => void
}

export function StatusCards({ checks, warnings, fields, onSelect }: StatusCardsProps) {
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Do the numbers add up?</CardTitle>
          <p className="text-xs text-muted-foreground">Matching totals do not prove that every figure was read correctly.</p>
        </CardHeader>
        <CardContent>
          {checks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No calculations are available for this section.</p>
          ) : (
            <ul className="space-y-4">
              {checks.map((check) => {
                const copy = explainCheck(check)
                const Icon = copy.unavailable ? TriangleAlert : check.passed ? Check : X
                return (
                  <li key={check.name} className="flex gap-2 text-sm">
                    <Icon className={`mt-0.5 size-4 shrink-0 ${copy.unavailable ? 'text-warning' : check.passed ? 'text-success' : 'text-danger'}`} aria-hidden />
                    <div className="min-w-0 space-y-1">
                      <div className="font-medium">{copy.title}: {copy.status}</div>
                      <p className="text-xs text-muted-foreground">{copy.explanation}</p>
                      <details className="text-xs text-muted-foreground">
                        <summary className="cursor-pointer">Calculation details</summary>
                        <p className="mt-2 break-words font-mono">{check.detail}</p>
                      </details>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Extraction notes</CardTitle>
          <p className="text-xs text-muted-foreground">Issues and adjustments recorded while reading the report.</p>
        </CardHeader>
        <CardContent>
          {warnings.length === 0 ? (
            <p className="text-sm text-muted-foreground">No extraction notes were reported.</p>
          ) : (
            <ul className="space-y-4">
              {warnings.map((warning, index) => {
                const { field, title, explanation } = explainWarning(warning, fields)
                const review = field && ['Needs review', 'Not checked'].includes(fieldVerification(field).label)
                const Icon = review ? TriangleAlert : Info
                return (
                  <li key={`${index}-${warning}`} className="flex gap-2 text-sm">
                    <Icon className={`mt-0.5 size-4 shrink-0 ${review ? 'text-warning' : 'text-muted-foreground'}`} aria-hidden />
                    <div className="min-w-0 space-y-1">
                      <div className="font-medium">{title}</div>
                      <p className="text-xs text-muted-foreground">{explanation}</p>
                      {field?.source && onSelect && (
                        <Button variant="outline" size="xs" className="mt-1" onClick={() => onSelect(field.key)}>
                          Open source, page {field.source.page}
                        </Button>
                      )}
                      <details className="text-xs text-muted-foreground">
                        <summary className="cursor-pointer">Extraction details</summary>
                        <p className="mt-2 break-words">{warning}</p>
                      </details>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
