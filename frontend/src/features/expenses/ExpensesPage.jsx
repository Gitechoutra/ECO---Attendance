import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Paperclip, Pencil, Plus, Receipt, Trash2 } from 'lucide-react'
import { api, downloadFile, errorMessage } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions, invalidateOptions } from '../../hooks/useOptions'
import {
  Badge, BarList, Button, Card, CardHeader, ColumnChart, ConfirmDialog, DataTable, EmptyState, Field, FileDrop, FormModal,
  IconButton, Input, Modal, PageHeader, Pagination, PersonCell, Segmented, Select, StatCard, StatusBadge, Tabs, Textarea, Toolbar,
} from '../../components/ui'
import { fmtDate, fmtCompactMoney, fmtMoney, isoDate, MONTHS } from '../../lib/format'

function SubmitModal({ open, onClose, onDone }) {
  const toast = useToast()
  const cats = useOptions('expenseCategories', open)
  const projects = useOptions('projects', open)
  const [f, setF] = useState({})
  const [file, setFile] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (open) { setF({ expense_date: isoDate() }); setFile(null); setErr(null) } }, [open])
  const cat = cats.find((c) => String(c.value) === String(f.category_id))
  const submit = async () => {
    setErr(null)
    if (!f.title || !f.amount || !f.category_id || !f.expense_date) { setErr('Title, amount, category and date are required.'); return }
    if (cat?.raw.requires_receipt && !file) { setErr(`A receipt is required for ${cat.label}.`); return }
    const fd = new FormData()
    Object.entries(f).forEach(([k, v]) => v !== '' && v != null && fd.append(k, v))
    if (file) fd.append('receipt', file)
    setBusy(true)
    try {
      const r = await api.post('/expenses', fd)
      toast.success('Expense submitted', r.data.warning || 'Sent for approval.')
      onDone(); onClose()
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy(false) }
  }
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  return (
    <Modal open={open} onClose={onClose} title="Submit expense" size="lg" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={busy} onClick={submit}>Submit claim</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        {err && <div className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2.5 text-[13px] text-danger sm:col-span-2">{err}</div>}
        <Field label="Title" required className="sm:col-span-2"><Input value={f.title || ''} onChange={set('title')} placeholder="e.g. Cab to client office" /></Field>
        <Field label="Amount (INR)" required><Input type="number" min="0" step="0.01" value={f.amount || ''} onChange={set('amount')} /></Field>
        <Field label="Date" required><Input type="date" max={isoDate()} value={f.expense_date || ''} onChange={set('expense_date')} /></Field>
        <Field label="Category" required hint={cat?.raw.monthly_limit ? `Monthly limit ${fmtMoney(cat.raw.monthly_limit)}` : undefined}><Select value={f.category_id || ''} onChange={set('category_id')} placeholder="Select" options={cats} /></Field>
        <Field label="Project"><Select value={f.project_id || ''} onChange={set('project_id')} placeholder="Not project-related" options={projects} /></Field>
        <Field label="Description" className="sm:col-span-2"><Textarea rows={2} value={f.description || ''} onChange={set('description')} /></Field>
        <Field label={`Receipt${cat?.raw.requires_receipt ? ' *' : ''}`} className="sm:col-span-2"><FileDrop value={file} onChange={setFile} accept="image/*,application/pdf" hint="Photo or PDF of the bill, up to 15 MB" /></Field>
      </div>
    </Modal>
  )
}

const columns = (extra = []) => [
  { key: 'title', header: 'Expense', mobile: 'title', render: (e) => <div><p className="font-medium text-ink">{e.title}</p><p className="text-xs text-muted">{e.category.name}{e.project ? ` · ${e.project.name}` : ''}</p></div> },
  ...extra,
  { key: 'date', header: 'Date', render: (e) => fmtDate(e.expense_date) },
  { key: 'amount', header: 'Amount', align: 'right', render: (e) => <span className="font-semibold text-ink">{fmtMoney(e.amount, e.currency)}</span> },
  { key: 'receipt', header: 'Receipt', render: (e) => e.receipt_file_id ? <button className="link inline-flex items-center gap-1" onClick={(ev) => { ev.stopPropagation(); downloadFile(`/files/${e.receipt_file_id}`, { inline: false }, 'receipt') }}><Paperclip className="h-3.5 w-3.5" />View</button> : '—' },
  { key: 'status', header: 'Status', render: (e) => <span title={e.review_note || ''}><StatusBadge status={e.status} /></span> },
]

