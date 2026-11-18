import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Download, Pencil, Plus, Trash2, Wallet } from 'lucide-react'
import { api, downloadFile } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useOptions } from '../../hooks/useOptions'
import {
  Badge, Button, Card, CardHeader, ColumnChart, ConfirmDialog, DataTable, Drawer, EmptyState, Field, FormModal, IconButton,
  Input, PageHeader, PersonCell, Select, StatusBadge, Tabs, Toolbar,
} from '../../components/ui'
import { fmtDate, fmtCompactMoney, fmtMoney, isoDate, MONTHS, titleCase } from '../../lib/format'

const CALC = [{ value: 'fixed', label: 'Fixed amount' }, { value: 'percent_basic', label: '% of basic' }, { value: 'percent_gross', label: '% of gross' }]

function MyPayslips() {
  const { data, loading, error, reload } = useApi('/payroll/my-payslips')
  const [open, setOpen] = useState(null)
  return (
    <>
      <div className="card overflow-hidden">
        <DataTable loading={loading} error={error} onRetry={reload} rows={data} onRowClick={setOpen}
          empty={<EmptyState icon={Wallet} title="No payslips yet" description="Payslips appear here once payroll is finalized." />}
          columns={[
            { key: 'period', header: 'Period', mobile: 'title', render: (p) => <span className="font-medium text-ink">{p.period}</span> },
            { key: 'days', header: 'Paid days', align: 'right', render: (p) => `${p.paid_days} / ${p.working_days}` },
            { key: 'gross', header: 'Gross', align: 'right', render: (p) => fmtMoney(p.gross_earnings + p.bonus) },
            { key: 'ded', header: 'Deductions', align: 'right', render: (p) => fmtMoney(p.total_deductions) },
            { key: 'net', header: 'Net pay', align: 'right', render: (p) => <span className="font-semibold text-ink">{fmtMoney(p.net_pay)}</span> },
            { key: 'st', header: 'Payment', render: (p) => <StatusBadge status={p.payment_status} /> },
            { key: 'a', header: '', align: 'right', render: (p) => <IconButton icon={Download} size="sm" label="Download PDF" onClick={(e) => { e.stopPropagation(); downloadFile(`/payroll/payslips/${p.id}/pdf`) }} /> },
          ]} />
      </div>
      <PayslipDrawer slip={open} onClose={() => setOpen(null)} />
    </>
  )
}

export function PayslipDrawer({ slip, onClose }) {
  if (!slip) return null
  const b = slip.breakdown
  return (
    <Drawer open={Boolean(slip)} onClose={onClose} title={`Payslip${slip.period ? ` · ${slip.period}` : ''}`} subtitle={slip.employee?.full_name}
      footer={<Button icon={Download} onClick={() => downloadFile(`/payroll/payslips/${slip.id}/pdf`)}>Download PDF</Button>}>
      <div className="rounded-xl bg-night p-5 text-white">
        <p className="text-xs text-[#A9BAC4]">Net pay</p><p className="num mt-1 text-3xl font-semibold">{fmtMoney(slip.net_pay)}</p>
        <p className="mt-2 text-xs text-[#8DA1AC]">{slip.paid_days} paid of {slip.working_days} working days{slip.lop_days ? ` · ${slip.lop_days} LOP` : ''}</p>
      </div>
      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        {[['Earnings', b.earnings], ['Deductions', b.deductions]].map(([t, rows]) => (
          <div key={t}><p className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">{t}</p>
            <ul className="space-y-1.5 text-sm">{rows.length ? rows.map((r, i) => <li key={i} className="flex justify-between gap-2"><span className="text-ink-2">{r.name}</span><span className="num">{fmtMoney(r.amount)}</span></li>) : <li className="text-muted">None</li>}</ul>
          </div>
        ))}
      </div>
      {b.attendance && <p className="mt-6 text-xs text-muted">Attendance basis: {b.attendance.absent} absent · {b.attendance.unpaid_leave} unpaid leave · {b.attendance.half_days} half days.</p>}
    </Drawer>
  )
}

