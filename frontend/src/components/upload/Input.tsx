import type { InputHTMLAttributes, ReactNode } from 'react'

type InputProps = InputHTMLAttributes<HTMLInputElement> & { icon?: ReactNode }

// Local acrylic text input: hairline border, translucent --bg-1 fill, accent focus ring.
// Written here rather than promoted into components/ui/ — v002 scope only (see evidence).
export function Input({ icon, className = '', ...props }: InputProps) {
  return (
    <div className={`relative min-w-0 flex-1 ${className}`}>
      {icon && (
        <span className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground [&_svg]:size-4">
          {icon}
        </span>
      )}
      <input
        {...props}
        className={`h-8 w-full rounded-lg border border-input bg-background/50 text-sm transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50 ${
          icon ? 'pr-3 pl-8' : 'px-2.5'
        }`}
      />
    </div>
  )
}