function Mine() {
  const toast = useToast()
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [del, setDel] = useState(null)
  const { data, loading, error, reload } = useApi('/expenses', { scope: 'mine', status: status || undefined, page, page_size: 20 })
  const [run, busy] = useAction(toast)
  return (
    <div className="card overflow-hidden">
      <Toolbar>
        <Segmented size="sm" value={status} onChange={(v) => { setStatus(v); setPage(1) }} options={[{ value: '', label: 'All' }, { value: 'submitted', label: 'Pending' }, { value: 'approved', label: 'Approved' }, { value: 'reimbursed', label: 'Reimbursed' }, { value: 'rejected', label: 'Rejected' }]} />
        {data && <span className="text-[13px] text-muted">Total {fmtMoney(data.sum_amount)}</span>}
        <Button size="sm" icon={Plus} className="sm:ml-auto" onClick={() => setOpen(true)}>Submit expense</Button>
      </Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items}
        empty={<EmptyState icon={Receipt} title="No expense claims" action={<Button size="sm" onClick={() => setOpen(true)}>Submit expense</Button>} />}
        columns={[...columns(), { key: 'a', header: '', align: 'right', render: (e) => e.status === 'submitted' && <IconButton icon={Trash2} size="sm" variant="danger" label="Withdraw" onClick={() => setDel(e)} /> }]} />
      <Pagination page={page} pages={data?.pages} total={data?.total} pageSize={20} onChange={setPage} />
      <SubmitModal open={open} onClose={() => setOpen(false)} onDone={reload} />
      <ConfirmDialog open={Boolean(del)} onClose={() => setDel(null)} title="Withdraw claim" description={`Withdraw “${del?.title}”?`} confirmLabel="Withdraw" loading={busy}
        onConfirm={async () => { await run(() => api.delete(`/expenses/${del.id}`), { success: 'Claim withdrawn' }); setDel(null); reload() }} />
    </div>
  )
}

function Approvals() {
  const { can } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState(can('expenses.approve') ? 'submitted' : 'approved')
  const [page, setPage] = useState(1)
  const { data, loading, error, reload } = useApi('/expenses', { scope: 'all', status: status || undefined, page, page_size: 20 })
  const [reject, setReject] = useState(null)
  const [reimb, setReimb] = useState(null)
  const [run, busy] = useAction(toast)
  return (
    <div className="card overflow-hidden">
      <Toolbar>
        <Segmented size="sm" value={status} onChange={(v) => { setStatus(v); setPage(1) }} options={[{ value: 'submitted', label: 'Pending' }, { value: 'approved', label: 'To reimburse' }, { value: 'reimbursed', label: 'Reimbursed' }, { value: 'rejected', label: 'Rejected' }, { value: '', label: 'All' }]} />
        {data && <span className="text-[13px] text-muted">Total {fmtMoney(data.sum_amount)}</span>}
      </Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items}
        empty={<EmptyState icon={Receipt} title="Nothing to review" />}
        columns={[...columns([{ key: 'emp', header: 'Employee', render: (e) => <PersonCell name={e.employee.full_name} fileId={e.employee.photo_file_id} size="xs" /> }]),
          { key: 'a', header: '', align: 'right', render: (e) => (
            <div className="flex justify-end gap-1.5">
              {e.status === 'submitted' && can('expenses.approve') && <>
                <Button size="xs" variant="secondary" disabled={busy} onClick={() => setReject(e)}>Reject</Button>
                <Button size="xs" disabled={busy} onClick={async () => { await run(() => api.post(`/expenses/${e.id}/review`, { approve: true }), { success: 'Approved' }); reload() }}>Approve</Button>
              </>}
              {e.status === 'approved' && can('expenses.reimburse') && <Button size="xs" onClick={() => setReimb(e)}>Reimburse</Button>}
            </div>) }]} />
      <Pagination page={page} pages={data?.pages} total={data?.total} pageSize={20} onChange={setPage} />
      <FormModal open={Boolean(reject)} onClose={() => setReject(null)} title="Reject claim" submitLabel="Reject" fields={[{ name: 'note', label: 'Reason', type: 'textarea', required: true }]}
        onSubmit={async (v) => { await api.post(`/expenses/${reject.id}/review`, { approve: false, note: v.note }); toast.success('Claim rejected'); reload() }} />
      <FormModal open={Boolean(reimb)} onClose={() => setReimb(null)} title={`Reimburse ${reimb ? fmtMoney(reimb.amount) : ''}`} submitLabel="Mark reimbursed" fields={[{ name: 'reference', label: 'Payment reference (UTR / txn ID)' }]}
        onSubmit={async (v) => { await api.post(`/expenses/${reimb.id}/reimburse`, v); toast.success('Marked as reimbursed'); reload() }} />
    </div>
  )
}

