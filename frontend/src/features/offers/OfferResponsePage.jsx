import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2, Download, XCircle } from 'lucide-react'
import axios from 'axios'
import { errorMessage } from '../../api/client'
import { Button, Field, Input, Spinner, Textarea } from '../../components/ui'
import { fmtDate, fmtMoney } from '../../lib/format'

const BASE = import.meta.env.VITE_API_URL || '/api/v1'

/** Public page (no login) where a recipient reviews and signs their offer. */
export default function OfferResponsePage() {
  const { token } = useParams()
  const [o, setO] = useState(null)
  const [err, setErr] = useState(null)
  const [sig, setSig] = useState('')
  const [note, setNote] = useState('')
  const [agree, setAgree] = useState(false)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)

  useEffect(() => {
    document.title = 'Your offer · ECHOUTRA IT SOLUTIONS'
    axios.get(`${BASE}/public/offers/${token}`).then((r) => setO(r.data)).catch((e) => setErr(errorMessage(e)))
  }, [token])

  const respond = async (accept) => {
    setBusy(true); setErr(null)
    try {
      const r = await axios.post(`${BASE}/public/offers/${token}/respond`, { accept, signature: sig, note: note || null })
      setDone(r.data.status)
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy(false) }
  }

  const final = done || (o && ['accepted', 'declined', 'withdrawn'].includes(o.status) ? o.status : null)
  return (
    <div className="min-h-screen bg-canvas">
      <header className="bg-night px-6 py-5"><div className="mx-auto max-w-3xl"><img src="/echoutra-logo.png" alt="ECHOUTRA IT SOLUTIONS" className="h-10 w-auto" /></div></header>
      <main className="mx-auto max-w-3xl px-4 py-10">
        {!o && !err && <Spinner label="Loading your offer…" />}
        {err && !o && <div className="card p-8 text-center"><XCircle className="mx-auto h-10 w-10 text-danger" /><p className="mt-3 font-semibold">This link isn’t available</p><p className="mt-1 text-sm text-muted">{err}</p></div>}
        {o && (
          <div className="card animate-fade-up p-6 sm:p-10">
            <p className="text-xs text-muted">Ref: {o.reference_no}</p>
            <h1 className="mt-2 text-2xl font-semibold">Offer of Employment</h1>
            <p className="mt-1 text-sm text-muted">{o.designation}{o.department && ` · ${o.department}`} · joining {fmtDate(o.joining_date)} · {fmtMoney(o.annual_ctc)} per annum</p>
            <div className="mt-6 space-y-3 text-[15px] leading-relaxed text-ink-2">{o.body.split('\n\n').map((p, i) => <p key={i} className="whitespace-pre-wrap">{p}</p>)}</div>
            <a href={`${BASE}/public/offers/${token}/pdf`} target="_blank" rel="noreferrer" className="mt-6 inline-flex h-10 items-center gap-2 rounded-lg border border-line-strong px-4 text-sm font-medium hover:bg-surface-2"><Download className="h-4 w-4" />Download PDF</a>

            <div className="mt-8 border-t border-line pt-8">
              {final ? (
                <div className="text-center">
                  {final === 'accepted' ? <CheckCircle2 className="mx-auto h-12 w-12 text-success" /> : <XCircle className="mx-auto h-12 w-12 text-muted" />}
                  <p className="mt-3 text-lg font-semibold">{final === 'accepted' ? `Welcome to ${o.company_name}!` : final === 'declined' ? 'You declined this offer' : 'This offer was withdrawn'}</p>
                  <p className="mt-1 text-sm text-muted">{final === 'accepted' ? 'Your acceptance has been recorded. HR will be in touch about onboarding.' : 'Thank you for letting us know.'}</p>
                </div>
              ) : o.expired ? (
                <p className="text-center text-sm text-muted">This offer expired on {fmtDate(o.valid_until)}. Please contact HR.</p>
              ) : (
                <div className="space-y-4">
                  <h2 className="text-base font-semibold">Your response</h2>
                  {err && <div className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2.5 text-[13px] text-danger">{err}</div>}
                  <Field label="Type your full name to sign" hint={`Must match: ${o.recipient_name}`}><Input value={sig} onChange={(e) => setSig(e.target.value)} placeholder={o.recipient_name} /></Field>
                  <Field label="Message to HR (optional)"><Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} /></Field>
                  <label className="flex items-start gap-2.5 text-[13px] text-ink-2"><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-0.5 accent-[rgb(var(--brand-strong))]" />I have read the offer and understand that typing my name is my electronic signature.</label>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Button size="lg" className="flex-1" disabled={!agree || sig.trim().length < 2} loading={busy} onClick={() => respond(true)}>Accept offer</Button>
                    <Button size="lg" variant="secondary" disabled={!agree || sig.trim().length < 2 || busy} onClick={() => respond(false)}>Decline</Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
        <p className="mt-6 text-center text-xs text-muted">© {new Date().getFullYear()} ECHOUTRA IT SOLUTIONS</p>
      </main>
    </div>
  )
}
