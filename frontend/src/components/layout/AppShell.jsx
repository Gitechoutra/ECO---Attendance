import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import {
  Bell, CalendarCheck, CheckSquare, ChevronsLeft, ChevronsRight, LayoutDashboard, LogOut, Menu as MenuIcon, Moon,
  MoreHorizontal, Search, Sun, User, WifiOff, X, CalendarDays,
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { api } from '../../api/client'
import { visibleNav } from './nav'
import { Avatar } from '../ui'
import { fromNow } from '../../lib/format'
import { GlobalSearch } from './GlobalSearch'
import { useTheme } from '../../hooks/useTheme'
import { useOnline } from '../../hooks/useOnline'

function SidebarContent({ collapsed, onNavigate }) {
  const { canAny } = useAuth()
  const sections = visibleNav(canAny)
  return (
    <nav className="nav-scroll flex-1 overflow-y-auto px-3 pb-6">
      {sections.map((s) => (
        <div key={s.section} className="mt-5 first:mt-2">
          {!collapsed && <p className="mb-1.5 px-3 text-2xs font-semibold uppercase tracking-[0.12em] text-[#5D7380]">{s.section}</p>}
          <ul className="space-y-0.5">
            {s.items.map((i) => (
              <li key={i.to}>
                <NavLink
                  to={i.to}
                  end={i.end}
                  onClick={onNavigate}
                  title={collapsed ? i.label : undefined}
                  className={({ isActive }) => clsx(
                    'group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors',
                    collapsed && 'justify-center px-0',
                    isActive ? 'bg-[#0F2A2C] text-white' : 'text-[#A9BAC4] hover:bg-night-3 hover:text-white',
                  )}
                >
                  {({ isActive }) => (
                    <>
                      {isActive && <span className="absolute inset-y-1.5 left-0 w-[3px] rounded-r-full bg-brand" />}
                      <i.icon className={clsx('h-[18px] w-[18px] shrink-0', isActive ? 'text-brand' : 'text-[#6F8792] group-hover:text-[#C8D5DC]')} />
                      {!collapsed && <span className="truncate">{i.label}</span>}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

function Brand({ collapsed }) {
  return (
    <Link to="/" className={clsx('flex h-16 shrink-0 items-center', collapsed ? 'justify-center' : 'px-5')} aria-label="ECHOUTRA ONE home">
      {collapsed
        ? <img src="/echoutra-mark.png" alt="ECHOUTRA" className="h-8 w-auto" />
        : (
          <div className="flex flex-col">
            <img src="/echoutra-logo.png" alt="ECHOUTRA IT SOLUTIONS" className="h-[38px] w-auto self-start" />
          </div>
        )}
    </Link>
  )
}

function NotificationsBell() {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState({ items: [], unread_count: 0 })
  const ref = useRef(null)
  const nav = useNavigate()
  const load = () => api.get('/notifications', { params: { page_size: 8 } }).then((r) => setData(r.data)).catch(() => {})
  useEffect(() => {
    load()
    const t = setInterval(load, 60000)
    return () => clearInterval(t)
  }, [])
  useEffect(() => {
    if (!open) return
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])
  const openItem = async (n) => {
    setOpen(false)
    if (!n.is_read) await api.post(`/notifications/${n.id}/read`).catch(() => {})
    load()
    if (n.link) nav(n.link)
  }
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => { setOpen((o) => !o); if (!open) load() }} className="relative flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink" aria-label="Notifications">
        <Bell className="h-[18px] w-[18px]" />
        {data.unread_count > 0 && <span className="num absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">{data.unread_count > 9 ? '9+' : data.unread_count}</span>}
      </button>
      {open && (
        <div className="fixed inset-x-3 top-16 z-50 animate-scale-in rounded-xl border border-line bg-surface shadow-pop sm:absolute sm:inset-x-auto sm:right-0 sm:top-11 sm:w-96">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <p className="text-sm font-semibold">Notifications</p>
            {data.unread_count > 0 && <button className="text-xs font-medium text-brand-ink hover:underline" onClick={() => api.post('/notifications/read-all').then(load)}>Mark all read</button>}
          </div>
          <div className="scrollbar-thin max-h-[60vh] overflow-y-auto">
            {data.items.length === 0 && <p className="px-4 py-10 text-center text-sm text-muted">You’re all caught up.</p>}
            {data.items.map((n) => (
              <button key={n.id} onClick={() => openItem(n)} className={clsx('flex w-full gap-3 border-b border-line/70 px-4 py-3 text-left last:border-0 hover:bg-surface-2', !n.is_read && 'bg-brand-soft/30')}>
                <span className={clsx('mt-1.5 h-2 w-2 shrink-0 rounded-full', n.is_read ? 'bg-transparent' : 'bg-brand')} />
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium text-ink">{n.title}</span>
                  {n.body && <span className="mt-0.5 line-clamp-2 block text-xs text-muted">{n.body}</span>}
                  <span className="mt-1 block text-2xs text-faint">{fromNow(n.created_at)}</span>
                </span>
              </button>
            ))}
          </div>
          <Link to="/notifications" onClick={() => setOpen(false)} className="block border-t border-line px-4 py-2.5 text-center text-xs font-medium text-brand-ink hover:bg-surface-2">View all notifications</Link>
        </div>
      )}
    </div>
  )
}

function UserMenu() {
  const { user, employee, logout } = useAuth()
  const [theme, toggleTheme] = useTheme()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])
  const name = employee?.full_name || user?.email
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-2.5 rounded-lg py-1 pl-1 pr-2 hover:bg-surface-2" aria-label="Account menu">
        <Avatar name={name} fileId={employee?.photo_file_id} size="sm" />
        <span className="hidden text-left lg:block">
          <span className="block max-w-[150px] truncate text-[13px] font-semibold leading-tight">{name}</span>
          <span className="block text-2xs text-muted">{user?.role?.name}</span>
        </span>
      </button>
      {open && (
        <div className="absolute right-0 top-12 z-50 w-60 animate-scale-in rounded-xl border border-line bg-surface p-1.5 shadow-pop">
          <div className="border-b border-line px-2.5 pb-2.5 pt-1.5">
            <p className="truncate text-sm font-semibold">{name}</p>
            <p className="truncate text-xs text-muted">{user?.email}</p>
          </div>
          <div className="pt-1.5">
            <Link to="/profile" onClick={() => setOpen(false)} className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-ink-2 hover:bg-surface-2"><User className="h-4 w-4" />My profile</Link>
            <button onClick={toggleTheme} className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-ink-2 hover:bg-surface-2">
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}{theme === 'dark' ? 'Light mode' : 'Dark mode'}
            </button>
            <button onClick={logout} className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-danger hover:bg-danger-soft"><LogOut className="h-4 w-4" />Sign out</button>
          </div>
        </div>
      )}
    </div>
  )
}

const MOBILE_TABS = [
  { to: '/', label: 'Home', icon: LayoutDashboard, end: true },
  { to: '/attendance', label: 'Attendance', icon: CalendarCheck },
  { to: '/tasks', label: 'Tasks', icon: CheckSquare },
  { to: '/leave', label: 'Leave', icon: CalendarDays },
]

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('eo-collapsed') === '1' } catch { return false } })
  const [mobileOpen, setMobileOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const location = useLocation()
  const online = useOnline()

  useEffect(() => { setMobileOpen(false) }, [location.pathname])
  useEffect(() => { try { localStorage.setItem('eo-collapsed', collapsed ? '1' : '0') } catch { /* ignore */ } }, [collapsed])
  useEffect(() => {
    const h = (e) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearchOpen(true) } }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar */}
      <aside className={clsx('fixed inset-y-0 left-0 z-40 hidden flex-col bg-night transition-[width] duration-200 lg:flex', collapsed ? 'w-[72px]' : 'w-[248px]')}>
        <Brand collapsed={collapsed} />
        <SidebarContent collapsed={collapsed} />
        <button onClick={() => setCollapsed((c) => !c)} className="flex h-11 items-center justify-center gap-2 border-t border-night-line text-xs text-[#6F8792] hover:text-white" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          {collapsed ? <ChevronsRight className="h-4 w-4" /> : <><ChevronsLeft className="h-4 w-4" />Collapse</>}
        </button>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-[60] lg:hidden">
          <div className="absolute inset-0 animate-fade-in bg-night/60" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-[82%] max-w-[300px] animate-fade-up flex-col bg-night">
            <div className="flex items-center justify-between pr-3">
              <Brand />
              <button onClick={() => setMobileOpen(false)} className="rounded-lg p-2 text-[#A9BAC4] hover:text-white" aria-label="Close menu"><X className="h-5 w-5" /></button>
            </div>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className={clsx('transition-[padding] duration-200', collapsed ? 'lg:pl-[72px]' : 'lg:pl-[248px]')}>
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur-md sm:px-6">
          <button onClick={() => setMobileOpen(true)} className="-ml-1 rounded-lg p-2 text-ink-2 hover:bg-surface-2 lg:hidden" aria-label="Open menu"><MenuIcon className="h-5 w-5" /></button>
          <Link to="/" className="lg:hidden"><img src="/echoutra-mark.png" alt="ECHOUTRA" className="h-7 w-auto" /></Link>
          <button onClick={() => setSearchOpen(true)} className="ml-auto flex h-9 items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 text-[13px] text-faint transition-colors hover:border-line-strong sm:ml-0 sm:w-72 lg:w-80">
            <Search className="h-4 w-4" />
            <span className="hidden sm:inline">Search people, projects, clients…</span>
            <kbd className="ml-auto hidden rounded border border-line bg-surface px-1.5 text-2xs font-medium text-muted sm:inline">Ctrl K</kbd>
          </button>
          <div className="flex items-center gap-1 sm:ml-auto">
            <NotificationsBell />
            <UserMenu />
          </div>
        </header>
        {!online && (
          <div className="flex items-center justify-center gap-2 bg-warning-soft px-4 py-2 text-xs font-medium text-warning"><WifiOff className="h-3.5 w-3.5" />You are offline. Changes can’t be saved until you reconnect.</div>
        )}
        <main className="mx-auto w-full max-w-[1440px] px-4 pb-28 pt-6 sm:px-6 lg:px-8 lg:pb-12">
          <div key={location.pathname} className="animate-fade-up"><Outlet /></div>
        </main>
      </div>

      {/* Mobile bottom navigation */}
      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur-md lg:hidden">
        <div className="grid grid-cols-5">
          {MOBILE_TABS.map((t) => (
            <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => clsx('flex flex-col items-center gap-1 py-2.5 text-[10.5px] font-medium', isActive ? 'text-brand-ink' : 'text-muted')}>
              <t.icon className="h-5 w-5" />{t.label}
            </NavLink>
          ))}
          <button onClick={() => setMobileOpen(true)} className="flex flex-col items-center gap-1 py-2.5 text-[10.5px] font-medium text-muted"><MoreHorizontal className="h-5 w-5" />More</button>
        </div>
      </nav>

      <GlobalSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  )
}
