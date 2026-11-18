import { useState } from 'react'
import { MessageSquare, Pencil, Send, Trash2 } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useToast } from '../../context/ToastContext'
import {
  Avatar, Badge, Button, ConfirmDialog, DescriptionList, Drawer, ErrorState, FormModal, IconButton, Progress, Select,
  Skeleton, StatusBadge, Tabs, Textarea,
} from '../../components/ui'
import { fmtDate, fmtDateTime, fromNow, isoDate, titleCase } from '../../lib/format'

export const STATUSES = [
  { value: 'todo', label: 'To do' }, { value: 'in_progress', label: 'In progress' }, { value: 'review', label: 'In review' },
  { value: 'blocked', label: 'Blocked' }, { value: 'done', label: 'Done' },
]
export const PRIORITIES = ['low', 'medium', 'high', 'urgent'].map((p) => ({ value: p, label: titleCase(p) }))

export function taskFields({ projects, members, milestones, projectFixed }) {
  return [
    { name: 'title', label: 'Title', required: true },
    { name: 'description', label: 'Description', type: 'textarea', rows: 4 },
    ...(projectFixed ? [] : [{ name: 'project_id', label: 'Project', type: 'select', numeric: true, options: projects, placeholder: 'Personal task (no project)' }]),
    { name: 'assignee_id', label: 'Assignee', type: 'select', numeric: true, options: members, placeholder: 'Unassigned', span: 1 },
    { name: 'priority', label: 'Priority', type: 'select', options: PRIORITIES, default: 'medium', span: 1 },
    { name: 'status', label: 'Status', type: 'select', options: STATUSES, default: 'todo', span: 1 },
    { name: 'due_date', label: 'Due date', type: 'date', span: 1 },
    ...(milestones?.length ? [{ name: 'milestone_id', label: 'Milestone', type: 'select', numeric: true, options: milestones, placeholder: 'None', span: 1 }] : []),
    { name: 'estimated_hours', label: 'Estimate (hours)', type: 'number', min: 0, step: 0.5, span: 1 },
  ]
}

