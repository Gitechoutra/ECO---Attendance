import { Link } from 'react-router-dom'
import {
  AlertTriangle, ArrowRight, Briefcase, CalendarCheck, CalendarDays, CheckSquare, Clock, FileSignature, FolderKanban,
  Megaphone, Receipt, UserCheck, UserPlus, Users, Video,
} from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import {
  Avatar, Badge, BarList, Card, CardHeader, ColumnChart, EmptyState, ErrorState, PageHeader, PersonCell, Progress,
  Skeleton, StatCard, StatusBadge,
} from '../../components/ui'
import { fmtDate, fmtDateTime, fmtMinutes, fmtMoney, fromNow, MONTHS } from '../../lib/format'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

const APPROVAL_LINKS = {
  leave: { label: 'Leave requests', to: '/leave?tab=approvals', icon: CalendarDays },
  attendance: { label: 'Attendance requests', to: '/attendance?tab=requests', icon: CalendarCheck },
  expenses: { label: 'Expense claims', to: '/expenses?tab=approvals', icon: Receipt },
  reimbursements: { label: 'Awaiting reimbursement', to: '/expenses?tab=approvals', icon: Receipt },
  offers: { label: 'Offer letters', to: '/offers?status=pending_approval', icon: FileSignature },
}

function TodayCard({ personal }) {
  const rec = personal.attendance_today
  const state = !personal.is_working_day && !rec ? 'off' : !rec?.check_in_at ? 'out' : rec.check_out_at ? 'done' : rec.on_break ? 'break' : 'in'
  const copy = {
    off: ['Non-working day', 'Enjoy your day off.'],
    out: ['Not checked in', 'Start your day with a verified check-in.'],
    in: ['Checked in', `Since ${rec?.check_in_local}${rec?.late_minutes ? ` · ${rec.late_minutes} min late` : ''}`],
    break: ['On a break', `Checked in at ${rec?.check_in_local}`],
    done: ['Day complete', `${rec?.check_in_local} – ${rec?.check_out_local} · ${fmtMinutes(rec?.worked_minutes)} worked`],
  }[state]
  return (
    <div className="card relative overflow-hidden bg-night p-5 text-white">
      <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full border border-night-line" />
      <div className="pointer-events-none absolute -right-6 -top-6 h-28 w-28 rounded-full border border-night-line" />
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">Today</p>
      <p className="mt-2 text-xl font-semibold">{copy[0]}</p>
      <p className="mt-1 text-sm text-[#A9BAC4]">{copy[1]}</p>
      <div className="mt-5 grid grid-cols-3 gap-3 border-t border-night-line pt-4 text-center">
        <div><p className="num text-lg font-semibold">{personal.month_attendance.present}</p><p className="text-2xs text-[#8DA1AC]">Days present</p></div>
        <div><p className="num text-lg font-semibold">{personal.month_attendance.late}</p><p className="text-2xs text-[#8DA1AC]">Late arrivals</p></div>
        <div><p className="num text-lg font-semibold">{personal.month_attendance.hours}</p><p className="text-2xs text-[#8DA1AC]">Hours (month)</p></div>
      </div>
      {(state === 'out' || state === 'in' || state === 'break') && (
        <Link to="/attendance" className="mt-4 flex h-10 items-center justify-center gap-2 rounded-lg bg-brand text-sm font-semibold text-[#03211D] transition-colors hover:bg-brand-strong">
          {state === 'out' ? 'Check in' : 'Check out'}<ArrowRight className="h-4 w-4" />
        </Link>
      )}
    </div>
  )
}

