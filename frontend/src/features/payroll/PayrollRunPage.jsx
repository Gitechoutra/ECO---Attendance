import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, Download, Lock, RefreshCw, Trash2 } from 'lucide-react'
import { api, downloadFile } from '../../api/client'
import { useApi, useAction } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import {
  Button, ConfirmDialog, DataTable, EmptyState, ErrorState, FormModal, IconButton, PageHeader, PersonCell, Skeleton,
  StatCard, StatusBadge,
} from '../../components/ui'
import { fmtMoney, isoDate } from '../../lib/format'
import { PayslipDrawer } from './PayrollPage'

export default function PayrollRunPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const { can } = useAuth()
  const toast = useToast()
  const { data: r, loading, error, reload } = useApi(`/payroll/runs/${id}`)
  const [slip, setSlip] = useState(null)
  const [fin, setFin] = useState(false)
  const [pay, setPay] = useState(false)
  const [del, setDel] = useState(false)
  const [run, busy] = useAction(toast)
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (loading || !r) return <Skeleton className="h-72" />
  const manage = can('payroll.manage')
  return (
    <>
      <PageHeader title={`Payroll · ${r.period}`} breadcrumbs={[{ label: 'Payroll', to: '/payroll' }, { label: r.period }]}
        description={`${r.employee_count} payslips · ${r.working_days} working days`}
        actions={<>
          <Button variant="secondary" icon={Download} onClick={() => downloadFile('/reports/payroll', { format: 'xlsx', date_from: `${r.year}-${String(r.month).padStart(2, '0')}-01`, date_to: `${r.year}-${String(r.month).padStart(2, '0')}-28` })}>Register (Excel)</Button>
          {manage && r.status === 'draft' && <>
            <Button variant="secondary" icon={RefreshCw} loading={busy} onClick={async () => { const x = await run(() => api.post('/payroll/runs', { year: r.year, month: r.month }), { success: 'Recalculated' }); if (x.data.skipped.length) toast.warning(`${x.data.skipped.length} employee(s) without salary structure`); reload() }}>Recalculate</Button>
            <IconButton icon={Trash2} label="Delete draft" variant="danger" onClick={() => setDel(true)} />
            <Button icon={Lock} onClick={() => setFin(true)}>Finalize</Button>
          </>}
          {manage && r.status === 'finalized' && <Button icon={CheckCircle2} onClick={() => setPay(true)}>Record payment</Button>}
        </>} />
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Status" value={<StatusBadge status={r.status} />} tone="neutral" />
        <StatCard label="Total gross" value={fmtMoney(r.total_gross)} tone="neutral" />
        <StatCard label="Deductions" value={fmtMoney(r.total_deductions)} tone="neutral" />
        <StatCard label="Net payable" value={fmtMoney(r.total_net)} hint={`${r.paid_count} of ${r.employee_count} paid`} />
      </div>
      <div className="card overflow-hidden">
        <DataTable rows={r.payslips} onRowClick={setSlip} empty={<EmptyState title="No payslips" description="Add salary structures, then recalculate." />}
          columns={[
            { key: 'emp', header: 'Employee', mobile: 'title', render: (p) => <PersonCell name={p.employee.full_name} subtitle={p.employee.employee_code} fileId={p.employee.photo_file_id} /> },
            { key: 'days', header: 'Paid days', align: 'right', render: (p) => `${p.paid_days}/${p.working_days}` },
            { key: 'lop', header: 'LOP', align: 'right', render: (p) => p.lop_days ? <span className="text-warning">{p.lop_days}</span> : 0 },
            { key: 'gross', header: 'Gross', align: 'right', render: (p) => fmtMoney(p.gross_earnings) },
            { key: 'bonus', header: 'Bonus', align: 'right', render: (p) => p.bonus ? fmtMoney(p.bonus) : '—' },
            { key: 'ded', header: 'Deductions', align: 'right', render: (p) => fmtMoney(p.total_deductions) },
            { key: 'net', header: 'Net', align: 'right', render: (p) => <span className="font-semibold text-ink">{fmtMoney(p.net_pay)}</span> },
            { key: 'pay', header: 'Payment', render: (p) => <StatusBadge status={p.payment_status} /> },
          ]} />
      </div>
      <PayslipDrawer slip={slip && { ...slip, period: r.period }} onClose={() => setSlip(null)} />
      <ConfirmDialog open={fin} onClose={() => setFin(false)} tone="primary" title="Finalize payroll" confirmLabel="Finalize" loading={busy}
        description={`Lock ${r.period} payroll and publish ${r.employee_count} payslips to employees? Finalized payroll cannot be recalculated.`}
        onConfirm={async () => { await run(() => api.post(`/payroll/runs/${r.id}/finalize`), { success: 'Payroll finalized', }); setFin(false); reload() }} />
      <ConfirmDialog open={del} onClose={() => setDel(false)} title="Delete draft" description="Delete this draft payroll run?" confirmLabel="Delete" loading={busy}
        onConfirm={async () => { await run(() => api.delete(`/payroll/runs/${r.id}`), { success: 'Draft deleted' }); nav('/payroll') }} />
      <FormModal open={pay} onClose={() => setPay(false)} title="Record salary payment" submitLabel="Mark as paid" description="Marks all unpaid payslips in this run as paid."
        fields={[{ name: 'paid_on', label: 'Paid on', type: 'date', required: true, default: isoDate(), span: 1 },
          { name: 'mode', label: 'Mode', type: 'select', default: 'bank_transfer', span: 1, options: [{ value: 'bank_transfer', label: 'Bank transfer' }, { value: 'upi', label: 'UPI' }, { value: 'cheque', label: 'Cheque' }, { value: 'cash', label: 'Cash' }] },
          { name: 'reference', label: 'Batch / transaction reference' }]}
        onSubmit={async (v) => { await api.post(`/payroll/runs/${r.id}/pay`, v); toast.success('Payment recorded'); reload() }} />
    </>
  )
}
