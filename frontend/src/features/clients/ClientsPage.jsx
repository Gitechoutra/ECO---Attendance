import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Briefcase, Plus } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useDebounced } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions, invalidateOptions } from '../../hooks/useOptions'
import { Button, DataTable, EmptyState, FormModal, PageHeader, Pagination, SearchInput, Select, StatusBadge, Toolbar } from '../../components/ui'

export function clientFields(employees) {
  return [
    { name: 'name', label: 'Client name', required: true, span: 1 },
    { name: 'company_name', label: 'Registered company name', span: 1 },
    { name: 'industry', label: 'Industry', span: 1 },
    { name: 'status', label: 'Status', type: 'select', default: 'active', span: 1, options: [{ value: 'lead', label: 'Lead' }, { value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }] },
    { name: 'email', label: 'Email', type: 'email', span: 1 },
    { name: 'phone', label: 'Phone', span: 1 },
    { name: 'website', label: 'Website', span: 1, placeholder: 'https://' },
    { name: 'tax_id', label: 'GSTIN / Tax ID', span: 1 },
    { name: 'account_manager_id', label: 'Account manager', type: 'select', numeric: true, options: employees, placeholder: 'None' },
    { name: 'address', label: 'Address', type: 'textarea', rows: 2 },
    { name: 'city', label: 'City', span: 1 }, { name: 'country', label: 'Country', span: 1 },
    { name: 'notes', label: 'Notes', type: 'textarea' },
  ]
}

export default function ClientsPage() {
  const { can } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const dq = useDebounced(q)
  const employees = useOptions('employees', creating)
  const { data, loading, error, reload } = useApi('/clients', { q: dq || undefined, status: status || undefined, page, page_size: 20 })
  useEffect(() => { setPage(1) }, [dq, status])
  return (
    <>
      <PageHeader title="Clients" description="Relationships, requirements and communication history."
        actions={can('clients.manage') && <Button icon={Plus} onClick={() => setCreating(true)}>New client</Button>} />
      <div className="card overflow-hidden">
        <Toolbar>
          <SearchInput value={q} onChange={setQ} placeholder="Search clients" className="sm:w-72" />
          <Select value={status} onChange={(e) => setStatus(e.target.value)} placeholder="All statuses" className="sm:w-40" options={[{ value: 'lead', label: 'Lead' }, { value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }]} />
        </Toolbar>
        <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items} onRowClick={(c) => nav(`/clients/${c.id}`)}
          empty={<EmptyState icon={Briefcase} title="No clients yet" action={can('clients.manage') && <Button icon={Plus} onClick={() => setCreating(true)}>New client</Button>} />}
          columns={[
            { key: 'name', header: 'Client', mobile: 'title', render: (c) => <div><p className="font-medium text-ink">{c.name}</p><p className="text-xs text-muted">{c.industry || c.company_name || '—'}</p></div> },
            { key: 'contact', header: 'Primary contact', render: (c) => c.primary_contact ? <div><p className="text-ink-2">{c.primary_contact.name}</p><p className="text-xs text-muted">{c.primary_contact.email}</p></div> : '—' },
            { key: 'manager', header: 'Account manager', render: (c) => c.account_manager?.full_name || '—' },
            { key: 'projects', header: 'Projects', align: 'right', render: (c) => `${c.active_projects} / ${c.project_count}` },
            { key: 'status', header: 'Status', render: (c) => <StatusBadge status={c.status} /> },
          ]} />
        <Pagination page={page} pages={data?.pages} total={data?.total} pageSize={20} onChange={setPage} />
      </div>
      <FormModal open={creating} onClose={() => setCreating(false)} title="New client" size="lg" submitLabel="Create client" fields={clientFields(employees)}
        onSubmit={async (v) => { const r = await api.post('/clients', v); invalidateOptions('clients'); toast.success('Client created'); nav(`/clients/${r.data.id}`) }} />
    </>
  )
}
