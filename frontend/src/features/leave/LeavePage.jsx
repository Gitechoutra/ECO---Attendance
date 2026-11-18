import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CalendarDays, CalendarPlus, Pencil, Plus, Trash2 } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions } from '../../hooks/useOptions'
import {
  Badge, Button, Card, ConfirmDialog, DataTable, EmptyState, ErrorState, FormModal, IconButton, Input, PageHeader,
  PersonCell, Progress, Segmented, Skeleton, StatusBadge, Tabs, Toolbar,
} from '../../components/ui'
import { fmtDate, isoDate } from '../../lib/format'

function ApplyModal({ open, onClose, onDone }) {
  const toast = useToast()
  const types = useOptions('leaveTypes', open)
  return (
    <FormModal open={open} onClose={onClose} title="Apply for leave" submitLabel="Submit request"
      description="Weekends and company holidays are excluded automatically."
      fields={[
        { name: 'leave_type_id', label: 'Leave type', type: 'select', numeric: true, required: true, options: types },
        { name: 'start_date', label: 'From', type: 'date', required: true, span: 1, default: isoDate() },
        { name: 'end_date', label: 'To', type: 'date', required: true, span: 1, default: isoDate(), validate: (v, a) => v < a.start_date ? 'Must be on or after the start date' : null },
        { name: 'half_day', label: 'Half day', type: 'checkbox', hint: 'Only for single-day leave' },
        { name: 'reason', label: 'Reason', type: 'textarea', required: true },
      ]}
      onSubmit={async (v) => { await api.post('/leave/requests', v); toast.success('Leave requested', 'Your approver has been notified.'); onDone?.() }} />
  )
}

function MyLeave({ applyOpen, setApplyOpen }) {
  const toast = useToast()
  const year = new Date().getFullYear()
  const bal = useApi('/leave/balances/me', { year })
  const reqs = useApi('/leave/requests', { scope: 'mine', page_size: 50 })
  const [cancel, setCancel] = useState(null)
  const [run, busy] = useAction(toast)
  const refresh = () => { bal.reload(); reqs.reload() }
  return (
    <div className="space-y-5">
      {bal.error ? <ErrorState message={bal.error} onRetry={bal.reload} /> : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {bal.loading ? [1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-32" />) : bal.data.map((b) => (
            <div key={b.id} className="card p-4">
              <div className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: b.leave_type.color }} /><p className="truncate text-[13px] font-medium text-muted">{b.leave_type.name}</p></div>
              <p className="num mt-2 text-[26px] font-semibold leading-tight">{b.leave_type.is_paid ? b.available : b.used}<span className="ml-1 text-sm font-normal text-muted">{b.leave_type.is_paid ? `/ ${b.allocated + b.carried}` : 'used'}</span></p>
              {b.leave_type.is_paid ? <Progress value={(b.allocated + b.carried) ? (b.available / (b.allocated + b.carried)) * 100 : 0} className="mt-3" /> : <p className="mt-3 text-xs text-muted">Unpaid · deducted in payroll</p>}
              <p className="mt-2 text-xs text-muted">{b.used} used{b.carried ? ` · ${b.carried} carried` : ''}</p>
            </div>
          ))}
        </div>
      )}
      <Card padded={false}>
        <div className="flex items-center justify-between p-5 pb-3"><h3 className="text-[15px] font-semibold">My requests</h3><Button size="sm" icon={CalendarPlus} onClick={() => setApplyOpen(true)}>Apply leave</Button></div>
        <DataTable loading={reqs.loading} error={reqs.error} onRetry={reqs.reload} rows={reqs.data?.items}
          empty={<EmptyState icon={CalendarDays} title="No leave requests yet" action={<Button size="sm" onClick={() => setApplyOpen(true)}>Apply leave</Button>} />}
          columns={[
            { key: 'type', header: 'Type', mobile: 'title', render: (r) => <span className="flex items-center gap-2 font-medium text-ink"><span className="h-2 w-2 rounded-full" style={{ background: r.leave_type.color }} />{r.leave_type.name}</span> },
            { key: 'dates', header: 'Dates', render: (r) => r.start_date === r.end_date ? fmtDate(r.start_date) : `${fmtDate(r.start_date, 'dd MMM')} – ${fmtDate(r.end_date)}` },
            { key: 'days', header: 'Days', align: 'right', render: (r) => r.days },
            { key: 'reason', header: 'Reason', className: 'max-w-[220px] truncate', render: (r) => r.reason },
            { key: 'status', header: 'Status', render: (r) => <span title={r.review_note || ''}><StatusBadge status={r.status} /></span> },
            { key: 'a', header: '', align: 'right', render: (r) => ['pending', 'approved'].includes(r.status) && r.start_date > isoDate() && <Button size="xs" variant="ghost" onClick={() => setCancel(r)}>Cancel</Button> },
          ]} />
      </Card>
      <ApplyModal open={applyOpen} onClose={() => setApplyOpen(false)} onDone={refresh} />
      <ConfirmDialog open={Boolean(cancel)} onClose={() => setCancel(null)} title="Cancel leave request" confirmLabel="Cancel request" loading={busy}
        description={`Cancel your ${cancel?.leave_type.name} from ${fmtDate(cancel?.start_date)}? Approved days are returned to your balance.`}
        onConfirm={async () => { await run(() => api.post(`/leave/requests/${cancel.id}/cancel`), { success: 'Request cancelled' }); setCancel(null); refresh() }} />
    </div>
  )
}