export default function TaskDrawer({ taskId, onClose, onChanged, memberOptions }) {
  const toast = useToast()
  const { data: t, loading, error, reload } = useApi(taskId ? `/tasks/${taskId}` : null)
  const [tab, setTab] = useState('activity')
  const [comment, setComment] = useState('')
  const [edit, setEdit] = useState(false)
  const [upd, setUpd] = useState(false)
  const [del, setDel] = useState(false)
  const [run, busy] = useAction(toast)
  const changed = () => { reload(); onChanged?.() }

  return (
    <Drawer open={Boolean(taskId)} onClose={onClose} width="max-w-2xl"
      title={t?.title || 'Task'}
      subtitle={t && <span>{t.project ? `${t.project.code} · ${t.project.name}` : 'Personal task'}</span>}
      actions={t?.can_edit && <><IconButton icon={Pencil} label="Edit task" size="sm" onClick={() => setEdit(true)} /><IconButton icon={Trash2} label="Delete task" size="sm" variant="danger" onClick={() => setDel(true)} /></>}>
      {error ? <ErrorState message={error} onRetry={reload} /> : loading || !t ? <div className="space-y-3"><Skeleton className="h-6 w-1/2" /><Skeleton className="h-32" /></div> : (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={t.status} label={STATUSES.find((s) => s.value === t.status)?.label} />
            <StatusBadge status={t.priority} label={`${titleCase(t.priority)} priority`} />
            {t.is_overdue && <Badge tone="danger" dot>Overdue</Badge>}
          </div>
          {t.description && <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-2">{t.description}</p>}
          <DescriptionList items={[
            ['Assignee', t.assignee?.full_name || 'Unassigned'], ['Reporter', t.reporter?.full_name],
            ['Due date', t.due_date ? fmtDate(t.due_date) : 'No due date'], ['Estimate', t.estimated_hours ? `${t.estimated_hours} h` : '—'],
            ['Created', fmtDateTime(t.created_at)], ['Completed', t.completed_at ? fmtDateTime(t.completed_at) : '—'],
          ]} />
          <div>
            <div className="mb-1.5 flex justify-between text-xs text-muted"><span>Progress</span></div>
            <Progress value={t.progress} showLabel />
          </div>
          {t.can_update_status && (
            <div className="flex flex-wrap items-end gap-2 rounded-xl border border-line bg-surface-2 p-3">
              <div className="min-w-[160px] flex-1">
                <label className="label">Status</label>
                <Select value={t.status} disabled={busy} options={STATUSES}
                  onChange={async (e) => { await run(() => api.patch(`/tasks/${t.id}/status`, { status: e.target.value }), { success: 'Status updated' }); changed() }} />
              </div>
              <Button variant="secondary" onClick={() => setUpd(true)}>Post daily update</Button>
            </div>
          )}
          <div>
            <Tabs value={tab} onChange={setTab} tabs={[
              { value: 'activity', label: 'Comments', count: t.comments.length }, { value: 'updates', label: 'Daily updates', count: t.updates.length },
              { value: 'history', label: 'History' }]} />
            <div className="pt-4">
              {tab === 'activity' && (
                <div className="space-y-4">
                  {t.comments.length === 0 && <p className="flex items-center gap-2 text-sm text-muted"><MessageSquare className="h-4 w-4" />No comments yet.</p>}
                  {t.comments.map((c) => (
                    <div key={c.id} className="flex gap-3">
                      <Avatar name={c.author?.name || c.author?.email || '?'} fileId={c.author?.photo_file_id} size="sm" />
                      <div className="min-w-0 flex-1 rounded-xl bg-surface-2 px-3.5 py-2.5">
                        <p className="text-xs"><span className="font-semibold text-ink">{c.author?.name || c.author?.email}</span> <span className="text-faint">· {fromNow(c.created_at)}</span></p>
                        <p className="mt-1 whitespace-pre-wrap text-sm text-ink-2">{c.body}</p>
                      </div>
                    </div>
                  ))}
                  <form className="flex items-end gap-2" onSubmit={async (e) => { e.preventDefault(); if (!comment.trim()) return; await run(() => api.post(`/tasks/${t.id}/comments`, { body: comment })); setComment(''); reload() }}>
                    <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} placeholder="Write a comment…" className="flex-1" />
                    <Button type="submit" icon={Send} disabled={!comment.trim()} loading={busy} aria-label="Send comment" />
                  </form>
                </div>
              )}
              {tab === 'updates' && (
                <ul className="space-y-3">
                  {t.updates.length === 0 && <p className="text-sm text-muted">No daily updates yet.</p>}
                  {t.updates.map((u) => (
                    <li key={u.id} className="rounded-xl border border-line p-3.5">
                      <div className="flex items-center justify-between text-xs text-muted"><span><b className="text-ink">{u.employee.full_name}</b> · {fmtDate(u.update_date)}</span><span className="num">{u.progress}% · {u.hours_spent} h</span></div>
                      <p className="mt-1.5 whitespace-pre-wrap text-sm text-ink-2">{u.note}</p>
                    </li>
                  ))}
                </ul>
              )}
              {tab === 'history' && (
                <ul className="space-y-2 text-[13px]">
                  {t.history.map((h, i) => (
                    <li key={i} className="flex gap-2 text-ink-2"><span className="text-faint">{fmtDateTime(h.created_at)}</span>
                      <span>{h.field === 'created' ? `Created by ${h.user}` : <>{titleCase(h.field)}: {h.old_value ?? '—'} → <b>{h.new_value ?? '—'}</b> <span className="text-faint">({h.user})</span></>}</span></li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
      {t && (
        <>
          <FormModal open={edit} onClose={() => setEdit(false)} title="Edit task" size="lg" initial={t}
            fields={taskFields({ members: memberOptions || (t.assignee ? [{ value: t.assignee.id, label: t.assignee.full_name }] : []), projectFixed: true })}
            onSubmit={async (v) => { await api.put(`/tasks/${t.id}`, { ...v, project_id: t.project_id, milestone_id: v.milestone_id ?? t.milestone_id }); toast.success('Task updated'); changed() }} />
          <FormModal open={upd} onClose={() => setUpd(false)} title="Daily progress update" submitLabel="Post update" initial={{ progress: t.progress, update_date: isoDate() }}
            fields={[
              { name: 'progress', label: 'Progress (%)', type: 'number', min: 0, max: 100, required: true, span: 1, validate: (v) => (v < 0 || v > 100 ? '0–100' : null) },
              { name: 'hours_spent', label: 'Hours spent today', type: 'number', min: 0, max: 24, step: 0.5, default: 0, span: 1 },
              { name: 'update_date', label: 'Date', type: 'date', max: isoDate() },
              { name: 'note', label: 'What did you do?', type: 'textarea', required: true },
            ]}
            onSubmit={async (v) => { await api.post(`/tasks/${t.id}/updates`, v); toast.success('Update posted'); changed() }} />
          <ConfirmDialog open={del} onClose={() => setDel(false)} title="Delete task" description={`Delete “${t.title}”? Comments and history are removed too.`} confirmLabel="Delete" loading={busy}
            onConfirm={async () => { await run(() => api.delete(`/tasks/${t.id}`), { success: 'Task deleted' }); setDel(false); onChanged?.(); onClose() }} />
        </>
      )}
    </Drawer>
  )
}
