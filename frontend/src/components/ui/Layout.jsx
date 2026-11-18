import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { ChevronRight } from 'lucide-react'

export function PageHeader({ title, description, actions, breadcrumbs, children }) {
  useEffect(() => {
    document.title = title ? `${title} · ECHOUTRA ONE` : 'ECHOUTRA ONE'
  }, [title])
  return (
    <div className="mb-6">
      {breadcrumbs && (
        <nav className="mb-2 flex items-center gap-1 text-xs text-muted">
          {breadcrumbs.map((b, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="h-3 w-3 text-faint" />}
              {b.to ? <Link to={b.to} className="hover:text-ink">{b.label}</Link> : <span className="text-ink-2">{b.label}</span>}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-[22px] font-semibold leading-tight sm:text-2xl">{title}</h1>
          {description && <p className="mt-1 text-sm text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  )
}

export function Tabs({ tabs, value, onChange, className }) {
  return (
    <div className={clsx('scrollbar-thin -mx-1 flex gap-1 overflow-x-auto border-b border-line px-1', className)} role="tablist">
      {tabs.filter((t) => !t.hidden).map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
          className={clsx(
            'relative -mb-px flex shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-[13px] font-medium transition-colors',
            value === t.value ? 'border-brand text-ink' : 'border-transparent text-muted hover:text-ink',
          )}
        >
          {t.icon && <t.icon className="h-4 w-4" />}
          {t.label}
          {t.count !== undefined && t.count !== null && (
            <span className={clsx('num rounded-full px-1.5 text-2xs font-semibold', value === t.value ? 'bg-brand-soft text-brand-ink' : 'bg-surface-2 text-muted')}>{t.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}

export function Toolbar({ children, className }) {
  return <div className={clsx('flex flex-col gap-2 border-b border-line p-3 sm:flex-row sm:flex-wrap sm:items-center', className)}>{children}</div>
}

export function Section({ title, description, children, action }) {
  return (
    <section className="grid gap-4 py-6 first:pt-0 last:pb-0 lg:grid-cols-[260px_1fr] lg:gap-10">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        {description && <p className="mt-1 text-[13px] text-muted">{description}</p>}
        {action && <div className="mt-3">{action}</div>}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  )
}
