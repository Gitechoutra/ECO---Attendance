import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, KeyRound } from 'lucide-react'
import clsx from 'clsx'
import { api, errorMessage } from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { Button, Field, Input } from '../../components/ui'

export const PW_RULES = [
  { test: (p) => p.length >= 8, label: 'At least 8 characters' },
  { test: (p) => /[a-z]/.test(p) && /[A-Z]/.test(p), label: 'Upper and lower case letters' },
  { test: (p) => /\d/.test(p), label: 'At least one number' },
]

export function PasswordForm({ onDone, compact }) {
  const { applyTokens } = useAuth()
  const toast = useToast()
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const ok = PW_RULES.every((r) => r.test(form.next)) && form.next === form.confirm && form.current

  const submit = async (e) => {
    e.preventDefault()
    if (form.next !== form.confirm) { setError('New passwords do not match.'); return }
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post('/auth/change-password', { current_password: form.current, new_password: form.next })
      applyTokens(data)
      toast.success('Password updated', 'Other sessions have been signed out.')
      setForm({ current: '', next: '', confirm: '' })
      onDone?.()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} className={clsx('space-y-4', compact && 'max-w-md')}>
      {error && <div className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2.5 text-[13px] text-danger">{error}</div>}
      <Field label="Current password"><Input type="password" autoComplete="current-password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} /></Field>
      <Field label="New password"><Input type="password" autoComplete="new-password" value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} /></Field>
      <Field label="Confirm new password"><Input type="password" autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} /></Field>
      <ul className="space-y-1">
        {PW_RULES.map((r) => (
          <li key={r.label} className={clsx('flex items-center gap-2 text-xs', r.test(form.next) ? 'text-success' : 'text-muted')}>
            <Check className="h-3.5 w-3.5" />{r.label}
          </li>
        ))}
      </ul>
      <Button type="submit" loading={busy} disabled={!ok}>Update password</Button>
    </form>
  )
}

export default function ChangePasswordPage() {
  const nav = useNavigate()
  const { user, logout } = useAuth()
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 py-12">
      <div className="card w-full max-w-md animate-fade-up p-7">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-soft text-brand-ink"><KeyRound className="h-5 w-5" /></span>
        <h1 className="mt-4 text-xl font-semibold">Set a new password</h1>
        <p className="mt-1 text-sm text-muted">
          {user?.must_change_password ? 'For security, replace the temporary password you were given before continuing.' : 'Choose a strong password you don’t use elsewhere.'}
        </p>
        <div className="mt-6"><PasswordForm onDone={() => nav('/', { replace: true })} /></div>
        <button onClick={logout} className="mt-5 text-xs text-muted hover:text-ink">Sign out instead</button>
      </div>
    </div>
  )
}