function Approvals() {
  const toast = useToast()
  const [status, setStatus] = useState('pending')
  const { data, loading, error, reload } = useApi('/leave/requests', { scope: 'approvals', status: status || undefined, page_size: 50 })
  const [reject, setReject] = useState(null)
  const [run, busy] = useAction(toast)
  return (
    <div className="card overflow-hidden">
      <Toolbar><Segmented value={status} onChange={setStatus} options={[{ value: 'pending', label: 'Pending' }, { value: 'approved', label: 'Approved' }, { value: 'rejected', label: 'Rejected' }, { value: '', label: 'All' }]} /></Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items}
        empty={<EmptyState icon={CalendarDays} title={status === 'pending' ? 'All caught up' : 'Nothing here'} description={status === 'pending' ? 'No leave requests are waiting for you.' : undefined} />}
        columns={[
          { key: 'emp', header: 'Employee', mobile: 'title', render: (r) => <PersonCell name={r.employee.full_name} subtitle={r.employee.department || r.employee.employee_code} fileId={r.employee.photo_file_id} /> },
          { key: 'type', header: 'Type', render: (r) => r.leave_type.name },
          { key: 'dates', header: 'Dates', render: (r) => `${fmtDate(r.start_date, 'dd MMM')} – ${fmtDate(r.end_date, 'dd MMM')}` },
          { key: 'days', header: 'Days', align: 'right', render: (r) => r.days },
          { key: 'reason', header: 'Reason', mobile: 'full', className: 'max-w-xs', render: (r) => <span className="line-clamp-2">{r.reason}</span> },
          { key: 'a', header: '', align: 'right', render: (r) => r.status === 'pending' ? (
            <div className="flex justify-end gap-1.5">
              <Button size="xs" variant="secondary" disabled={busy} onClick={() => setReject(r)}>Reject</Button>
              <Button size="xs" disabled={busy} onClick={async () => { await run(() => api.post(`/leave/requests/${r.id}/review`, { approve: true }), { success: 'Leave approved' }); reload() }}>Approve</Button>
            </div>) : <StatusBadge status={r.status} /> },
        ]} />
      <FormModal open={Boolean(reject)} onClose={() => setReject(null)} title="Reject leave request" submitLabel="Reject"
        fields={[{ name: 'note', label: 'Reason (shared with the employee)', type: 'textarea', required: true }]}
        onSubmit={async (v) => { await api.post(`/leave/requests/${reject.id}/review`, { approve: false, note: v.note }); toast.success('Leave rejected'); reload() }} />
    </div>
  )
}

