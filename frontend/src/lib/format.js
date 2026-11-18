import { format, formatDistanceToNowStrict, isValid, parseISO } from 'date-fns'

const toDate = (v) => {
  if (!v) return null
  if (v instanceof Date) return v
  // API datetimes are naive UTC unless suffixed
  const s = typeof v === 'string' && /T\d{2}:\d{2}/.test(v) && !/[zZ]|[+-]\d{2}:\d{2}$/.test(v) ? `${v}Z` : v
  const d = typeof s === 'string' ? parseISO(s) : new Date(s)
  return isValid(d) ? d : null
}

export const fmtDate = (v, f = 'dd MMM yyyy') => { const d = toDate(v); return d ? format(d, f) : '—' }
export const fmtDateTime = (v) => fmtDate(v, 'dd MMM yyyy, h:mm a')
export const fmtTime = (v) => fmtDate(v, 'h:mm a')
export const fromNow = (v) => { const d = toDate(v); return d ? `${formatDistanceToNowStrict(d)} ago` : '—' }
export const isoDate = (d = new Date()) => format(d, 'yyyy-MM-dd')

export const fmtMoney = (v, currency = 'INR') => {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: n % 1 ? 2 : 0 }).format(n)
}
export const fmtNumber = (v, digits = 0) =>
  v === null || v === undefined ? '—' : new Intl.NumberFormat('en-IN', { maximumFractionDigits: digits }).format(v)

export const fmtMinutes = (m) => {
  if (!m) return '0h'
  const h = Math.floor(m / 60)
  const mm = m % 60
  return h ? `${h}h${mm ? ` ${mm}m` : ''}` : `${mm}m`
}

export const fmtBytes = (b) => {
  if (!b) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(b) / Math.log(1024)), 3)
  return `${(b / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`
}

export const titleCase = (s) => (s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
export const initials = (name = '') => name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase()

export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December']

export const fmtCompactMoney = (v, currency = 'INR') =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency, notation: 'compact', maximumFractionDigits: 1 }).format(Number(v) || 0)
