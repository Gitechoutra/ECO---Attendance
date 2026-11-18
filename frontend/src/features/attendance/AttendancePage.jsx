import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { ArrowRight, CalendarCheck, Clock, Coffee, Download, LogIn, LogOut, Plus, ScanFace } from 'lucide-react'
import { api, downloadFile } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions } from '../../hooks/useOptions'
import {
  Badge, Button, Card, CardHeader, DataTable, EmptyState, ErrorState, FormModal, Input, Modal, PageHeader, Pagination,
  PersonCell, Segmented, Select, Skeleton, StatCard, StatusBadge, Tabs, Toolbar,
} from '../../components/ui'
import { fmtDate, fmtMinutes, isoDate, titleCase } from '../../lib/format'
import FaceCapture from './FaceCapture'
import FaceEnrollModal from './FaceEnrollModal'

function useMonth() {
  const n = new Date()
  const [ym, setYm] = useState(`${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}`)
  const [y, m] = ym.split('-').map(Number)
  return { ym, setYm, y, m }
}

const DOT = { present: 'bg-success', late: 'bg-warning', half_day: 'bg-warning', absent: 'bg-danger', on_leave: 'bg-info' }

function MonthCalendar({ y, m, records, workingDays }) {
  const recs = Object.fromEntries(records.map((r) => [r.work_date, r]))
  const wd = new Set(workingDays)
  const first = new Date(y, m - 1, 1)
  const offset = (first.getDay() + 6) % 7
  const days = new Date(y, m, 0).getDate()
  const today = isoDate()
  const cells = [...Array(offset).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)]
  return (
    <div>
      <div className="mb-2 grid grid-cols-7 text-center text-2xs font-semibold uppercase tracking-wide text-faint">
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <span key={d}>{d}</span>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((d, i) => {
          if (!d) return <span key={`e${i}`} />
          const iso = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
          const r = recs[iso]
          const off = !wd.has(iso)
          const missed = !r && !off && iso < today
          return (
            <div key={iso} title={r ? `${titleCase(r.status)} · ${r.check_in_local || ''}–${r.check_out_local || ''}` : off ? 'Off day' : ''}
              className={clsx('flex aspect-square flex-col items-center justify-center rounded-lg text-[13px]',
                iso === today && 'ring-2 ring-brand', off ? 'text-faint' : 'bg-surface-2 text-ink-2')}>
              <span className="num">{d}</span>
              <span className={clsx('mt-1 h-1.5 w-1.5 rounded-full', r ? DOT[r.status] || 'bg-success' : missed ? 'bg-danger/60' : 'bg-transparent')} />
            </div>
          )
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted">
        {[['Present', 'bg-success'], ['Late / half day', 'bg-warning'], ['On leave', 'bg-info'], ['Absent', 'bg-danger']].map(([l, c]) => (
          <span key={l} className="flex items-center gap-1.5"><span className={clsx('h-2 w-2 rounded-full', c)} />{l}</span>
        ))}
      </div>
    </div>
  )
}

function CorrectionModal({ open, onClose, onDone, kind = 'correction' }) {
  const toast = useToast()
  return (
    <FormModal open={open} onClose={onClose} title={kind === 'manual' ? 'Request manual attendance' : 'Request attendance correction'}
      description={kind === 'manual' ? 'Use this when the camera or verification fails. HR will review your request.' : 'Fix a missed or incorrect check-in / check-out.'}
      submitLabel="Submit request"
      fields={[
        { name: 'work_date', label: 'Date', type: 'date', required: true, default: isoDate(), max: isoDate() },
        { name: 'check_in', label: 'Check-in time', type: 'time', span: 1 },
        { name: 'check_out', label: 'Check-out time', type: 'time', span: 1, validate: (v, all) => v && all.check_in && v <= all.check_in ? 'Must be after check-in' : null },
        { name: 'reason', label: 'Reason', type: 'textarea', required: true, validate: (v) => (v || '').length < 5 ? 'Please explain in a few words' : null },
      ]}
      onSubmit={async (v) => {
        if (!v.check_in && !v.check_out) throw { response: { data: { detail: 'Enter a check-in or check-out time' } } }
        await api.post('/attendance/corrections', { ...v, kind })
        toast.success('Request submitted', 'You’ll be notified once it is reviewed.')
        onDone?.()
      }} />
  )
}

function MyAttendance() {
  const toast = useToast()
  const { employee } = useAuth()
  const [enrolling, setEnrolling] = useState(false)
  const today = useApi('/attendance/today')
  const { ym, setYm, y, m } = useMonth()
  const month = useApi('/attendance/my', { year: y, month: m })
  const requests = useApi('/attendance/corrections', { mine: true, page_size: 10 })
  const [faceFor, setFaceFor] = useState(null)
  const [corr, setCorr] = useState(null)
  const [run, busy] = useAction(toast)
  const refresh = () => { today.reload(); month.reload(); requests.reload() }

  if (today.error) return <ErrorState message={today.error} onRetry={today.reload} />
  const t = today.data
  const r = t?.record
  const state = !r?.check_in_at ? 'out' : r.check_out_at ? 'done' : 'in'
  const act = async (purpose) => {
    if (t.face_required) { setFaceFor(purpose); return }
    await run(() => api.post(purpose === 'check_in' ? '/attendance/check-in' : '/attendance/check-out'), { success: purpose === 'check_in' ? 'Checked in' : 'Checked out' })
    refresh()
  }
  const s = month.data?.summary

  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <Card>
          {today.loading ? <Skeleton className="h-48" /> : (
            <>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium text-muted">{fmtDate(t.date, 'EEEE, dd MMMM')}</p>
                  <p className="mt-1 text-2xl font-semibold">{state === 'out' ? 'Not checked in' : state === 'in' ? (r.on_break ? 'On break' : 'Working') : 'Day complete'}</p>
                  <p className="mt-1 text-sm text-muted">Shift {t.shift.start} – {t.shift.end} · {t.shift.grace_minutes} min grace</p>
                </div>
                {t.face_required && <Badge tone={t.face_enrolled ? 'brand' : 'warning'}><ScanFace className="h-3 w-3" />{t.face_enrolled ? 'Face verified' : 'Face not enrolled'}</Badge>}
              </div>
              <div className="mt-5 grid grid-cols-3 gap-3 rounded-xl bg-surface-2 p-4 text-center">
                <div><p className="text-2xs font-medium uppercase tracking-wide text-faint">Check in</p><p className="num mt-1 text-lg font-semibold">{r?.check_in_local || '—'}</p>{r?.late_minutes > 0 && <p className="text-2xs text-warning">{r.late_minutes} min late</p>}</div>
                <div><p className="text-2xs font-medium uppercase tracking-wide text-faint">Check out</p><p className="num mt-1 text-lg font-semibold">{r?.check_out_local || '—'}</p></div>
                <div><p className="text-2xs font-medium uppercase tracking-wide text-faint">Worked</p><p className="num mt-1 text-lg font-semibold">{r?.check_out_at ? fmtMinutes(r.worked_minutes) : '—'}</p>{r?.break_minutes > 0 && <p className="text-2xs text-muted">{r.break_minutes} min breaks</p>}</div>
              </div>
              {!t.is_working_day && state === 'out' && <p className="mt-4 text-[13px] text-muted">Today is not a working day. You can still check in if you are working.</p>}
              {t.face_required && !t.face_enrolled && (
                <div className="mt-4 flex flex-col gap-3 rounded-xl border border-warning/30 bg-warning-soft p-4 sm:flex-row sm:items-center">
                  <ScanFace className="h-5 w-5 shrink-0 text-warning" />
                  <p className="flex-1 text-[13px] text-warning">Set up face check-in once with a quick live camera scan (about 6 seconds). Your profile photo can’t be used, because attendance needs live verification.</p>
                  <Button size="sm" icon={ScanFace} onClick={() => setEnrolling(true)}>Set up face check-in</Button>
                </div>
              )}
              <div className="mt-5 flex flex-wrap gap-2">
                {state === 'out' && <Button size="lg" icon={LogIn} onClick={() => act('check_in')} loading={busy} disabled={t.face_required && !t.face_enrolled} className="flex-1">Check in</Button>}
                {state === 'in' && (
                  <>
                    <Button size="lg" icon={LogOut} onClick={() => act('check_out')} loading={busy} disabled={t.face_required && !t.face_enrolled} className="flex-1">Check out</Button>
                    <Button size="lg" variant="secondary" icon={Coffee} loading={busy} onClick={async () => { await run(() => api.post('/attendance/break', { action: r.on_break ? 'end' : 'start' }), { success: r.on_break ? 'Break ended' : 'Break started' }); refresh() }}>
                      {r.on_break ? 'End break' : 'Take break'}
                    </Button>
                  </>
                )}
                {state !== 'done' && <Button size="lg" variant="ghost" onClick={() => setCorr('manual')}>Manual request</Button>}
              </div>
            </>
          )}
        </Card>
        <Card>
          <CardHeader title="My month" action={<Input type="month" value={ym} onChange={(e) => setYm(e.target.value)} className="h-9 w-40" />} />
          {month.loading && !month.data ? <Skeleton className="h-64" /> : month.data && <MonthCalendar y={y} m={m} records={month.data.records} workingDays={month.data.working_days} />}
        </Card>
      </div>

      {s && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <StatCard label="Present" value={s.present} icon={CalendarCheck} tone="success" hint={`of ${s.working_days} working days`} />
          <StatCard label="Late arrivals" value={s.late} icon={Clock} tone="warning" />
          <StatCard label="Half days" value={s.half_days} tone="warning" />
          <StatCard label="Leave" value={s.leave_days} tone="info" />
          <StatCard label="Hours worked" value={s.worked_hours} tone="neutral" hint={`${s.avg_hours} h avg/day`} />
        </div>
      )}

      <Card padded={false}>
        <div className="flex items-center justify-between p-5 pb-3">
          <h3 className="text-[15px] font-semibold">My requests</h3>
          <Button size="sm" variant="secondary" icon={Plus} onClick={() => setCorr('correction')}>Correction request</Button>
        </div>
        <DataTable loading={requests.loading} error={requests.error} rows={requests.data?.items} dense
          empty={<EmptyState compact title="No requests" description="Missed a check-in? Request a correction." />}
          columns={[
            { key: 'date', header: 'Date', mobile: 'title', render: (c) => fmtDate(c.work_date) },
            { key: 'kind', header: 'Type', render: (c) => titleCase(c.kind) },
            { key: 'times', header: 'Requested', render: (c) => `${c.requested_check_in || '—'} → ${c.requested_check_out || '—'}` },
            { key: 'reason', header: 'Reason', className: 'max-w-xs truncate', render: (c) => c.reason },
            { key: 'status', header: 'Status', render: (c) => <StatusBadge status={c.status} /> },
          ]} />
      </Card>

      <Modal open={Boolean(faceFor)} onClose={() => setFaceFor(null)} title={faceFor === 'check_in' ? 'Face check-in' : 'Face check-out'} size="md">
        {faceFor && (
          <FaceCapture purpose={faceFor} submitLabel={faceFor === 'check_in' ? 'Start live check-in' : 'Start live check-out'}
            submit={async (p) => (await api.post(faceFor === 'check_in' ? '/attendance/check-in/face' : '/attendance/check-out/face', p)).data}
            onDone={() => { toast.success(faceFor === 'check_in' ? 'Checked in' : 'Checked out'); setFaceFor(null); refresh() }}
            onFallback={() => { setFaceFor(null); setCorr('manual') }} />
        )}
      </Modal>
      <CorrectionModal open={Boolean(corr)} kind={corr} onClose={() => setCorr(null)} onDone={refresh} />
      <FaceEnrollModal open={enrolling} self employee={employee} onClose={() => setEnrolling(false)} onEnrolled={refresh} />
    </div>
  )
}

