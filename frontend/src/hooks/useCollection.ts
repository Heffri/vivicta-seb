import { useState } from 'react'

export type Collection = 'wallenberg' | 'midcap' | 'all'
const KEY = 'arp-kb-collection'

// Most tabs share their scope. Views such as the complete saved-report library can
// use a separate preference so a directory filter doesn't hide newly saved reports.
export function useCollection(defaultCollection: Collection = 'wallenberg', storageKey = KEY) {
  const [collection, setCollection] = useState<Collection>(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      return saved === 'all' || saved === 'midcap' || saved === 'wallenberg' ? saved : defaultCollection
    }
    catch { return defaultCollection }
  })
  const changeCollection = (value: Collection) => {
    setCollection(value)
    try { localStorage.setItem(storageKey, value) } catch { /* storage can be unavailable */ }
  }
  return [collection, changeCollection] as const
}
