import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertTriangle, FolderKanban, LayoutGrid, List, Plus } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useDebounced } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions, invalidateOptions } from '../../hooks/useOptions'
import {
  Avatar, Badge, Button, Checkbox, DataTable, EmptyState, ErrorState, FormModal, PageHeader, Pagination, Progress,
  SearchInput, Segmented, Select, Skeleton, StatusBadge, Toolbar,
} from '../../components/ui'
import { fmtDate, titleCase } from '../../lib/format'

export const PROJECT_STATUSES = ['planning', 'active', 'on_hold', 'completed', 'cancelled'].map((s) => ({ value: s, label: titleCase(s) }))

export function projectFields({ clients, employees }) {
  return [
    { name: 'name', label: 'Project name', required: true },
    { name: 'client_id', label: 'Client', type: 'select', numeric: true, options: clients, placeholder: 'Internal project', span: 1 },
    { name: 'manager_id', label: 'Project manager', type: 'select', numeric: true, options: employees, placeholder: 'Select', span: 1 },
    { name: 'start_date', label: 'Start date', type: 'date', span: 1 },
    { name: 'end_date', label: 'End date', type: 'date', span: 1, validate: (v, a) => v && a.start_date && v < a.start_date ? 'Must be after the start date' : null },
    { name: 'status', label: 'Status', type: 'select', options: PROJECT_STATUSES, default: 'planning', span: 1 },
    { name: 'priority', label: 'Priority', type: 'select', default: 'medium', span: 1, options: ['low', 'medium', 'high', 'urgent'].map((p) => ({ value: p, label: titleCase(p) })) },
    { name: 'budget', label: 'Budget (INR)', type: 'number', min: 0 },
    { name: 'description', label: 'Description', type: 'textarea', rows: 4 },
  ]
}

function ProjectCard({ p }) {
  return (
    <Link to={`/projects/${p.id}`} className="card flex flex-col p-4 transition-colors hover:border-line-strong">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-2xs font-semibold uppercase tracking-wide text-faint">{p.code}</p>
          <p className="mt-0.5 truncate text-[15px] font-semibold">{p.name}</p>
          <p className="truncate text-xs text-muted">{p.client?.name || 'Internal'}</p>
        </div>
        {p.is_delayed ? <Badge tone="danger" dot>Delayed</Badge> : <StatusBadge status={p.status} />}
      </div>
      <Progress value={p.progress} showLabel className="mt-4" tone={p.is_delayed ? 'danger' : 'brand'} />
      <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-xs text-muted">
        <span className="flex items-center gap-2">{p.manager && <Avatar name={p.manager.full_name} fileId={p.manager.photo_file_id} size="xs" />}{p.manager?.full_name || 'No manager'}</span>
        <span className="num">{p.task_total - (p.task_counts.done || 0)} open{p.overdue_tasks ? <span className="text-danger"> · {p.overdue_tasks} overdue</span> : ''}</span>
      </div>
      {p.end_date && <p className="mt-2 text-2xs text-faint">Due {fmtDate(p.end_date)}</p>}
    </Link>
  )
}

export default function ProjectsPage() {
  const { can } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [delayed, setDelayed] = useState(false)
  const [view, setView] = useState('grid')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(params.get('new') === '1')
  const dq = useDebounced(q)
  const clients = useOptions('clients', creating)
  const employees = useOptions('employees', creating)
  const { data, loading, error, reload } = useApi('/projects', { q: dq || undefined, status: status || undefined, delayed: delayed || undefined, page, page_size: 24 })
  useEffect(() => { setPage(1) }, [dq, status, delayed])

  return (
    <>
      <PageHeader title="Projects" description={data ? `${data.total} project${data.total === 1 ? '' : 's'} you can access` : 'Delivery across clients and internal work'}
        actions={can('projects.manage') && <Button icon={Plus} onClick={() => setCreating(true)}>New project</Button>} />
      <div className="card mb-4 overflow-hidden">
        <Toolbar>
          <SearchInput value={q} onChange={setQ} placeholder="Search by name or code" className="sm:w-64" />
          <Select value={status} onChange={(e) => setStatus(e.target.value)} placeholder="All statuses" options={PROJECT_STATUSES} className="sm:w-40" />
          <Checkbox label="Delayed only" checked={delayed} onChange={(e) => setDelayed(e.target.checked)} />
          <div className="sm:ml-auto"><Segmented size="sm" value={view} onChange={setView} options={[{ value: 'grid', label: 'Cards', icon: LayoutGrid }, { value: 'list', label: 'List', icon: List }]} /></div>
        </Toolbar>
        {view === 'list' && (
          <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items} onRowClick={(p) => nav(`/projects/${p.id}`)}
            empty={<EmptyState icon={FolderKanban} title="No projects found" />}
            columns={[
              { key: 'name', header: 'Project', mobile: 'title', render: (p) => <div><p className="font-medium text-ink">{p.name}</p><p className="text-xs text-muted">{p.code} · {p.client?.name || 'Internal'}</p></div> },
              { key: 'manager', header: 'Manager', render: (p) => p.manager?.full_name || '—' },
              { key: 'dates', header: 'Timeline', render: (p) => `${fmtDate(p.start_date, 'dd MMM yy')} – ${fmtDate(p.end_date, 'dd MMM yy')}` },
              { key: 'progress', header: 'Progress', render: (p) => <Progress value={p.progress} showLabel className="w-32" tone={p.is_delayed ? 'danger' : 'brand'} /> },
              { key: 'status', header: 'Status', render: (p) => <div className="flex gap-1.5"><StatusBadge status={p.status} />{p.is_delayed && <Badge tone="danger"><AlertTriangle className="h-3 w-3" />Delayed</Badge>}</div> },
            ]} />
        )}
      </div>
      {view === 'grid' && (error ? <ErrorState message={error} onRetry={reload} /> : loading && !data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-48" />)}</div>
      ) : data?.items.length ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{data.items.map((p) => <ProjectCard key={p.id} p={p} />)}</div>
      ) : <EmptyState icon={FolderKanban} title="No projects yet" description={can('projects.manage') ? 'Create a project to start planning delivery.' : 'Projects you are assigned to will appear here.'}
        action={can('projects.manage') && <Button icon={Plus} onClick={() => setCreating(true)}>New project</Button>} />)}
      {view === 'grid' && <div className="card mt-4 overflow-hidden"><Pagination page={page} pages={data?.pages} total={data?.total} pageSize={24} onChange={setPage} /></div>}
      <FormModal open={creating} onClose={() => { setCreating(false); if (params.get('new')) setParams({}) }} title="New project" size="lg" submitLabel="Create project"
        fields={projectFields({ clients, employees })}
        onSubmit={async (v) => { const r = await api.post('/projects', v); invalidateOptions('projects'); toast.success('Project created', r.data.code); nav(`/projects/${r.data.id}`) }} />
    </>
  )
}
