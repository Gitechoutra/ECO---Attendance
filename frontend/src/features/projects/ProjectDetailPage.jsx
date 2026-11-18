import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Calendar, CheckCircle2, Flag, Pencil, Plus, Trash2, Upload, UserPlus } from 'lucide-react'
import { api, downloadFile } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useToast } from '../../context/ToastContext'
import { useOptions, invalidateOptions } from '../../hooks/useOptions'
import {
  Badge, BarList, Button, Card, CardHeader, ConfirmDialog, DataTable, DescriptionList, EmptyState, ErrorState, Field,
  FileDrop, FormModal, IconButton, Input, Modal, PageHeader, PersonCell, Progress, Skeleton, StatCard, StatusBadge, Tabs,
} from '../../components/ui'
import { fmtBytes, fmtDate, fmtMoney, titleCase } from '../../lib/format'
import TaskBoard from '../tasks/TaskBoard'
import TaskDrawer, { taskFields } from '../tasks/TaskDrawer'
import { projectFields } from './ProjectsPage'

function Milestones({ p }) {
  const toast = useToast()
  const { data, loading, reload } = useApi(`/projects/${p.id}/milestones`)
  const [form, setForm] = useState(null)
  const [del, setDel] = useState(null)
  const [run, busy] = useAction(toast)
  if (loading) return <Skeleton className="h-40" />
  return (
    <Card>
      <CardHeader title="Milestones" action={p.can_manage && <Button size="sm" icon={Plus} onClick={() => setForm({})}>Add milestone</Button>} />
      {!data?.length ? <EmptyState compact icon={Flag} title="No milestones" description="Break delivery into checkpoints." /> : (
        <ol className="relative space-y-4 border-l border-line pl-6">
          {data.map((m) => (
            <li key={m.id} className="relative">
              <span className={`absolute -left-[31px] top-0.5 flex h-5 w-5 items-center justify-center rounded-full border-2 border-surface ${m.status === 'completed' ? 'bg-success text-white' : m.is_overdue ? 'bg-danger' : 'bg-line-strong'}`}>
                {m.status === 'completed' && <CheckCircle2 className="h-3 w-3" />}
              </span>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold">{m.title}</p>
                  <p className="text-xs text-muted">Due {fmtDate(m.due_date)} · {m.task_done}/{m.task_total} tasks done</p>
                  {m.description && <p className="mt-1 text-[13px] text-ink-2">{m.description}</p>}
                </div>
                <div className="flex items-center gap-1">
                  {m.is_overdue ? <Badge tone="danger" dot>Overdue</Badge> : <StatusBadge status={m.status} />}
                  {p.can_manage && <><IconButton icon={Pencil} size="sm" label="Edit" onClick={() => setForm(m)} /><IconButton icon={Trash2} size="sm" variant="danger" label="Delete" onClick={() => setDel(m)} /></>}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={form?.id ? 'Edit milestone' : 'Add milestone'} initial={form}
        fields={[{ name: 'title', label: 'Title', required: true }, { name: 'due_date', label: 'Due date', type: 'date', span: 1 },
          { name: 'status', label: 'Status', type: 'select', span: 1, default: 'pending', options: ['pending', 'in_progress', 'completed'].map((s) => ({ value: s, label: titleCase(s) })) },
          { name: 'description', label: 'Description', type: 'textarea' }]}
        onSubmit={async (v) => { form.id ? await api.put(`/projects/${p.id}/milestones/${form.id}`, v) : await api.post(`/projects/${p.id}/milestones`, v); toast.success('Milestone saved'); reload() }} />
      <ConfirmDialog open={Boolean(del)} onClose={() => setDel(null)} title="Delete milestone" description={`Delete “${del?.title}”? Tasks stay in the project.`} loading={busy} confirmLabel="Delete"
        onConfirm={async () => { await run(() => api.delete(`/projects/${p.id}/milestones/${del.id}`), { success: 'Deleted' }); setDel(null); reload() }} />
    </Card>
  )
}

function Team({ p, reload }) {
  const toast = useToast()
  const emps = useOptions('employees')
  const [add, setAdd] = useState(false)
  const [rm, setRm] = useState(null)
  const [run, busy] = useAction(toast)
  const available = emps.filter((e) => !p.members.some((m) => m.employee.id === e.value))
  return (
    <Card padded={false}>
      <div className="flex items-center justify-between p-5 pb-3"><h3 className="text-[15px] font-semibold">Team ({p.members.length})</h3>{p.can_manage && <Button size="sm" icon={UserPlus} onClick={() => setAdd(true)}>Add member</Button>}</div>
      <DataTable rows={p.members} empty={<EmptyState compact title="No team members" />}
        columns={[
          { key: 'emp', header: 'Member', mobile: 'title', render: (m) => <PersonCell name={m.employee.full_name} subtitle={m.employee.designation} fileId={m.employee.photo_file_id} /> },
          { key: 'role', header: 'Project role', render: (m) => m.role || '—' },
          { key: 'alloc', header: 'Allocation', align: 'right', render: (m) => `${m.allocation_percent}%` },
          { key: 'a', header: '', align: 'right', render: (m) => p.can_manage && m.employee.id !== p.manager_id && <IconButton icon={Trash2} size="sm" variant="danger" label="Remove" onClick={() => setRm(m)} /> },
        ]} />
      <FormModal open={add} onClose={() => setAdd(false)} title="Add team member"
        fields={[{ name: 'employee_id', label: 'Employee', type: 'select', numeric: true, required: true, options: available },
          { name: 'role', label: 'Role on project', placeholder: 'e.g. Frontend developer', span: 1 },
          { name: 'allocation_percent', label: 'Allocation %', type: 'number', min: 1, max: 100, default: 100, span: 1 }]}
        onSubmit={async (v) => { await api.post(`/projects/${p.id}/members`, v); toast.success('Member added'); reload() }} />
      <ConfirmDialog open={Boolean(rm)} onClose={() => setRm(null)} title="Remove member" description={`Remove ${rm?.employee.full_name} from this project?`} loading={busy} confirmLabel="Remove"
        onConfirm={async () => { await run(() => api.delete(`/projects/${p.id}/members/${rm.id}`), { success: 'Member removed' }); setRm(null); reload() }} />
    </Card>
  )
}

function Files({ p }) {
  const toast = useToast()
  const { data, loading, error, reload } = useApi(`/projects/${p.id}/files`)
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState(null)
  const [desc, setDesc] = useState('')
  const [run, busy] = useAction(toast)
  return (
    <Card padded={false}>
      <div className="flex items-center justify-between p-5 pb-3"><h3 className="text-[15px] font-semibold">Project files</h3><Button size="sm" icon={Upload} onClick={() => setOpen(true)}>Upload</Button></div>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data} empty={<EmptyState compact title="No files yet" description="Share specs, designs and documents with the team." />}
        columns={[
          { key: 'name', header: 'File', mobile: 'title', render: (f) => <button className="link text-left" onClick={() => downloadFile(`/files/${f.id}`, { inline: false }, f.name)}>{f.name}</button> },
          { key: 'desc', header: 'Description', render: (f) => f.description || '—' },
          { key: 'size', header: 'Size', render: (f) => fmtBytes(f.size) },
          { key: 'by', header: 'Uploaded', render: (f) => `${fmtDate(f.created_at)} · ${f.uploaded_by || ''}` },
          { key: 'a', header: '', align: 'right', render: (f) => <IconButton icon={Trash2} size="sm" variant="danger" label="Delete" onClick={async () => { await run(() => api.delete(`/projects/${p.id}/files/${f.id}`), { success: 'File deleted' }); reload() }} /> },
        ]} />
      <Modal open={open} onClose={() => setOpen(false)} title="Upload file" footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button disabled={!file} loading={busy} onClick={async () => {
        const fd = new FormData(); fd.append('file', file); if (desc) fd.append('description', desc)
        await run(() => api.post(`/projects/${p.id}/files`, fd), { success: 'File uploaded' }); setOpen(false); setFile(null); setDesc(''); reload()
      }}>Upload</Button></>}>
        <div className="space-y-4"><FileDrop value={file} onChange={setFile} /><Field label="Description"><Input value={desc} onChange={(e) => setDesc(e.target.value)} /></Field></div>
      </Modal>
    </Card>
  )
}

function Report({ p }) {
  const { data, loading } = useApi(`/projects/${p.id}/report`)
  if (loading || !data) return <Skeleton className="h-64" />
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card><CardHeader title="Tasks by status" /><BarList items={data.status_breakdown.map((s) => ({ label: titleCase(s.status), value: s.count }))} /></Card>
      <Card><CardHeader title="Tasks by priority" /><BarList items={data.priority_breakdown.map((s) => ({ label: titleCase(s.priority), value: s.count }))} /></Card>
      <Card padded={false} className="lg:col-span-2">
        <div className="p-5 pb-3"><h3 className="text-[15px] font-semibold">Contribution by member</h3></div>
        <DataTable rows={data.members.map((m) => ({ ...m, id: m.name }))} empty={<EmptyState compact title="No tasks yet" />}
          columns={[
            { key: 'name', header: 'Member', mobile: 'title', render: (m) => <span className="font-medium text-ink">{m.name}</span> },
            { key: 'total', header: 'Tasks', align: 'right', render: (m) => m.total },
            { key: 'done', header: 'Done', align: 'right', render: (m) => m.done },
            { key: 'overdue', header: 'Overdue', align: 'right', render: (m) => <span className={m.overdue ? 'font-semibold text-danger' : ''}>{m.overdue}</span> },
            { key: 'hours', header: 'Hours logged', align: 'right', render: (m) => m.hours },
          ]} />
      </Card>
    </div>
  )
}

export default function ProjectDetailPage() {
  const { id } = useParams()
  const toast = useToast()
  const { data: p, loading, error, reload } = useApi(`/projects/${id}`)
  const tasks = useApi('/tasks', { scope: 'all', project_id: id, page_size: 200 })
  const ms = useApi(`/projects/${id}/milestones`)
  const clients = useOptions('clients')
  const employees = useOptions('employees')
  const [tab, setTab] = useState('overview')
  const [edit, setEdit] = useState(false)
  const [newTask, setNewTask] = useState(false)
  const [openTask, setOpenTask] = useState(null)

  if (error) return <ErrorState message={error} onRetry={reload} />
  if (loading || !p) return <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-72" /></div>
  const members = p.members.map((m) => ({ value: m.employee.id, label: m.employee.full_name }))
  const counts = p.task_counts
  const refreshAll = () => { reload(); tasks.reload({ silent: true }) }
  const daysLeft = p.end_date ? Math.ceil((new Date(p.end_date) - new Date()) / 864e5) : null

  return (
    <>
      <PageHeader title={p.name} breadcrumbs={[{ label: 'Projects', to: '/projects' }, { label: p.code }]}
        description={`${p.client?.name || 'Internal project'} · Managed by ${p.manager?.full_name || 'nobody yet'}`}
        actions={<>
          {p.can_manage && <Button variant="secondary" icon={Pencil} onClick={() => setEdit(true)}>Edit</Button>}
          <Button icon={Plus} onClick={() => setNewTask(true)}>New task</Button>
        </>} />
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="card p-4"><p className="flex min-h-8 items-center text-[13px] font-medium text-muted">Progress</p><p className="num mt-2 text-[26px] font-semibold leading-tight">{Math.round(p.progress)}%</p><Progress value={p.progress} className="mt-2" tone={p.is_delayed ? 'danger' : 'brand'} /></div>
        <StatCard label="Open tasks" value={p.task_total - (counts.done || 0)} hint={`${counts.done || 0} done · ${p.task_total} total`} tone="neutral" />
        <StatCard label="Overdue tasks" value={p.overdue_tasks} tone={p.overdue_tasks ? 'danger' : 'neutral'} />
        <StatCard label={p.is_delayed ? 'Past deadline' : 'Days remaining'} value={daysLeft === null ? '—' : Math.abs(daysLeft)} icon={Calendar} tone={p.is_delayed ? 'danger' : 'neutral'} hint={p.end_date ? `Ends ${fmtDate(p.end_date)}` : 'No end date'} />
      </div>
      <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[
        { value: 'overview', label: 'Overview' }, { value: 'tasks', label: 'Tasks', count: p.task_total },
        { value: 'milestones', label: 'Milestones' }, { value: 'team', label: 'Team', count: p.members.length },
        { value: 'files', label: 'Files' }, { value: 'report', label: 'Report' }]} />
      {tab === 'overview' && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2"><CardHeader title="About this project" />
            {p.description ? <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-2">{p.description}</p> : <p className="text-sm text-muted">No description yet.</p>}
          </Card>
          <Card><DescriptionList cols={1} items={[
            ['Status', <span key="s" className="flex gap-1.5"><StatusBadge status={p.status} />{p.is_delayed && <Badge tone="danger">Delayed</Badge>}</span>],
            ['Priority', titleCase(p.priority)], ['Client', p.client?.name || 'Internal'], ['Timeline', `${fmtDate(p.start_date)} – ${fmtDate(p.end_date)}`],
            ['Budget', p.budget ? fmtMoney(p.budget) : '—'], ['Created', fmtDate(p.created_at)],
          ]} /></Card>
        </div>
      )}
      {tab === 'tasks' && (tasks.loading && !tasks.data ? <Skeleton className="h-64" /> : tasks.data?.items.length
        ? <TaskBoard tasks={tasks.data.items} onOpen={(t) => setOpenTask(t.id)} onMove={async (t, s) => { try { await api.patch(`/tasks/${t.id}/status`, { status: s }); refreshAll() } catch (e) { toast.apiError(e, 'Could not move task') } }} />
        : <EmptyState title="No tasks yet" action={<Button icon={Plus} onClick={() => setNewTask(true)}>New task</Button>} />)}
      {tab === 'milestones' && <Milestones p={p} />}
      {tab === 'team' && <Team p={p} reload={reload} />}
      {tab === 'files' && <Files p={p} />}
      {tab === 'report' && <Report p={p} />}

      <TaskDrawer taskId={openTask} onClose={() => setOpenTask(null)} onChanged={refreshAll} memberOptions={members} />
      <FormModal open={newTask} onClose={() => setNewTask(false)} title="New task" size="lg" submitLabel="Create task"
        fields={taskFields({ members, milestones: (ms.data || []).map((m) => ({ value: m.id, label: m.title })), projectFixed: true })}
        onSubmit={async (v) => { await api.post('/tasks', { ...v, project_id: p.id }); toast.success('Task created'); refreshAll(); setTab('tasks') }} />
      <FormModal open={edit} onClose={() => setEdit(false)} title="Edit project" size="lg" initial={p}
        fields={projectFields({ clients, employees })}
        onSubmit={async (v) => { await api.put(`/projects/${p.id}`, v); invalidateOptions('projects'); toast.success('Project updated'); reload() }} />
    </>
  )
}
