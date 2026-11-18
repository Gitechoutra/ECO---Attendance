import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Globe, Mail, MapPin, Pencil, Phone, Plus, Star, Trash2, Upload } from 'lucide-react'
import { api, downloadFile } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useToast } from '../../context/ToastContext'
import { useOptions, invalidateOptions } from '../../hooks/useOptions'
import {
  Badge, Button, Card, CardHeader, ConfirmDialog, DataTable, DescriptionList, EmptyState, ErrorState, FormModal,
  IconButton, PageHeader, Progress, Skeleton, StatusBadge, Tabs,
} from '../../components/ui'
import { fmtDate, fmtDateTime, fmtMoney, titleCase } from '../../lib/format'
import { clientFields } from './ClientsPage'

const P = ['low', 'medium', 'high', 'urgent'].map((v) => ({ value: v, label: titleCase(v) }))

function configs(projects) {
  const proj = { name: 'project_id', label: 'Project', type: 'select', numeric: true, options: projects, placeholder: 'Not project-specific' }
  return {
    contacts: {
      title: 'Contact persons', singular: 'contact',
      fields: [{ name: 'name', label: 'Name', required: true, span: 1 }, { name: 'designation', label: 'Designation', span: 1 },
        { name: 'email', label: 'Email', type: 'email', span: 1 }, { name: 'phone', label: 'Phone', span: 1 }, { name: 'is_primary', label: 'Primary contact', type: 'checkbox' }],
      columns: [
        { key: 'name', header: 'Name', mobile: 'title', render: (c) => <span className="font-medium text-ink">{c.name} {c.is_primary && <Badge tone="brand">Primary</Badge>}</span> },
        { key: 'designation', header: 'Designation', render: (c) => c.designation || '—' },
        { key: 'email', header: 'Email', render: (c) => c.email ? <a className="link" href={`mailto:${c.email}`}>{c.email}</a> : '—' },
        { key: 'phone', header: 'Phone', render: (c) => c.phone || '—' }],
    },
    requirements: {
      title: 'Requirements', singular: 'requirement',
      fields: [{ name: 'title', label: 'Requirement', required: true }, { name: 'description', label: 'Details', type: 'textarea' },
        { name: 'priority', label: 'Priority', type: 'select', options: P, default: 'medium', span: 1 },
        { name: 'status', label: 'Status', type: 'select', default: 'open', span: 1, options: ['open', 'in_progress', 'delivered', 'dropped'].map((v) => ({ value: v, label: titleCase(v) })) }, proj],
      columns: [
        { key: 'title', header: 'Requirement', mobile: 'title', render: (r) => <div><p className="font-medium text-ink">{r.title}</p>{r.description && <p className="line-clamp-1 text-xs text-muted">{r.description}</p>}</div> },
        { key: 'priority', header: 'Priority', render: (r) => <StatusBadge status={r.priority} /> },
        { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
        { key: 'created', header: 'Logged', render: (r) => fmtDate(r.created_at) }],
    },
    meetings: {
      title: 'Meetings', singular: 'meeting', openToAll: true,
      fields: [{ name: 'title', label: 'Title', required: true }, { name: 'scheduled_at', label: 'Date & time', type: 'datetime-local', required: true, span: 1 },
        { name: 'duration_minutes', label: 'Duration (min)', type: 'number', default: 60, span: 1 }, { name: 'location', label: 'Location / link' },
        { name: 'status', label: 'Status', type: 'select', default: 'scheduled', span: 1, options: ['scheduled', 'completed', 'cancelled'].map((v) => ({ value: v, label: titleCase(v) })) }, { ...proj, span: 1 },
        { name: 'agenda', label: 'Agenda', type: 'textarea' }, { name: 'minutes', label: 'Minutes of meeting', type: 'textarea', rows: 4 }],
      columns: [
        { key: 'title', header: 'Meeting', mobile: 'title', render: (m) => <span className="font-medium text-ink">{m.title}</span> },
        { key: 'when', header: 'When', render: (m) => fmtDateTime(m.scheduled_at) },
        { key: 'loc', header: 'Location', render: (m) => m.location || '—' },
        { key: 'status', header: 'Status', render: (m) => <StatusBadge status={m.status} /> }],
    },
    contracts: {
      title: 'Contracts', singular: 'contract',
      fields: [{ name: 'title', label: 'Title', required: true }, { name: 'value', label: 'Value', type: 'number', min: 0, span: 1 },
        { name: 'currency', label: 'Currency', default: 'INR', span: 1 }, { name: 'start_date', label: 'Start', type: 'date', span: 1 }, { name: 'end_date', label: 'End', type: 'date', span: 1 },
        { name: 'status', label: 'Status', type: 'select', default: 'draft', options: ['draft', 'active', 'expired', 'terminated'].map((v) => ({ value: v, label: titleCase(v) })), span: 1 }, { ...proj, span: 1 }],
      columns: [
        { key: 'title', header: 'Contract', mobile: 'title', render: (k) => <span className="font-medium text-ink">{k.title}</span> },
        { key: 'value', header: 'Value', align: 'right', render: (k) => k.value !== null ? fmtMoney(k.value, k.currency) : '—' },
        { key: 'term', header: 'Term', render: (k) => `${fmtDate(k.start_date)} – ${fmtDate(k.end_date)}` },
        { key: 'status', header: 'Status', render: (k) => <StatusBadge status={k.status} /> }],
    },
    feedback: {
      title: 'Client feedback', singular: 'feedback',
      fields: [{ name: 'rating', label: 'Rating (1–5)', type: 'number', min: 1, max: 5, required: true, span: 1, validate: (v) => v < 1 || v > 5 ? 'Between 1 and 5' : null },
        { name: 'received_at', label: 'Received on', type: 'date', required: true, span: 1 }, proj, { name: 'comments', label: 'Comments', type: 'textarea' }],
      columns: [
        { key: 'rating', header: 'Rating', mobile: 'title', render: (f) => <span className="flex">{[1, 2, 3, 4, 5].map((i) => <Star key={i} className={`h-4 w-4 ${i <= f.rating ? 'fill-warning text-warning' : 'text-line-strong'}`} />)}</span> },
        { key: 'comments', header: 'Comments', mobile: 'full', render: (f) => f.comments || '—' },
        { key: 'date', header: 'Received', render: (f) => fmtDate(f.received_at) }],
    },
  }
}

function SubResource({ clientId, kind, cfg, canManage, extraActions }) {
  const toast = useToast()
  const { data, loading, error, reload } = useApi(`/clients/${clientId}/${kind}`)
  const [form, setForm] = useState(null)
  const [del, setDel] = useState(null)
  const [run, busy] = useAction(toast)
  const editable = canManage || cfg.openToAll
  return (
    <Card padded={false}>
      <div className="flex items-center justify-between p-5 pb-3"><h3 className="text-[15px] font-semibold">{cfg.title}</h3>{editable && <Button size="sm" icon={Plus} onClick={() => setForm({})}>Add {cfg.singular}</Button>}</div>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data} empty={<EmptyState compact title={`No ${cfg.title.toLowerCase()} yet`} />}
        columns={[...cfg.columns, { key: 'a', header: '', align: 'right', render: (r) => (
          <div className="flex justify-end gap-1">
            {extraActions?.(r, reload)}
            {editable && <IconButton icon={Pencil} size="sm" label="Edit" onClick={() => setForm({ ...r, scheduled_at: r.scheduled_at?.slice(0, 16) })} />}
            {canManage && <IconButton icon={Trash2} size="sm" variant="danger" label="Delete" onClick={() => setDel(r)} />}
          </div>) }]} />
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={`${form?.id ? 'Edit' : 'Add'} ${cfg.singular}`} initial={form} fields={cfg.fields} size="lg"
        onSubmit={async (v) => { form.id ? await api.put(`/clients/${clientId}/${kind}/${form.id}`, v) : await api.post(`/clients/${clientId}/${kind}`, v); toast.success('Saved'); reload() }} />
      <ConfirmDialog open={Boolean(del)} onClose={() => setDel(null)} title={`Delete ${cfg.singular}`} description="This cannot be undone." loading={busy} confirmLabel="Delete"
        onConfirm={async () => { await run(() => api.delete(`/clients/${clientId}/${kind}/${del.id}`), { success: 'Deleted' }); setDel(null); reload() }} />
    </Card>
  )
}

