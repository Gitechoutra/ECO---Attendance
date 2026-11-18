import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import { Briefcase, CalendarClock, MapPin, Pencil, Plus, Users } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useDebounced } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions } from '../../hooks/useOptions'
import {
  Badge, Button, Card, DataTable, EmptyState, ErrorState, FormModal, IconButton, PageHeader, PersonCell, SearchInput,
  Select, Skeleton, StatusBadge, Tabs, Toolbar,
} from '../../components/ui'
import { fmtDate, fmtDateTime, titleCase } from '../../lib/format'

export const STAGES = ['applied', 'screening', 'interview', 'offered', 'hired', 'rejected', 'withdrawn']
const TYPES = ['full_time', 'part_time', 'contract', 'intern', 'consultant'].map((v) => ({ value: v, label: titleCase(v) }))

export function candidateFields(jobs) {
  return [
    { name: 'first_name', label: 'First name', required: true, span: 1 }, { name: 'last_name', label: 'Last name', span: 1 },
    { name: 'email', label: 'Email', type: 'email', required: true, span: 1 }, { name: 'phone', label: 'Phone', span: 1 },
    { name: 'job_id', label: 'Applied for', type: 'select', numeric: true, options: jobs, placeholder: 'General application' },
    { name: 'current_company', label: 'Current company', span: 1 }, { name: 'experience_years', label: 'Experience (years)', type: 'number', min: 0, step: 0.5, span: 1 },
    { name: 'current_ctc', label: 'Current CTC (annual)', type: 'number', min: 0, span: 1 }, { name: 'expected_ctc', label: 'Expected CTC (annual)', type: 'number', min: 0, span: 1 },
    { name: 'notice_period_days', label: 'Notice period (days)', type: 'number', min: 0, span: 1 },
    { name: 'source', label: 'Source', type: 'select', span: 1, placeholder: 'Select', options: ['LinkedIn', 'Referral', 'Job portal', 'Careers page', 'Campus', 'Agency', 'Other'].map((v) => ({ value: v, label: v })) },
    { name: 'skills', label: 'Key skills', placeholder: 'React, Python, AWS…' },
    { name: 'status', label: 'Stage', type: 'select', default: 'applied', options: STAGES.filter((s) => s !== 'hired').map((s) => ({ value: s, label: titleCase(s) })), span: 1 },
    { name: 'rating', label: 'Rating (1–5)', type: 'number', min: 1, max: 5, span: 1 },
    { name: 'notes', label: 'Notes', type: 'textarea' },
  ]
}

