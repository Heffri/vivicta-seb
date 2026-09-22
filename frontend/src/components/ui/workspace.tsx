import { useId, useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

/** The shared page template: heading, local navigation, then one task surface. */
export function PageHeader({ eyebrow, title, description, actions }: {
  eyebrow: string; title: ReactNode; description?: ReactNode; actions?: ReactNode
}) {
  return <header className="page-header">
    <div className="min-w-0 flex-1">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{eyebrow}</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">{title}</h1>
      {description && <div className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</div>}
    </div>
    {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
  </header>
}

export type WorkspacePage<T extends string> = {
  value: T; label: string; icon?: LucideIcon; count?: number; content: ReactNode; keepMounted?: boolean
}

export function Workspace<T extends string>({ label, value, onChange, pages, toolbar, footer }: {
  label: string; value: T; onChange: (value: T) => void; pages: WorkspacePage<T>[]; toolbar?: ReactNode; footer?: ReactNode
}) {
  const id = useId()
  // Once opened, preserve local forms, questions and comparisons across navigation.
  // Unvisited pages remain unmounted unless they explicitly need background state.
  const [visited, setVisited] = useState<Set<string>>(() => new Set([value]))
  if (!visited.has(value)) setVisited(new Set([...visited, value]))
  return <section className="workspace-surface" aria-label={label}>
    <nav className="workspace-subnav" aria-label={label}>
      {pages.map(page => <button key={page.value} type="button" id={`${id}-${page.value}-nav`}
        aria-current={value === page.value ? 'page' : undefined} aria-controls={`${id}-${page.value}`}
        onClick={() => onChange(page.value)}>
        {page.icon && <page.icon className="size-4" aria-hidden />}{page.label}
        {page.count !== undefined && page.count > 0 && <span className="workspace-count">{page.count}</span>}
      </button>)}
    </nav>
    {toolbar && <div className="workspace-toolbar">{toolbar}</div>}
    {pages.map(page => <div key={page.value} id={`${id}-${page.value}`} role="region"
      aria-labelledby={`${id}-${page.value}-nav`} hidden={value !== page.value} className="workspace-content">
      {(visited.has(page.value) || page.keepMounted) && page.content}
    </div>)}
    {footer && <div className="workspace-footer">{footer}</div>}
  </section>
}