function Approvals({ approvals }) {
  const entries = Object.entries(approvals || {}).filter(([, n]) => n > 0)
  if (!entries.length) return null
  return (
    <div className="card flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-warning-soft text-warning"><Clock className="h-4 w-4" /></span>
        <p className="text-sm font-semibold">Waiting for your approval</p>
      </div>
      <div className="flex flex-wrap gap-2 sm:ml-auto">
        {entries.map(([k, n]) => {
          const a = APPROVAL_LINKS[k]
          return (
            <Link key={k} to={a.to} className="flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-1.5 text-[13px] font-medium text-ink-2 hover:border-line-strong hover:text-ink">
              <a.icon className="h-3.5 w-3.5 text-muted" />{a.label}<span className="num rounded-full bg-warning-soft px-1.5 text-xs font-semibold text-warning">{n}</span>
            </Link>
          )
        })}
      </div>
    </div>
  )
}

function CompanySection({ company }) {
  const t = company.today
  const ps = company.projects.by_status || {}
  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Active employees" value={company.headcount} icon={Users} hint={`${company.new_joiners} joined · ${company.exits} left this month`} />
        <StatCard label="Checked in today" value={t.is_working_day ? `${t.checked_in}` : '—'} icon={UserCheck} tone="success"
          hint={t.is_working_day ? `${t.late} late · ${t.not_checked_in} not yet in` : 'Non-working day'} />
        <StatCard label="On leave today" value={t.on_leave} icon={CalendarDays} tone="info" />
        <StatCard label="Active projects" value={ps.active || 0} icon={FolderKanban} tone="neutral" hint={`${company.projects.delayed.length} delayed · ${company.projects.total} total`} />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Attendance — last 14 working days" subtitle="Employees checked in per day, and how many arrived late" />
          {company.attendance_trend.length ? (
            <ColumnChart
              data={company.attendance_trend}
              xKey="date"
              series={[{ key: 'present', name: 'Checked in' }, { key: 'late', name: 'Late' }]}
              tickFormat={(d) => fmtDate(d, 'dd MMM')}
              labelFormat={(d) => fmtDate(d, 'EEE, dd MMM')}
            />
          ) : <EmptyState compact icon={CalendarCheck} title="No attendance recorded yet" description="The trend appears once employees start checking in." />}
        </Card>
        <Card>
          <CardHeader title="Headcount by department" />
          <BarList items={company.departments.map((d) => ({ label: d.name, value: d.count }))} emptyLabel="Add departments to see the breakdown" />
        </Card>
      </div>
    </>
  )
}

function ProjectRow({ p }) {
  return (
    <Link to={`/projects/${p.id}`} className="block rounded-lg px-2 py-2.5 hover:bg-surface-2">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{p.name}</p>
          <p className="truncate text-xs text-muted">{p.client?.name || 'Internal'} · due {fmtDate(p.end_date)}</p>
        </div>
        {p.is_delayed ? <Badge tone="danger" dot>Delayed</Badge> : <StatusBadge status={p.status} />}
      </div>
      <Progress value={p.progress} showLabel className="mt-2" tone={p.is_delayed ? 'danger' : 'brand'} />
    </Link>
  )
}