const STATE_LABEL = { working: 'Working', on_break: 'On break', checked_out: 'Checked out', not_checked_in: 'Not checked in', on_leave: 'On leave' }

function TeamToday() {
  const { data, loading, error, reload } = useApi('/attendance/live')
  const [filter, setFilter] = useState('all')
  const [q, setQ] = useState('')
  const rows = useMemo(() => (data?.rows || []).filter((r) => (filter === 'all' || r.state === filter) && r.employee.full_name.toLowerCase().includes(q.toLowerCase())), [data, filter, q])
  if (error) return <ErrorState message={error} onRetry={reload} />
  const c = data?.counts || {}
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard label="Working" value={c.working || 0} tone="success" loading={loading} />
        <StatCard label="On break" value={c.on_break || 0} tone="warning" loading={loading} />
        <StatCard label="Checked out" value={c.checked_out || 0} tone="neutral" loading={loading} />
        <StatCard label="On leave" value={c.on_leave || 0} tone="info" loading={loading} />
        <StatCard label="Not checked in" value={c.not_checked_in || 0} tone="danger" loading={loading} />
      </div>
      <div className="card overflow-hidden">
        <Toolbar>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by name" className="sm:w-64" />
          <div className="overflow-x-auto"><Segmented value={filter} onChange={setFilter} size="sm" options={[{ value: 'all', label: 'All' }, ...Object.entries(STATE_LABEL).map(([value, label]) => ({ value, label, count: c[value] || 0 }))]} /></div>
        </Toolbar>
        <DataTable loading={loading} rows={rows.map((r) => ({ ...r, key: r.employee.id }))} rowKey="key" dense
          empty={<EmptyState compact title="Nobody here" />}
          columns={[
            { key: 'emp', header: 'Employee', mobile: 'title', render: (r) => <PersonCell name={r.employee.full_name} subtitle={r.employee.department || r.employee.employee_code} fileId={r.employee.photo_file_id} /> },
            { key: 'state', header: 'Status', render: (r) => <StatusBadge status={r.state} label={STATE_LABEL[r.state]} /> },
            { key: 'in', header: 'In', render: (r) => r.record?.check_in_local || '—' },
            { key: 'out', header: 'Out', render: (r) => r.record?.check_out_local || '—' },
            { key: 'late', header: 'Late', render: (r) => r.record?.late_minutes ? <span className="text-warning">{r.record.late_minutes} min</span> : '—' },
            { key: 'method', header: 'Method', render: (r) => r.record?.check_in_method ? titleCase(r.record.check_in_method) : '—' },
          ].map((c2) => c2)}
        />
      </div>
    </div>
  )
}