function Communication({ clientId }) {
  const toast = useToast()
  const comms = useApi(`/clients/${clientId}/communications`)
  const [form, setForm] = useState(false)
  const ICON = { call: Phone, email: Mail, meeting: Globe, note: Pencil, chat: Mail }
  return (
    <Card>
      <CardHeader title="Communication history" subtitle="Calls, meetings, notes and linked emails" action={<Button size="sm" icon={Plus} onClick={() => setForm(true)}>Log interaction</Button>} />
      {comms.loading ? <Skeleton className="h-32" /> : !comms.data?.length ? <EmptyState compact title="No interactions logged" /> : (
        <ol className="relative space-y-5 border-l border-line pl-6">
          {comms.data.map((c) => {
            const I = ICON[c.channel] || Pencil
            return (
              <li key={c.id} className="relative">
                <span className="absolute -left-[37px] flex h-6 w-6 items-center justify-center rounded-full border-2 border-surface bg-brand-soft text-brand-ink"><I className="h-3 w-3" /></span>
                <p className="text-sm font-medium">{c.subject}</p>
                <p className="text-xs text-muted">{titleCase(c.channel)} · {fmtDateTime(c.occurred_at)}{c.user && ` · ${c.user}`}</p>
                {c.summary && <p className="mt-1 whitespace-pre-wrap text-[13px] text-ink-2">{c.summary}</p>}
                {c.email_message_id && <Link to={`/email?message=${c.email_message_id}`} className="mt-1 inline-block text-xs font-medium text-brand-ink hover:underline">Open email</Link>}
              </li>
            )
          })}
        </ol>
      )}
      <FormModal open={form} onClose={() => setForm(false)} title="Log interaction"
        fields={[{ name: 'channel', label: 'Channel', type: 'select', required: true, default: 'call', span: 1, options: ['call', 'meeting', 'note', 'chat', 'email'].map((v) => ({ value: v, label: titleCase(v) })) },
          { name: 'occurred_at', label: 'When', type: 'datetime-local', span: 1 }, { name: 'subject', label: 'Subject', required: true }, { name: 'summary', label: 'Summary', type: 'textarea', rows: 4 }]}
        onSubmit={async (v) => { await api.post(`/clients/${clientId}/communications`, v); toast.success('Interaction logged'); comms.reload() }} />
    </Card>
  )
}

