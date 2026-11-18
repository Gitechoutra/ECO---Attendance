import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { AlarmClock, ArrowLeft, Check, Inbox, Link2, Mail, PenSquare, Plug, RefreshCw, Reply, Unplug } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useAction, useDebounced } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions } from '../../hooks/useOptions'
import {
  Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, FormModal, IconButton, Modal, PageHeader, Pagination,
  SearchInput, Segmented, Select, Skeleton, StatusBadge, Tabs,
} from '../../components/ui'
import { fmtDateTime, fromNow } from '../../lib/format'

function ConnectModal({ open, onClose, status }) {
  const { can } = useAuth()
  const toast = useToast()
  const [shared, setShared] = useState(false)
  const connect = async (provider) => {
    try {
      const { data } = await api.post('/email/connect', { provider, shared })
      window.location.href = data.auth_url
    } catch (e) { toast.apiError(e, 'Cannot connect mailbox') }
  }
  return (
    <Modal open={open} onClose={onClose} title="Connect a mailbox" description="You’ll sign in with the provider and grant read/send access. ECHOUTRA ONE never sees your password.">
      <div className="space-y-3">
        {[{ id: 'gmail', name: 'Google Workspace / Gmail' }, { id: 'outlook', name: 'Microsoft 365 / Outlook' }].map((p) => (
          <button key={p.id} onClick={() => connect(p.id)} disabled={!status?.[p.id]}
            className="flex w-full items-center gap-3 rounded-xl border border-line p-4 text-left transition-colors hover:border-brand disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:border-line">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-2"><Mail className="h-5 w-5 text-ink-2" /></span>
            <span className="flex-1"><span className="block text-sm font-semibold">{p.name}</span>
              <span className="block text-xs text-muted">{status?.[p.id] ? 'OAuth 2.0 · official API' : 'Not configured by your administrator'}</span></span>
            <Plug className="h-4 w-4 text-muted" />
          </button>
        ))}
        {can('email.view_shared') && (
          <label className="flex items-start gap-2.5 rounded-lg bg-surface-2 p-3 text-[13px]">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} className="mt-0.5 accent-[rgb(var(--brand-strong))]" />
            <span><b className="text-ink">Shared company mailbox</b><br /><span className="text-muted">Visible to users with shared-mailbox permission (e.g. sales@ or info@). Never connect personal inboxes as shared.</span></span>
          </label>
        )}
        {!status?.gmail && !status?.outlook && (
          <p className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-[13px] text-warning">
            Email integration needs OAuth credentials. An administrator must add GOOGLE_CLIENT_ID/SECRET and/or MICROSOFT_CLIENT_ID/SECRET to the server configuration (see docs/INTEGRATIONS.md).
          </p>
        )}
      </div>
    </Modal>
  )
}

function Compose({ open, onClose, accounts, replyTo, onSent }) {
  const toast = useToast()
  const mine = accounts.filter((a) => a.sync_status !== 'disconnected')
  return (
    <FormModal open={open} onClose={onClose} title={replyTo ? 'Reply' : 'New email'} size="lg" submitLabel="Send"
      initial={replyTo ? { account_id: replyTo.account_id, to: (replyTo.from_address?.match(/<([^>]+)>/)?.[1] || replyTo.from_address || ''), subject: replyTo.subject?.startsWith('Re:') ? replyTo.subject : `Re: ${replyTo.subject || ''}` } : { account_id: mine[0]?.id }}
      fields={[
        { name: 'account_id', label: 'From', type: 'select', numeric: true, required: true, options: mine.map((a) => ({ value: a.id, label: a.email_address })) },
        { name: 'to', label: 'To', required: true, placeholder: 'name@company.com, other@company.com' },
        { name: 'cc', label: 'Cc' },
        { name: 'subject', label: 'Subject', required: true },
        { name: 'body', label: 'Message', type: 'textarea', rows: 10, required: true },
      ]}
      onSubmit={async (v) => {
        const split = (s) => (s || '').split(/[,;\s]+/).filter(Boolean)
        await api.post('/email/send', { ...v, to: split(v.to), cc: split(v.cc), reply_to_message_id: replyTo?.id })
        toast.success('Email sent'); onSent?.()
      }} />
  )
}

