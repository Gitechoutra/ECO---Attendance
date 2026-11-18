import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Download, Plus, Users } from 'lucide-react'
import { useApi, useDebounced } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useOptions } from '../../hooks/useOptions'
import { downloadFile } from '../../api/client'
import { Button, DataTable, EmptyState, PageHeader, Pagination, PersonCell, SearchInput, Select, StatusBadge, Toolbar } from '../../components/ui'
import { fmtDate, titleCase } from '../../lib/format'
import EmployeeForm from './EmployeeForm'

export default function EmployeesPage() {
  const { can } = useAuth()
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState('')
  const [dept, setDept] = useState('')
  const [status, setStatus] = useState('active')
  const [page, setPage] = useState(1)
  const [formOpen, setFormOpen] = useState(params.get('new') === '1')
  const dq = useDebounced(q)
  const depts = useOptions('departments')
  const { data, loading, error, reload } = useApi('/employees', { q: dq, department_id: dept || undefined, status: status || undefined, page, page_size: 20 })

  useEffect(() => { setPage(1) }, [dq, dept, status])

  const columns = [
    { key: 'name', header: 'Employee', mobile: 'title', render: (e) => <PersonCell name={e.full_name} subtitle={e.email} fileId={e.photo_file_id} /> },
    { key: 'employee_code', header: 'ID', render: (e) => <span className="num text-ink-2">{e.employee_code}</span> },
    { key: 'department', header: 'Department', render: (e) => e.department?.name || '—' },
    { key: 'designation', header: 'Designation', render: (e) => e.designation?.title || '—' },
    { key: 'type', header: 'Type', render: (e) => titleCase(e.employment_type) },
    { key: 'joining', header: 'Joined', render: (e) => fmtDate(e.joining_date) },
    { key: 'status', header: 'Status', render: (e) => <StatusBadge status={e.status} /> },
  ]

  return (
    <>
      <PageHeader
        title="Employees"
        description={data ? `${data.total} ${status ? titleCase(status).toLowerCase() : ''} employee${data.total === 1 ? '' : 's'}` : 'Your people directory'}
        actions={
          <>
            {can('reports.hr') && <Button variant="secondary" icon={Download} onClick={() => downloadFile('/reports/employees', { format: 'xlsx', date_from: '2000-01-01', status: status || undefined })}>Export</Button>}
            {can('employees.manage') && <Button icon={Plus} onClick={() => setFormOpen(true)}>Add employee</Button>}
          </>
        }
      />
      <div className="card overflow-hidden">
        <Toolbar>
          <SearchInput value={q} onChange={setQ} placeholder="Search name, ID, email or phone" className="sm:w-80" />
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <Select value={dept} onChange={(e) => setDept(e.target.value)} placeholder="All departments" options={depts} className="sm:w-48" />
            <Select value={status} onChange={(e) => setStatus(e.target.value)} placeholder="All statuses" className="sm:w-40"
              options={[{ value: 'active', label: 'Active' }, { value: 'on_notice', label: 'On notice' }, { value: 'inactive', label: 'Inactive' }]} />
          </div>
        </Toolbar>
        <DataTable
          columns={columns}
          rows={data?.items}
          loading={loading}
          error={error}
          onRetry={reload}
          onRowClick={(e) => nav(`/employees/${e.id}`)}
          empty={<EmptyState icon={Users} title={dq || dept ? 'No employees match these filters' : 'No employees yet'}
            description={dq || dept ? 'Try a different search or filter.' : 'Add your first employee to get started.'}
            action={!dq && !dept && can('employees.manage') && <Button icon={Plus} onClick={() => setFormOpen(true)}>Add employee</Button>} />}
        />
        <Pagination page={page} pages={data?.pages} total={data?.total} pageSize={20} onChange={setPage} />
      </div>
      <EmployeeForm open={formOpen} onClose={() => { setFormOpen(false); if (params.get('new')) setParams({}) }} onSaved={() => reload()} />
    </>
  )
}