function Openings({ jobs, reload, canManage }) {
  const toast = useToast()
  const depts = useOptions('departments')
  const desigs = useOptions('designations')
  const emps = useOptions('employees')
  const [form, setForm] = useState(null)
  return (
    <>
      {canManage && <div className="mb-4 flex justify-end"><Button icon={Plus} onClick={() => setForm({})}>New opening</Button></div>}
      {!jobs.length ? <Card><EmptyState icon={Briefcase} title="No job openings" description="Create an opening to start tracking candidates." /></Card> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {jobs.map((j) => (
            <div key={j.id} className="card flex flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0"><p className="truncate text-[15px] font-semibold">{j.title}</p><p className="text-xs text-muted">{j.department || 'Any department'} · {titleCase(j.employment_type)}</p></div>
                <div className="flex items-center gap-1"><StatusBadge status={j.status} />{canManage && <IconButton icon={Pencil} size="sm" label="Edit" onClick={() => setForm(j)} />}</div>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                {j.location && <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{j.location}</span>}
                {(j.experience_min !== null || j.experience_max !== null) && <span>{j.experience_min ?? 0}–{j.experience_max ?? '∞'} yrs</span>}
                {j.closes_on && <span>Closes {fmtDate(j.closes_on)}</span>}
              </div>
              <div className="mt-4 grid grid-cols-4 gap-1 rounded-lg bg-surface-2 p-2 text-center">
                {['applied', 'interview', 'offered', 'hired'].map((s) => (
                  <div key={s}><p className="num text-base font-semibold">{j.pipeline[s] || 0}</p><p className="text-2xs text-muted">{titleCase(s)}</p></div>
                ))}
              </div>
              <p className="mt-3 text-xs text-muted">{j.hired} of {j.positions} position(s) filled · {j.candidate_count} candidates</p>
            </div>
          ))}
        </div>
      )}
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={form?.id ? 'Edit opening' : 'New job opening'} size="lg" initial={form}
        fields={[
          { name: 'title', label: 'Job title', required: true },
          { name: 'department_id', label: 'Department', type: 'select', numeric: true, options: depts, placeholder: 'Any', span: 1 },
          { name: 'designation_id', label: 'Designation', type: 'select', numeric: true, options: desigs, placeholder: 'Any', span: 1 },
          { name: 'employment_type', label: 'Type', type: 'select', options: TYPES, default: 'full_time', span: 1 },
          { name: 'location', label: 'Location', span: 1 },
          { name: 'experience_min', label: 'Min experience (yrs)', type: 'number', min: 0, span: 1 }, { name: 'experience_max', label: 'Max experience (yrs)', type: 'number', min: 0, span: 1 },
          { name: 'positions', label: 'Positions', type: 'number', min: 1, default: 1, span: 1 }, { name: 'closes_on', label: 'Closes on', type: 'date', span: 1 },
          { name: 'hiring_manager_id', label: 'Hiring manager', type: 'select', numeric: true, options: emps, placeholder: 'None', span: 1 },
          { name: 'status', label: 'Status', type: 'select', default: 'open', span: 1, options: ['draft', 'open', 'on_hold', 'closed'].map((v) => ({ value: v, label: titleCase(v) })) },
          { name: 'description', label: 'Description', type: 'textarea', rows: 4 }, { name: 'requirements', label: 'Requirements', type: 'textarea', rows: 4 },
        ]}
        onSubmit={async (v) => { form.id ? await api.put(`/recruitment/jobs/${form.id}`, v) : await api.post('/recruitment/jobs', v); toast.success('Opening saved'); reload() }} />
    </>
  )
}

