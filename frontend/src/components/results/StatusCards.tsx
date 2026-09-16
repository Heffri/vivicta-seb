import { Check, TriangleAlert, X } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Check as CheckType } from '@/types'

type StatusCardsProps = {
  checks: CheckType[]
  warnings: string[]
}

/** Backend verification, compact: arithmetic checks pass/fail and free-text warnings,
 *  coloured by status tokens (success / danger / warning). */
export function StatusCards({ checks, warnings }: StatusCardsProps) {
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Checks</CardTitle>
        </CardHeader>
        <CardContent>
          {checks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No checks for this section.</p>
          ) : (
            <ul className="space-y-3">
              {checks.map((c) => (
                <li key={c.name} className="flex gap-2 text-sm">
                  {c.passed ? (
                    <Check className="mt-0.5 size-4 shrink-0 text-success" aria-label="passed" />
                  ) : (
                    <X className="mt-0.5 size-4 shrink-0 text-danger" aria-label="failed" />
                  )}
                  <div className="min-w-0">
                    <div className="font-medium">{c.name}</div>
                    <div className="break-words font-mono text-xs text-muted-foreground">{c.detail}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Warnings</CardTitle>
        </CardHeader>
        <CardContent>
          {warnings.length === 0 ? (
            <p className="text-sm text-muted-foreground">None.</p>
          ) : (
            <ul className="space-y-3">
              {warnings.map((w) => (
                <li key={w} className="flex gap-2 text-sm">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                  <span className="break-words">{w}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