function Reader({ id, accounts, onBack, onChanged }) {
  const toast = useToast()
  const { data: m, loading, error, reload } = useApi(id ? `/email/messages/${id}` : null)
  const clients = useOptions('clients')
  const projects = useOptions('projects')
  const [link, setLink] = useState(false)
  const [fu, setFu] = useState(false)
  const [reply, setReply] = useState(false)
  if (!id) return <EmptyState icon={Mail} title="Select an email" description="Choose a message to read it here." className="h-full" />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (loading || !m) return <div className="space-y-3 p-5"><Skeleton className="h-6 w-2/3" /><Skeleton className="h-40" /></div>
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-line px-3 py-2">
        <IconButton icon={ArrowLeft} label="Back" onClick={onBack} className="lg:hidden" />
        <Button size="sm" variant="ghost" icon={Reply} onClick={() => setReply(true)} disabled={!accounts.some((a) => a.id === m.account_id && a.sync_status !== 'disconnected')}>Reply</Button>
        <Button size="sm" variant="ghost" icon={Link2} onClick={() => setLink(true)}>Link</Button>
        <Button size="sm" variant="ghost" icon={AlarmClock} onClick={() => setFu(true)}>Follow up</Button>
      </div>
      <div className="scrollbar-thin flex-1 overflow-y-auto p-5">
        <h2 className="text-lg font-semibold">{m.subject || '(no subject)'}</h2>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {m.client && <Badge tone="brand">{m.client.name}</Badge>}
          {m.project && <Badge tone="info">{m.project.name}</Badge>}
          {m.followups.filter((f) => !f.is_done).map((f) => <Badge key={f.id} tone="warning"><AlarmClock className="h-3 w-3" />Follow up {fmtDateTime(f.due_at)}</Badge>)}
        </div>
        <div className="mt-4 rounded-lg bg-surface-2 p-3 text-[13px]">
          <p><span className="text-muted">From </span><span className="text-ink">{m.from_address}</span></p>
          <p className="mt-0.5"><span className="text-muted">To </span><span className="text-ink-2">{m.to_addresses}</span></p>
          {m.cc_addresses && <p className="mt-0.5"><span className="text-muted">Cc </span><span className="text-ink-2">{m.cc_addresses}</span></p>}
          <p className="mt-0.5 text-muted">{fmtDateTime(m.sent_at)} · via {m.account}</p>
        </div>
        <div className="mt-5 whitespace-pre-wrap break-words text-sm leading-relaxed text-ink-2">{m.body_text || m.snippet}</div>
        {m.thread.length > 0 && (
          <div className="mt-8 border-t border-line pt-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">Conversation ({m.thread.length + 1})</p>
            {m.thread.map((t) => <p key={t.id} className="truncate py-1 text-[13px] text-ink-2">{fmtDateTime(t.sent_at)} · <b>{t.from_address}</b> — {t.snippet}</p>)}
          </div>
        )}
      </div>
      <FormModal open={link} onClose={() => setLink(false)} title="Link to client or project" initial={{ client_id: m.client?.id, project_id: m.project?.id }}
        fields={[{ name: 'client_id', label: 'Client', type: 'select', numeric: true, options: clients, placeholder: 'None' }, { name: 'project_id', label: 'Project', type: 'select', numeric: true, options: projects, placeholder: 'None' }]}
        onSubmit={async (v) => { await api.post(`/email/messages/${m.id}/link`, v); toast.success('Email linked', 'It now appears in the client’s communication history.'); reload(); onChanged() }} />
      <FormModal open={fu} onClose={() => setFu(false)} title="Set follow-up reminder"
        fields={[{ name: 'due_at', label: 'Remind me at', type: 'datetime-local', required: true }, { name: 'note', label: 'Note' }]}
        onSubmit={async (v) => { await api.post(`/email/messages/${m.id}/followups`, { ...v, due_at: new Date(v.due_at).toISOString() }); toast.success('Reminder set'); reload() }} />
      <Compose open={reply} onClose={() => setReply(false)} accounts={accounts} replyTo={m} onSent={onChanged} />
    </div>
  )
}

