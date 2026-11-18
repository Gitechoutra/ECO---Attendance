import { useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Camera, FileText, KeyRound, MoreHorizontal, Pencil, RotateCcw, ScanFace, Trash2, Upload, UserMinus, UserPlus,
} from 'lucide-react'
import { api, downloadFile } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import {
  Avatar, Badge, Button, Card, CardHeader, ConfirmDialog, DataTable, DescriptionList, EmptyState, ErrorState, Field,
  FileDrop, FormModal, IconButton, Input, Menu, Modal, PageHeader, Select, Skeleton, StatusBadge, Tabs,
} from '../../components/ui'
import { fmtBytes, fmtDate, fmtDateTime, fmtMinutes, fmtMoney, isoDate, titleCase } from '../../lib/format'
import EmployeeForm, { TempPasswordModal } from './EmployeeForm'
import FaceEnrollModal from '../attendance/FaceEnrollModal'

const DOC_CATEGORIES = ['id_proof', 'address_proof', 'education', 'experience', 'offer_letter', 'contract', 'resume', 'other']

function Documents({ emp, canManage }) {
  const toast = useToast()
  const { data, loading, error, reload } = useApi(`/employees/${emp.id}/documents`)
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState(null)
  const [category, setCategory] = useState('id_proof')
  const [desc, setDesc] = useState('')
  const [del, setDel] = useState(null)
  const [run, busy] = useAction(toast)
  const upload = async () => {
    const fd = new FormData()
    fd.append('file', file); fd.append('category', category); if (desc) fd.append('description', desc)
    await run(() => api.post(`/employees/${emp.id}/documents`, fd), { success: 'Document uploaded' })
    setOpen(false); setFile(null); setDesc(''); reload()
  }
  return (
    <Card padded={false}>
      <div className="flex items-center justify-between p-5 pb-3">
        <h3 className="text-[15px] font-semibold">Documents</h3>
        <Button size="sm" icon={Upload} onClick={() => setOpen(true)}>Upload</Button>
      </div>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data}
        empty={<EmptyState icon={FileText} title="No documents yet" description="Upload ID proofs, certificates and letters." />}
        columns={[
          { key: 'name', header: 'Document', mobile: 'title', render: (d) => <button className="link text-left" onClick={() => downloadFile(`/files/${d.id}`, { inline: false }, d.name)}>{d.name}</button> },
          { key: 'category', header: 'Category', render: (d) => <Badge>{titleCase(d.category)}</Badge> },
          { key: 'size', header: 'Size', render: (d) => fmtBytes(d.size) },
          { key: 'created_at', header: 'Uploaded', render: (d) => fmtDate(d.created_at) },
          { key: 'a', header: '', align: 'right', render: (d) => canManage && <IconButton icon={Trash2} label="Delete" variant="danger" size="sm" onClick={() => setDel(d)} /> },
        ]} />
      <Modal open={open} onClose={() => setOpen(false)} title="Upload document" footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button disabled={!file} loading={busy} onClick={upload}>Upload</Button></>}>
        <div className="space-y-4">
          <FileDrop value={file} onChange={setFile} />
          <Field label="Category"><Select value={category} onChange={(e) => setCategory(e.target.value)} options={DOC_CATEGORIES.map((c) => ({ value: c, label: titleCase(c) }))} /></Field>
          <Field label="Description"><Input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Optional" /></Field>
        </div>
      </Modal>
      <ConfirmDialog open={Boolean(del)} onClose={() => setDel(null)} title="Delete document" description={`Delete “${del?.name}”? This cannot be undone.`}
        confirmLabel="Delete" loading={busy} onConfirm={async () => { await run(() => api.delete(`/employees/${emp.id}/documents/${del.id}`), { success: 'Document deleted' }); setDel(null); reload() }} />
    </Card>
  )
}

