import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { AlertCircle, Inbox, Loader2, RefreshCw } from 'lucide-react'
import { fileObjectUrl } from '../../api/client'
import { initials, titleCase } from '../../lib/format'
import { Button } from './Button'

export function Card({ className, children, padded = true, ...rest }) {
  return <div className={clsx('card', padded && 'p-5', className)} {...rest}>{children}</div>
}

export function CardHeader({ title, subtitle, action, className, icon: Icon }) {
  return (
    <div className={clsx('mb-4 flex items-start justify-between gap-3', className)}>
      <div className="flex min-w-0 items-center gap-2.5">
        {Icon && <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-soft text-brand-ink"><Icon className="h-4 w-4" /></span>}
        <div className="min-w-0">
          <h3 className="truncate text-[15px] font-semibold">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

const TONES = {
  neutral: 'bg-surface-2 text-ink-2 border-line',
  brand: 'bg-brand-soft text-brand-ink border-transparent',
  success: 'bg-success-soft text-success border-transparent',
  warning: 'bg-warning-soft text-warning border-transparent',
  danger: 'bg-danger-soft text-danger border-transparent',
  info: 'bg-info-soft text-info border-transparent',
}

export function Badge({ tone = 'neutral', children, className, dot }) {
  return (
    <span className={clsx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium', TONES[tone], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}

const STATUS_TONES = {
  active: 'success', present: 'success', approved: 'success', completed: 'success', done: 'success', paid: 'success',
  accepted: 'success', hired: 'success', reimbursed: 'success', finalized: 'brand', working: 'success', delivered: 'success',
  connected: 'success', open: 'brand', in_progress: 'brand', scheduled: 'brand', sent: 'brand', interview: 'brand',
  review: 'info', screening: 'info', planning: 'info', submitted: 'info', offered: 'info', applied: 'neutral',
  pending: 'warning', pending_approval: 'warning', late: 'warning', half_day: 'warning', on_hold: 'warning',
  on_notice: 'warning', on_break: 'warning', draft: 'neutral', todo: 'neutral', unpaid: 'warning', lead: 'info',
  rejected: 'danger', absent: 'danger', cancelled: 'neutral', declined: 'danger', blocked: 'danger', inactive: 'neutral',
  error: 'danger', overdue: 'danger', withdrawn: 'neutral', closed: 'neutral', on_leave: 'info', not_checked_in: 'neutral',
  checked_out: 'neutral', expired: 'neutral', terminated: 'danger', urgent: 'danger', high: 'warning', medium: 'info',
  low: 'neutral', no_show: 'danger', disconnected: 'neutral',
}

export function StatusBadge({ status, label, className }) {
  if (!status) return null
  return <Badge tone={STATUS_TONES[status] || 'neutral'} dot className={className}>{label || titleCase(status)}</Badge>
}

const AVATAR_SIZES = { xs: 'h-6 w-6 text-[10px]', sm: 'h-8 w-8 text-xs', md: 'h-10 w-10 text-sm', lg: 'h-14 w-14 text-lg', xl: 'h-20 w-20 text-2xl' }
const AVATAR_BG = ['bg-[#E0F7F2] text-[#06766C]', 'bg-[#E1F0F5] text-[#0F6C78]', 'bg-[#ECEFF3] text-[#2C3840]', 'bg-[#FDF3DC] text-[#8A5A02]', 'bg-[#EEE9FB] text-[#5B45A8]']

export function Avatar({ name = '', fileId, size = 'md', className }) {
  const [src, setSrc] = useState(null)
  useEffect(() => {
    let alive = true
    setSrc(null)
    if (fileId) fileObjectUrl(fileId).then((u) => alive && setSrc(u)).catch(() => {})
    return () => { alive = false }
  }, [fileId])
  const tone = AVATAR_BG[(name.charCodeAt(0) || 0) % AVATAR_BG.length]
  return (
    <span className={clsx('inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-semibold ring-2 ring-surface', AVATAR_SIZES[size], !src && tone, className)}>
      {src ? <img src={src} alt={name} className="h-full w-full object-cover" /> : initials(name) || '?'}
    </span>
  )
}

export function PersonCell({ name, subtitle, fileId, size = 'sm', to, onClick }) {
  const body = (
    <span className="flex min-w-0 items-center gap-2.5">
      <Avatar name={name} fileId={fileId} size={size} />
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium text-ink">{name}</span>
        {subtitle && <span className="block truncate text-xs text-muted">{subtitle}</span>}
      </span>
    </span>
  )
  if (onClick) return <button onClick={onClick} className="min-w-0 text-left hover:opacity-80">{body}</button>
  return body
}

export function Skeleton({ className }) {
  return <div className={clsx('skeleton', className)} />
}

export function Spinner({ className, label }) {
  return (
    <div className={clsx('flex items-center justify-center gap-2 py-10 text-sm text-muted', className)}>
      <Loader2 className="h-5 w-5 animate-spin text-brand" />
      {label}
    </div>
  )
}

export function EmptyState({ icon: Icon = Inbox, title, description, action, className, compact }) {
  return (
    <div className={clsx('flex flex-col items-center justify-center text-center', compact ? 'py-8' : 'py-14', className)}>
      <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-surface-2 text-faint">
        <Icon className="h-5 w-5" />
      </span>
      <p className="text-sm font-semibold text-ink">{title}</p>
      {description && <p className="mt-1 max-w-sm text-[13px] text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry, className }) {
  return (
    <div className={clsx('flex flex-col items-center justify-center py-12 text-center', className)}>
      <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-danger-soft text-danger"><AlertCircle className="h-5 w-5" /></span>
      <p className="text-sm font-semibold">Couldn’t load this data</p>
      <p className="mt-1 max-w-sm text-[13px] text-muted">{message}</p>
      {onRetry && <Button variant="secondary" size="sm" icon={RefreshCw} className="mt-4" onClick={() => onRetry()}>Try again</Button>}
    </div>
  )
}

export function Progress({ value = 0, tone = 'brand', className, showLabel }) {
  const v = Math.max(0, Math.min(100, Number(value) || 0))
  const bar = { brand: 'bg-brand', success: 'bg-success', warning: 'bg-warning', danger: 'bg-danger' }[tone]
  return (
    <div className={clsx('flex items-center gap-2', className)}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
        <div className={clsx('h-full rounded-full transition-[width] duration-500', bar)} style={{ width: `${v}%` }} />
      </div>
      {showLabel && <span className="num w-9 text-right text-xs font-medium text-ink-2">{Math.round(v)}%</span>}
    </div>
  )
}

export function StatCard({ label, value, hint, icon: Icon, tone = 'brand', loading, onClick }) {
  const iconTone = { brand: 'bg-brand-soft text-brand-ink', success: 'bg-success-soft text-success', warning: 'bg-warning-soft text-warning', danger: 'bg-danger-soft text-danger', info: 'bg-info-soft text-info', neutral: 'bg-surface-2 text-ink-2' }[tone]
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag onClick={onClick} className={clsx('card flex flex-col p-4 text-left', onClick && 'transition-colors hover:border-line-strong')}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-medium text-muted">{label}</span>
        {Icon && <span className={clsx('flex h-8 w-8 items-center justify-center rounded-lg', iconTone)}><Icon className="h-4 w-4" /></span>}
      </div>
      {loading ? <Skeleton className="mt-3 h-7 w-20" /> : <span className="num mt-2 text-[26px] font-semibold leading-tight tracking-tight">{value ?? '—'}</span>}
      {hint && <span className="mt-1 text-xs text-muted">{hint}</span>}
    </Tag>
  )
}

export function DescriptionList({ items, cols = 2 }) {
  return (
    <dl className={clsx('grid gap-x-6 gap-y-4', cols === 3 ? 'sm:grid-cols-3' : cols === 1 ? '' : 'sm:grid-cols-2')}>
      {items.filter(Boolean).map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-xs font-medium text-muted">{k}</dt>
          <dd className="mt-0.5 break-words text-sm text-ink">{v === null || v === undefined || v === '' ? '—' : v}</dd>
        </div>
      ))}
    </dl>
  )
}