function Pipeline({ jobs, canManage }) {
  const toast = useToast()
  const nav = useNavigate()
  const [job, setJob] = useState('')
  const [q, setQ] = useState('')
  const [adding, setAdding] = useState(false)
  const [drag, setDrag] = useState(null)
  const dq = useDebounced(q)
  const { data, loading, error, reload } = useApi('/recruitment/candidates', { job_id: job || undefined, q: dq || undefined, page_size: 200 })
  const jobOpts = jobs.map((j) => ({ value: j.id, label: j.title }))
  if (error) return <ErrorState message={error} onRetry={reload} />
  const move = async (c, status) => {
    if (status === 'hired') { toast.info('Open the candidate to convert them to an employee'); return }
    try { await api.patch(`/recruitment/candidates/${c.id}/status`, { status }); reload({ silent: true }) } catch (e) { toast.apiError(e) }
  }
  return (
    <>
      <div className="card mb-4 overflow-hidden">
        <Toolbar>
          <SearchInput value={q} onChange={setQ} placeholder="Search name, email, skills" className="sm:w-64" />
          <Select value={job} onChange={(e) => setJob(e.target.value)} placeholder="All openings" options={jobOpts} className="sm:w-56" />
          {canManage && <Button size="sm" icon={Plus} className="sm:ml-auto" onClick={() => setAdding(true)}>Add candidate</Button>}
        </Toolbar>
      </div>
      {loading && !data ? <Skeleton className="h-72" /> : (
        <div className="scrollbar-thin -mx-4 flex gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0">
          {STAGES.map((s) => {
            const items = (data?.items || []).filter((c) => c.status === s)
            return (
              <div key={s} onDragOver={(e) => drag && canManage && e.preventDefault()} onDrop={() => { if (drag && drag.status !== s) move(drag, s); setDrag(null) }}
                className="flex w-[250px] shrink-0 flex-col rounded-xl border border-line bg-surface-2/70">
                <div className="flex items-center justify-between px-3 py-2.5"><span className="text-[13px] font-semibold">{titleCase(s)}</span><span className="num rounded-full bg-surface px-2 text-xs text-muted">{items.length}</span></div>
                <div className="flex min-h-[100px] flex-col gap-2 px-2 pb-2">
                  {items.map((c) => (
                    <button key={c.id} draggable={canManage} onDragStart={() => setDrag(c)} onClick={() => nav(`/recruitment/candidates/${c.id}`)}
                      className={clsx('rounded-lg border border-line bg-surface p-3 text-left shadow-card hover:border-line-strong', drag?.id === c.id && 'opacity-50')}>
                      <p className="truncate text-[13px] font-semibold">{c.full_name}</p>
                      <p className="truncate text-2xs text-muted">{c.job?.title || 'General'}</p>
                      <div className="mt-2 flex items-center justify-between text-2xs text-muted">
                        <span>{c.experience_years != null ? `${c.experience_years} yrs` : '—'}</span>
                        {c.rating && <span className="text-warning">{'★'.repeat(c.rating)}</span>}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
      <FormModal open={adding} onClose={() => setAdding(false)} title="Add candidate" size="lg" fields={candidateFields(jobOpts)} initial={{ job_id: job ? Number(job) : undefined }}
        onSubmit={async (v) => { const r = await api.post('/recruitment/candidates', v); toast.success('Candidate added', 'Upload their resume from the profile.'); nav(`/recruitment/candidates/${r.data.id}`) }} />
    </>
  )
}

function Interviews() {
  const [mine, setMine] = useState(false)
  const { data, loading, error, reload } = useApi('/recruitment/interviews', { upcoming: true, mine: mine || undefined })
  return (
    <div className="card overflow-hidden">
      <Toolbar><label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} className="accent-[rgb(var(--brand-strong))]" />Only interviews I’m conducting</label></Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data} empty={<EmptyState icon={CalendarClock} title="No upcoming interviews" />}
        columns={[
          { key: 'when', header: 'When', mobile: 'title', render: (i) => <span className="font-medium text-ink">{fmtDateTime(i.scheduled_at)}</span> },
          { key: 'cand', header: 'Candidate', render: (i) => <Link className="link" to={`/recruitment/candidates/${i.candidate_id}`}>{i.candidate}</Link> },
          { key: 'job', header: 'Role', render: (i) => i.job || '—' },
          { key: 'round', header: 'Round', render: (i) => i.round_name },
          { key: 'mode', header: 'Mode', render: (i) => <Badge>{titleCase(i.mode)}</Badge> },
          { key: 'iv', header: 'Interviewer', render: (i) => i.interviewer ? <PersonCell name={i.interviewer.full_name} size="xs" /> : '—' },
        ]} />
    </div>
  )
}

export default function RecruitmentPage() {
  const { can } = useAuth()
  const [tab, setTab] = useState('pipeline')
  const jobs = useApi('/recruitment/jobs')
  const canManage = can('recruitment.manage')
  return (
    <>
      <PageHeader title="Recruitment" description="Openings, candidate pipeline and interviews." />
      <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[
        { value: 'pipeline', label: 'Pipeline', icon: Users }, { value: 'openings', label: 'Openings', count: jobs.data?.filter((j) => j.status === 'open').length },
        { value: 'interviews', label: 'Interviews' }]} />
      {jobs.error ? <ErrorState message={jobs.error} onRetry={jobs.reload} /> : jobs.loading && !jobs.data ? <Skeleton className="h-64" /> : (
        <>
          {tab === 'pipeline' && <Pipeline jobs={jobs.data} canManage={canManage} />}
          {tab === 'openings' && <Openings jobs={jobs.data} reload={jobs.reload} canManage={canManage} />}
          {tab === 'interviews' && <Interviews />}
        </>
      )}
    </>
  )
}