function AttendanceTab({ emp }) {
  const now = new Date()
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  const [y, m] = month.split('-').map(Number)
  const last = new Date(y, m, 0).getDate()
  const { data, loading, error, reload } = useApi('/attendance/records', { employee_id: emp.id, date_from: `${month}-01`, date_to: `${month}-${last}`, page_size: 31 })
  return (
    <Card padded={false}>
      <div className="flex items-center justify-between gap-3 p-5 pb-3">
        <h3 className="text-[15px] font-semibold">Attendance</h3>
        <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-44" />
      </div>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items} dense
        empty={<EmptyState compact title="No attendance this month" />}
        columns={[
          { key: 'work_date', header: 'Date', mobile: 'title', render: (r) => fmtDate(r.work_date, 'EEE, dd MMM') },
          { key: 'in', header: 'In', render: (r) => r.check_in_local || '—' },
          { key: 'out', header: 'Out', render: (r) => r.check_out_local || '—' },
          { key: 'worked', header: 'Worked', render: (r) => fmtMinutes(r.worked_minutes) },
          { key: 'method', header: 'Method', render: (r) => titleCase(r.check_in_method || '—') },
          { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
        ]} />
    </Card>
  )
}

function LeaveTab({ emp }) {
  const { data, loading, error, reload } = useApi('/leave/requests', { scope: 'all', employee_id: emp.id, page_size: 50 })
  return (
    <Card padded={false}>
      <div className="p-5 pb-3"><h3 className="text-[15px] font-semibold">Leave history</h3></div>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items} empty={<EmptyState compact title="No leave requests" />}
        columns={[
          { key: 'type', header: 'Type', mobile: 'title', render: (r) => r.leave_type.name },
          { key: 'dates', header: 'Dates', render: (r) => `${fmtDate(r.start_date, 'dd MMM')} – ${fmtDate(r.end_date, 'dd MMM yyyy')}` },
          { key: 'days', header: 'Days', align: 'right', render: (r) => r.days },
          { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
        ]} />
    </Card>
  )
}

