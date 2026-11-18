import { useRef, useState } from 'react'
import { Camera, LogOut, ScanFace, ShieldCheck } from 'lucide-react'
import { api, downloadFile } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import {
  Avatar, Badge, Button, Card, CardHeader, ConfirmDialog, DescriptionList, EmptyState, FormModal, PageHeader, Section,
  Skeleton, Tabs,
} from '../../components/ui'
import { fmtBytes, fmtDate, fmtDateTime, titleCase } from '../../lib/format'
import { PasswordForm } from '../auth/ChangePasswordPage'
import { CONSENT_TEXT } from '../attendance/FaceEnrollModal'

export default function ProfilePage() {
  const { user, employee, reload: reloadMe } = useAuth()
  const toast = useToast()
  const me = useApi(employee ? '/employees/me' : null)
  const face = useApi(employee ? `/attendance/face/status/${employee.id}` : null)
  const docs = useApi(employee ? `/employees/${employee.id}/documents` : null)
  const [tab, setTab] = useState('profile')
  const [edit, setEdit] = useState(false)
  const [revoke, setRevoke] = useState(false)
  const [signOutAll, setSignOutAll] = useState(false)
  const [run, busy] = useAction(toast)
  const photo = useRef(null)
  const e = me.data

  return (
    <>
      <PageHeader title="My profile" description="Your details, security and privacy settings." />
      <Card className="mb-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div className="relative w-fit">
            <Avatar name={employee?.full_name || user.email} fileId={employee?.photo_file_id} size="xl" />
            {employee && <>
              <button onClick={() => photo.current?.click()} className="absolute -bottom-1 -right-1 flex h-8 w-8 items-center justify-center rounded-full border-2 border-surface bg-ink text-surface" aria-label="Change photo"><Camera className="h-3.5 w-3.5" /></button>
              <input ref={photo} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={async (ev) => {
                const f = ev.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append('file', f)
                await run(() => api.post(`/employees/${employee.id}/photo`, fd), { success: 'Photo updated' }); reloadMe()
              }} />
            </>}
          </div>
          <div>
            <h2 className="text-xl font-semibold">{employee?.full_name || user.email}</h2>
            <p className="text-sm text-muted">{[employee?.designation, employee?.department, employee?.employee_code].filter(Boolean).join(' · ')}</p>
            <div className="mt-2 flex gap-2"><Badge tone="brand">{user.role.name}</Badge>{face.data?.enrolled && <Badge><ScanFace className="h-3 w-3" />Face enrolled</Badge>}</div>
          </div>
        </div>
      </Card>
      <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[{ value: 'profile', label: 'Details', hidden: !employee }, { value: 'documents', label: 'My documents', hidden: !employee }, { value: 'security', label: 'Security' }, { value: 'privacy', label: 'Biometric privacy', hidden: !employee }]} />
      {tab === 'profile' && employee && (me.loading || !e ? <Skeleton className="h-64" /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card><CardHeader title="Personal details" action={<Button size="sm" variant="secondary" onClick={() => setEdit(true)}>Edit</Button>} />
            <DescriptionList items={[['Phone', e.phone], ['Personal email', e.personal_email], ['Date of birth', e.date_of_birth && fmtDate(e.date_of_birth)],
              ['Blood group', e.blood_group], ['Marital status', e.marital_status], ['Address', [e.address, e.city, e.state, e.postal_code].filter(Boolean).join(', ')],
              ['Emergency contact', e.emergency_contact_name && `${e.emergency_contact_name} · ${e.emergency_contact_phone || ''}`]]} /></Card>
          <Card><CardHeader title="Employment" subtitle="Contact HR to change these details" />
            <DescriptionList items={[['Employee ID', e.employee_code], ['Work email', e.email], ['Department', e.department?.name], ['Designation', e.designation?.title],
              ['Manager', e.manager?.full_name], ['Joined', fmtDate(e.joining_date)], ['Type', titleCase(e.employment_type)], ['Bank account', e.bank_account]]} /></Card>
        </div>
      ))}
      {tab === 'documents' && (
        <Card>
          <CardHeader title="My documents" subtitle="Offer letters, contracts and ID proofs filed by HR" />
          {docs.loading ? <Skeleton className="h-24" /> : !docs.data?.length ? <EmptyState compact title="No documents on file" /> : (
            <ul className="divide-y divide-line">{docs.data.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0"><p className="truncate text-sm font-medium">{d.name}</p><p className="text-xs text-muted">{titleCase(d.category)} · {fmtBytes(d.size)} · {fmtDate(d.created_at)}</p></div>
                <Button size="xs" variant="secondary" onClick={() => downloadFile(`/files/${d.id}`, { inline: false }, d.name)}>Download</Button>
              </li>))}</ul>
          )}
        </Card>
      )}
      {tab === 'security' && (
        <Card className="divide-y divide-line">
          <Section title="Password" description="Use at least 8 characters with upper and lower case letters and a number."><PasswordForm compact /></Section>
          <Section title="Sessions" description={`Last sign-in ${user.last_login_at ? fmtDateTime(user.last_login_at) : '—'}`}>
            <Button variant="secondary" icon={LogOut} onClick={() => setSignOutAll(true)}>Sign out of all devices</Button>
          </Section>
        </Card>
      )}
      {tab === 'privacy' && (
        <Card>
          <CardHeader title="Face verification consent" icon={ShieldCheck} />
          <ul className="mb-5 space-y-2 text-[13px] text-ink-2">{CONSENT_TEXT.map((t) => <li key={t}>• {t}</li>)}</ul>
          {face.data?.enrolled ? (
            <div className="flex flex-col gap-3 rounded-xl border border-line p-4 sm:flex-row sm:items-center">
              <div className="flex-1 text-sm"><p className="font-medium">Enrolled {fmtDate(face.data.enrolled_at)}</p><p className="text-xs text-muted">Consent version {face.data.consent?.version} given {fmtDateTime(face.data.consent?.given_at)}{face.data.last_verified_at && ` · last used ${fmtDateTime(face.data.last_verified_at)}`}</p></div>
              <Button variant="danger-ghost" onClick={() => setRevoke(true)}>Revoke consent & delete</Button>
            </div>
          ) : <p className="rounded-xl bg-surface-2 p-4 text-sm text-muted">No face template is stored for you. HR can enroll you with your consent; until then use manual attendance requests.</p>}
        </Card>
      )}
      {e && (
        <FormModal open={edit} onClose={() => setEdit(false)} title="Edit personal details" initial={e} size="lg"
          fields={[{ name: 'phone', label: 'Phone', span: 1 }, { name: 'personal_email', label: 'Personal email', type: 'email', span: 1 },
            { name: 'blood_group', label: 'Blood group', span: 1 }, { name: 'marital_status', label: 'Marital status', span: 1 },
            { name: 'address', label: 'Address', type: 'textarea', rows: 2 }, { name: 'city', label: 'City', span: 1 }, { name: 'state', label: 'State', span: 1 },
            { name: 'postal_code', label: 'Postal code', span: 1 }, { name: 'emergency_contact_name', label: 'Emergency contact', span: 1 }, { name: 'emergency_contact_phone', label: 'Emergency phone', span: 1 }]}
          onSubmit={async (v) => { await api.put('/employees/me', v); toast.success('Profile updated'); me.reload() }} />
      )}
      <ConfirmDialog open={revoke} onClose={() => setRevoke(false)} title="Revoke biometric consent" confirmLabel="Revoke & delete" loading={busy}
        description="Your face template will be deleted immediately. You’ll need to use manual attendance requests until you re-enroll."
        onConfirm={async () => { await run(() => api.delete(`/attendance/face/${employee.id}`), { success: 'Face template deleted' }); setRevoke(false); face.reload() }} />
      <ConfirmDialog open={signOutAll} onClose={() => setSignOutAll(false)} tone="primary" title="Sign out everywhere" confirmLabel="Sign out all" loading={busy}
        description="All your sessions, including this one, will end."
        onConfirm={async () => { await run(() => api.post('/auth/logout-all')); window.location.href = '/login' }} />
    </>
  )
}