function Records() {
  const depts = useOptions('departments')
  const emps = useOptions('employees')
  const [f, setF] = useState({ date_from: isoDate(new Date(Date.now() - 6 * 864e5)), date_to: isoDate(), employee_id: '', department_id: '', status: '' })
  const [page, setPage] = useState(1)
  const params = Object.fromEntries(Object.entries({ ...f, page, page_size: 25 }).filter(([, v]) => v !== ''))
  const { data, loading, error, reload } = useApi('/attendance/records', params)
  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value }); setPage(1) }
  return (
    <div className="card overflow-hidden">
      <Toolbar>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <Input type="date" value={f.date_from} onChange={set('date_from')} className="sm:w-40" />
          <Input type="date" value={f.date_to} onChange={set('date_to')} className="sm:w-40" />
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <Select value={f.employee_id} onChange={set('employee_id')} placeholder="All employees" options={emps} className="sm:w-52" />
          <Select value={f.department_id} onChange={set('department_id')} placeholder="All departments" options={depts} className="sm:w-44" />
          <Select value={f.status} onChange={set('status')} placeholder="Any status" className="sm:w-36" options={['present', 'late', 'half_day', 'absent', 'on_leave'].map((s) => ({ value: s, label: titleCase(s) }))} />
        </div>
        <Button variant="secondary" size="sm" icon={Download} className="sm:ml-auto" onClick={() => downloadFile('/reports/attendance', { format: 'xlsx', date_from: f.date_from, date_to: f.date_to, department_id: f.department_id || undefined })}>Export</Button>
      </Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items} dense
        empty={<EmptyState compact title="No attendance records for these filters" />}
        columns={[
          { key: 'emp', header: 'Employee', mobile: 'title', render: (r) => <PersonCell name={r.employee.full_name} subtitle={r.employee.employee_code} fileId={r.employee.photo_file_id} /> },
          { key: 'date', header: 'Date', render: (r) => fmtDate(r.work_date, 'EEE, dd MMM') },
          { key: 'in', header: 'In', render: (r) => r.check_in_local || '—' },
          { key: 'out', header: 'Out', render: (r) => r.check_out_local || '—' },
          { key: 'worked', header: 'Worked', render: (r) => fmtMinutes(r.worked_minutes) },
          { key: 'method', header: 'Method', render: (r) => titleCase(r.check_in_method || '—') },
          { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
        ]} />
      <Pagination page={page} pages={data?.pages} total={data?.total} pageSize={25} onChange={setPage} />
    </div>
  )
}