function Runs() {
  const { can } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const runs = useApi('/payroll/runs')
  const year = new Date().getFullYear()
  const summary = useApi('/payroll/summary', { year })
  const now = new Date()
  const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  const [ym, setYm] = useState(`${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, '0')}`)
  const [run, busy] = useAction(toast)
  return (
    <div className="space-y-4">
      {can('payroll.manage') && (
        <Card>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Field label="Process payroll for" className="sm:w-56"><Input type="month" value={ym} max={isoDate().slice(0, 7)} onChange={(e) => setYm(e.target.value)} /></Field>
            <Button icon={Wallet} loading={busy} onClick={async () => {
              const [y, m] = ym.split('-').map(Number)
              const r = await run(() => api.post('/payroll/runs', { year: y, month: m }))
              toast.success('Payroll calculated', r.data.skipped.length ? `${r.data.skipped.length} employee(s) skipped — no salary structure` : 'Review and finalize when ready.')
              nav(`/payroll/runs/${r.data.id}`)
            }}>Calculate payroll</Button>
            <p className="text-xs text-muted sm:ml-2 sm:pb-2.5">Uses salary structures, attendance (LOP) and adjustments. Draft runs can be recalculated.</p>
          </div>
        </Card>
      )}
      {summary.data?.length > 0 && (
        <Card><CardHeader title={`Net payroll ${year}`} subtitle="Finalized and draft runs" />
          <ColumnChart data={summary.data} xKey="label" series={[{ key: 'net', name: 'Net pay' }]} format={(v) => fmtMoney(v)} axisFormat={(v) => fmtCompactMoney(v)} height={220} /></Card>
      )}
      <div className="card overflow-hidden">
        <DataTable loading={runs.loading} error={runs.error} onRetry={runs.reload} rows={runs.data} onRowClick={(r) => nav(`/payroll/runs/${r.id}`)}
          empty={<EmptyState icon={Wallet} title="No payroll runs yet" />}
          columns={[
            { key: 'period', header: 'Period', mobile: 'title', render: (r) => <span className="font-medium text-ink">{r.period}</span> },
            { key: 'emps', header: 'Employees', align: 'right', render: (r) => r.employee_count },
            { key: 'gross', header: 'Gross', align: 'right', render: (r) => fmtMoney(r.total_gross) },
            { key: 'net', header: 'Net', align: 'right', render: (r) => <span className="font-semibold text-ink">{fmtMoney(r.total_net)}</span> },
            { key: 'paid', header: 'Paid', align: 'right', render: (r) => `${r.paid_count}/${r.employee_count}` },
            { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
          ]} />
      </div>
    </div>
  )
}

function StructureForm({ open, onClose, employee, components, onSaved }) {
  const toast = useToast()
  const [eff, setEff] = useState(isoDate())
  const [basic, setBasic] = useState('')
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!open || !employee) return
    const cur = employee.structure
    setEff(isoDate())
    setBasic(cur?.monthly_basic ?? '')
    setItems(cur ? cur.items.map((i) => ({ component_id: i.component_id, value: i.value }))
      : components.filter((c) => c.is_active && c.default_value > 0).map((c) => ({ component_id: c.id, value: c.default_value })))
  }, [open, employee]) // eslint-disable-line react-hooks/exhaustive-deps
  const save = async () => {
    setBusy(true)
    try {
      await api.post('/payroll/structures', { employee_id: employee.employee.id, effective_from: eff, monthly_basic: Number(basic), items: items.filter((i) => i.component_id).map((i) => ({ component_id: Number(i.component_id), value: Number(i.value) || 0 })) })
      toast.success('Salary structure saved'); onSaved(); close()
    } catch (e) { toast.apiError(e) } finally { setBusy(false) }
  }
  const close = () => onClose()
  return (
    <Drawer open={open} onClose={close} title={`Salary structure — ${employee?.employee.full_name || ''}`} subtitle="A new structure applies from its effective date; history is kept."
      footer={<><Button variant="secondary" onClick={close}>Cancel</Button><Button loading={busy} disabled={!basic} onClick={save}>Save structure</Button></>}>
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Effective from" required><Input type="date" value={eff} onChange={(e) => setEff(e.target.value)} /></Field>
          <Field label="Monthly basic (INR)" required><Input type="number" min="0" value={basic} onChange={(e) => setBasic(e.target.value)} /></Field>
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between"><p className="label mb-0">Components</p><Button size="xs" variant="secondary" icon={Plus} onClick={() => setItems([...items, { component_id: '', value: '' }])}>Add</Button></div>
          <div className="space-y-2">
            {items.map((it, i) => {
              const c = components.find((x) => String(x.id) === String(it.component_id))
              return (
                <div key={i} className="flex items-center gap-2">
                  <Select value={it.component_id} placeholder="Component" onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, component_id: e.target.value } : x)))}
                    options={components.filter((x) => x.is_active).map((x) => ({ value: x.id, label: `${x.name} (${x.kind})` }))} />
                  <Input type="number" min="0" className="w-28" value={it.value} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
                  <span className="w-10 text-xs text-muted">{c ? (c.calc_type === 'fixed' ? '₹' : '%') : ''}</span>
                  <IconButton icon={Trash2} size="sm" variant="danger" label="Remove" onClick={() => setItems(items.filter((_, j) => j !== i))} />
                </div>
              )
            })}
            {!items.length && <p className="text-[13px] text-muted">Basic only. Add allowances or deductions configured under Components.</p>}
          </div>
        </div>
        <p className="rounded-lg bg-surface-2 p-3 text-xs text-muted">Statutory deductions (PF, ESI, professional tax, TDS) are not assumed. Configure them as components using rules verified for your jurisdiction.</p>
      </div>
    </Drawer>
  )
}

