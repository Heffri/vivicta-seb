import { Columns3, FileText, Library, Network, MessageCircleQuestion, Settings, UploadCloud, type LucideIcon } from 'lucide-react'

export type Tab = 'extract' | 'results' | 'compare' | 'ask' | 'kb' | 'map' | 'settings'

export const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'extract', label: 'Extract', icon: UploadCloud },
  { id: 'results', label: 'Results', icon: FileText },
  { id: 'compare', label: 'Compare', icon: Columns3 },
  { id: 'ask', label: 'Ask', icon: MessageCircleQuestion },
  { id: 'kb', label: 'Knowledge base', icon: Library },
  { id: 'map', label: 'Company map', icon: Network },
  // Last in the rail's tablist, directly above the tone toggle (a separate control below the list,
  // see Rail.tsx) — always enabled, unlike the report-dependent tabs above it.
  { id: 'settings', label: 'Settings', icon: Settings },
]