function Requests({ onChanged }) {
  const toast = useToast()
  const { employee: me } = useAuth()
  const [status, setStatus] = useState('pending')
  const { data, loading, error, reload } = useApi('/attendance/corrections', { status: status || undefined, page_size: 50 })
  const [run, busy] = useAction(toast)
  const review = async (c, approve) => { await run(() => api.post(`/attendance/corrections/${c.id}/review`, { approve }), { success: approve ? 'Approved' : 'Rejected' }); reload(); onChanged?.() }
  return (
    <div className="card overflow-hidden">
      <Toolbar><Segmented value={status} onChange={setStatus} options={[{ value: 'pending', label: 'Pending' }, { value: 'approved', label: 'Approved' }, { value: 'rejected', label: 'Rejected' }, { value: '', label: 'All' }]} /></Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data?.items}
        empty={<EmptyState compact icon={CalendarCheck} title={status === 'pending' ? 'No pending requests' : 'Nothing here'} />}
        columns={[
          { key: 'emp', header: 'Employee', mobile: 'title', render: (c) => <PersonCell name={c.employee.full_name} subtitle={c.employee.employee_code} /> },
          { key: 'date', header: 'Date', render: (c) => fmtDate(c.work_date) },
          { key: 'kind', header: 'Type', render: (c) => <Badge tone={c.kind === 'manual' ? 'info' : 'neutral'}>{titleCase(c.kind)}</Badge> },
          { key: 'times', header: 'Requested', render: (c) => `${c.requested_check_in || '—'} → ${c.requested_check_out || '—'}` },
          { key: 'reason', header: 'Reason', mobile: 'full', className: 'max-w-xs', render: (c) => <span className="line-clamp-2">{c.reason}</span> },
          { key: 'a', header: '', align: 'right', render: (c) => c.status === 'pending' && c.employee.id === me?.id ? <Badge tone="warning">Your request · needs another approver</Badge> : c.status === 'pending' ? (
            <div className="flex justify-end gap-1.5">
              <Button size="xs" variant="secondary" disabled={busy} onClick={() => review(c, false)}>Reject</Button>
              <Button size="xs" disabled={busy} onClick={() => review(c, true)}>Approve</Button>
            </div>) : <StatusBadge status={c.status} /> },
        ]} />
    </div>
  )
}

