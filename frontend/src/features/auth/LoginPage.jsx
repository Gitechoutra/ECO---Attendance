import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { CalendarCheck, Eye, EyeOff, FolderKanban, Lock, Mail, ShieldCheck } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { errorMessage } from '../../api/client'
import { Button, Field, Input } from '../../components/ui'

const POINTS = [
  { icon: CalendarCheck, title: 'Verified attendance', text: 'Face check-in with live verification.' },
  { icon: FolderKanban, title: 'Projects & clients', text: 'Delivery, tasks and client records in one place.' },
  { icon: ShieldCheck, title: 'Secure by role', text: 'Everyone sees exactly what they should.' },
]

export default function LoginPage() {
  const { login } = useAuth()
  const nav = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { document.title = 'Sign in · ECHOUTRA ONE' }, [])

  const submit = async (e) => {
    e.preventDefault()
    if (!email || !password) { setError('Enter your work email and password.'); return }
    setBusy(true)
    setError(null)
    try {
      const user = await login(email.trim(), password)
      nav(user.must_change_password ? '/change-password' : (location.state?.from?.pathname || '/'), { replace: true })
    } catch (err) {
      setError(errorMessage(err, 'Unable to sign in'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen bg-surface">
      <aside className="relative hidden w-[46%] max-w-[640px] flex-col justify-between overflow-hidden bg-night p-12 lg:flex">
        <div className="pointer-events-none absolute -right-40 -top-40 h-[520px] w-[520px] rounded-full border border-night-line" />
        <div className="pointer-events-none absolute -right-20 -top-20 h-[360px] w-[360px] rounded-full border border-night-line" />
        <img src="/echoutra-logo.png" alt="ECHOUTRA IT SOLUTIONS" className="relative h-14 w-auto self-start" />
        <div className="relative">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand">ECHOUTRA ONE</p>
          <h1 className="mt-3 max-w-md text-[34px] font-semibold leading-[1.15] tracking-tight text-white">
            One workspace for the people and work behind every delivery.
          </h1>
          <div className="mt-10 space-y-5">
            {POINTS.map((p) => (
              <div key={p.title} className="flex gap-4">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-night-line bg-night-2 text-brand"><p.icon className="h-[18px] w-[18px]" /></span>
                <div>
                  <p className="text-sm font-semibold text-white">{p.title}</p>
                  <p className="text-[13px] text-[#8DA1AC]">{p.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-xs text-[#5D7380]">© {new Date().getFullYear()} ECHOUTRA IT SOLUTIONS. Internal use only.</p>
      </aside>

      <main className="flex flex-1 flex-col">
        <div className="bg-night px-6 py-6 lg:hidden">
          <img src="/echoutra-logo.png" alt="ECHOUTRA IT SOLUTIONS" className="h-10 w-auto" />
        </div>
        <div className="flex flex-1 items-center justify-center px-6 py-12">
          <form onSubmit={submit} className="w-full max-w-[380px] animate-fade-up" noValidate>
            <h2 className="text-2xl font-semibold">Sign in</h2>
            <p className="mt-1.5 text-sm text-muted">Use your ECHOUTRA work account.</p>
            {error && <div role="alert" className="mt-6 rounded-lg border border-danger/25 bg-danger-soft px-3.5 py-2.5 text-[13px] text-danger">{error}</div>}
            <div className="mt-6 space-y-4">
              <Field label="Work email" htmlFor="email">
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
                  <Input id="email" type="email" autoComplete="username" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className="h-11 pl-9" placeholder="name@echoutra.com" />
                </div>
              </Field>
              <Field label="Password" htmlFor="password">
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
                  <Input id="password" type={show ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="h-11 pl-9 pr-10" />
                  <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-faint hover:text-ink" aria-label={show ? 'Hide password' : 'Show password'}>
                    {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </Field>
            </div>
            <Button type="submit" size="lg" loading={busy} className="mt-6 w-full">Sign in</Button>
            <p className="mt-6 text-center text-xs text-muted">Forgot your password? Ask HR or an administrator to reset it.</p>
          </form>
        </div>
      </main>
    </div>
  )
}
