import { Segmented } from '@/components/ui/segmented'
import type { Collection } from '@/hooks/useCollection'

export function CollectionPicker({ value, onChange, companies = false, disabled = false }: {
  value: Collection; onChange: (value: Collection) => void; companies?: boolean; disabled?: boolean
}) {
  return <fieldset disabled={disabled} className="flex items-center gap-2 disabled:opacity-50">
    <span className="text-xs text-muted-foreground">Collection</span>
    <Segmented aria-label="Collection" value={value} onChange={onChange} options={[
      { value: 'wallenberg', label: 'Wallenberg' }, { value: 'midcap', label: 'SEB Mid Cap (132)' }, { value: 'all', label: companies ? 'All companies' : 'All' },
    ]} />
  </fieldset>
}
