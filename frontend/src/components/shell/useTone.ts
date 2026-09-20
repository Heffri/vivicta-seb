import { useEffect, useState } from 'react'

export type Tone = 'dark' | 'light'

const STORAGE_KEY = 'acrylic-tone'

// Applies the tone to <html data-tone> (not a .dark class — see docs/acrylic/DESIGN.md)
// and remembers the choice; :root's own defaults are dark glass.
export function useTone() {
  const [tone, setTone] = useState<Tone>(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved === 'light' || saved === 'dark' ? saved : 'dark'
  })

  useEffect(() => {
    document.documentElement.dataset.tone = tone
    localStorage.setItem(STORAGE_KEY, tone)
  }, [tone])

  return [tone, setTone] as const
}
