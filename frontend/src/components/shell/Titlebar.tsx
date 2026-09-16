type TitlebarProps = { subtitle: string }

export function Titlebar({ subtitle }: TitlebarProps) {
  return (
    <header className="flex h-11 shrink-0 items-center gap-3 border-b border-border px-4">
      <span className="text-sm font-semibold tracking-tight text-foreground">Annual Report Parser</span>
      <span className="truncate text-xs text-muted-foreground" title={subtitle}>
        {subtitle}
      </span>
    </header>
  )
}