export default function ClientDetailPage() {
  const { id } = useParams()
  const toast = useToast()
  const { data: c, loading, error, reload } = useApi(`/clients/${id}`)
  const projects = useApi(`/clients/${id}/projects`)
  const employees = useOptions('employees')
  const [tab, setTab] = useState('overview')
  const [edit, setEdit] = useState(false)
  const [run] = useAction(toast)
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (loading || !c) return <Skeleton className="h-64" />
  const projOpts = (projects.data || []).map((p) => ({ value: p.id, label: p.name }))
  const cfg = configs(projOpts)
  const canManage = Boolean(c.can_manage)

  const uploadContract = (row, reloadList) => canManage && (
    <label className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink" title={row.file_id ? 'Replace document' : 'Upload document'}>
      <Upload className="h-4 w-4" />
      <input type="file" className="hidden" accept=".pdf,.doc,.docx,image/*" onChange={async (e) => {
        const f = e.target.files?.[0]; if (!f) return
        const fd = new FormData(); fd.append('file', f)
        await run(() => api.post(`/clients/${id}/contracts/${row.id}/file`, fd), { success: 'Contract document uploaded' }); reloadList()
      }} />
    </label>
  )
  const contractCfg = { ...cfg.contracts, columns: [...cfg.contracts.columns, { key: 'doc', header: 'Document', render: (k) => k.file_id ? <button className="link" onClick={() => downloadFile(`/files/${k.file_id}`, { inline: false })}>Download</button> : '—' }] }

  return (
    <>
      <PageHeader title={c.name} breadcrumbs={[{ label: 'Clients', to: '/clients' }, { label: c.name }]}
        description={[c.industry, c.city, c.country].filter(Boolean).join(' · ') || c.company_name}
        actions={canManage && <Button variant="secondary" icon={Pencil} onClick={() => setEdit(true)}>Edit</Button>} />
      <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[
        { value: 'overview', label: 'Overview' }, { value: 'projects', label: 'Projects', count: projects.data?.length },
        { value: 'requirements', label: 'Requirements' }, { value: 'meetings', label: 'Meetings' }, { value: 'communication', label: 'Communication' },
        { value: 'contracts', label: 'Contracts' }, { value: 'feedback', label: 'Feedback' }]} />
      {tab === 'overview' && (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader title="Company details" action={<StatusBadge status={c.status} />} />
              <DescriptionList items={[
                ['Registered name', c.company_name], ['Industry', c.industry],
                ['Email', c.email && <a key="e" href={`mailto:${c.email}`} className="link">{c.email}</a>], ['Phone', c.phone],
                ['Website', c.website && <a key="w" href={c.website.startsWith('http') ? c.website : `https://${c.website}`} target="_blank" rel="noreferrer" className="link">{c.website}</a>],
                ['GSTIN / Tax ID', c.tax_id], ['Account manager', c.account_manager?.full_name], ['Client since', fmtDate(c.created_at)],
              ]} />
              {c.address && <p className="mt-4 flex gap-2 text-sm text-ink-2"><MapPin className="mt-0.5 h-4 w-4 text-muted" />{c.address}</p>}
              {c.notes && <p className="mt-4 whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-[13px] text-ink-2">{c.notes}</p>}
            </Card>
            <Card>
              <CardHeader title="At a glance" />
              <DescriptionList cols={1} items={[['Projects', `${c.active_projects} active · ${c.project_count} total`],
                ['Average feedback', c.avg_rating ? `${c.avg_rating} / 5` : 'No feedback yet'], ['Primary contact', c.primary_contact ? `${c.primary_contact.name} (${c.primary_contact.email || c.primary_contact.phone || ''})` : '—']]} />
            </Card>
          </div>
          <SubResource clientId={id} kind="contacts" cfg={cfg.contacts} canManage={canManage} />
        </div>
      )}
      {tab === 'projects' && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.data?.length ? projects.data.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="card p-4 hover:border-line-strong">
              <div className="flex justify-between gap-2"><div><p className="text-2xs font-semibold uppercase tracking-wide text-faint">{p.code}</p><p className="font-semibold">{p.name}</p></div><StatusBadge status={p.status} /></div>
              <Progress value={p.progress} showLabel className="mt-3" tone={p.is_delayed ? 'danger' : 'brand'} />
              <p className="mt-2 text-xs text-muted">{fmtDate(p.start_date)} – {fmtDate(p.end_date)}</p>
            </Link>
          )) : <EmptyState title="No projects for this client" description="Projects created for this client appear here automatically." className="sm:col-span-2 xl:col-span-3" />}
        </div>
      )}
      {['requirements', 'meetings', 'feedback'].includes(tab) && <SubResource clientId={id} kind={tab} cfg={cfg[tab]} canManage={canManage} />}
      {tab === 'contracts' && <SubResource clientId={id} kind="contracts" cfg={contractCfg} canManage={canManage} extraActions={uploadContract} />}
      {tab === 'communication' && <Communication clientId={id} />}
      <FormModal open={edit} onClose={() => setEdit(false)} title="Edit client" size="lg" initial={c} fields={clientFields(employees)}
        onSubmit={async (v) => { await api.put(`/clients/${id}`, v); invalidateOptions('clients'); toast.success('Client updated'); reload() }} />
    </>
  )
}
