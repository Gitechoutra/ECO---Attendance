import { useEffect, useState } from 'react'
import { Copy, KeyRound } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { useOptions, invalidateOptions } from '../../hooks/useOptions'
import { Button, Checkbox, Drawer, Field, Input, Modal, Select, Textarea } from '../../components/ui'

const EMPTY = {
  first_name: '', last_name: '', email: '', personal_email: '', phone: '', date_of_birth: '', gender: '', marital_status: '',
  blood_group: '', address: '', city: '', state: '', country: 'India', postal_code: '', emergency_contact_name: '',
  emergency_contact_phone: '', department_id: '', designation_id: '', manager_id: '', employment_type: 'full_time',
  work_location: '', joining_date: '', probation_end_date: '', bank_name: '', bank_account: '', bank_ifsc: '', pan: '',
  national_id: '', create_login: true, role_code: 'employee',
}

const TYPES = [
  { value: 'full_time', label: 'Full time' }, { value: 'part_time', label: 'Part time' }, { value: 'contract', label: 'Contract' },
  { value: 'intern', label: 'Intern' }, { value: 'consultant', label: 'Consultant' },
]

function S({ title, children }) {
  return (
    <section className="border-b border-line pb-6 pt-1 last:border-0">
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wide text-faint">{title}</h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">{children}</div>
    </section>
  )
}

