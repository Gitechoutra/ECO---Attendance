import { useState } from 'react'
import clsx from 'clsx'
import { CalendarClock } from 'lucide-react'
import { Avatar, Badge } from '../../components/ui'
import { fmtDate } from '../../lib/format'
import { STATUSES } from './TaskDrawer'

const PRI = { urgent: 'bg-danger', high: 'bg-warning', medium: 'bg-info', low: 'bg-line-strong' }

/** Kanban board with drag-and-drop between columns (desktop) and tap-to-open (mobile). */
export default function TaskBoard({ tasks, onOpen, onMove, canMove = () => true }) {
  const [drag, setDrag] = useState(null)
  const [over, setOver] = useState(null)
  return (
    <div className="scrollbar-thin -mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0">
      {STATUSES.map((col) => {
        const items = tasks.filter((t) => t.status === col.value)
        return (
          <div key={col.value}
            onDragOver={(e) => { if (drag) { e.preventDefault(); setOver(col.value) } }}
            onDragLeave={() => setOver(null)}
            onDrop={() => { if (drag && drag.status !== col.value) onMove(drag, col.value); setDrag(null); setOver(null) }}
            className={clsx('flex w-[280px] shrink-0 snap-start flex-col rounded-xl border bg-surface-2/70 transition-colors', over === col.value ? 'border-brand bg-brand-soft/40' : 'border-line')}>
            <div className="flex items-center justify-between px-3 py-2.5">
              <span className="text-[13px] font-semibold">{col.label}</span>
              <span className="num rounded-full bg-surface px-2 text-xs text-muted">{items.length}</span>
            </div>
            <div className="flex min-h-[120px] flex-1 flex-col gap-2 px-2 pb-2">
              {items.map((t) => (
                <button key={t.id} draggable={canMove(t)} onDragStart={() => setDrag(t)} onDragEnd={() => setDrag(null)} onClick={() => onOpen(t)}
                  className={clsx('rounded-lg border border-line bg-surface p-3 text-left shadow-card transition-shadow hover:border-line-strong hover:shadow-pop', drag?.id === t.id && 'opacity-50')}>
                  <div className="flex items-start gap-2">
                    <span className={clsx('mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full', PRI[t.priority])} title={`${t.priority} priority`} />
                    <p className="line-clamp-2 text-[13px] font-medium text-ink">{t.title}</p>
                  </div>
                  {t.project && <p className="mt-1.5 truncate pl-3.5 text-2xs text-muted">{t.project.code}</p>}
                  <div className="mt-2.5 flex items-center justify-between pl-3.5">
                    {t.due_date ? (
                      <span className={clsx('flex items-center gap-1 text-2xs', t.is_overdue ? 'font-semibold text-danger' : 'text-muted')}><CalendarClock className="h-3 w-3" />{fmtDate(t.due_date, 'dd MMM')}</span>
                    ) : <span />}
                    {t.assignee ? <Avatar name={t.assignee.full_name} fileId={t.assignee.photo_file_id} size="xs" /> : <Badge className="text-2xs">Unassigned</Badge>}
                  </div>
                  {t.progress > 0 && t.status !== 'done' && <div className="mt-2 ml-3.5 h-1 overflow-hidden rounded-full bg-line"><div className="h-full rounded-full bg-brand" style={{ width: `${t.progress}%` }} /></div>}
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
