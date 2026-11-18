import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createPortal } from 'react-dom'
import { Briefcase, FolderKanban, Loader2, Search, User, CheckSquare } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../api/client'
import { useDebounced } from '../../hooks/useApi'

const ICONS = { employee: User, project: FolderKanban, client: Briefcase, task: CheckSquare }

export function GlobalSearch({ open, onClose }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [active, setActive] = useState(0)
  const dq = useDebounced(q, 250)
  const nav = useNavigate()

  useEffect(() => { if (open) { setQ(''); setResults([]) } }, [open])
  useEffect(() => {
    if (!open || dq.trim().length < 2) { setResults([]); return }
    setLoading(true)
    api.get('/search', { params: { q: dq } })
      .then((r) => { setResults(r.data); setActive(0) })
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [dq, open])

  if (!open) return null
  const go = (r) => { onClose(); nav(r.link) }
  const onKey = (e) => {
    if (e.key === 'Escape') onClose()
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    if (e.key === 'Enter' && results[active]) go(results[active])
  }
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-start justify-center px-4 pt-[12vh]" role="dialog" aria-modal="true" aria-label="Search">
      <div className="absolute inset-0 animate-fade-in bg-night/50 backdrop-blur-[2px]" onClick={onClose} />
      <div className="relative w-full max-w-xl animate-scale-in overflow-hidden rounded-2xl border border-line bg-surface shadow-pop">
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search className="h-5 w-5 text-faint" />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} placeholder="Search employees, projects, clients, tasks…" className="h-14 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-faint" />
          {loading && <Loader2 className="h-4 w-4 animate-spin text-brand" />}
        </div>
        <div className="scrollbar-thin max-h-[50vh] overflow-y-auto p-2">
          {dq.trim().length < 2 && <p className="px-3 py-8 text-center text-sm text-muted">Type at least two characters to search.</p>}
          {dq.trim().length >= 2 && !loading && results.length === 0 && <p className="px-3 py-8 text-center text-sm text-muted">No matches for “{dq}”.</p>}
          {results.map((r, i) => {
            const Icon = ICONS[r.type] || Search
            return (
              <button key={`${r.type}-${r.id}`} onMouseEnter={() => setActive(i)} onClick={() => go(r)} className={clsx('flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left', i === active && 'bg-surface-2')}>
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-soft text-brand-ink"><Icon className="h-4 w-4" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{r.title}</span>
                  {r.subtitle && <span className="block truncate text-xs text-muted">{r.subtitle}</span>}
                </span>
                <span className="text-2xs font-medium uppercase tracking-wide text-faint">{r.type}</span>
              </button>
            )
          })}
        </div>
      </div>
    </div>,
    document.body,
  )
}
