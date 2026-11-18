import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { CheckCircle2, CircleDashed, Database, Download, Save } from 'lucide-react'
import { api, downloadFile, errorMessage } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { Button, Card, DataTable, EmptyState, ErrorState, Field, Input, PageHeader, Section, Skeleton, Switch, Tabs, Textarea } from '../../components/ui'
import { fmtBytes, fmtDateTime } from '../../lib/format'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const INTEGRATIONS = [
  ['gemini', 'Google Gemini', 'AI assistant', 'GEMINI_API_KEY'],
  ['gmail', 'Gmail / Google Workspace', 'Email sync & send', 'GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET'],
  ['outlook', 'Microsoft 365 / Outlook', 'Email sync & send', 'MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET'],
  ['s3', 'AWS S3', 'Document storage (local disk otherwise)', 'STORAGE_BACKEND=s3, AWS_S3_BUCKET, AWS keys'],
  ['redis', 'Redis', 'Shared rate limits across servers', 'REDIS_URL'],
]

function Backups() {
  const toast = useToast()
  const { data, loading, error, reload } = useApi('/admin/backups')
  const [run, busy] = useAction(toast)
  if (error) return <ErrorState message={error} onRetry={reload} />
  return (
    <Card padded={false}>
      <div className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center">
        <div><h3 className="text-[15px] font-semibold">Database backups</h3><p className="text-[13px] text-muted">Full MySQL dumps stored on the server in backend/backups. Schedule regular off-site copies — see docs/DEPLOYMENT.md.</p></div>
        <Button className="sm:ml-auto" icon={Database} loading={busy} disabled={!data?.tool_available} onClick={async () => { await run(() => api.post('/admin/backups'), { success: 'Backup created' }); reload() }}>Create backup</Button>
      </div>
      {data && !data.tool_available && <p className="mx-5 mb-4 rounded-lg bg-warning-soft p-3 text-[13px] text-warning">mysqldump was not found on the server, so backups can’t be created from here.</p>}
      <DataTable loading={loading} rows={data?.backups.map((b) => ({ ...b, id: b.name }))} empty={<EmptyState compact title="No backups yet" />}
        columns={[
          { key: 'name', header: 'File', mobile: 'title', render: (b) => <span className="num font-medium text-ink">{b.name}</span> },
          { key: 'size', header: 'Size', render: (b) => fmtBytes(b.size) },
          { key: 'at', header: 'Created', render: (b) => fmtDateTime(b.created_at) },
          { key: 'a', header: '', align: 'right', render: (b) => <Button size="xs" variant="ghost" icon={Download} onClick={() => downloadFile(`/admin/backups/${b.name}`, null, b.name)}>Download</Button> },
        ]} />
    </Card>
  )
}

