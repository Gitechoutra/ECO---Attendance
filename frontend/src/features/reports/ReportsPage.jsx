import { useState } from 'react'
import clsx from 'clsx'
import { BarChart3, FileSpreadsheet, FileText } from 'lucide-react'
import { downloadFile } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import { useOptions } from '../../hooks/useOptions'
import { useToast } from '../../context/ToastContext'
import { BarList, Button, Card, CardHeader, EmptyState, ErrorState, Field, Input, PageHeader, Select, Skeleton } from '../../components/ui'
import { isoDate } from '../../lib/format'

const DESC = {
  attendance: 'Presence, lateness, absences and hours per employee.',
  employees: 'Register of employees with department, role and status.',
  leave: 'Leave requests and approved days by type.',
  recruitment: 'Candidates added and their pipeline stage.',
  projects: 'Status, progress and delays across projects.',
  tasks: 'Tasks due or created in the period, with overdue flags.',
  clients: 'Client portfolio, projects and interaction volume.',
  payroll: 'Payslip register for finalized payroll months.',
  expenses: 'Claims by employee, category and status.',
}
const STATUS_FILTER = {
  employees: ['active', 'on_notice', 'inactive'], leave: ['pending', 'approved', 'rejected', 'cancelled'],
  projects: ['planning', 'active', 'on_hold', 'completed', 'cancelled'], tasks: ['todo', 'in_progress', 'review', 'blocked', 'done'],
  clients: ['lead', 'active', 'inactive'], expenses: ['submitted', 'approved', 'rejected', 'reimbursed'],
  recruitment: ['applied', 'screening', 'interview', 'offered', 'hired', 'rejected'],
}
const PRESETS = [
  { label: 'This month', range: () => { const n = new Date(); return [new Date(n.getFullYear(), n.getMonth(), 1), n] } },
  { label: 'Last month', range: () => { const n = new Date(); return [new Date(n.getFullYear(), n.getMonth() - 1, 1), new Date(n.getFullYear(), n.getMonth(), 0)] } },
  { label: 'This quarter', range: () => { const n = new Date(); return [new Date(n.getFullYear(), Math.floor(n.getMonth() / 3) * 3, 1), n] } },
  { label: 'Year to date', range: () => { const n = new Date(); return [new Date(n.getFullYear(), 0, 1), n] } },
]

export default function ReportsPage() {
  const toast = useToast()
  const list = useApi('/reports')
  const depts = useOptions('departments')
  const [kind, setKind] = useState(null)
  const [from, setFrom] = useState(isoDate(new Date(new Date().getFullYear(), new Date().getMonth(), 1)))
  const [to, setTo] = useState(isoDate())
  const [dept, setDept] = useState('')
  const [status, setStatus] = useState('')
  const active = kind || list.data?.[0]?.key
  const params = { date_from: from, date_to: to, department_id: dept || undefined, status: status || undefined }
  const report = useApi(active ? `/reports/${active}` : null, params)
  const exportAs = async (format) => {
    try { await downloadFile(`/reports/${active}`, { ...params, format }, `${active}.${format}`) } catch (e) { toast.apiError(e, 'Export failed') }
  }
  if (list.error) return <ErrorState message={list.error} onRetry={list.reload} />
  return (
    <>
      <PageHeader title="Reports" description="Filter by date, preview and export to PDF or Excel." />
      <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
        <nav className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
          {list.loading ? <Skeleton className="h-64 w-full" /> : list.data.map((r) => (
            <button key={r.key} onClick={() => { setKind(r.key); setStatus('') }}
              className={clsx('shrink-0 rounded-xl border px-4 py-3 text-left transition-colors lg:w-full', active === r.key ? 'border-brand bg-brand-soft/50' : 'border-line bg-surface hover:border-line-strong')}>
              <p className="text-sm font-semibold">{r.title}</p>
              <p className="mt-0.5 hidden text-xs text-muted lg:block">{DESC[r.key]}</p>
            </button>
          ))}
        </nav>
        <div className="min-w-0 space-y-4">
          <Card>
            <div className="flex flex-wrap items-end gap-3">
              <Field label="From"><Input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className="w-40" /></Field>
              <Field label="To"><Input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} className="w-40" /></Field>
              {['attendance', 'employees', 'leave', 'expenses'].includes(active) && <Field label="Department"><Select value={dept} onChange={(e) => setDept(e.target.value)} placeholder="All" options={depts} className="w-44" /></Field>}
              {STATUS_FILTER[active] && <Field label="Status"><Select value={status} onChange={(e) => setStatus(e.target.value)} placeholder="All" className="w-40" options={STATUS_FILTER[active].map((s) => ({ value: s, label: s.replace(/_/g, ' ') }))} /></Field>}
              <div className="flex flex-wrap gap-1.5">
                {PRESETS.map((p) => <Button key={p.label} size="sm" variant="ghost" onClick={() => { const [a, b] = p.range(); setFrom(isoDate(a)); setTo(isoDate(b)) }}>{p.label}</Button>)}
              </div>
              <div className="ml-auto flex gap-2">
                <Button variant="secondary" icon={FileSpreadsheet} onClick={() => exportAs('xlsx')} disabled={!report.data}>Excel</Button>
                <Button variant="secondary" icon={FileText} onClick={() => exportAs('pdf')} disabled={!report.data}>PDF</Button>
              </div>
            </div>
          </Card>
          {report.error ? <ErrorState message={report.error} onRetry={report.reload} /> : report.loading && !report.data ? <Skeleton className="h-80" /> : report.data && (
            <>
              <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                {report.data.summary.map(([k, v]) => <div key={k} className="card p-4"><p className="text-[13px] text-muted">{k}</p><p className="num mt-1 text-xl font-semibold">{v}</p></div>)}
              </div>
              {report.data.chart.length > 0 && (
                <Card><CardHeader title={report.data.title} subtitle="Top entries" /><BarList items={[...report.data.chart].sort((a, b) => b.value - a.value).slice(0, 12)} /></Card>
              )}
              <Card padded={false}>
                <div className="flex items-center justify-between p-5 pb-3"><h3 className="text-[15px] font-semibold">{report.data.rows.length} rows</h3>{report.data.rows.length > 200 && <span className="text-xs text-muted">Showing first 200 — export for the full report</span>}</div>
                {report.data.rows.length === 0 ? <EmptyState compact icon={BarChart3} title="No records for these filters" /> : (
                  <div className="scrollbar-thin overflow-x-auto">
                    <table className="w-full text-left text-[13px]">
                      <thead><tr className="border-b border-line">{report.data.columns.map((c) => <th key={c} className="whitespace-nowrap px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-faint">{c}</th>)}</tr></thead>
                      <tbody>{report.data.rows.slice(0, 200).map((r, i) => <tr key={i} className="border-b border-line/60 last:border-0">{r.map((c, j) => <td key={j} className="num whitespace-nowrap px-4 py-2.5 text-ink-2">{String(c)}</td>)}</tr>)}</tbody>
                    </table>
                  </div>
                )}
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  )
}
