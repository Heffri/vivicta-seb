import { useEffect, useState } from 'react'
import { ThinkingOrb as LibrariesOrb } from 'thinking-orbs'

const currentTheme = () => document.documentElement.dataset.tone === 'light' ? 'light' : 'dark'

export function ThinkingOrb({ thinking = false, className = '' }: { thinking?: boolean; className?: string }) {
  const [theme, setTheme] = useState<'light' | 'dark'>(currentTheme)

  useEffect(() => {
    // The app uses data-tone; the library's auto theme looks for data-theme.
    const observer = new MutationObserver(() => setTheme(currentTheme()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-tone'] })
    return () => observer.disconnect()
  }, [])

  return <div aria-hidden="true" data-orb-state={thinking ? 'thinking' : 'idle'} className={`flex shrink-0 items-center justify-center ${className}`}>
    <LibrariesOrb state={thinking ? 'searching' : 'breathing'} size={64} theme={theme} data-orb-theme={theme} />
  </div>
}
