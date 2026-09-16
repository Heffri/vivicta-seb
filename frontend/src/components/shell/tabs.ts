import { Columns3, FileText, Library, MessageCircleQuestion, UploadCloud, type LucideIcon } from 'lucide-react'

export type Tab = 'extract' | 'results' | 'compare' | 'ask' | 'kb'

export const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'extract', label: 'Extract', icon: UploadCloud },
  { id: 'results', label: 'Results', icon: FileText },
  { id: 'compare', label: 'Compare', icon: Columns3 },
  { id: 'ask', label: 'Ask', icon: MessageCircleQuestion },
  { id: 'kb', label: 'Knowledge base', icon: Library },
]
