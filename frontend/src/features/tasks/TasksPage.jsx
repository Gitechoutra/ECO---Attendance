import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CheckSquare, Columns3, List, Plus } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useDebounced } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions } from '../../hooks/useOptions'
import {
  Button, Checkbox, DataTable, EmptyState, FormModal, PageHeader, Pagination, PersonCell, SearchInput, Segmented,
  Select, StatusBadge, Toolbar,
} from '../../components/ui'
import { fmtDate } from '../../lib/format'
import TaskDrawer, { PRIORITIES, STATUSES, taskFields } from './TaskDrawer'
import TaskBoard from './TaskBoard'

export default function TasksPage() {
  const { taskId } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const { employee } = useAuth()
  const [scope, setScope] = useState(employee ? 'mine' : 'all')
  const [view, setView] = useState(() => { try { return localStorage.getItem('eo-task-view') || 'list' } catch { return 'list' } })
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [overdue, setOverdue] = useState(false)
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const dq = useDebounced(q)
  const projects = useOptions('projects')
  const people = useOptions('employees')
  const pageSize = view === 'board' ? 200 : 25
  const { data, loading, error, reload } = useApi('/tasks', {
    scope, q: dq || undefined, status: status || (view === 'list' ? undefined : undefined), priority: priority || undefined,
    overdue: overdue || undefined, page: view === 'board' ? 1 : page, page_size: pageSize,
  })
  useEffect(() => { setPage(1) }, [scope, dq, status, priority, overdue])
  useEffect(() => { try { localStorage.setItem('eo-task-view', view) } catch { /* ignore */ } }, [view])

  const move = async (t, s) => {
    try { await api.patch(`/tasks/${t.id}/status`, { status: s }); reload({ silent: true }) } catch (e) { toast.apiError(e, 'Could not move task') }
  }

  return (
    <>
      <PageHeader title="Tasks" description="Everything on your plate, across projects."
        actions={<Button icon={Plus} onClick={() => setCreating(true)} disabled={!employee}>New task</Button>} />
      <div className="card mb-4 overflow-hidden">
        <Toolbar>
          <Segmented value={scope} onChange={setScope} options={[
            ...(employee ? [{ value: 'mine', label: 'Assigned to me' }, { value: 'created', label: 'Created by me' }] : []),
            { value: 'all', label: 'All visible' }]} />
          <SearchInput value={q} onChange={setQ} placeholder="Search tasks" className="sm:w-56" />
          <div className="grid grid-cols-2 gap-2 sm:flex">
            {view === 'list' && <Select value={status} onChange={(e) => setStatus(e.target.value)} placeholder="Any status" options={STATUSES} className="sm:w-36" />}
            <Select value={priority} onChange={(e) => setPriority(e.target.value)} placeholder="Any priority" options={PRIORITIES} className="sm:w-36" />
          </div>
          <Checkbox label="Overdue only" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} />
          <div className="sm:ml-auto"><Segmented value={view} onChange={setView} size="sm" options={[{ value: 'list', label: 'List', icon: List }, { value: 'board', label: 'Board', icon: Columns3 }]} /></div>
        </Toolbar>
        {view === 'list' && (
          <>
            <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items} onRowClick={(t) => nav(`/tasks/${t.id}`)}
              empty={<EmptyState icon={CheckSquare} title="No tasks here" description={scope === 'mine' ? 'Nothing assigned to you. Enjoy the calm.' : 'Try other filters.'} />}
              columns={[
                { key: 'title', header: 'Task', mobile: 'title', render: (t) => <div className="min-w-0"><p className="truncate font-medium text-ink">{t.title}</p><p className="truncate text-xs text-muted">{t.project?.name || 'Personal'}</p></div> },
                { key: 'assignee', header: 'Assignee', render: (t) => t.assignee ? <PersonCell name={t.assignee.full_name} fileId={t.assignee.photo_file_id} size="xs" /> : <span className="text-muted">Unassigned</span> },
                { key: 'priority', header: 'Priority', render: (t) => <StatusBadge status={t.priority} /> },
                { key: 'due', header: 'Due', render: (t) => t.due_date ? <span className={t.is_overdue ? 'font-semibold text-danger' : ''}>{fmtDate(t.due_date, 'dd MMM yyyy')}</span> : '—' },
                { key: 'progress', header: 'Progress', render: (t) => <span className="num">{t.progress}%</span> },
                { key: 'status', header: 'Status', render: (t) => <StatusBadge status={t.status} label={STATUSES.find((s) => s.value === t.status)?.label} /> },
              ]} />
            <Pagination page={page} pages={data?.pages} total={data?.total} pageSize={pageSize} onChange={setPage} />
          </>
        )}
      </div>
      {view === 'board' && (loading && !data ? null : (
        data?.items.length ? <TaskBoard tasks={data.items} onOpen={(t) => nav(`/tasks/${t.id}`)} onMove={move} />
          : <EmptyState icon={CheckSquare} title="No tasks to show" />
      ))}
      <TaskDrawer taskId={taskId} onClose={() => nav('/tasks')} onChanged={() => reload({ silent: true })} memberOptions={people} />
      <FormModal open={creating} onClose={() => setCreating(false)} title="New task" size="lg" submitLabel="Create task"
        description="Project tasks can be assigned to project members. Personal tasks stay with you."
        initial={{ assignee_id: employee?.id }}
        fields={taskFields({ projects, members: people })}
        onSubmit={async (v) => { const r = await api.post('/tasks', v); toast.success('Task created'); reload(); nav(`/tasks/${r.data.id}`) }} />
    </>
  )
}

