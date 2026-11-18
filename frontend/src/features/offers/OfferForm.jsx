import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import { useOptions } from '../../hooks/useOptions'
import { Button, Drawer, Field, IconButton, Input, Select, Segmented, Textarea } from '../../components/ui'
import { fmtMoney } from '../../lib/format'

const DEFAULT_LINES = [{ label: 'Basic salary', pct: 50 }, { label: 'House rent allowance', pct: 20 }, { label: 'Special allowance', pct: 30 }]

export default function OfferForm({ open, onClose, offer, candidateId, onSaved }) {
  const candidates = useApi(open ? '/recruitment/candidates' : null, { page_size: 200 })
  const templates = useApi(open ? '/offers/templates' : null)
  const depts = useOptions('departments', open)
  const emps = useOptions('employees', open)
  const [target, setTarget] = useState('candidate')
  const [f, setF] = useState({})
  const [lines, setLines] = useState([])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setErr(null)
    if (offer) {
      setTarget(offer.candidate_id ? 'candidate' : offer.employee_id ? 'employee' : 'other')
      setF({ ...offer })
      setLines(offer.salary_breakup?.map((l) => ({ label: l.label, monthly: l.monthly })) || [])
    } else {
      setTarget(candidateId ? 'candidate' : 'candidate')
      setF({ candidate_id: candidateId || '', joining_date: '', designation: '', annual_ctc: '', work_location: '', valid_until: '', additional_terms: '' })
      setLines([])
    }
  }, [open, offer, candidateId])

  useEffect(() => {
    if (!f.candidate_id || offer) return
    const c = candidates.data?.items.find((x) => String(x.id) === String(f.candidate_id))
    if (c && !f.designation && c.job) setF((p) => ({ ...p, designation: c.job.title }))
  }, [f.candidate_id, candidates.data]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }))
  const ctc = Number(f.annual_ctc) || 0
  const total = lines.reduce((s, l) => s + (Number(l.monthly) || 0) * 12, 0)
  const mismatch = lines.length > 0 && Math.abs(total - ctc) > 1

  const autoSplit = () => setLines(DEFAULT_LINES.map((l, i) => {
    const m = Math.round((ctc * l.pct) / 100 / 12)
    return { label: l.label, monthly: i === DEFAULT_LINES.length - 1 ? Math.round(ctc / 12) - DEFAULT_LINES.slice(0, -1).reduce((s, x) => s + Math.round((ctc * x.pct) / 100 / 12), 0) : m }
  }))

  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    if (!f.designation || !f.joining_date || !ctc) { setErr('Designation, joining date and annual CTC are required.'); return }
    if (mismatch) { setErr('The salary breakup must add up to the annual CTC.'); return }
    const body = {
      candidate_id: target === 'candidate' && f.candidate_id ? Number(f.candidate_id) : null,
      employee_id: target === 'employee' && f.employee_id ? Number(f.employee_id) : null,
      recipient_name: target === 'other' ? f.recipient_name : null, recipient_email: target === 'other' ? f.recipient_email : null,
      template_id: f.template_id ? Number(f.template_id) : null, designation: f.designation, department_id: f.department_id ? Number(f.department_id) : null,
      joining_date: f.joining_date, annual_ctc: ctc, work_location: f.work_location || null, valid_until: f.valid_until || null,
      additional_terms: f.additional_terms || null,
      salary_breakup: lines.filter((l) => l.label).map((l) => ({ label: l.label, monthly: Number(l.monthly) || 0, annual: (Number(l.monthly) || 0) * 12 })),
    }
    setBusy(true)
    try {
      const r = offer ? await api.put(`/offers/${offer.id}`, body) : await api.post('/offers', body)
      onSaved?.(r.data)
      onClose()
    } catch (x) { setErr(errorMessage(x)) } finally { setBusy(false) }
  }

  return (
    <Drawer open={open} onClose={onClose} title={offer ? `Edit ${offer.reference_no}` : 'New offer letter'} width="max-w-2xl"
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="offer-form" loading={busy}>{offer ? 'Save draft' : 'Create draft'}</Button></>}>
      <form id="offer-form" onSubmit={submit} className="space-y-5">
        {err && <div className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2.5 text-[13px] text-danger">{err}</div>}
        <div>
          <p className="label">Offer for</p>
          <Segmented value={target} onChange={setTarget} options={[{ value: 'candidate', label: 'Candidate' }, { value: 'employee', label: 'Existing employee' }, { value: 'other', label: 'Other' }]} />
        </div>
        {target === 'candidate' && <Field label="Candidate" required><Select value={f.candidate_id || ''} onChange={set('candidate_id')} placeholder="Select candidate" options={(candidates.data?.items || []).filter((c) => c.status !== 'hired').map((c) => ({ value: c.id, label: `${c.full_name} · ${c.job?.title || 'General'}` }))} /></Field>}
        {target === 'employee' && <Field label="Employee" required hint="For appointment / revision letters. Approved letters are filed in the employee’s documents."><Select value={f.employee_id || ''} onChange={set('employee_id')} placeholder="Select employee" options={emps} /></Field>}
        {target === 'other' && <div className="grid gap-4 sm:grid-cols-2"><Field label="Recipient name" required><Input value={f.recipient_name || ''} onChange={set('recipient_name')} /></Field><Field label="Recipient email" required><Input type="email" value={f.recipient_email || ''} onChange={set('recipient_email')} /></Field></div>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Designation" required><Input value={f.designation || ''} onChange={set('designation')} /></Field>
          <Field label="Department"><Select value={f.department_id || ''} onChange={set('department_id')} placeholder="Select" options={depts} /></Field>
          <Field label="Joining date" required><Input type="date" value={f.joining_date || ''} onChange={set('joining_date')} /></Field>
          <Field label="Offer valid until"><Input type="date" value={f.valid_until || ''} onChange={set('valid_until')} /></Field>
          <Field label="Annual CTC (INR)" required><Input type="number" min="0" value={f.annual_ctc ?? ''} onChange={set('annual_ctc')} /></Field>
          <Field label="Work location"><Input value={f.work_location || ''} onChange={set('work_location')} /></Field>
          <Field label="Template" className="sm:col-span-2"><Select value={f.template_id || ''} onChange={set('template_id')} placeholder="Default template" options={(templates.data || []).filter((t) => t.is_active).map((t) => ({ value: t.id, label: t.name }))} /></Field>
        </div>
        <div className="rounded-xl border border-line p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-semibold">Compensation breakup <span className="font-normal text-muted">(optional)</span></p>
            <div className="flex gap-2">{ctc > 0 && <Button size="xs" variant="ghost" onClick={autoSplit}>Suggest split</Button>}<Button size="xs" variant="secondary" icon={Plus} onClick={() => setLines([...lines, { label: '', monthly: '' }])}>Line</Button></div>
          </div>
          {lines.length === 0 ? <p className="text-[13px] text-muted">Add components to include an annexure in the letter.</p> : (
            <div className="space-y-2">
              {lines.map((l, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input value={l.label} placeholder="Component" onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                  <Input type="number" min="0" value={l.monthly} placeholder="Monthly" className="w-36" onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, monthly: e.target.value } : x)))} />
                  <span className="num hidden w-28 text-right text-xs text-muted sm:block">{fmtMoney((Number(l.monthly) || 0) * 12)}/yr</span>
                  <IconButton icon={Trash2} size="sm" variant="danger" label="Remove line" onClick={() => setLines(lines.filter((_, j) => j !== i))} />
                </div>
              ))}
              <p className={`pt-1 text-right text-xs ${mismatch ? 'font-semibold text-danger' : 'text-muted'}`}>Total {fmtMoney(total)} / CTC {fmtMoney(ctc)}</p>
            </div>
          )}
        </div>
        <Field label="Additional terms"><Textarea rows={4} value={f.additional_terms || ''} onChange={set('additional_terms')} placeholder="Probation, notice period, benefits…" /></Field>
      </form>
    </Drawer>
  )
}