function Summary() {
  const { ym, setYm, y, m } = useMonth()
  const depts = useOptions('departments')
  const [dept, setDept] = useState('')
  const { data, loading, error, reload } = useApi('/attendance/summary', { year: y, month: m, department_id: dept || undefined })
  return (
    <div className="card overflow-hidden">
      <Toolbar>
        <Input type="month" value={ym} onChange={(e) => setYm(e.target.value)} className="sm:w-44" />
        <Select value={dept} onChange={(e) => setDept(e.target.value)} placeholder="All departments" options={depts} className="sm:w-48" />
        <Button variant="secondary" size="sm" icon={Download} className="sm:ml-auto" onClick={() => downloadFile('/reports/attendance', { format: 'pdf', date_from: `${ym}-01`, date_to: `${ym}-${new Date(y, m, 0).getDate()}`, department_id: dept || undefined })}>PDF</Button>
      </Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data?.map((r) => ({ ...r, id: r.employee.id }))} dense
        empty={<EmptyState compact title="No data for this month" />}
        columns={[
          { key: 'emp', header: 'Employee', mobile: 'title', render: (r) => <PersonCell name={r.employee.full_name} subtitle={r.employee.department || r.employee.employee_code} /> },
          { key: 'wd', header: 'Working', align: 'right', render: (r) => r.working_days },
          { key: 'p', header: 'Present', align: 'right', render: (r) => r.present },
          { key: 'h', header: 'Half', align: 'right', render: (r) => r.half_days },
          { key: 'l', header: 'Late', align: 'right', render: (r) => r.late },
          { key: 'lv', header: 'Leave', align: 'right', render: (r) => r.leave_days },
          { key: 'a', header: 'Absent', align: 'right', render: (r) => <span className={r.absent ? 'font-semibold text-danger' : ''}>{r.absent}</span> },
          { key: 'hrs', header: 'Hours', align: 'right', render: (r) => r.worked_hours },
        ]} />
    </div>
  )
}

