import {
  BarChart3, Briefcase, Building2, CalendarCheck, CalendarDays, CheckSquare, FileSignature, FolderKanban,
  LayoutDashboard, Mail, Megaphone, Receipt, ScrollText, Settings, ShieldCheck, Sparkles, UserPlus, Users, Wallet,
} from 'lucide-react'

/**
 * Navigation. `perm` = required permission(s) (any of). `employee` = requires a linked employee profile.
 * The backend enforces every permission independently; this only hides links users can't use.
 */
export const NAV = [
  {
    section: 'Overview',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
      { to: '/assistant', label: 'AI Assistant', icon: Sparkles, perm: ['ai.use'] },
    ],
  },
  {
    section: 'People',
    items: [
      { to: '/employees', label: 'Employees', icon: Users, perm: ['employees.view_all'] },
      { to: '/attendance', label: 'Attendance', icon: CalendarCheck },
      { to: '/leave', label: 'Leave', icon: CalendarDays },
      { to: '/recruitment', label: 'Recruitment', icon: UserPlus, perm: ['recruitment.view'] },
      { to: '/offers', label: 'Offer Letters', icon: FileSignature, perm: ['offers.manage', 'offers.approve'] },
    ],
  },
  {
    section: 'Work',
    items: [
      { to: '/projects', label: 'Projects', icon: FolderKanban },
      { to: '/tasks', label: 'Tasks', icon: CheckSquare },
      { to: '/clients', label: 'Clients', icon: Briefcase, perm: ['clients.view', 'clients.manage'] },
      { to: '/email', label: 'Email', icon: Mail, perm: ['email.use'] },
    ],
  },
  {
    section: 'Finance',
    items: [
      { to: '/payroll', label: 'Payroll', icon: Wallet },
      { to: '/expenses', label: 'Expenses', icon: Receipt },
    ],
  },
  {
    section: 'Company',
    items: [
      { to: '/communication', label: 'Communication', icon: Megaphone },
      { to: '/reports', label: 'Reports', icon: BarChart3, perm: ['reports.view', 'reports.hr', 'reports.finance'] },
    ],
  },
  {
    section: 'Administration',
    items: [
      { to: '/admin/organization', label: 'Organization', icon: Building2, perm: ['departments.manage'] },
      { to: '/admin/users', label: 'Users & Roles', icon: ShieldCheck, perm: ['admin.users', 'admin.roles'] },
      { to: '/admin/audit', label: 'Audit Log', icon: ScrollText, perm: ['admin.audit'] },
      { to: '/admin/settings', label: 'Settings', icon: Settings, perm: ['admin.settings'] },
    ],
  },
]

export function visibleNav(canAny) {
  return NAV.map((s) => ({ ...s, items: s.items.filter((i) => !i.perm || canAny(...i.perm)) })).filter((s) => s.items.length)
}
