import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { Cake, CalendarDays, MapPin, Megaphone, Pencil, Pin, Plus, PartyPopper, Trash2, Video, X } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions } from '../../hooks/useOptions'
import {
  Avatar, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, FormModal, IconButton, Input, PageHeader, Segmented,
  Skeleton, Tabs,
} from '../../components/ui'
import { fmtDate, fmtTime, fromNow, titleCase } from '../../lib/format'

const CAT_TONE = { urgent: 'danger', policy: 'info', event: 'brand', update: 'neutral', general: 'neutral' }

function Announcements() {
  const { can } = useAuth()
  const toast = useToast()
  const depts = useOptions('departments')
  const { data, loading, error, reload } = useApi('/announcements', { page_size: 50 })
  const [form, setForm] = useState(null)
  const [del, setDel] = useState(null)
  const [run, busy] = useAction(toast)
  if (error) return <ErrorState message={error} onRetry={reload} />
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      {can('announcements.manage') && <div className="flex justify-end"><Button icon={Plus} onClick={() => setForm({})}>New announcement</Button></div>}
      {loading && !data ? <Skeleton className="h-40" /> : !data?.items.length ? <Card><EmptyState icon={Megaphone} title="No announcements yet" /></Card> : data.items.map((a) => (
        <Card key={a.id} className={clsx(a.is_pinned && 'border-brand/40')}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {a.is_pinned && <Badge tone="brand"><Pin className="h-3 w-3" />Pinned</Badge>}
              <Badge tone={CAT_TONE[a.category]}>{titleCase(a.category)}</Badge>
              {a.audience !== 'all' && <Badge>{a.audience === 'department' ? a.department : titleCase(a.role_code)}</Badge>}
            </div>
            {can('announcements.manage') && <div className="flex gap-1"><IconButton icon={Pencil} size="sm" label="Edit" onClick={() => setForm({ ...a, expires_at: a.expires_at?.slice(0, 16) })} /><IconButton icon={Trash2} size="sm" variant="danger" label="Delete" onClick={() => setDel(a)} /></div>}
          </div>
          <h3 className="mt-3 text-base font-semibold">{a.title}</h3>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink-2">{a.body}</p>
          <p className="mt-4 text-xs text-muted">{a.author} · {fromNow(a.published_at)}{a.expires_at && ` · until ${fmtDate(a.expires_at)}`}</p>
        </Card>
      ))}
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={form?.id ? 'Edit announcement' : 'New announcement'} size="lg" initial={form} submitLabel={form?.id ? 'Save' : 'Publish'}
        description={form?.id ? undefined : 'Recipients are notified immediately.'}
        fields={[{ name: 'title', label: 'Title', required: true }, { name: 'body', label: 'Message', type: 'textarea', rows: 6, required: true },
          { name: 'category', label: 'Category', type: 'select', default: 'general', span: 1, options: ['general', 'update', 'policy', 'event', 'urgent'].map((v) => ({ value: v, label: titleCase(v) })) },
          { name: 'audience', label: 'Audience', type: 'select', default: 'all', span: 1, options: [{ value: 'all', label: 'Everyone' }, { value: 'department', label: 'A department' }, { value: 'role', label: 'A role' }] },
          { name: 'department_id', label: 'Department', type: 'select', numeric: true, options: depts, hidden: (v) => v.audience !== 'department' },
          { name: 'role_code', label: 'Role', type: 'select', options: [{ value: 'employee', label: 'Employees' }, { value: 'project_manager', label: 'Project managers' }, { value: 'hr_admin', label: 'HR / Admin' }, { value: 'super_admin', label: 'Leadership' }], hidden: (v) => v.audience !== 'role' },
          { name: 'expires_at', label: 'Hide after', type: 'datetime-local', span: 1 }, { name: 'is_pinned', label: 'Pin to top', type: 'checkbox' }]}
        onSubmit={async (v) => { const body = { ...v, expires_at: v.expires_at ? new Date(v.expires_at).toISOString() : null }; form.id ? await api.put(`/announcements/${form.id}`, body) : await api.post('/announcements', body); toast.success(form.id ? 'Saved' : 'Announcement published'); reload() }} />
      <ConfirmDialog open={Boolean(del)} onClose={() => setDel(null)} title="Delete announcement" description={`Delete “${del?.title}”?`} confirmLabel="Delete" loading={busy}
        onConfirm={async () => { await run(() => api.delete(`/announcements/${del.id}`), { success: 'Deleted' }); setDel(null); reload() }} />
    </div>
  )
}

