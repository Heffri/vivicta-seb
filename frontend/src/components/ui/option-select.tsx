import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './select'

/** Labeled, full-width select for filter bars and forms. */
export function OptionSelect({ label, value, onChange, options, disabled = false }: {
  label: string; value: string; onChange: (value: string) => void
  options: { value: string; label: string }[]; disabled?: boolean
}) {
  return <div className="min-w-0 space-y-1.5">
    <span className="block text-xs font-medium text-muted-foreground">{label}</span>
    <Select value={value} onValueChange={next => next !== null && onChange(next)} items={Object.fromEntries(options.map(option => [option.value, option.label]))} disabled={disabled}>
      <SelectTrigger aria-label={label} className="w-full"><SelectValue /></SelectTrigger>
      <SelectContent>{options.map(option => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
    </Select>
  </div>
}