export default function EmailPage() {
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const status = useApi('/email/status')
  const accounts = useApi('/email/accounts')
  const [tab, setTab] = useState('inbox')
  const [acc, setAcc] = useState('')
  const [dir, setDir] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [connect, setConnect] = useState(false)
  const [compose, setCompose] = useState(false)
  const [disc, setDisc] = useState(null)
  const selected = params.get('message')
  const dq = useDebounced(q)
  const msgs = useApi('/email/messages', { q: dq || undefined, account_id: acc || undefined, direction: dir || undefined, page, page_size: 30 })
  const fups = useApi(tab === 'followups' ? '/email/followups' : null)
  const [run, busy] = useAction(toast)
  useEffect(() => { setPage(1) }, [dq, acc, dir])
  useEffect(() => {
    const c = params.get('connected')
    if (c === '1') { toast.success('Mailbox connected', 'Initial sync runs in the background.'); setParams({}) }
    else if (c === '0') { toast.error('Mailbox not connected', params.get('error') || 'Authorization was cancelled'); setParams({}) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const accs = accounts.data || []
  const select = (id) => setParams({ message: String(id) })

  return (
    <>
      <PageHeader title="Email" description="Authorized company mailboxes, linked to clients and projects."
        actions={<>
          <Button variant="secondary" icon={Plug} onClick={() => setConnect(true)}>Connect mailbox</Button>
          <Button icon={PenSquare} disabled={!accs.some((a) => a.sync_status !== 'disconnected')} onClick={() => setCompose(true)}>Compose</Button>
        </>} />
      {accs.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {accs.map((a) => (
            <div key={a.id} className="card flex items-center gap-3 px-3 py-2">
              <span className={clsx('h-2 w-2 rounded-full', a.sync_status === 'connected' ? 'bg-success' : a.sync_status === 'error' ? 'bg-danger' : 'bg-line-strong')} />
              <div className="text-[13px]"><p className="font-medium">{a.email_address} {a.is_shared && <Badge tone="info">Shared</Badge>}</p>
                <p className="text-2xs text-muted">{a.sync_error || (a.last_synced_at ? `Synced ${fromNow(a.last_synced_at)}` : 'Not synced yet')}</p></div>
              {a.sync_status !== 'disconnected' && <IconButton icon={RefreshCw} label="Sync now" size="sm" disabled={busy}
                onClick={async () => { const r = await run(() => api.post(`/email/accounts/${a.id}/sync`)); toast.success(`${r.data.new_messages} new message(s)`); accounts.reload(); msgs.reload() }} />}
              <IconButton icon={Unplug} label="Disconnect" size="sm" variant="danger" onClick={() => setDisc(a)} />
            </div>
          ))}
        </div>
      )}
      <Tabs className="mb-4" value={tab} onChange={setTab} tabs={[{ value: 'inbox', label: 'Messages', count: msgs.data?.total }, { value: 'followups', label: 'Follow-ups' }]} />
      {tab === 'inbox' ? (
        accs.length === 0 && !accounts.loading ? (
          <Card><EmptyState icon={Inbox} title="No mailbox connected" description="Connect your authorized work mailbox to sync conversations and link them to clients and projects."
            action={<Button icon={Plug} onClick={() => setConnect(true)}>Connect mailbox</Button>} /></Card>
        ) : (
          <div className="card grid h-[calc(100vh-300px)] min-h-[520px] overflow-hidden lg:grid-cols-[380px_1fr]">
            <div className={clsx('flex min-h-0 flex-col border-line lg:border-r', selected && 'hidden lg:flex')}>
              <div className="space-y-2 border-b border-line p-3">
                <SearchInput value={q} onChange={setQ} placeholder="Search subject, sender…" />
                <div className="flex gap-2">
                  <Select value={acc} onChange={(e) => setAcc(e.target.value)} placeholder="All mailboxes" options={accs.map((a) => ({ value: a.id, label: a.email_address }))} />
                  <Segmented size="sm" value={dir} onChange={setDir} options={[{ value: '', label: 'All' }, { value: 'in', label: 'In' }, { value: 'out', label: 'Sent' }]} />
                </div>
              </div>
              <div className="scrollbar-thin flex-1 overflow-y-auto">
                {msgs.loading && !msgs.data ? <div className="space-y-3 p-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
                  : msgs.error ? <ErrorState message={msgs.error} onRetry={msgs.reload} />
                    : !msgs.data?.items.length ? <EmptyState compact icon={Inbox} title="No messages" />
                      : msgs.data.items.map((m) => (
                        <button key={m.id} onClick={() => select(m.id)} className={clsx('block w-full border-b border-line/70 px-4 py-3 text-left hover:bg-surface-2', String(m.id) === selected && 'bg-brand-soft/50')}>
                          <div className="flex items-baseline justify-between gap-2">
                            <p className={clsx('truncate text-[13px]', m.is_read ? 'text-ink-2' : 'font-semibold text-ink')}>{m.direction === 'out' ? `To: ${m.to_addresses}` : m.from_address}</p>
                            <span className="shrink-0 text-2xs text-faint">{fromNow(m.sent_at)}</span>
                          </div>
                          <p className={clsx('truncate text-[13px]', m.is_read ? 'text-ink-2' : 'font-medium text-ink')}>{m.subject || '(no subject)'}</p>
                          <p className="truncate text-xs text-muted">{m.snippet}</p>
                          {(m.client || m.project) && <div className="mt-1 flex gap-1">{m.client && <Badge tone="brand" className="text-2xs">{m.client.name}</Badge>}{m.project && <Badge tone="info" className="text-2xs">{m.project.name}</Badge>}</div>}
                        </button>
                      ))}
              </div>
              <Pagination page={page} pages={msgs.data?.pages} total={msgs.data?.total} pageSize={30} onChange={setPage} />
            </div>
            <div className={clsx('min-h-0', !selected && 'hidden lg:block')}>
              <Reader id={selected} accounts={accs} onBack={() => setParams({})} onChanged={() => msgs.reload({ silent: true })} />
            </div>
          </div>
        )
      ) : (
        <Card>
          {fups.loading ? <Skeleton className="h-32" /> : !fups.data?.length ? <EmptyState compact icon={AlarmClock} title="No follow-ups pending" /> : (
            <ul className="divide-y divide-line">
              {fups.data.map((f) => (
                <li key={f.id} className="flex items-center gap-3 py-3">
                  <AlarmClock className={clsx('h-4 w-4 shrink-0', f.is_overdue ? 'text-danger' : 'text-warning')} />
                  <button className="min-w-0 flex-1 text-left" onClick={() => { setTab('inbox'); select(f.message.id) }}>
                    <p className="truncate text-sm font-medium">{f.message.subject || '(no subject)'}</p>
                    <p className="truncate text-xs text-muted">{fmtDateTime(f.due_at)}{f.note && ` · ${f.note}`}</p>
                  </button>
                  {f.is_overdue && <StatusBadge status="overdue" />}
                  <Button size="xs" variant="secondary" icon={Check} onClick={async () => { await run(() => api.post(`/email/followups/${f.id}/done`), { success: 'Done' }); fups.reload() }}>Done</Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      <ConnectModal open={connect} onClose={() => setConnect(false)} status={status.data} />
      <Compose open={compose} onClose={() => setCompose(false)} accounts={accs} onSent={() => msgs.reload()} />
      <ConfirmDialog open={Boolean(disc)} onClose={() => setDisc(null)} title="Disconnect mailbox" loading={busy} confirmLabel="Disconnect"
        description={`Stop syncing ${disc?.email_address}? Access tokens are deleted. Already-synced messages stay linked to clients.`}
        onConfirm={async () => { await run(() => api.delete(`/email/accounts/${disc.id}`), { success: 'Mailbox disconnected' }); setDisc(null); accounts.reload() }} />
    </>
  )
}