export default function SettingsPage() {
  const { can } = useAuth()
  const toast = useToast()
  const { data, loading, error, reload } = useApi('/admin/settings')
  const [f, setF] = useState(null)
  const [tab, setTab] = useState('company')
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (data) setF({ ...data, face_match_threshold: data.face_match_threshold ?? '' }) }, [data])
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (loading || !f) return <Skeleton className="h-96" />
  const set = (k) => (e) => setF({ ...f, [k]: e?.target ? e.target.value : e })
  const save = async () => {
    setBusy(true)
    try {
      const body = { ...f, grace_minutes: Number(f.grace_minutes), half_day_minutes: Number(f.half_day_minutes), full_day_minutes: Number(f.full_day_minutes),
        biometric_retention_days: Number(f.biometric_retention_days), session_timeout_minutes: Number(f.session_timeout_minutes),
        face_match_threshold: f.face_match_threshold === '' ? null : Number(f.face_match_threshold) }
      ;['legal_name', 'email', 'phone', 'website', 'address', 'tax_id'].forEach((k) => { if (body[k] === '') body[k] = null })
      await api.put('/admin/settings', body)
      toast.success('Settings saved'); reload()
    } catch (e) { toast.error('Could not save settings', errorMessage(e)) } finally { setBusy(false) }
  }
  const saveBar = <div className="flex justify-end border-t border-line pt-5"><Button icon={Save} loading={busy} onClick={save}>Save settings</Button></div>
  return (
    <>
      <PageHeader title="Settings" description="Company profile, attendance rules, security and integrations." />
      <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[{ value: 'company', label: 'Company' }, { value: 'attendance', label: 'Attendance & time' }, { value: 'security', label: 'Security & privacy' }, { value: 'integrations', label: 'Integrations' }, { value: 'backups', label: 'Backups', hidden: !can('admin.backup') }]} />
      {tab === 'company' && (
        <Card className="divide-y divide-line">
          <Section title="Company profile" description="Shown on offer letters, payslips and reports.">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Company name"><Input value={f.company_name || ''} onChange={set('company_name')} /></Field>
              <Field label="Legal name"><Input value={f.legal_name || ''} onChange={set('legal_name')} /></Field>
              <Field label="Email"><Input type="email" value={f.email || ''} onChange={set('email')} /></Field>
              <Field label="Phone"><Input value={f.phone || ''} onChange={set('phone')} /></Field>
              <Field label="Website"><Input value={f.website || ''} onChange={set('website')} /></Field>
              <Field label="GSTIN / Tax ID"><Input value={f.tax_id || ''} onChange={set('tax_id')} /></Field>
              <Field label="Address" className="sm:col-span-2"><Textarea rows={2} value={f.address || ''} onChange={set('address')} /></Field>
            </div>
          </Section>
          <Section title="Regional" description="Time zone drives attendance dates and lateness.">
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Time zone"><Input value={f.timezone} onChange={set('timezone')} placeholder="Asia/Kolkata" /></Field>
              <Field label="Currency"><Input value={f.currency} onChange={set('currency')} maxLength={3} /></Field>
              <Field label="Employee ID prefix" hint="e.g. ECH → ECH0001"><Input value={f.employee_code_prefix} onChange={set('employee_code_prefix')} /></Field>
            </div>
          </Section>
          {saveBar}
        </Card>
      )}
      {tab === 'attendance' && (
        <Card className="divide-y divide-line">
          <Section title="Working hours" description="Used for lateness, early departure and half-day rules.">
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Shift start"><Input type="time" value={f.work_start} onChange={set('work_start')} /></Field>
              <Field label="Shift end"><Input type="time" value={f.work_end} onChange={set('work_end')} /></Field>
              <Field label="Grace period (min)"><Input type="number" min="0" value={f.grace_minutes} onChange={set('grace_minutes')} /></Field>
              <Field label="Half-day minimum (min)"><Input type="number" min="30" value={f.half_day_minutes} onChange={set('half_day_minutes')} /></Field>
              <Field label="Full-day minimum (min)" hint="Below the midpoint of these two counts as a half day"><Input type="number" min="60" value={f.full_day_minutes} onChange={set('full_day_minutes')} /></Field>
            </div>
          </Section>
          <Section title="Weekly off days" description="Non-working days excluded from leave and attendance counts.">
            <div className="flex flex-wrap gap-2">
              {DAYS.map((d, i) => {
                const on = f.weekly_offs.includes(i)
                return <button key={d} type="button" onClick={() => setF({ ...f, weekly_offs: on ? f.weekly_offs.filter((x) => x !== i) : [...f.weekly_offs, i].sort() })}
                  className={clsx('h-10 w-14 rounded-lg border text-sm font-medium transition-colors', on ? 'border-brand bg-brand-soft text-brand-ink' : 'border-line text-muted hover:border-line-strong')}>{d}</button>
              })}
            </div>
          </Section>
          <Section title="Face verification" description="Live camera verification with liveness checks for check-in and check-out.">
            <div className="space-y-4">
              <Switch checked={f.require_face_for_attendance} onChange={set('require_face_for_attendance')} label="Require face verification" description="When off, employees can check in with a single click (less secure)." />
              <Field label="Match threshold" hint="Cosine similarity 0.30–0.80. Leave blank for the recommended default (0.42). Higher = stricter." className="max-w-xs">
                <Input type="number" step="0.01" min="0.3" max="0.8" value={f.face_match_threshold} onChange={set('face_match_threshold')} />
              </Field>
            </div>
          </Section>
          {saveBar}
        </Card>
      )}
      {tab === 'security' && (
        <Card className="divide-y divide-line">
          <Section title="Biometric data retention" description="Face templates of former employees are deleted automatically after this many days from their exit date.">
            <Field label="Retention (days)" className="max-w-xs"><Input type="number" min="0" value={f.biometric_retention_days} onChange={set('biometric_retention_days')} /></Field>
          </Section>
          <Section title="Sessions" description="Server-enforced token lifetimes (set in the server environment).">
            <dl className="grid gap-4 text-sm sm:grid-cols-2">
              <div><dt className="text-muted">Access token lifetime</dt><dd className="font-medium">{f.security.access_token_minutes} minutes</dd></div>
              <div><dt className="text-muted">Refresh token lifetime (rotating)</dt><dd className="font-medium">{f.security.refresh_token_days} days</dd></div>
              <div><dt className="text-muted">Lockout</dt><dd className="font-medium">{f.security.max_login_attempts} failed attempts → {f.security.lockout_minutes} min</dd></div>
              <div><dt className="text-muted">Passwords</dt><dd className="font-medium">Argon2id hashing</dd></div>
            </dl>
          </Section>
          {saveBar}
        </Card>
      )}
      {tab === 'integrations' && (
        <Card padded={false}>
          <div className="p-5 pb-2"><h3 className="text-[15px] font-semibold">External integrations</h3><p className="text-[13px] text-muted">Credentials live in the server’s environment file — never in the database or browser.</p></div>
          <ul className="divide-y divide-line">
            {INTEGRATIONS.map(([k, name, use, env]) => {
              const on = f.integrations[k]
              return (
                <li key={k} className="flex items-start gap-3 px-5 py-4">
                  {on ? <CheckCircle2 className="mt-0.5 h-5 w-5 text-success" /> : <CircleDashed className="mt-0.5 h-5 w-5 text-faint" />}
                  <div className="min-w-0 flex-1"><p className="text-sm font-semibold">{name}</p><p className="text-xs text-muted">{use}</p>{!on && <p className="mt-1 text-xs text-muted">Set <code className="rounded bg-surface-2 px-1">{env}</code></p>}</div>
                  <span className={clsx('text-xs font-medium', on ? 'text-success' : 'text-muted')}>{on ? 'Configured' : 'Not configured'}</span>
                </li>
              )
            })}
          </ul>
        </Card>
      )}
      {tab === 'backups' && can('admin.backup') && <Backups />}
    </>
  )
}