export default function AttendancePage() {
  const { can, employee } = useAuth()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || (employee ? 'me' : 'team')
  const setTab = (t) => setParams({ tab: t })
  const pending = useApi(can('attendance.manage') ? '/attendance/corrections' : null, { status: 'pending', page_size: 1 })
  const pendingCount = pending.data?.total || 0
  return (
    <>
      <PageHeader title="Attendance" description="Verified check-ins, working hours and attendance requests." />
      {pendingCount > 0 && tab !== 'requests' && (
        <button onClick={() => setTab('requests')} className="mb-4 flex w-full items-center gap-3 rounded-xl border border-warning/30 bg-warning-soft px-4 py-3 text-left transition-colors hover:border-warning/60">
          <Clock className="h-5 w-5 shrink-0 text-warning" />
          <span className="flex-1 text-sm text-warning"><b>{pendingCount}</b> attendance request{pendingCount === 1 ? '' : 's'} waiting for your approval</span>
          <span className="flex items-center gap-1 text-sm font-semibold text-warning">Review<ArrowRight className="h-4 w-4" /></span>
        </button>
      )}
      <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[
        { value: 'me', label: 'My attendance', hidden: !employee },
        { value: 'team', label: 'Today', hidden: !can('attendance.view_all') },
        { value: 'records', label: 'Records', hidden: !can('attendance.view_all') },
        { value: 'summary', label: 'Monthly summary', hidden: !can('attendance.view_all') },
        { value: 'requests', label: 'Requests', count: pendingCount || undefined, hidden: !can('attendance.manage') },
      ]} />
      {tab === 'me' && employee && <MyAttendance />}
      {tab === 'team' && can('attendance.view_all') && <TeamToday />}
      {tab === 'records' && can('attendance.view_all') && <Records />}
      {tab === 'summary' && can('attendance.view_all') && <Summary />}
      {tab === 'requests' && can('attendance.manage') && <Requests onChanged={() => pending.reload({ silent: true })} />}
    </>
  )
}