function TaskRow({ t }) {
  return (
    <Link to={`/tasks/${t.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-surface-2">
      <span className={`h-2 w-2 shrink-0 rounded-full ${t.is_overdue ? 'bg-danger' : t.priority === 'high' || t.priority === 'urgent' ? 'bg-warning' : 'bg-line-strong'}`} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{t.title}</p>
        <p className="truncate text-xs text-muted">{t.project?.name || 'Personal'}{t.assignee && ` · ${t.assignee.full_name}`}</p>
      </div>
      <span className={`whitespace-nowrap text-xs ${t.is_overdue ? 'font-semibold text-danger' : 'text-muted'}`}>{t.due_date ? fmtDate(t.due_date, 'dd MMM') : 'No due date'}</span>
    </Link>
  )
}

export default function DashboardPage() {
  const { employee, user, can } = useAuth()
  const { data, loading, error, reload } = useApi('/dashboard')
  const name = employee?.first_name || user?.email?.split('@')[0]

  if (error) return <ErrorState message={error} onRetry={reload} />
  if (loading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28" />)}</div>
        <Skeleton className="h-72" />
      </div>
    )
  }
  const { personal, company, manager } = data

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${greeting()}, ${name}`}
        description={`${fmtDate(data.date, 'EEEE, dd MMMM yyyy')} · ${user.role.name}`}
        actions={
          <>
            {can('employees.manage') && <Link to="/employees?new=1" className="inline-flex h-9 items-center gap-2 rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium hover:bg-surface-2"><UserPlus className="h-4 w-4" />Add employee</Link>}
            {can('projects.manage') && <Link to="/projects?new=1" className="inline-flex h-9 items-center gap-2 rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium hover:bg-surface-2"><FolderKanban className="h-4 w-4" />New project</Link>}
            {personal && <Link to="/leave?apply=1" className="inline-flex h-9 items-center gap-2 rounded-lg bg-brand px-3 text-[13px] font-semibold text-[#03211D] hover:bg-brand-strong"><CalendarDays className="h-4 w-4" />Apply leave</Link>}
          </>
        }
      />

      <Approvals approvals={data.approvals} />

      {company && <CompanySection company={company} />}

      <div className="grid gap-4 xl:grid-cols-3">
        {personal && <TodayCard personal={personal} />}

        {personal && (
          <Card className={company ? '' : 'xl:col-span-2'}>
            <CardHeader title="My tasks" icon={CheckSquare}
              subtitle={`${personal.task_counts.open} open · ${personal.task_counts.overdue} overdue · ${personal.task_counts.due_this_week} due this week`}
              action={<Link to="/tasks" className="text-xs font-medium text-brand-ink hover:underline">View all</Link>} />
            {personal.tasks.length ? <div className="-mx-2">{personal.tasks.map((t) => <TaskRow key={t.id} t={t} />)}</div>
              : <EmptyState compact icon={CheckSquare} title="No open tasks" description="Tasks assigned to you will appear here." />}
          </Card>
        )}

        {personal && (
          <Card>
            <CardHeader title="Leave balance" icon={CalendarDays} action={<Link to="/leave" className="text-xs font-medium text-brand-ink hover:underline">Details</Link>} />
            {personal.leave_balances.length ? (
              <ul className="space-y-3">
                {personal.leave_balances.map((b) => (
                  <li key={b.code}>
                    <div className="flex items-baseline justify-between text-[13px]"><span className="text-ink-2">{b.name}</span><span className="num font-semibold">{b.available} <span className="font-normal text-muted">/ {b.allocated}</span></span></div>
                    <Progress value={b.allocated ? (b.available / b.allocated) * 100 : 0} className="mt-1.5" />
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No leave allocated yet.</p>}
            {personal.pending_leave > 0 && <p className="mt-4 text-xs text-muted">{personal.pending_leave} request(s) awaiting approval</p>}
          </Card>
        )}
      </div>

      {manager && (
        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader title="Projects I manage" icon={FolderKanban} action={<Link to="/projects" className="text-xs font-medium text-brand-ink hover:underline">All projects</Link>} />
            <div className="-mx-2 grid gap-x-4 md:grid-cols-2">{manager.projects.map((p) => <ProjectRow key={p.id} p={p} />)}</div>
          </Card>
          <Card>
            <CardHeader title="Team workload" subtitle="Open tasks per person across your projects" />
            {manager.workload.length ? (
              <ul className="space-y-2.5">
                {manager.workload.map((w) => (
                  <li key={w.employee.id} className="flex items-center justify-between gap-3">
                    <PersonCell name={w.employee.full_name} subtitle={w.employee.designation} fileId={w.employee.photo_file_id} />
                    <span className="num text-sm font-semibold">{w.open_tasks}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No open tasks in your projects.</p>}
          </Card>
          {manager.overdue_tasks.length > 0 && (
            <Card className="xl:col-span-3">
              <CardHeader title="Overdue in my projects" icon={AlertTriangle} />
              <div className="-mx-2 grid md:grid-cols-2">{manager.overdue_tasks.map((t) => <TaskRow key={t.id} t={t} />)}</div>
            </Card>
          )}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        {company?.projects.delayed.length > 0 && (
          <Card>
            <CardHeader title="Delayed projects" icon={AlertTriangle} subtitle="Past their end date and not completed" />
            <div className="-mx-2">{company.projects.delayed.map((p) => <ProjectRow key={p.id} p={p} />)}</div>
          </Card>
        )}
        <Card>
          <CardHeader title="Announcements" icon={Megaphone} action={<Link to="/communication" className="text-xs font-medium text-brand-ink hover:underline">All</Link>} />
          {data.announcements.length ? (
            <ul className="space-y-3.5">
              {data.announcements.map((a) => (
                <li key={a.id}>
                  <div className="flex items-center gap-2">
                    {a.is_pinned && <Badge tone="brand">Pinned</Badge>}
                    {a.category === 'urgent' && <Badge tone="danger">Urgent</Badge>}
                    <span className="text-2xs text-faint">{fromNow(a.published_at)}</span>
                  </div>
                  <p className="mt-1 text-sm font-medium">{a.title}</p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-muted">{a.body}</p>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No announcements right now.</p>}
        </Card>
        <Card>
          <CardHeader title="Coming up" icon={CalendarDays} />
          <ul className="space-y-3">
            {personal?.meetings.map((m) => (
              <li key={`m${m.id}`} className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-info-soft text-info"><Video className="h-4 w-4" /></span>
                <div className="min-w-0"><p className="truncate text-sm font-medium">{m.title}</p><p className="text-xs text-muted">{fmtDateTime(m.start_at)}</p></div>
              </li>
            ))}
            {data.holidays.map((h) => (
              <li key={`h${h.date}`} className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 flex-col items-center justify-center rounded-lg bg-brand-soft text-brand-ink">
                  <span className="text-[9px] font-semibold uppercase leading-none">{fmtDate(h.date, 'MMM')}</span>
                  <span className="num text-sm font-bold leading-none">{fmtDate(h.date, 'd')}</span>
                </span>
                <div><p className="text-sm font-medium">{h.name}</p><p className="text-xs text-muted">Holiday · {fmtDate(h.date, 'EEEE')}</p></div>
              </li>
            ))}
            {!personal?.meetings.length && !data.holidays.length && <p className="text-sm text-muted">Nothing scheduled.</p>}
          </ul>
        </Card>
        {company && (
          <Card className={company.projects.delayed.length ? 'xl:col-span-3' : ''}>
            <CardHeader title="Recent activity" subtitle="Latest changes across the company" />
            {company.activity.length ? (
              <ul className="divide-y divide-line">
                {company.activity.map((a) => (
                  <li key={a.id} className="flex items-start gap-3 py-2.5">
                    <Avatar name={a.user} size="xs" className="mt-0.5" />
                    <p className="min-w-0 flex-1 text-[13px] text-ink-2"><span className="font-medium text-ink">{a.user}</span> · {a.summary}</p>
                    <span className="whitespace-nowrap text-2xs text-faint">{fromNow(a.created_at)}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No activity yet.</p>}
          </Card>
        )}
      </div>

      {company && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Active clients" value={company.clients.active} icon={Briefcase} tone="neutral" hint={`${company.clients.leads} leads`} />
          <StatCard label="Open positions" value={company.recruitment.open_jobs} icon={UserPlus} tone="neutral" hint={`${company.recruitment.active_candidates} candidates in pipeline`} />
          {company.last_payroll && (
            <StatCard label="Last payroll (net)" value={fmtMoney(company.last_payroll.total_net)} icon={Receipt} tone="neutral"
              hint={`${MONTHS[company.last_payroll.month - 1]} ${company.last_payroll.year} · ${company.last_payroll.status}`} />
          )}
        </div>
      )}
    </div>
  )
}