function Meetings() {
  const { can, employee } = useAuth()
  const toast = useToast()
  const emps = useOptions('employees')
  const projects = useOptions('projects')
  const [scope, setScope] = useState('mine')
  const { data, loading, error, reload } = useApi('/meetings', { scope })
  const [form, setForm] = useState(null)
  const [cancel, setCancel] = useState(null)
  const [run, busy] = useAction(toast)
  if (error) return <ErrorState message={error} onRetry={reload} />
  const toLocal = (iso) => { const d = new Date(`${iso}Z`); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {can('meetings.manage') ? <Segmented value={scope} onChange={setScope} options={[{ value: 'mine', label: 'My meetings' }, { value: 'all', label: 'All meetings' }]} /> : <span />}
        <Button icon={Plus} onClick={() => setForm({})} disabled={!employee}>Schedule meeting</Button>
      </div>
      {loading && !data ? <Skeleton className="h-40" /> : !data?.length ? <Card><EmptyState icon={CalendarDays} title="No upcoming meetings" /></Card> : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.map((m) => {
            const past = new Date(`${m.end_at}Z`) < new Date()
            return (
              <Card key={m.id} className={clsx(past && 'opacity-70')}>
                <div className="flex items-start gap-4">
                  <div className="flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-xl bg-brand-soft text-brand-ink">
                    <span className="text-2xs font-semibold uppercase">{fmtDate(m.start_at, 'MMM')}</span>
                    <span className="num text-xl font-bold leading-none">{fmtDate(m.start_at, 'd')}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{m.title}</p>
                    <p className="text-xs text-muted">{fmtTime(m.start_at)} – {fmtTime(m.end_at)} · {m.organizer?.full_name}</p>
                    {m.location && <p className="mt-1 flex items-center gap-1 text-xs text-muted"><MapPin className="h-3 w-3" />{m.location}</p>}
                    {m.description && <p className="mt-2 line-clamp-2 text-[13px] text-ink-2">{m.description}</p>}
                    <div className="mt-3 flex -space-x-1.5">{m.attendees.slice(0, 8).map((a) => <Avatar key={a.employee.id} name={a.employee.full_name} fileId={a.employee.photo_file_id} size="xs" />)}{m.attendees.length > 8 && <span className="ml-2 text-xs text-muted">+{m.attendees.length - 8}</span>}</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {m.meeting_link && <a href={m.meeting_link} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-brand px-3 text-xs font-semibold text-[#03211D]"><Video className="h-3.5 w-3.5" />Join</a>}
                      {m.my_response && m.organizer_id !== employee?.id && !past && (
                        <Segmented size="sm" value={m.my_response} onChange={async (v) => { await run(() => api.post(`/meetings/${m.id}/rsvp`, { response: v })); reload() }}
                          options={[{ value: 'accepted', label: 'Going' }, { value: 'declined', label: 'Not going' }]} />
                      )}
                      {(m.organizer_id === employee?.id || can('meetings.manage')) && !past && <>
                        <Button size="xs" variant="ghost" icon={Pencil} onClick={() => setForm({ ...m, start_at: toLocal(m.start_at), end_at: toLocal(m.end_at), attendee_ids: m.attendees.map((a) => a.employee.id) })}>Edit</Button>
                        <Button size="xs" variant="danger-ghost" icon={X} onClick={() => setCancel(m)}>Cancel</Button>
                      </>}
                    </div>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={form?.id ? 'Edit meeting' : 'Schedule meeting'} size="lg" initial={form}
        fields={[{ name: 'title', label: 'Title', required: true },
          { name: 'start_at', label: 'Starts', type: 'datetime-local', required: true, span: 1 },
          { name: 'end_at', label: 'Ends', type: 'datetime-local', required: true, span: 1, validate: (v, a) => v <= a.start_at ? 'Must be after start' : null },
          { name: 'location', label: 'Location', span: 1 }, { name: 'meeting_link', label: 'Video link', placeholder: 'https://meet…', span: 1, validate: (v) => v && !/^https?:\/\//.test(v) ? 'Must start with https://' : null },
          { name: 'project_id', label: 'Project', type: 'select', numeric: true, options: projects, placeholder: 'Company meeting' },
          { name: 'attendee_ids', label: 'Attendees', type: 'multiselect', options: emps.filter((e) => e.value !== employee?.id).map((e) => ({ value: e.value, label: e.name })) },
          { name: 'description', label: 'Agenda', type: 'textarea' }]}
        onSubmit={async (v) => {
          const body = { ...v, start_at: new Date(v.start_at).toISOString(), end_at: new Date(v.end_at).toISOString(), attendee_ids: v.attendee_ids || [] }
          form.id ? await api.put(`/meetings/${form.id}`, body) : await api.post('/meetings', body)
          toast.success('Meeting saved'); reload()
        }} />
      <ConfirmDialog open={Boolean(cancel)} onClose={() => setCancel(null)} title="Cancel meeting" description={`Cancel “${cancel?.title}”? Attendees are notified.`} confirmLabel="Cancel meeting" loading={busy}
        onConfirm={async () => { await run(() => api.post(`/meetings/${cancel.id}/cancel`), { success: 'Meeting cancelled' }); setCancel(null); reload() }} />
    </div>
  )
}

const EV = { holiday: ['bg-brand-soft text-brand-ink', CalendarDays], birthday: ['bg-warning-soft text-warning', Cake], anniversary: ['bg-info-soft text-info', PartyPopper], meeting: ['bg-surface-2 text-ink-2', Video], leave: ['bg-surface-2 text-muted', CalendarDays] }

function CalendarTab() {
  const n = new Date()
  const [ym, setYm] = useState(`${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}`)
  const [y, m] = ym.split('-').map(Number)
  const { data, loading } = useApi('/calendar/events', { date_from: `${ym}-01`, date_to: `${ym}-${new Date(y, m, 0).getDate()}` })
  const byDay = {}
  ;(data || []).forEach((e) => { const k = String(e.date).slice(0, 10); (byDay[k] ||= []).push(e) })
  return (
    <Card>
      <div className="mb-4 flex items-center justify-between"><h3 className="text-[15px] font-semibold">Company calendar</h3><Input type="month" value={ym} onChange={(e) => setYm(e.target.value)} className="h-9 w-40" /></div>
      {loading ? <Skeleton className="h-48" /> : !Object.keys(byDay).length ? <EmptyState compact title="Nothing scheduled this month" /> : (
        <div className="space-y-4">
          {Object.entries(byDay).map(([d, evs]) => (
            <div key={d} className="grid grid-cols-[64px_1fr] gap-3">
              <div className="text-right"><p className="num text-lg font-semibold leading-tight">{fmtDate(d, 'd')}</p><p className="text-2xs uppercase text-muted">{fmtDate(d, 'EEE')}</p></div>
              <div className="space-y-1.5 border-l border-line pl-3">
                {evs.map((e, i) => {
                  const [tone, I] = EV[e.type]
                  return <div key={i} className={clsx('flex items-center gap-2 rounded-lg px-3 py-2 text-[13px]', tone)}><I className="h-3.5 w-3.5 shrink-0" /><span className="font-medium">{e.title}</span>{e.start_at && <span className="ml-auto text-xs opacity-80">{fmtTime(e.start_at)}</span>}</div>
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function Celebrations() {
  const { data, loading } = useApi('/celebrations', { days: 45 })
  if (loading) return <Skeleton className="h-40" />
  if (!data?.length) return <Card><EmptyState icon={PartyPopper} title="No celebrations in the next 45 days" description="Birthdays appear once employees add their date of birth." /></Card>
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {data.map((c, i) => (
        <Card key={i} className="flex items-center gap-4">
          <Avatar name={c.employee.full_name} fileId={c.employee.photo_file_id} size="lg" />
          <div className="min-w-0">
            <p className="truncate font-semibold">{c.employee.full_name}</p>
            <p className="flex items-center gap-1.5 text-[13px] text-muted">{c.type === 'birthday' ? <Cake className="h-3.5 w-3.5 text-warning" /> : <PartyPopper className="h-3.5 w-3.5 text-info" />}
              {c.type === 'birthday' ? 'Birthday' : `${c.years} year work anniversary`}</p>
            <p className="text-xs font-medium text-brand-ink">{c.in_days === 0 ? 'Today 🎉' : c.in_days === 1 ? 'Tomorrow' : `${fmtDate(c.date, 'EEE, dd MMM')} · in ${c.in_days} days`}</p>
          </div>
        </Card>
      ))}
    </div>
  )
}

export default function CommunicationPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'announcements'
  return (
    <>
      <PageHeader title="Communication" description="Announcements, meetings, the company calendar and celebrations." />
      <Tabs className="mb-5" value={tab} onChange={(t) => setParams({ tab: t })} tabs={[
        { value: 'announcements', label: 'Announcements' }, { value: 'meetings', label: 'Meetings' }, { value: 'calendar', label: 'Calendar' }, { value: 'celebrations', label: 'Celebrations' }]} />
      {tab === 'announcements' && <Announcements />}
      {tab === 'meetings' && <Meetings />}
      {tab === 'calendar' && <CalendarTab />}
      {tab === 'celebrations' && <Celebrations />}
    </>
  )
}
