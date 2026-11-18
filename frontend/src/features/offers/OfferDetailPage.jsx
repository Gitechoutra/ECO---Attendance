import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Ban, Check, Copy, Download, Pencil, Send, ShieldCheck, X } from 'lucide-react'
import { api, downloadFile } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import {
  Button, Card, CardHeader, ConfirmDialog, DescriptionList, ErrorState, Field, FormModal, Modal, PageHeader, Select,
  Skeleton, StatusBadge,
} from '../../components/ui'
import { fmtDate, fmtDateTime, fmtMoney } from '../../lib/format'
import OfferForm from './OfferForm'

const STEPS = ['draft', 'pending_approval', 'approved', 'sent', 'accepted']

export default function OfferDetailPage() {
  const { id } = useParams()
  const { can, user } = useAuth()
  const toast = useToast()
  const { data: o, loading, error, reload } = useApi(`/offers/${id}`)
  const accounts = useApi(can('email.use') ? '/email/accounts' : null)
  const [edit, setEdit] = useState(false)
  const [decide, setDecide] = useState(null)
  const [sendOpen, setSendOpen] = useState(false)
  const [acc, setAcc] = useState('')
  const [link, setLink] = useState(null)
  const [withdraw, setWithdraw] = useState(false)
  const [run, busy] = useAction(toast)
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (loading || !o) return <Skeleton className="h-72" />
  const manage = can('offers.manage')
  const idx = STEPS.indexOf(o.status)
  const myMailboxes = (accounts.data || []).filter((a) => a.owner === user.email && a.sync_status !== 'disconnected')

  return (
    <>
      <PageHeader title={o.recipient_name} breadcrumbs={[{ label: 'Offer letters', to: '/offers' }, { label: o.reference_no }]}
        description={`${o.designation}${o.department ? ` · ${o.department}` : ''} · ${fmtMoney(o.annual_ctc)} per annum`}
        actions={<>
          {o.versions[0] && <Button variant="secondary" icon={Download} onClick={() => downloadFile(`/files/${o.versions[0].file_id}`, { inline: false })}>PDF v{o.versions[0].version}</Button>}
          {manage && ['draft', 'rejected'].includes(o.status) && <>
            <Button variant="secondary" icon={Pencil} onClick={() => setEdit(true)}>Edit</Button>
            <Button icon={ShieldCheck} loading={busy} onClick={async () => { await run(() => api.post(`/offers/${o.id}/submit`), { success: 'Submitted for approval' }); reload() }}>Submit for approval</Button>
          </>}
          {can('offers.approve') && o.status === 'pending_approval' && <>
            <Button variant="secondary" icon={X} onClick={() => setDecide('reject')}>Reject</Button>
            <Button icon={Check} onClick={() => setDecide('approve')}>Approve</Button>
          </>}
          {manage && ['approved', 'sent'].includes(o.status) && <Button icon={Send} onClick={() => setSendOpen(true)}>{o.status === 'sent' ? 'Resend link' : 'Send offer'}</Button>}
          {manage && !['accepted', 'declined', 'withdrawn'].includes(o.status) && <Button variant="danger-ghost" icon={Ban} onClick={() => setWithdraw(true)}>Withdraw</Button>}
        </>} />

      <Card className="mb-5">
        <div className="flex items-center gap-1 overflow-x-auto">
          {STEPS.map((s, i) => (
            <div key={s} className="flex flex-1 items-center gap-2">
              <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${i <= idx && idx >= 0 ? 'bg-brand text-[#03211D]' : 'bg-surface-2 text-muted'}`}>{i + 1}</span>
              <span className={`whitespace-nowrap text-xs font-medium ${i <= idx ? 'text-ink' : 'text-muted'}`}>{{ draft: 'Draft', pending_approval: 'Approval', approved: 'Approved', sent: 'Sent', accepted: 'Accepted' }[s]}</span>
              {i < STEPS.length - 1 && <span className={`mx-1 h-px min-w-4 flex-1 ${i < idx ? 'bg-brand' : 'bg-line'}`} />}
            </div>
          ))}
        </div>
        {['rejected', 'declined', 'withdrawn'].includes(o.status) && <p className="mt-3 text-[13px]"><StatusBadge status={o.status} /> {o.approval_note || o.response_note}</p>}
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Letter preview" subtitle="Rendered from the template; the PDF adds the company header and annexure." />
          <div className="rounded-xl border border-line bg-surface-2/60 p-6">
            <p className="text-xs text-muted">Ref: {o.reference_no}</p>
            <p className="mt-3 text-lg font-semibold">Offer of Employment</p>
            <div className="mt-4 space-y-3 text-sm leading-relaxed text-ink-2">{o.preview.split('\n\n').map((p, i) => <p key={i} className="whitespace-pre-wrap">{p}</p>)}</div>
            {o.salary_breakup.length > 0 && (
              <table className="mt-6 w-full text-sm">
                <thead><tr className="border-b border-line text-left text-xs text-muted"><th className="py-2">Component</th><th className="py-2 text-right">Monthly</th><th className="py-2 text-right">Annual</th></tr></thead>
                <tbody>{o.salary_breakup.map((l) => <tr key={l.label} className="border-b border-line/60"><td className="py-2">{l.label}</td><td className="num py-2 text-right">{fmtMoney(l.monthly)}</td><td className="num py-2 text-right">{fmtMoney(l.annual)}</td></tr>)}
                  <tr className="font-semibold"><td className="py-2">Total CTC</td><td className="num py-2 text-right">{fmtMoney(o.annual_ctc / 12)}</td><td className="num py-2 text-right">{fmtMoney(o.annual_ctc)}</td></tr></tbody>
              </table>
            )}
          </div>
        </Card>
        <div className="space-y-4">
          <Card><CardHeader title="Details" /><DescriptionList cols={1} items={[
            ['Status', <StatusBadge key="s" status={o.status} />], ['Recipient', `${o.recipient_name} · ${o.recipient_email}`],
            ['Joining date', fmtDate(o.joining_date)], ['Valid until', o.valid_until ? fmtDate(o.valid_until) : '—'], ['Work location', o.work_location],
            ['Approved by', o.approved_by ? `${o.approved_by} · ${fmtDateTime(o.approved_at)}` : '—'], ['Sent', o.sent_at ? fmtDateTime(o.sent_at) : '—'],
            o.responded_at && ['Response', `${o.status} · ${fmtDateTime(o.responded_at)}`], o.response_signature && ['Signed as', `${o.response_signature} (IP ${o.response_ip})`],
            o.candidate_id && ['Candidate', <Link key="c" className="link" to={`/recruitment/candidates/${o.candidate_id}`}>Open candidate</Link>],
            o.employee_id && ['Employee', <Link key="e" className="link" to={`/employees/${o.employee_id}`}>Open employee</Link>],
          ]} /></Card>
          <Card>
            <CardHeader title="Version history" />
            {!o.versions.length ? <p className="text-sm text-muted">A PDF is generated when the draft is submitted.</p> : (
              <ul className="space-y-2">{o.versions.map((v) => (
                <li key={v.version} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2">
                  <div className="min-w-0"><p className="text-[13px] font-medium">Version {v.version}</p><p className="truncate text-2xs text-muted">{v.change_note} · {fmtDateTime(v.created_at)}</p></div>
                  <Button size="xs" variant="ghost" icon={Download} onClick={() => downloadFile(`/files/${v.file_id}`, { inline: false })}>PDF</Button>
                </li>))}</ul>
            )}
          </Card>
        </div>
      </div>

      <OfferForm open={edit} onClose={() => setEdit(false)} offer={o} onSaved={() => { toast.success('Draft saved'); reload() }} />
      <FormModal open={Boolean(decide)} onClose={() => setDecide(null)} title={decide === 'approve' ? 'Approve offer' : 'Reject offer'} submitLabel={decide === 'approve' ? 'Approve' : 'Reject'}
        fields={[{ name: 'note', label: decide === 'approve' ? 'Note (optional)' : 'Reason', type: 'textarea', required: decide === 'reject' }]}
        onSubmit={async (v) => { await api.post(`/offers/${o.id}/decision`, { approve: decide === 'approve', note: v.note }); toast.success(decide === 'approve' ? 'Offer approved' : 'Offer rejected'); reload() }} />
      <Modal open={sendOpen} onClose={() => setSendOpen(false)} title="Send offer" description="Creates a secure, single-use link where the recipient can review, download and accept or decline."
        footer={<><Button variant="secondary" onClick={() => setSendOpen(false)}>Cancel</Button><Button icon={Send} loading={busy} onClick={async () => {
          const r = await run(() => api.post(`/offers/${o.id}/send`, null, { params: { account_id: acc || undefined } }), { success: acc ? 'Offer emailed' : 'Response link created' })
          setSendOpen(false); setLink(r.data.response_link); reload()
        }}>{acc ? 'Send email' : 'Create link'}</Button></>}>
        <Field label="Email it from" hint={myMailboxes.length ? 'Uses your connected mailbox.' : 'Connect a mailbox in Email to send directly. Otherwise copy the link and share it.'}>
          <Select value={acc} onChange={(e) => setAcc(e.target.value)} placeholder="Don’t email — just create the link" options={myMailboxes.map((a) => ({ value: a.id, label: a.email_address }))} />
        </Field>
        {o.status === 'sent' && <p className="mt-3 text-[13px] text-warning">Sending again invalidates the previous link.</p>}
      </Modal>
      <Modal open={Boolean(link)} onClose={() => setLink(null)} title="Offer response link" size="md" footer={<Button onClick={() => setLink(null)}>Done</Button>}>
        <p className="text-sm text-ink-2">Share this private link with {o.recipient_name}. It is shown only now.</p>
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-line bg-surface-2 p-3">
          <code className="flex-1 break-all text-xs">{link}</code>
          <Button size="sm" variant="secondary" icon={Copy} onClick={() => { navigator.clipboard?.writeText(link); toast.success('Link copied') }}>Copy</Button>
        </div>
      </Modal>
      <ConfirmDialog open={withdraw} onClose={() => setWithdraw(false)} title="Withdraw offer" description="The response link stops working immediately." confirmLabel="Withdraw" loading={busy}
        onConfirm={async () => { await run(() => api.post(`/offers/${o.id}/withdraw`), { success: 'Offer withdrawn' }); setWithdraw(false); reload() }} />
    </>
  )
}
