type TitlebarProps = { subtitle: string }

// desktop/preload.js only exposes window.arp inside the Electron shell (declared globally in
// main.tsx); a browser tab leaves it undefined. Only the Windows build sets titleBarStyle:
// 'hidden' + titleBarOverlay (desktop/main.js) — macOS/Linux keep the native, non-hidden
// titlebar, which already draws above this header, so neither of them needs the reserved
// caption-button width below.
const isWindowsDesktopShell = window.arp?.platform === 'win32'

export function Titlebar({ subtitle }: TitlebarProps) {
  return (
    <header
      className={
        'app-titlebar flex h-11 shrink-0 items-center gap-3 border-b border-border px-4' +
        (isWindowsDesktopShell ? ' pr-[138px]' : '')
      }
    >
      <span className="text-sm font-semibold tracking-tight text-foreground">Annual Report Parser</span>
      <span className="truncate text-xs text-muted-foreground" title={subtitle}>
        {subtitle}
      </span>
    </header>
  )
}