function SalaryTab({ emp }) {
  const { data, loading, error, reload } = useApi(`/payroll/structures/${emp.id}`)
  if (error) return <ErrorState message={error} onRetry={reload} />
  return (
    <Card>
      <CardHeader title="Salary structure history" subtitle="Manage structures from Payroll" />
      {loading ? <Skeleton className="h-24" /> : !data?.length ? <EmptyState compact title="No salary structure" description="Add one from Payroll → Salary structures." /> : (
        <div className="space-y-4">
          {data.map((s) => (
            <div key={s.id} className="rounded-lg border border-line p-4">
              <div className="flex items-center justify-between"><p className="text-sm font-semibold">Effective {fmtDate(s.effective_from)}</p><p className="num text-sm">Basic {fmtMoney(s.monthly_basic)}/mo</p></div>
              <div className="mt-2 flex flex-wrap gap-2">{s.items.map((i) => <Badge key={i.code} tone={i.kind === 'earning' ? 'brand' : 'warning'}>{i.name}: {i.calc_type === 'fixed' ? fmtMoney(i.value) : `${i.value}%`}</Badge>)}</div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function History({ emp }) {
  const { data, loading } = useApi(`/employees/${emp.id}/history`)
  if (loading) return <Skeleton className="h-40" />
  return (
    <Card>
      <CardHeader title="Employee history" />
      <ol className="relative space-y-5 border-l border-line pl-5">
        {data?.map((h) => (
          <li key={h.id} className="relative">
            <span className="absolute -left-[25px] top-1 h-2.5 w-2.5 rounded-full border-2 border-surface bg-brand" />
            <p className="text-sm font-medium">{h.description}</p>
            <p className="text-xs text-muted">{fmtDateTime(h.created_at)}{h.changed_by && ` · ${h.changed_by}`}</p>
            {h.changes && (
              <div className="mt-1.5 space-y-0.5 text-xs text-ink-2">
                {Object.entries(h.changes).map(([k, [a, b]]) => <p key={k}><span className="text-muted">{titleCase(k)}:</span> {a ?? '—'} → <span className="font-medium">{b ?? '—'}</span></p>)}
              </div>
            )}
          </li>
        ))}
      </ol>
    </Card>
  )
}

export default function EmployeeDetailPage() {
  const { id } = useParams()
  const { can, employee: me } = useAuth()
  const toast = useToast()
  const { data: emp, loading, error, reload } = useApi(`/employees/${id}`)
  const face = useApi(`/attendance/face/status/${id}`, null, { enabled: can('attendance.enroll_face') })
  const [tab, setTab] = useState('overview')
  const [edit, setEdit] = useState(false)
  const [deact, setDeact] = useState(false)
  const [enroll, setEnroll] = useState(false)
  const [tempPw, setTempPw] = useState(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const [run, busy] = useAction(toast)
  const photoRef = useRef(null)

  if (error) return <ErrorState message={error} onRetry={reload} />
  if (loading || !emp) return <div className="space-y-4"><Skeleton className="h-28" /><Skeleton className="h-64" /></div>
  const full = 'address' in emp
  const canManage = can('employees.manage')
  const isMe = me?.id === emp.id

  const uploadPhoto = async (file) => {
    if (!file) return
    const fd = new FormData(); fd.append('file', file)
    await run(() => api.post(`/employees/${emp.id}/photo`, fd), { success: 'Photo updated' })
    reload()
  }

  return (
    <>
      <PageHeader title={emp.full_name} breadcrumbs={[{ label: 'Employees', to: can('employees.view_all') ? '/employees' : undefined }, { label: emp.employee_code }]} />
      <Card className="mb-5">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <div className="relative w-fit">
            <Avatar name={emp.full_name} fileId={emp.photo_file_id} size="xl" />
            {(canManage || isMe) && (
              <>
                <button onClick={() => photoRef.current?.click()} className="absolute -bottom-1 -right-1 flex h-8 w-8 items-center justify-center rounded-full border-2 border-surface bg-ink text-surface" aria-label="Change photo"><Camera className="h-3.5 w-3.5" /></button>
                <input ref={photoRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => uploadPhoto(e.target.files?.[0])} />
              </>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold">{emp.full_name}</h2>
              <StatusBadge status={emp.status} />
              {face.data?.enrolled && <Badge tone="brand"><ScanFace className="h-3 w-3" />Face enrolled</Badge>}
            </div>
            <p className="mt-1 text-sm text-muted">{[emp.designation?.title, emp.department?.name, emp.employee_code].filter(Boolean).join(' · ')}</p>
            <p className="mt-0.5 text-sm text-muted">{emp.email}{emp.phone && ` · ${emp.phone}`}</p>
          </div>
          {canManage && full && (
            <div className="flex gap-2">
              <Button variant="secondary" icon={Pencil} onClick={() => setEdit(true)}>Edit</Button>
              <Menu trigger={<IconButton icon={MoreHorizontal} label="More actions" variant="outline" />} items={[
                { label: face.data?.enrolled ? 'Re-enroll face' : 'Enroll face', icon: ScanFace, onClick: () => setEnroll(true), hidden: !can('attendance.enroll_face') || emp.status === 'inactive' },
                { label: 'Create login', icon: UserPlus, hidden: Boolean(emp.account), onClick: async () => { const r = await run(() => api.post(`/employees/${emp.id}/account`, { role_code: 'employee' })); setTempPw(r.data); reload() } },
                { label: 'Reset password', icon: KeyRound, hidden: !emp.account || !can('admin.users'), onClick: () => setConfirmReset(true) },
                { label: 'Reactivate', icon: RotateCcw, hidden: emp.status === 'active', onClick: async () => { await run(() => api.post(`/employees/${emp.id}/reactivate`), { success: 'Employee reactivated' }); reload() } },
                { label: 'Deactivate / exit', icon: UserMinus, danger: true, hidden: emp.status === 'inactive' || isMe, onClick: () => setDeact(true) },
              ]} />
            </div>
          )}
        </div>
      </Card>

      {full ? (
        <>
          <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[
            { value: 'overview', label: 'Overview' }, { value: 'documents', label: 'Documents' },
            { value: 'attendance', label: 'Attendance', hidden: !can('attendance.view_all') },
            { value: 'leave', label: 'Leave', hidden: !can('leave.view_all') },
            { value: 'salary', label: 'Salary', hidden: !can('payroll.view') },
            { value: 'history', label: 'History' },
          ]} />
          {tab === 'overview' && (
            <div className="grid gap-4 lg:grid-cols-2">
              <Card><CardHeader title="Employment" /><DescriptionList items={[
                ['Employee ID', emp.employee_code], ['Department', emp.department?.name], ['Designation', emp.designation?.title],
                ['Reporting manager', emp.manager?.full_name], ['Employment type', titleCase(emp.employment_type)], ['Work location', emp.work_location],
                ['Joining date', fmtDate(emp.joining_date)], ['Probation ends', emp.probation_end_date && fmtDate(emp.probation_end_date)],
                emp.exit_date && ['Exit date', fmtDate(emp.exit_date)], emp.exit_reason && ['Exit reason', emp.exit_reason],
                ['Login', emp.account ? `${emp.account.role_name}${emp.account.is_active ? '' : ' (disabled)'}` : 'No login'],
                emp.account && ['Last sign-in', emp.account.last_login_at ? fmtDateTime(emp.account.last_login_at) : 'Never'],
              ]} /></Card>
              <Card><CardHeader title="Personal" /><DescriptionList items={[
                ['Date of birth', emp.date_of_birth && fmtDate(emp.date_of_birth)], ['Gender', emp.gender], ['Marital status', emp.marital_status],
                ['Blood group', emp.blood_group], ['Personal email', emp.personal_email],
                ['Address', [emp.address, emp.city, emp.state, emp.postal_code, emp.country].filter(Boolean).join(', ')],
                ['Emergency contact', emp.emergency_contact_name && `${emp.emergency_contact_name} · ${emp.emergency_contact_phone || ''}`],
              ]} /></Card>
              <Card className="lg:col-span-2"><CardHeader title="Bank & identity" subtitle="Stored encrypted. Full values are visible only to authorised HR." /><DescriptionList cols={3} items={[
                ['Bank', emp.bank_name], ['Account number', emp.bank_account], ['IFSC', emp.bank_ifsc], ['PAN', emp.pan], ['National ID', emp.national_id],
              ]} /></Card>
            </div>
          )}
          {tab === 'documents' && <Documents emp={emp} canManage={canManage} />}
          {tab === 'attendance' && <AttendanceTab emp={emp} />}
          {tab === 'leave' && <LeaveTab emp={emp} />}
          {tab === 'salary' && <SalaryTab emp={emp} />}
          {tab === 'history' && <History emp={emp} />}
        </>
      ) : (
        <Card><DescriptionList items={[['Department', emp.department?.name], ['Designation', emp.designation?.title], ['Email', emp.email], ['Phone', emp.phone], ['Joined', fmtDate(emp.joining_date)]]} /></Card>
      )}

      <EmployeeForm open={edit} onClose={() => setEdit(false)} employee={emp} onSaved={reload} />
      <FaceEnrollModal open={enroll} onClose={() => setEnroll(false)} employee={emp} onEnrolled={() => face.reload()} />
      <TempPasswordModal open={Boolean(tempPw)} onClose={() => setTempPw(null)} email={tempPw?.email || emp.email} password={tempPw?.temporary_password} />
      <ConfirmDialog open={confirmReset} onClose={() => setConfirmReset(false)} tone="primary" title="Reset password"
        description={`Generate a new temporary password for ${emp.full_name}? Their current sessions will be signed out.`} confirmLabel="Reset" loading={busy}
        onConfirm={async () => { const r = await run(() => api.post(`/employees/${emp.id}/reset-password`)); setConfirmReset(false); setTempPw({ ...r.data, email: emp.email }) }} />
      <FormModal open={deact} onClose={() => setDeact(false)} title={`Deactivate ${emp.full_name}`} submitLabel="Confirm"
        description="Inactive employees lose login access immediately. Records are retained."
        fields={[
          { name: 'status', label: 'New status', type: 'select', required: true, default: 'inactive', options: [{ value: 'on_notice', label: 'On notice (keeps access)' }, { value: 'inactive', label: 'Inactive (exit now)' }] },
          { name: 'exit_date', label: 'Exit / last working date', type: 'date', required: true, default: isoDate() },
          { name: 'exit_reason', label: 'Reason', type: 'textarea', required: true },
        ]}
        onSubmit={async (v) => { await api.post(`/employees/${emp.id}/deactivate`, v); toast.success('Status updated'); reload() }} />
    </>
  )
}