function Structures() {
  const { can } = useAuth()
  const { data, loading, error, reload } = useApi('/payroll/structures')
  const comps = useApi('/payroll/components')
  const [edit, setEdit] = useState(null)
  return (
    <div className="card overflow-hidden">
      <DataTable loading={loading} error={error} onRetry={reload} rows={data?.map((r) => ({ ...r, id: r.employee.id }))} empty={<EmptyState title="No employees" />}
        columns={[
          { key: 'emp', header: 'Employee', mobile: 'title', render: (r) => <PersonCell name={r.employee.full_name} subtitle={r.employee.employee_code} fileId={r.employee.photo_file_id} /> },
          { key: 'eff', header: 'Effective', render: (r) => r.structure ? fmtDate(r.structure.effective_from) : <Badge tone="warning">Not set</Badge> },
          { key: 'basic', header: 'Monthly basic', align: 'right', render: (r) => r.structure ? fmtMoney(r.structure.monthly_basic) : '—' },
          { key: 'gross', header: 'Est. monthly gross', align: 'right', render: (r) => r.monthly_gross_estimate ? fmtMoney(r.monthly_gross_estimate) : '—' },
          { key: 'items', header: 'Components', render: (r) => r.structure?.items.length ?? 0 },
          { key: 'a', header: '', align: 'right', render: (r) => can('payroll.manage') && <Button size="xs" variant="secondary" onClick={() => setEdit(r)}>{r.structure ? 'Revise' : 'Set up'}</Button> },
        ]} />
      <StructureForm open={Boolean(edit)} onClose={() => setEdit(null)} employee={edit} components={comps.data || []} onSaved={reload} />
    </div>
  )
}

function Components() {
  const { can } = useAuth()
  const toast = useToast()
  const { data, loading, error, reload } = useApi('/payroll/components')
  const [form, setForm] = useState(null)
  return (
    <div className="card overflow-hidden">
      {can('payroll.manage') && <Toolbar><p className="text-[13px] text-muted">Configurable salary rules used in structures.</p><Button size="sm" icon={Plus} className="sm:ml-auto" onClick={() => setForm({})}>New component</Button></Toolbar>}
      <DataTable loading={loading} error={error} onRetry={reload} rows={data}
        columns={[
          { key: 'name', header: 'Component', mobile: 'title', render: (c) => <span className="font-medium text-ink">{c.name} <Badge>{c.code}</Badge></span> },
          { key: 'kind', header: 'Type', render: (c) => <Badge tone={c.kind === 'earning' ? 'brand' : 'warning'}>{titleCase(c.kind)}</Badge> },
          { key: 'calc', header: 'Calculation', render: (c) => CALC.find((x) => x.value === c.calc_type)?.label },
          { key: 'def', header: 'Default', align: 'right', render: (c) => c.calc_type === 'fixed' ? fmtMoney(c.default_value) : `${c.default_value}%` },
          { key: 'pr', header: 'Prorated', render: (c) => c.prorate_with_attendance ? 'Yes' : 'No' },
          { key: 'st', header: 'Status', render: (c) => c.is_active ? <Badge tone="success" dot>Active</Badge> : <Badge dot>Inactive</Badge> },
          { key: 'a', header: '', align: 'right', render: (c) => can('payroll.manage') && <IconButton icon={Pencil} size="sm" label="Edit" onClick={() => setForm(c)} /> },
        ]} />
      <FormModal open={Boolean(form)} onClose={() => setForm(null)} title={form?.id ? 'Edit component' : 'New component'} initial={form}
        fields={[{ name: 'name', label: 'Name', required: true, span: 1 }, { name: 'code', label: 'Code', required: true, span: 1, placeholder: 'HRA' },
          { name: 'kind', label: 'Type', type: 'select', required: true, default: 'earning', span: 1, options: [{ value: 'earning', label: 'Earning' }, { value: 'deduction', label: 'Deduction' }] },
          { name: 'calc_type', label: 'Calculation', type: 'select', required: true, default: 'fixed', span: 1, options: CALC },
          { name: 'default_value', label: 'Default value', type: 'number', min: 0, default: 0, hint: 'Amount in INR, or a percentage' },
          { name: 'prorate_with_attendance', label: 'Prorate by paid days', type: 'checkbox', default: true },
          { name: 'is_active', label: 'Active', type: 'checkbox', default: true }, { name: 'description', label: 'Description' }]}
        onSubmit={async (v) => { form.id ? await api.put(`/payroll/components/${form.id}`, v) : await api.post('/payroll/components', v); toast.success('Component saved'); reload() }} />
    </div>
  )
}