export function TempPasswordModal({ open, onClose, email, password }) {
  const toast = useToast()
  return (
    <Modal open={open} onClose={onClose} title="Login created" size="sm" footer={<Button onClick={onClose}>Done</Button>}>
      <div className="flex gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand-ink"><KeyRound className="h-4 w-4" /></span>
        <div className="min-w-0 text-sm text-ink-2">
          <p>Share these sign-in details securely. The temporary password is shown <b>only once</b> and must be changed at first login.</p>
          <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3">
            <p className="text-xs text-muted">Email</p><p className="font-medium text-ink">{email}</p>
            <p className="mt-2 text-xs text-muted">Temporary password</p>
            <div className="flex items-center gap-2">
              <code className="num text-[15px] font-semibold text-ink">{password}</code>
              <button onClick={() => { navigator.clipboard?.writeText(password); toast.success('Copied') }} className="rounded p-1 text-muted hover:text-ink" aria-label="Copy password"><Copy className="h-4 w-4" /></button>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}

export default function EmployeeForm({ open, onClose, employee, onSaved }) {
  const toast = useToast()
  const { role } = useAuth()
  const depts = useOptions('departments', open)
  const desigs = useOptions('designations', open)
  const emps = useOptions('employees', open)
  const [f, setF] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)
  const editing = Boolean(employee)

  useEffect(() => {
    if (!open) return
    setErrors({})
    setFormError(null)
    if (employee) {
      const next = { ...EMPTY }
      Object.keys(EMPTY).forEach((k) => { if (employee[k] !== undefined && employee[k] !== null) next[k] = employee[k] })
      setF(next)
    } else setF(EMPTY)
  }, [open, employee])

  const set = (k) => (e) => { const v = e?.target ? (e.target.type === 'checkbox' ? e.target.checked : e.target.value) : e; setF((p) => ({ ...p, [k]: v })); setErrors((x) => ({ ...x, [k]: undefined })) }

  const validate = () => {
    const e = {}
    if (!f.first_name.trim()) e.first_name = 'First name is required'
    if (!/^\S+@\S+\.\S+$/.test(f.email)) e.email = 'Enter a valid work email'
    if (!f.joining_date) e.joining_date = 'Joining date is required'
    if (f.phone && !/^[0-9+()\-\s]{6,30}$/.test(f.phone)) e.phone = 'Enter a valid phone number'
    if (f.date_of_birth && f.joining_date && f.date_of_birth >= f.joining_date) e.date_of_birth = 'Must be before joining date'
    setErrors(e)
    return !Object.keys(e).length
  }

  const submit = async (ev) => {
    ev.preventDefault()
    if (!validate()) return
    const body = {}
    Object.entries(f).forEach(([k, v]) => { body[k] = v === '' ? null : v })
    ;['department_id', 'designation_id', 'manager_id'].forEach((k) => { body[k] = body[k] ? Number(body[k]) : null })
    body.last_name = f.last_name || ''
    if (editing) { delete body.create_login; delete body.role_code }
    setBusy(true)
    setFormError(null)
    try {
      const { data } = editing ? await api.put(`/employees/${employee.id}`, body) : await api.post('/employees', body)
      invalidateOptions('employees')
      toast.success(editing ? 'Employee updated' : `${data.full_name} added`, editing ? undefined : `Employee ID ${data.employee_code}`)
      onSaved?.(data)
      if (!editing && data.temporary_password) setCreated(data)
      else onClose()
    } catch (err) {
      setFormError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const filteredDesigs = f.department_id ? desigs.filter((d) => !d.department_id || String(d.department_id) === String(f.department_id)) : desigs
  const inp = (k, label, props = {}) => (
    <Field label={label} required={props.required} error={errors[k]} className={props.wide ? 'sm:col-span-2' : ''}>
      <Input value={f[k] ?? ''} onChange={set(k)} error={errors[k]} type={props.type || 'text'} placeholder={props.placeholder} />
    </Field>
  )

  return (
    <>
      <Drawer
        open={open && !created}
        onClose={busy ? undefined : onClose}
        title={editing ? `Edit ${employee.full_name}` : 'Add employee'}
        subtitle={editing ? employee.employee_code : 'An employee ID is generated automatically.'}
        width="max-w-2xl"
        footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" form="emp-form" loading={busy}>{editing ? 'Save changes' : 'Create employee'}</Button></>}
      >
        <form id="emp-form" onSubmit={submit} noValidate className="space-y-6">
          {formError && <div className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2.5 text-[13px] text-danger">{formError}</div>}
          <S title="Personal">
            {inp('first_name', 'First name', { required: true })}
            {inp('last_name', 'Last name')}
            {inp('email', 'Work email', { required: true, type: 'email' })}
            {inp('personal_email', 'Personal email', { type: 'email' })}
            {inp('phone', 'Phone', { placeholder: '+91 98765 43210' })}
            {inp('date_of_birth', 'Date of birth', { type: 'date' })}
            <Field label="Gender"><Select value={f.gender} onChange={set('gender')} placeholder="Select" options={['Female', 'Male', 'Non-binary', 'Prefer not to say'].map((x) => ({ value: x, label: x }))} /></Field>
            <Field label="Marital status"><Select value={f.marital_status} onChange={set('marital_status')} placeholder="Select" options={['Single', 'Married', 'Other'].map((x) => ({ value: x, label: x }))} /></Field>
            {inp('blood_group', 'Blood group')}
          </S>
          <S title="Employment">
            <Field label="Department"><Select value={f.department_id} onChange={set('department_id')} placeholder="No department" options={depts} /></Field>
            <Field label="Designation"><Select value={f.designation_id} onChange={set('designation_id')} placeholder="No designation" options={filteredDesigs} /></Field>
            <Field label="Reporting manager"><Select value={f.manager_id} onChange={set('manager_id')} placeholder="None" options={emps.filter((e) => e.value !== employee?.id)} /></Field>
            <Field label="Employment type"><Select value={f.employment_type} onChange={set('employment_type')} options={TYPES} /></Field>
            {inp('joining_date', 'Joining date', { required: true, type: 'date' })}
            {inp('probation_end_date', 'Probation ends', { type: 'date' })}
            {inp('work_location', 'Work location', { wide: true, placeholder: 'e.g. Hyderabad office / Remote' })}
          </S>
          <S title="Address & emergency contact">
            <Field label="Address" className="sm:col-span-2"><Textarea value={f.address} onChange={set('address')} rows={2} /></Field>
            {inp('city', 'City')}{inp('state', 'State')}{inp('postal_code', 'Postal code')}{inp('country', 'Country')}
            {inp('emergency_contact_name', 'Emergency contact')}{inp('emergency_contact_phone', 'Emergency phone')}
          </S>
          <S title="Bank & identity (encrypted)">
            {inp('bank_name', 'Bank name')}{inp('bank_account', 'Account number')}{inp('bank_ifsc', 'IFSC')}{inp('pan', 'PAN')}
            {inp('national_id', 'National ID (Aadhaar)', { wide: true })}
          </S>
          {!editing && (
            <section className="space-y-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">Login access</h3>
              <Checkbox label="Create a login for this employee" description="A temporary password is generated and must be changed at first sign-in." checked={f.create_login} onChange={set('create_login')} />
              {f.create_login && (
                <Field label="Role" className="max-w-xs">
                  <Select value={f.role_code} onChange={set('role_code')} options={[
                    { value: 'employee', label: 'Employee' }, { value: 'project_manager', label: 'Project Manager' },
                    { value: 'hr_admin', label: 'HR / Admin' }, ...(role === 'super_admin' ? [{ value: 'super_admin', label: 'Super Admin / CEO' }] : []),
                  ]} />
                </Field>
              )}
            </section>
          )}
        </form>
      </Drawer>
      <TempPasswordModal open={Boolean(created)} onClose={() => { setCreated(null); onClose() }} email={created?.email} password={created?.temporary_password} />
    </>
  )
}
