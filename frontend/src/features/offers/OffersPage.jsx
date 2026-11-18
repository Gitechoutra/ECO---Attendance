import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { FileSignature, Pencil, Plus } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useDebounced } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import {
  Badge, Button, DataTable, EmptyState, FormModal, IconButton, PageHeader, Pagination, SearchInput, Segmented, Tabs, Toolbar, StatusBadge,
} from '../../components/ui'
import { fmtDate, fmtMoney } from '../../lib/format'
import OfferForm from './OfferForm'

const PLACEHOLDERS = '{{candidate_name}} {{first_name}} {{designation}} {{department}} {{company_name}} {{joining_date}} {{annual_ctc}} {{work_location}} {{valid_until}} {{additional_terms}} {{reference_no}}'

function Templates() {
  const toast = useToast()
  const { data, loading, error, reload } = useApi('/offers/templates')
  const [form, setForm] = useState(null)
  return (
    <div className="card overflow-hidden">
      <Toolbar><p className="text-[13px] text-muted">Templates use placeholders filled from each offer.</p><Button size="sm" icon={Plus} className="sm:ml-auto" onClick={() => setForm({})}>New template</Button></Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data}
        columns={[
          { key: 'name', header: 'Template', mobile: 'title', render: (t) => <span className="font-medium text-ink">{t.name} {t.is_default && <Badge tone="brand">Default</Badge>}</span> },
          { key: 'preview', header: 'Preview', render: (t) => <span className="line-clamp-1 text-muted">{t.body.slice(0, 120)}</span> },
          { key: 'status', header: 'Status', render: (t) => t.is_active ? <Badge tone="success" dot>Active</Badge> : <Badge dot>Inactive</Badge> },
          { key: 'a', header: '', align: 'right', render: (t) => <IconButton icon={Pencil} size="sm" label="Edit" onClick={() => setForm(t)} /> },
        ]} />
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={form?.id ? 'Edit template' : 'New template'} size="xl" initial={form}
        fields={[{ name: 'name', label: 'Name', required: true }, { name: 'body', label: 'Letter body', type: 'textarea', rows: 16, required: true, hint: `Placeholders: ${PLACEHOLDERS}. Separate paragraphs with a blank line.` },
          { name: 'is_default', label: 'Default template', type: 'checkbox' }, { name: 'is_active', label: 'Active', type: 'checkbox', default: true }]}
        onSubmit={async (v) => { form.id ? await api.put(`/offers/templates/${form.id}`, v) : await api.post('/offers/templates', v); toast.success('Template saved'); reload() }} />
    </div>
  )
}

export default function OffersPage() {
  const { can } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const [tab, setTab] = useState('offers')
  const [status, setStatus] = useState(params.get('status') || '')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(Boolean(params.get('candidate')))
  const dq = useDebounced(q)
  const { data, loading, error, reload } = useApi('/offers', { status: status || undefined, q: dq || undefined, page, page_size: 20 })
  useEffect(() => { setPage(1) }, [status, dq])
  return (
    <>
      <PageHeader title="Offer letters" description="Branded offers with approvals, versioning and digital acceptance."
        actions={can('offers.manage') && <Button icon={Plus} onClick={() => setCreating(true)}>New offer</Button>} />
      <Tabs className="mb-4" value={tab} onChange={setTab} tabs={[{ value: 'offers', label: 'Offers' }, { value: 'templates', label: 'Templates', hidden: !can('offers.manage') }]} />
      {tab === 'offers' ? (
        <div className="card overflow-hidden">
          <Toolbar>
            <SearchInput value={q} onChange={setQ} placeholder="Search name or reference" className="sm:w-64" />
            <div className="overflow-x-auto"><Segmented size="sm" value={status} onChange={setStatus} options={[{ value: '', label: 'All' }, { value: 'draft', label: 'Draft' }, { value: 'pending_approval', label: 'Pending' }, { value: 'approved', label: 'Approved' }, { value: 'sent', label: 'Sent' }, { value: 'accepted', label: 'Accepted' }, { value: 'declined', label: 'Declined' }]} /></div>
          </Toolbar>
          <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items} onRowClick={(o) => nav(`/offers/${o.id}`)}
            empty={<EmptyState icon={FileSignature} title="No offer letters" />}
            columns={[
              { key: 'ref', header: 'Reference', render: (o) => <span className="num text-ink-2">{o.reference_no}</span> },
              { key: 'name', header: 'Recipient', mobile: 'title', render: (o) => <div><p className="font-medium text-ink">{o.recipient_name}</p><p className="text-xs text-muted">{o.recipient_email}</p></div> },
              { key: 'role', header: 'Role', render: (o) => o.designation },
              { key: 'ctc', header: 'Annual CTC', align: 'right', render: (o) => fmtMoney(o.annual_ctc) },
              { key: 'join', header: 'Joining', render: (o) => fmtDate(o.joining_date) },
              { key: 'status', header: 'Status', render: (o) => <StatusBadge status={o.status} /> },
            ]} />
          <Pagination page={page} pages={data?.pages} total={data?.total} pageSize={20} onChange={setPage} />
        </div>
      ) : <Templates />}
      <OfferForm open={creating} onClose={() => setCreating(false)} candidateId={params.get('candidate') ? Number(params.get('candidate')) : undefined}
        onSaved={(o) => { toast.success('Offer drafted', o.reference_no); nav(`/offers/${o.id}`) }} />
    </>
  )
}