function Overview() {
  const year = new Date().getFullYear()
  const { data } = useApi('/expenses/stats', { year })
  if (!data) return null
  const months = Array.from({ length: 12 }, (_, i) => ({ label: MONTHS[i].slice(0, 3), amount: data.by_month.find((m) => m.month === i + 1)?.amount || 0 }))
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <StatCard label="Pending approval" value={data.pending_count} tone="warning" />
        <StatCard label="Awaiting reimbursement" value={fmtMoney(data.awaiting_reimbursement)} tone="info" />
        <StatCard label={`Approved spend ${year}`} value={fmtMoney(data.by_category.reduce((s, c) => s + c.amount, 0))} tone="neutral" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2"><CardHeader title={`Approved expenses by month · ${year}`} /><ColumnChart data={months} xKey="label" series={[{ key: 'amount', name: 'Amount' }]} format={(v) => fmtMoney(v)} axisFormat={(v) => fmtCompactMoney(v)} /></Card>
        <Card><CardHeader title="By category" /><BarList items={data.by_category.sort((a, b) => b.amount - a.amount).map((c) => ({ label: c.name, value: c.amount }))} format={(v) => fmtMoney(v)} axisFormat={(v) => fmtCompactMoney(v)} /></Card>
      </div>
    </div>
  )
}

function Categories() {
  const toast = useToast()
  const { data, loading, reload } = useApi('/expenses/categories')
  const [form, setForm] = useState(null)
  return (
    <div className="card overflow-hidden">
      <Toolbar><Button size="sm" icon={Plus} className="sm:ml-auto" onClick={() => setForm({})}>New category</Button></Toolbar>
      <DataTable loading={loading} rows={data}
        columns={[
          { key: 'name', header: 'Category', mobile: 'title', render: (c) => <span className="font-medium text-ink">{c.name}</span> },
          { key: 'limit', header: 'Monthly limit', align: 'right', render: (c) => c.monthly_limit ? fmtMoney(c.monthly_limit) : 'No limit' },
          { key: 'r', header: 'Receipt', render: (c) => c.requires_receipt ? 'Required' : 'Optional' },
          { key: 's', header: 'Status', render: (c) => c.is_active ? <Badge tone="success" dot>Active</Badge> : <Badge dot>Inactive</Badge> },
          { key: 'a', header: '', align: 'right', render: (c) => <IconButton icon={Pencil} size="sm" label="Edit" onClick={() => setForm(c)} /> },
        ]} />
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={form?.id ? 'Edit category' : 'New category'} initial={form}
        fields={[{ name: 'name', label: 'Name', required: true }, { name: 'monthly_limit', label: 'Monthly limit per employee (INR)', type: 'number', min: 0 },
          { name: 'requires_receipt', label: 'Receipt required', type: 'checkbox', default: true }, { name: 'is_active', label: 'Active', type: 'checkbox', default: true }]}
        onSubmit={async (v) => { form.id ? await api.put(`/expenses/categories/${form.id}`, v) : await api.post('/expenses/categories', v); invalidateOptions('expenseCategories'); toast.success('Category saved'); reload() }} />
    </div>
  )
}

export default function ExpensesPage() {
  const { can, canAny, employee } = useAuth()
  const [params, setParams] = useSearchParams()
  const reviewer = canAny('expenses.approve', 'expenses.reimburse', 'expenses.view_all')
  const tab = params.get('tab') || (employee ? 'mine' : 'approvals')
  return (
    <>
      <PageHeader title="Expenses" description="Claims, approvals and reimbursements." />
      <Tabs className="mb-5" value={tab} onChange={(t) => setParams({ tab: t })} tabs={[
        { value: 'mine', label: 'My expenses', hidden: !employee }, { value: 'approvals', label: 'Approvals', hidden: !reviewer },
        { value: 'overview', label: 'Overview', hidden: !can('expenses.view_all') }, { value: 'categories', label: 'Categories', hidden: !can('expenses.approve') }]} />
      {tab === 'mine' && employee && <Mine />}
      {tab === 'approvals' && reviewer && <Approvals />}
      {tab === 'overview' && can('expenses.view_all') && <Overview />}
      {tab === 'categories' && can('expenses.approve') && <Categories />}
    </>
  )
}
