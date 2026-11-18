import { forwardRef, useId } from 'react'
import clsx from 'clsx'
import { ChevronDown, Search, X } from 'lucide-react'

export function Field({ label, error, hint, required, children, className, htmlFor }) {
  return (
    <div className={className}>
      {label && (
        <label className="label" htmlFor={htmlFor}>
          {label}
          {required && <span className="ml-0.5 text-danger">*</span>}
        </label>
      )}
      {children}
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

export const Input = forwardRef(function Input({ className, error, ...rest }, ref) {
  return <input ref={ref} className={clsx('input', error && 'input-error', className)} {...rest} />
})

export const Textarea = forwardRef(function Textarea({ className, error, rows = 3, ...rest }, ref) {
  return <textarea ref={ref} rows={rows} className={clsx('input resize-y', error && 'input-error', className)} {...rest} />
})

export const Select = forwardRef(function Select({ className, error, children, placeholder, options, ...rest }, ref) {
  return (
    <div className="relative">
      <select ref={ref} className={clsx('input appearance-none pr-9', error && 'input-error', className)} {...rest}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options
          ? options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)
          : children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
    </div>
  )
})

export function Checkbox({ label, description, className, ...rest }) {
  const id = useId()
  return (
    <label htmlFor={id} className={clsx('flex cursor-pointer items-start gap-2.5', className)}>
      <input id={id} type="checkbox" className="mt-0.5 h-4 w-4 cursor-pointer rounded border-line-strong accent-[rgb(var(--brand-strong))]" {...rest} />
      <span>
        <span className="block text-sm text-ink">{label}</span>
        {description && <span className="block text-xs text-muted">{description}</span>}
      </span>
    </label>
  )
}

export function Switch({ checked, onChange, label, description, disabled }) {
  return (
    <label className={clsx('flex items-center justify-between gap-4', disabled ? 'opacity-60' : 'cursor-pointer')}>
      {(label || description) && (
        <span>
          {label && <span className="block text-sm font-medium text-ink">{label}</span>}
          {description && <span className="block text-xs text-muted">{description}</span>}
        </span>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={clsx('relative h-6 w-11 shrink-0 rounded-full transition-colors', checked ? 'bg-brand' : 'bg-line-strong')}
      >
        <span className={clsx('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform', checked ? 'translate-x-[22px]' : 'translate-x-0.5')} />
      </button>
    </label>
  )
}

export function SearchInput({ value, onChange, placeholder = 'Search…', className }) {
  return (
    <div className={clsx('relative', className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="input pl-9 pr-8"
        type="search"
      />
      {value && (
        <button onClick={() => onChange('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-faint hover:text-ink" aria-label="Clear search">
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}

/** Segmented control for small option sets (filters, views). */
export function Segmented({ value, onChange, options, size = 'md' }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={clsx(
            'inline-flex items-center gap-1.5 rounded-md font-medium transition-colors',
            size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-8 px-3 text-[13px]',
            value === o.value ? 'bg-surface text-ink shadow-card' : 'text-muted hover:text-ink',
          )}
        >
          {o.icon && <o.icon className="h-3.5 w-3.5" />}
          {o.label}
          {o.count !== undefined && <span className="num text-faint">{o.count}</span>}
        </button>
      ))}
    </div>
  )
}