function Adjustments() {
  const { can } = useAuth()
  const toast = useToast()
  const emps = useOptions('employees')
  const now = new Date()
  const [ym, setYm] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  const [y, m] = ym.split('-').map(Number)
  const { data, loading, error, reload } = useApi('/payroll/adjustments', { year: y, month: m })
  const [form, setForm] = useState(false)
  const [del, setDel] = useState(null)
  const [run, busy] = useAction(toast)
  return (
    <div className="card overflow-hidden">
      <Toolbar>
        <Input type="month" value={ym} onChange={(e) => setYm(e.target.value)} className="sm:w-44" />
        {can('payroll.manage') && <Button size="sm" icon={Plus} className="sm:ml-auto" onClick={() => setForm(true)}>Add bonus / deduction</Button>}
      </Toolbar>
      <DataTable loading={loading} error={error} onRetry={reload} rows={data} empty={<EmptyState compact title={`No adjustments for ${MONTHS[m - 1]} ${y}`} />}
        columns={[
          { key: 'emp', header: 'Employee', mobile: 'title', render: (a) => a.employee.full_name },
          { key: 'kind', header: 'Type', render: (a) => <Badge tone={a.kind === 'bonus' ? 'success' : 'warning'}>{titleCase(a.kind)}</Badge> },
          { key: 'label', header: 'Description', render: (a) => a.label },
          { key: 'amt', header: 'Amount', align: 'right', render: (a) => fmtMoney(a.amount) },
          { key: 'x', header: '', align: 'right', render: (a) => can('payroll.manage') && <IconButton icon={Trash2} size="sm" variant="danger" label="Delete" onClick={() => setDel(a)} /> },
        ]} />
      <FormModal open={form} onClose={() => setForm(false)} title="Add adjustment"
        fields={[{ name: 'employee_id', label: 'Employee', type: 'select', numeric: true, required: true, options: emps },
          { name: 'kind', label: 'Type', type: 'select', default: 'bonus', span: 1, options: [{ value: 'bonus', label: 'Bonus / incentive' }, { value: 'deduction', label: 'Deduction' }] },
          { name: 'amount', label: 'Amount (INR)', type: 'number', min: 1, required: true, span: 1 }, { name: 'label', label: 'Description', required: true, placeholder: 'e.g. Performance bonus' }]}
        onSubmit={async (v) => { await api.post('/payroll/adjustments', { ...v, year: y, month: m }); toast.success('Adjustment added'); reload() }} />
      <ConfirmDialog open={Boolean(del)} onClose={() => setDel(null)} title="Delete adjustment" description={`Remove “${del?.label}”?`} loading={busy} confirmLabel="Delete"
        onConfirm={async () => { await run(() => api.delete(`/payroll/adjustments/${del.id}`), { success: 'Deleted' }); setDel(null); reload() }} />
    </div>
  )
}

export default function PayrollPage() {
  const { can, employee } = useAuth()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || (can('payroll.view') ? 'runs' : 'mine')
  return (
    <>
      <PageHeader title="Payroll" description={can('payroll.view') ? 'Salary structures, monthly processing and payslips.' : 'Your payslips and salary history.'} />
      <Tabs className="mb-5" value={tab} onChange={(t) => setParams({ tab: t })} tabs={[
        { value: 'mine', label: 'My payslips', hidden: !employee },
        { value: 'runs', label: 'Payroll runs', hidden: !can('payroll.view') },
        { value: 'structures', label: 'Salary structures', hidden: !can('payroll.view') },
        { value: 'adjustments', label: 'Bonuses & deductions', hidden: !can('payroll.view') },
        { value: 'components', label: 'Components', hidden: !can('payroll.view') },
      ]} />
      {tab === 'mine' && employee && <MyPayslips />}
      {tab === 'runs' && can('payroll.view') && <Runs />}
      {tab === 'structures' && can('payroll.view') && <Structures />}
      {tab === 'adjustments' && can('payroll.view') && <Adjustments />}
      {tab === 'components' && can('payroll.view') && <Components />}
    </>
  )
}
