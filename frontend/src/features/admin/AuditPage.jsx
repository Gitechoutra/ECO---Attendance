import { useEffect, useState } from 'react'
import { ScrollText } from 'lucide-react'
import { useApi, useDebounced } from '../../hooks/useApi'
import { Badge, DataTable, Drawer, EmptyState, Input, PageHeader, Pagination, SearchInput, Select, Toolbar } from '../../components/ui'
import { fmtDateTime } from '../../lib/format'

const MODULES = ['auth', 'employee', 'attendance', 'biometric', 'leave', 'project', 'task', 'client', 'email', 'candidate', 'offer', 'payroll', 'expense', 'announcement', 'report', 'user', 'role', 'settings', 'admin', 'ai']

export default function AuditPage() {
  const [q, setQ] = useState('')
  const [action, setAction] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [sel, setSel] = useState(null)
  const dq = useDebounced(q)
  const { data, loading, error, reload } = useApi('/admin/audit', { q: dq || undefined, action: action || undefined, date_from: from || undefined, date_to: to || undefined, page, page_size: 50 })
  useEffect(() => { setPage(1) }, [dq, action, from, to])
  return (
    <>
      <PageHeader title="Audit log" description="Tamper-evident record of sign-ins, changes, approvals and exports." />
      <div className="card overflow-hidden">
        <Toolbar>
          <SearchInput value={q} onChange={setQ} placeholder="Search activity" className="sm:w-64" />
          <Select value={action} onChange={(e) => setAction(e.target.value)} placeholder="All modules" className="sm:w-44" options={MODULES.map((m) => ({ value: m, label: m.replace(/^\w/, (c) => c.toUpperCase()) }))} />
          <div className="grid grid-cols-2 gap-2 sm:flex"><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="sm:w-40" /><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="sm:w-40" /></div>
        </Toolbar>
        <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items} onRowClick={setSel} dense
          empty={<EmptyState icon={ScrollText} title="No activity for these filters" />}
          columns={[
            { key: 'when', header: 'When', render: (a) => <span className="num whitespace-nowrap">{fmtDateTime(a.created_at)}</span> },
            { key: 'user', header: 'User', mobile: 'title', render: (a) => <span className="font-medium text-ink">{a.user}</span> },
            { key: 'action', header: 'Action', render: (a) => <Badge>{a.action}</Badge> },
            { key: 'summary', header: 'Details', mobile: 'full', className: 'max-w-md', render: (a) => <span className="line-clamp-1">{a.summary}</span> },
            { key: 'ip', header: 'IP', render: (a) => <span className="num text-xs text-muted">{a.ip_address || '—'}</span> },
          ]} />
        <Pagination page={page} pages={data?.pages} total={data?.total} pageSize={50} onChange={setPage} />
      </div>
      <Drawer open={Boolean(sel)} onClose={() => setSel(null)} title={sel?.action} subtitle={sel && fmtDateTime(sel.created_at)}>
        {sel && (
          <div className="space-y-4 text-sm">
            <p className="text-ink-2">{sel.summary}</p>
            <dl className="grid grid-cols-2 gap-3 text-[13px]"><div><dt className="text-muted">User</dt><dd>{sel.user}</dd></div><div><dt className="text-muted">IP address</dt><dd>{sel.ip_address || '—'}</dd></div>
              <div><dt className="text-muted">Entity</dt><dd>{sel.entity_type || '—'} {sel.entity_id ? `#${sel.entity_id}` : ''}</dd></div></dl>
            {sel.details && <pre className="scrollbar-thin overflow-x-auto rounded-lg bg-surface-2 p-3 text-xs">{JSON.stringify(sel.details, null, 2)}</pre>}
          </div>
        )}
      </Drawer>
    </>
  )
}
