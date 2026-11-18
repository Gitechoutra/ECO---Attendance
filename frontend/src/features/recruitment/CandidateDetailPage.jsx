import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CalendarPlus, FileSignature, FileText, MessageSquareText, Pencil, Star, Upload, UserCheck } from 'lucide-react'
import { api, downloadFile } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions } from '../../hooks/useOptions'
import {
  Badge, Button, Card, CardHeader, DescriptionList, EmptyState, ErrorState, FormModal, PageHeader, Select, Skeleton,
  StatusBadge,
} from '../../components/ui'
import { fmtDate, fmtDateTime, fmtMoney, titleCase } from '../../lib/format'
import { TempPasswordModal } from '../employees/EmployeeForm'
import { candidateFields, STAGES } from './RecruitmentPage'

export default function CandidateDetailPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const { can } = useAuth()
  const toast = useToast()
  const { data: c, loading, error, reload } = useApi(`/recruitment/candidates/${id}`)
  const jobs = useApi('/recruitment/jobs')
  const emps = useOptions('employees')
  const depts = useOptions('departments')
  const desigs = useOptions('designations')
  const [edit, setEdit] = useState(false)
  const [schedule, setSchedule] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const [convert, setConvert] = useState(false)
  const [created, setCreated] = useState(null)
  const [run, busy] = useAction(toast)
  const fileRef = useRef(null)
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (loading || !c) return <Skeleton className="h-64" />
  const manage = can('recruitment.manage')
  const jobOpts = (jobs.data || []).map((j) => ({ value: j.id, label: j.title }))
  const accepted = c.offers.find((o) => o.status === 'accepted')

  return (
    <>
      <PageHeader title={c.full_name} breadcrumbs={[{ label: 'Recruitment', to: '/recruitment' }, { label: c.full_name }]}
        description={`${c.job?.title || 'General application'} · added ${fmtDate(c.created_at)}`}
        actions={manage && c.status !== 'hired' && <>
          <Button variant="secondary" icon={Pencil} onClick={() => setEdit(true)}>Edit</Button>
          {can('offers.manage') && <Button variant="secondary" icon={FileSignature} onClick={() => nav(`/offers?candidate=${c.id}`)}>Create offer</Button>}
          {can('employees.manage') && <Button icon={UserCheck} onClick={() => setConvert(true)}>Convert to employee</Button>}
        </>} />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader title="Profile" action={<div className="flex items-center gap-2"><StatusBadge status={c.status} />{c.rating && <span className="flex">{[1, 2, 3, 4, 5].map((i) => <Star key={i} className={`h-3.5 w-3.5 ${i <= c.rating ? 'fill-warning text-warning' : 'text-line-strong'}`} />)}</span>}</div>} />
            <DescriptionList items={[
              ['Email', <a key="e" className="link" href={`mailto:${c.email}`}>{c.email}</a>], ['Phone', c.phone], ['Current company', c.current_company],
              ['Experience', c.experience_years != null ? `${c.experience_years} years` : null], ['Current CTC', c.current_ctc && fmtMoney(c.current_ctc)],
              ['Expected CTC', c.expected_ctc && fmtMoney(c.expected_ctc)], ['Notice period', c.notice_period_days != null ? `${c.notice_period_days} days` : null],
              ['Source', c.source], ['Skills', c.skills],
            ]} />
            {c.notes && <p className="mt-4 whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-[13px] text-ink-2">{c.notes}</p>}
            {c.employee_id && <Link to={`/employees/${c.employee_id}`} className="mt-4 inline-block text-sm font-medium text-brand-ink hover:underline">View employee profile →</Link>}
          </Card>
          <Card>
            <CardHeader title="Interviews" icon={MessageSquareText} action={manage && c.status !== 'hired' && <Button size="sm" icon={CalendarPlus} onClick={() => setSchedule(true)}>Schedule</Button>} />
            {!c.interviews.length ? <EmptyState compact title="No interviews scheduled" /> : (
              <ul className="space-y-3">
                {c.interviews.map((i) => (
                  <li key={i.id} className="rounded-xl border border-line p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div><p className="text-sm font-semibold">{i.round_name}</p><p className="text-xs text-muted">{fmtDateTime(i.scheduled_at)} · {titleCase(i.mode)} · {i.interviewer?.full_name || 'No interviewer'}</p>{i.location && <p className="text-xs text-muted">{i.location}</p>}</div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={i.status} />
                        {i.recommendation && <Badge tone={i.recommendation === 'hire' ? 'success' : i.recommendation === 'no_hire' ? 'danger' : 'warning'}>{titleCase(i.recommendation)}</Badge>}
                        <Button size="xs" variant="secondary" onClick={() => setFeedback(i)}>Feedback</Button>
                      </div>
                    </div>
                    {i.feedback && <p className="mt-2 whitespace-pre-wrap text-[13px] text-ink-2">{i.feedback}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <div className="space-y-4">
          {manage && c.status !== 'hired' && (
            <Card>
              <CardHeader title="Stage" />
              <Select value={c.status} disabled={busy} options={STAGES.filter((s) => s !== 'hired').map((s) => ({ value: s, label: titleCase(s) }))}
                onChange={async (e) => { await run(() => api.patch(`/recruitment/candidates/${c.id}/status`, { status: e.target.value }), { success: 'Stage updated' }); reload() }} />
            </Card>
          )}
          <Card>
            <CardHeader title="Resume" icon={FileText} />
            {c.resume_file_id ? <Button variant="secondary" className="w-full" onClick={() => downloadFile(`/files/${c.resume_file_id}`, { inline: false }, `${c.full_name}-resume`)}>Download resume</Button> : <p className="text-sm text-muted">No resume uploaded.</p>}
            {manage && (
              <>
                <Button variant="ghost" icon={Upload} className="mt-2 w-full" loading={busy} onClick={() => fileRef.current?.click()}>{c.resume_file_id ? 'Replace' : 'Upload'} resume</Button>
                <input ref={fileRef} type="file" accept=".pdf,.doc,.docx" className="hidden" onChange={async (e) => {
                  const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append('file', f)
                  await run(() => api.post(`/recruitment/candidates/${c.id}/resume`, fd), { success: 'Resume uploaded' }); reload()
                }} />
              </>
            )}
          </Card>
          <Card>
            <CardHeader title="Offer letters" icon={FileSignature} />
            {!c.offers.length ? <p className="text-sm text-muted">No offers yet.</p> : (
              <ul className="space-y-2">{c.offers.map((o) => (
                <li key={o.id}><Link to={`/offers/${o.id}`} className="flex items-center justify-between rounded-lg border border-line p-3 hover:border-line-strong">
                  <span><span className="block text-[13px] font-medium">{o.reference_no}</span><span className="text-xs text-muted">{o.designation} · {fmtMoney(o.annual_ctc)}</span></span><StatusBadge status={o.status} />
                </Link></li>))}</ul>
            )}
          </Card>
        </div>
      </div>

      <FormModal open={edit} onClose={() => setEdit(false)} title="Edit candidate" size="lg" initial={c} fields={candidateFields(jobOpts)}
        onSubmit={async (v) => { await api.put(`/recruitment/candidates/${c.id}`, v); toast.success('Candidate updated'); reload() }} />
      <FormModal open={schedule} onClose={() => setSchedule(false)} title="Schedule interview"
        fields={[{ name: 'round_name', label: 'Round', required: true, placeholder: 'e.g. Technical round 1' },
          { name: 'scheduled_at', label: 'Date & time', type: 'datetime-local', required: true, span: 1 }, { name: 'duration_minutes', label: 'Duration (min)', type: 'number', default: 60, span: 1 },
          { name: 'mode', label: 'Mode', type: 'select', default: 'video', span: 1, options: [{ value: 'video', label: 'Video' }, { value: 'in_person', label: 'In person' }, { value: 'phone', label: 'Phone' }] },
          { name: 'interviewer_id', label: 'Interviewer', type: 'select', numeric: true, options: emps, placeholder: 'Select', span: 1 },
          { name: 'location', label: 'Location / meeting link' }]}
        onSubmit={async (v) => { await api.post(`/recruitment/candidates/${c.id}/interviews`, { ...v, scheduled_at: new Date(v.scheduled_at).toISOString() }); toast.success('Interview scheduled', 'The interviewer has been notified.'); reload() }} />
      <FormModal open={Boolean(feedback)} onClose={() => setFeedback(null)} title={`Feedback — ${feedback?.round_name || ''}`} initial={feedback}
        fields={[{ name: 'status', label: 'Outcome', type: 'select', default: 'completed', span: 1, options: ['scheduled', 'completed', 'cancelled', 'no_show'].map((v) => ({ value: v, label: titleCase(v) })) },
          { name: 'rating', label: 'Rating (1–5)', type: 'number', min: 1, max: 5, span: 1 },
          { name: 'recommendation', label: 'Recommendation', type: 'select', placeholder: 'None', options: [{ value: 'hire', label: 'Hire' }, { value: 'hold', label: 'Hold' }, { value: 'no_hire', label: 'No hire' }] },
          { name: 'feedback', label: 'Feedback', type: 'textarea', rows: 5 }]}
        onSubmit={async (v) => { await api.post(`/recruitment/interviews/${feedback.id}/feedback`, v); toast.success('Feedback saved'); reload() }} />
      <FormModal open={convert} onClose={() => setConvert(false)} title="Convert to employee" submitLabel="Create employee"
        description={accepted ? `Uses accepted offer ${accepted.reference_no}. The offer letter and resume are filed in the employee’s documents.` : 'No accepted offer found — enter the joining details.'}
        fields={[{ name: 'joining_date', label: 'Joining date', type: 'date', required: !accepted, span: 1 },
          { name: 'department_id', label: 'Department', type: 'select', numeric: true, options: depts, placeholder: 'From offer / opening', span: 1 },
          { name: 'designation_id', label: 'Designation', type: 'select', numeric: true, options: desigs, placeholder: 'From offer / opening', span: 1 },
          { name: 'manager_id', label: 'Reporting manager', type: 'select', numeric: true, options: emps, placeholder: 'None', span: 1 },
          { name: 'create_login', label: 'Create login', type: 'checkbox', default: true },
          { name: 'role_code', label: 'Role', type: 'select', default: 'employee', options: [{ value: 'employee', label: 'Employee' }, { value: 'project_manager', label: 'Project Manager' }, { value: 'hr_admin', label: 'HR / Admin' }], hidden: (v) => !v.create_login }]}
        onSubmit={async (v) => { const r = await api.post(`/recruitment/candidates/${c.id}/convert`, v); toast.success(`${r.data.full_name} is now ${r.data.employee_code}`); reload(); if (r.data.temporary_password) setCreated(r.data); else nav(`/employees/${r.data.id}`) }} />
      <TempPasswordModal open={Boolean(created)} onClose={() => { const e = created; setCreated(null); nav(`/employees/${e.id}`) }} email={created?.email} password={created?.temporary_password} />
    </>
  )
}
