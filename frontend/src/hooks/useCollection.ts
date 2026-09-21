import { useState } from 'react'

export type Collection = 'wallenberg' | 'all'
const KEY = 'arp-kb-collection'

// Tabs mount one at a time; share the user's choice when moving between them.
export function useCollection() {
  const [collection, setCollection] = useState<Collection>(() => {
    try { return localStorage.getItem(KEY) === 'all' ? 'all' : 'wallenberg' }
    catch { return 'wallenberg' }
  })
  const changeCollection = (value: Collection) => {
    setCollection(value)
    try { localStorage.setItem(KEY, value) } catch { /* storage can be unavailable */ }
  }
  return [collection, changeCollection] as const
}