function TeamCalendar() {
  const n = new Date()
  const [ym, setYm] = useState(`${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}`)
  const [y, m] = ym.split('-').map(Number)
  const last = new Date(y, m, 0).getDate()
  const { data, loading } = useApi('/leave/calendar', { date_from: `${ym}-01`, date_to: `${ym}-${last}` })
  const hols = useApi('/holidays', { year: y })
  const monthHols = (hols.data || []).filter((h) => h.date.startsWith(ym))
  return (
    <Card>
      <div className="mb-4 flex items-center justify-between"><h3 className="text-[15px] font-semibold">Who’s away</h3><Input type="month" value={ym} onChange={(e) => setYm(e.target.value)} className="h-9 w-40" /></div>
      {loading ? <Skeleton className="h-40" /> : (
        <div className="space-y-2">
          {monthHols.map((h) => (
            <div key={h.id} className="flex items-center gap-3 rounded-lg bg-brand-soft/60 px-3 py-2.5 text-sm"><CalendarDays className="h-4 w-4 text-brand-ink" /><span className="font-medium">{h.name}</span><span className="ml-auto text-xs text-muted">{fmtDate(h.date, 'EEE, dd MMM')}</span></div>
          ))}
          {data?.map((l) => (
            <div key={l.id} className="flex items-center gap-3 rounded-lg border border-line px-3 py-2.5">
              <span className="h-8 w-1 rounded-full" style={{ background: l.leave_type.color }} />
              <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{l.employee.full_name}</p><p className="text-xs text-muted">{l.leave_type.name}{l.half_day && ' · half day'}</p></div>
              <span className="whitespace-nowrap text-xs text-muted">{fmtDate(l.start_date, 'dd MMM')} – {fmtDate(l.end_date, 'dd MMM')}</span>
            </div>
          ))}
          {!data?.length && !monthHols.length && <EmptyState compact title="Everyone’s in this month" />}
        </div>
      )}
    </Card>
  )
}

function Holidays() {
  const { can } = useAuth()
  const toast = useToast()
  const [year, setYear] = useState(new Date().getFullYear())
  const { data, loading, error, reload } = useApi('/holidays', { year })
  const [form, setForm] = useState(null)
  const [del, setDel] = useState(null)
  const [run, busy] = useAction(toast)
  const manage = can('leave.configure')
  return (
    <div className="card overflow-hidden">
      <Toolbar>
        <Segmented value={year} onChange={setYear} options={[year - 1, new Date().getFullYear(), new Date().getFullYear() + 1].filter((v, i, a) => a.indexOf(v) === i).sort().map((v) => ({ value: v, label: String(v) }))} />
        {manage && <Button size="sm" icon={Plus} className="sm:ml-auto" onClick={() => setForm({})}>Add holiday</Button>}
      </Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data}
        empty={<EmptyState icon={CalendarDays} title={`No holidays for ${year}`} description={manage ? 'Add the company holiday calendar.' : undefined} />}
        columns={[
          { key: 'date', header: 'Date', mobile: 'title', render: (h) => <span className="font-medium text-ink">{fmtDate(h.date, 'EEE, dd MMM yyyy')}</span> },
          { key: 'name', header: 'Holiday', render: (h) => h.name },
          { key: 'type', header: 'Type', render: (h) => h.is_optional ? <Badge tone="info">Optional</Badge> : <Badge tone="brand">Company holiday</Badge> },
          { key: 'a', header: '', align: 'right', render: (h) => manage && <div className="flex justify-end gap-1"><IconButton icon={Pencil} size="sm" label="Edit" onClick={() => setForm(h)} /><IconButton icon={Trash2} size="sm" variant="danger" label="Delete" onClick={() => setDel(h)} /></div> },
        ]} />
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={form?.id ? 'Edit holiday' : 'Add holiday'} initial={form}
        fields={[{ name: 'date', label: 'Date', type: 'date', required: true, span: 1 }, { name: 'name', label: 'Name', required: true, span: 1 },
          { name: 'is_optional', label: 'Optional holiday', type: 'checkbox', hint: 'Optional holidays do not count as off days' }, { name: 'description', label: 'Notes', type: 'textarea' }]}
        onSubmit={async (v) => { form.id ? await api.put(`/holidays/${form.id}`, v) : await api.post('/holidays', v); toast.success('Holiday saved'); reload() }} />
      <ConfirmDialog open={Boolean(del)} onClose={() => setDel(null)} title="Delete holiday" description={`Delete ${del?.name}?`} confirmLabel="Delete" loading={busy}
        onConfirm={async () => { await run(() => api.delete(`/holidays/${del.id}`), { success: 'Deleted' }); setDel(null); reload() }} />
    </div>
  )
}

