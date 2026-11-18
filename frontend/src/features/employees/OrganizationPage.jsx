import { useState } from 'react'
import { Building2, Pencil, Plus, Trash2 } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useOptions, invalidateOptions } from '../../hooks/useOptions'
import { useToast } from '../../context/ToastContext'
import { Badge, Button, ConfirmDialog, DataTable, EmptyState, FormModal, IconButton, PageHeader, Tabs } from '../../components/ui'

export default function OrganizationPage() {
  const toast = useToast()
  const [tab, setTab] = useState('departments')
  const depts = useApi('/departments')
  const desigs = useApi('/designations')
  const emps = useOptions('employees')
  const deptOpts = useOptions('departments')
  const [form, setForm] = useState(null) // {kind, item}
  const [del, setDel] = useState(null)
  const [run, busy] = useAction(toast)

  const deptFields = [
    { name: 'name', label: 'Department name', required: true, span: 1 },
    { name: 'code', label: 'Code', required: true, span: 1, placeholder: 'ENG' },
    { name: 'head_id', label: 'Department head', type: 'select', numeric: true, options: emps, placeholder: 'None' },
    { name: 'description', label: 'Description', type: 'textarea' },
    { name: 'is_active', label: 'Active', type: 'checkbox', default: true },
  ]
  const desigFields = [
    { name: 'title', label: 'Title', required: true },
    { name: 'department_id', label: 'Department', type: 'select', numeric: true, options: deptOpts, placeholder: 'Any department', span: 1 },
    { name: 'level', label: 'Level', type: 'number', min: 1, max: 20, default: 1, span: 1, hint: '1 = entry level' },
    { name: 'is_active', label: 'Active', type: 'checkbox', default: true },
  ]
  const isDept = form?.kind === 'department'
  const save = async (v) => {
    const base = isDept ? '/departments' : '/designations'
    if (form.item) await api.put(`${base}/${form.item.id}`, v)
    else await api.post(base, v)
    toast.success(form.item ? 'Saved' : 'Created')
    invalidateOptions(isDept ? 'departments' : 'designations')
    isDept ? depts.reload() : desigs.reload()
  }

  return (
    <>
      <PageHeader title="Organization" description="Departments and designations used across employees, recruitment and reports."
        actions={<Button icon={Plus} onClick={() => setForm({ kind: tab === 'departments' ? 'department' : 'designation' })}>{tab === 'departments' ? 'New department' : 'New designation'}</Button>} />
      <Tabs className="mb-4" value={tab} onChange={setTab} tabs={[
        { value: 'departments', label: 'Departments', count: depts.data?.length },
        { value: 'designations', label: 'Designations', count: desigs.data?.length },
      ]} />
      <div className="card overflow-hidden">
        {tab === 'departments' ? (
          <DataTable loading={depts.loading} error={depts.error} onRetry={depts.reload} rows={depts.data}
            empty={<EmptyState icon={Building2} title="No departments yet" description="Create departments to organise your teams." action={<Button icon={Plus} onClick={() => setForm({ kind: 'department' })}>New department</Button>} />}
            columns={[
              { key: 'name', header: 'Department', mobile: 'title', render: (d) => <span className="font-medium text-ink">{d.name}</span> },
              { key: 'code', header: 'Code', render: (d) => <Badge>{d.code}</Badge> },
              { key: 'head', header: 'Head', render: (d) => d.head?.full_name || '—' },
              { key: 'count', header: 'Employees', align: 'right', render: (d) => d.employee_count },
              { key: 'status', header: 'Status', render: (d) => d.is_active ? <Badge tone="success" dot>Active</Badge> : <Badge dot>Inactive</Badge> },
              { key: 'a', header: '', align: 'right', render: (d) => <div className="flex justify-end gap-1"><IconButton icon={Pencil} label="Edit" size="sm" onClick={() => setForm({ kind: 'department', item: d })} /><IconButton icon={Trash2} label="Delete" size="sm" variant="danger" onClick={() => setDel({ kind: 'departments', item: d })} /></div> },
            ]} />
        ) : (
          <DataTable loading={desigs.loading} error={desigs.error} onRetry={desigs.reload} rows={desigs.data}
            empty={<EmptyState title="No designations yet" action={<Button icon={Plus} onClick={() => setForm({ kind: 'designation' })}>New designation</Button>} />}
            columns={[
              { key: 'title', header: 'Designation', mobile: 'title', render: (d) => <span className="font-medium text-ink">{d.title}</span> },
              { key: 'department', header: 'Department', render: (d) => d.department || 'Any' },
              { key: 'level', header: 'Level', align: 'right', render: (d) => d.level },
              { key: 'status', header: 'Status', render: (d) => d.is_active ? <Badge tone="success" dot>Active</Badge> : <Badge dot>Inactive</Badge> },
              { key: 'a', header: '', align: 'right', render: (d) => <div className="flex justify-end gap-1"><IconButton icon={Pencil} label="Edit" size="sm" onClick={() => setForm({ kind: 'designation', item: d })} /><IconButton icon={Trash2} label="Delete" size="sm" variant="danger" onClick={() => setDel({ kind: 'designations', item: d })} /></div> },
            ]} />
        )}
      </div>
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={`${form?.item ? 'Edit' : 'New'} ${form?.kind || ''}`}
        fields={isDept ? deptFields : desigFields} initial={form?.item} onSubmit={save} />
      <ConfirmDialog open={Boolean(del)} onClose={() => setDel(null)} title="Delete" loading={busy} confirmLabel="Delete"
        description={`Delete “${del?.item.name || del?.item.title}”? Records that use it must be reassigned first.`}
        onConfirm={async () => { await run(() => api.delete(`/${del.kind}/${del.item.id}`), { success: 'Deleted' }); setDel(null); invalidateOptions(); del.kind === 'departments' ? depts.reload() : desigs.reload() }} />
    </>
  )
}