function LeaveSettings() {
  const toast = useToast()
  const { data, loading, error, reload } = useApi('/leave/types')
  const [form, setForm] = useState(null)
  return (
    <div className="card overflow-hidden">
      <Toolbar><p className="text-sm text-muted">Leave types and annual quotas. New employees receive a pro-rated allocation.</p><Button size="sm" icon={Plus} className="sm:ml-auto" onClick={() => setForm({})}>New leave type</Button></Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data}
        columns={[
          { key: 'name', header: 'Leave type', mobile: 'title', render: (t) => <span className="flex items-center gap-2 font-medium text-ink"><span className="h-2.5 w-2.5 rounded-full" style={{ background: t.color }} />{t.name} <Badge>{t.code}</Badge></span> },
          { key: 'quota', header: 'Annual quota', align: 'right', render: (t) => t.annual_quota },
          { key: 'paid', header: 'Paid', render: (t) => t.is_paid ? 'Paid' : 'Unpaid' },
          { key: 'cf', header: 'Carry forward', render: (t) => t.carry_forward ? `Up to ${t.max_carry_forward}` : 'No' },
          { key: 'st', header: 'Status', render: (t) => t.is_active ? <Badge tone="success" dot>Active</Badge> : <Badge dot>Inactive</Badge> },
          { key: 'a', header: '', align: 'right', render: (t) => <IconButton icon={Pencil} size="sm" label="Edit" onClick={() => setForm(t)} /> },
        ]} />
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={form?.id ? 'Edit leave type' : 'New leave type'} initial={form}
        fields={[
          { name: 'name', label: 'Name', required: true, span: 1 }, { name: 'code', label: 'Code', required: true, span: 1 },
          { name: 'annual_quota', label: 'Annual quota (days)', type: 'number', min: 0, step: 0.5, default: 0, span: 1 },
          { name: 'color', label: 'Colour', type: 'color', default: '#00BEA3', span: 1 },
          { name: 'is_paid', label: 'Paid leave', type: 'checkbox', default: true },
          { name: 'carry_forward', label: 'Allow carry forward', type: 'checkbox' },
          { name: 'max_carry_forward', label: 'Max carry forward (days)', type: 'number', min: 0, default: 0, hidden: (v) => !v.carry_forward },
          { name: 'description', label: 'Description' }, { name: 'is_active', label: 'Active', type: 'checkbox', default: true },
        ]}
        onSubmit={async (v) => { form.id ? await api.put(`/leave/types/${form.id}`, v) : await api.post('/leave/types', v); toast.success('Leave type saved'); reload() }} />
    </div>
  )
}

export default function LeavePage() {
  const { can, employee } = useAuth()
  const [params, setParams] = useSearchParams()
  const [applyOpen, setApplyOpen] = useState(params.get('apply') === '1')
  const tab = params.get('tab') || (employee ? 'mine' : 'approvals')
  const canApprove = can('leave.approve') || Boolean(employee)
  return (
    <>
      <PageHeader title="Leave" description="Balances, requests, approvals and the holiday calendar."
        actions={employee && <Button icon={CalendarPlus} onClick={() => { setParams({ tab: 'mine' }); setApplyOpen(true) }}>Apply leave</Button>} />
      <Tabs className="mb-5" value={tab} onChange={(t) => setParams({ tab: t })} tabs={[
        { value: 'mine', label: 'My leave', hidden: !employee },
        { value: 'approvals', label: 'Approvals', hidden: !canApprove },
        { value: 'calendar', label: 'Team calendar' },
        { value: 'holidays', label: 'Holidays' },
        { value: 'settings', label: 'Leave types', hidden: !can('leave.configure') },
      ]} />
      {tab === 'mine' && employee && <MyLeave applyOpen={applyOpen} setApplyOpen={setApplyOpen} />}
      {tab === 'approvals' && <Approvals />}
      {tab === 'calendar' && <TeamCalendar />}
      {tab === 'holidays' && <Holidays />}
      {tab === 'settings' && can('leave.configure') && <LeaveSettings />}
    </>
  )
}
