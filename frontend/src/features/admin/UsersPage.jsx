import { Fragment, useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { Check, Lock, Minus, Plus, ShieldCheck } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useAction, useDebounced } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import {
  Badge, Button, Card, DataTable, Drawer, EmptyState, ErrorState, Field, FormModal, PageHeader, Pagination, PersonCell,
  SearchInput, Select, Skeleton, StatusBadge, Switch, Tabs, Toolbar,
} from '../../components/ui'
import { fmtDateTime } from '../../lib/format'

function UserDrawer({ user, roles, perms, onClose, onSaved }) {
  const { user: me, can } = useAuth()
  const toast = useToast()
  const [role, setRole] = useState('')
  const [active, setActive] = useState(true)
  const [overrides, setOverrides] = useState([])
  const [run, busy] = useAction(toast)
  useEffect(() => { if (user) { setRole(user.role.code); setActive(user.is_active); setOverrides(user.overrides) } }, [user])
  if (!user) return null
  const roleObj = roles.find((r) => r.code === role)
  const ov = Object.fromEntries(overrides.map((o) => [o.code, o.granted]))
  const setOv = async (code, granted) => {
    const r = await run(() => api.put(`/admin/users/${user.id}/permissions`, { code, granted }))
    setOverrides(r.data.overrides); onSaved()
  }
  const grouped = perms.reduce((a, p) => { (a[p.module] ||= []).push(p); return a }, {})
  const isSuper = user.role.code === 'super_admin'
  return (
    <Drawer open={Boolean(user)} onClose={onClose} title={user.employee?.full_name || user.email} subtitle={user.email} width="max-w-xl"
      footer={<Button loading={busy} disabled={role === user.role.code && active === user.is_active} onClick={async () => {
        await run(() => api.put(`/admin/users/${user.id}`, { role_code: role, is_active: active }), { success: 'User updated' }); onSaved(); onClose()
      }}>Save role & status</Button>}>
      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Role"><Select value={role} onChange={(e) => setRole(e.target.value)} disabled={user.id === me.id}
            options={roles.filter((r) => r.code !== 'super_admin' || me.role.code === 'super_admin').map((r) => ({ value: r.code, label: r.name }))} /></Field>
          <div className="flex items-end pb-2"><Switch checked={active} onChange={setActive} disabled={user.id === me.id} label="Account active" description="Inactive users cannot sign in" /></div>
        </div>
        <p className="text-xs text-muted">Last sign-in: {user.last_login_at ? fmtDateTime(user.last_login_at) : 'never'}{user.locked && ' · currently locked out'}</p>
        {can('admin.roles') && !isSuper && (
          <div>
            <h3 className="text-sm font-semibold">Individual permissions</h3>
            <p className="mb-3 text-xs text-muted">Grant or revoke specific permissions on top of the <b>{roleObj?.name}</b> role. Changes apply on the user’s next request.</p>
            <div className="space-y-4">
              {Object.entries(grouped).map(([mod, list]) => (
                <div key={mod}>
                  <p className="mb-1.5 text-2xs font-semibold uppercase tracking-wide text-faint">{mod}</p>
                  <div className="divide-y divide-line rounded-lg border border-line">
                    {list.map((p) => {
                      const fromRole = roleObj?.permissions.includes(p.code)
                      const state = ov[p.code]
                      const effective = state === undefined ? fromRole : state
                      return (
                        <div key={p.code} className="flex items-center gap-3 px-3 py-2">
                          <span className={clsx('flex h-5 w-5 items-center justify-center rounded-full', effective ? 'bg-success-soft text-success' : 'bg-surface-2 text-faint')}>{effective ? <Check className="h-3 w-3" /> : <Minus className="h-3 w-3" />}</span>
                          <span className="min-w-0 flex-1 text-[13px] text-ink-2">{p.description}{state !== undefined && <Badge tone={state ? 'success' : 'danger'} className="ml-2">{state ? 'Granted' : 'Revoked'}</Badge>}</span>
                          <Select value={state === undefined ? '' : state ? 'grant' : 'revoke'} disabled={busy} className="h-8 w-32 text-xs"
                            onChange={(e) => setOv(p.code, e.target.value === '' ? null : e.target.value === 'grant')}
                            options={[{ value: '', label: 'Role default' }, { value: 'grant', label: 'Grant' }, { value: 'revoke', label: 'Revoke' }]} />
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {isSuper && <p className="flex items-center gap-2 rounded-lg bg-surface-2 p-3 text-[13px] text-muted"><Lock className="h-4 w-4" />Super Admins always have every permission.</p>}
      </div>
    </Drawer>
  )
}

function RolesMatrix({ roles, perms, reload }) {
  const toast = useToast()
  const [draft, setDraft] = useState({})
  const [busy, setBusy] = useState(false)
  const [creating, setCreating] = useState(false)
  useEffect(() => setDraft(Object.fromEntries(roles.map((r) => [r.id, new Set(r.permissions)]))), [roles])
  const grouped = useMemo(() => perms.reduce((a, p) => { (a[p.module] ||= []).push(p); return a }, {}), [perms])
  const dirty = roles.filter((r) => r.code !== 'super_admin' && draft[r.id] && (draft[r.id].size !== r.permissions.length || r.permissions.some((p) => !draft[r.id].has(p))))
  const toggle = (rid, code) => setDraft((d) => { const s = new Set(d[rid]); s.has(code) ? s.delete(code) : s.add(code); return { ...d, [rid]: s } })
  const save = async () => {
    setBusy(true)
    try {
      for (const r of dirty) await api.put(`/admin/roles/${r.id}`, { name: r.name, description: r.description, permissions: [...draft[r.id]] })
      toast.success('Role permissions saved'); reload()
    } catch (e) { toast.apiError(e) } finally { setBusy(false) }
  }
  return (
    <Card padded={false}>
      <Toolbar>
        <p className="text-[13px] text-muted">Default permissions per role. The server enforces these on every request.</p>
        <div className="flex gap-2 sm:ml-auto">
          <Button size="sm" variant="secondary" icon={Plus} onClick={() => setCreating(true)}>Custom role</Button>
          <Button size="sm" icon={ShieldCheck} disabled={!dirty.length} loading={busy} onClick={save}>Save changes{dirty.length ? ` (${dirty.length})` : ''}</Button>
        </div>
      </Toolbar>
      <div className="scrollbar-thin overflow-x-auto">
        <table className="w-full min-w-[720px] text-[13px]">
          <thead className="sticky top-0 bg-surface"><tr className="border-b border-line"><th className="px-4 py-3 text-left text-xs font-semibold text-faint">Permission</th>
            {roles.map((r) => <th key={r.id} className="px-3 py-3 text-center text-xs font-semibold text-ink">{r.name}<span className="block font-normal text-faint">{r.user_count} users</span></th>)}</tr></thead>
          <tbody>
            {Object.entries(grouped).map(([mod, list]) => (
              <Fragment key={mod}>
                <tr className="bg-surface-2/70"><td colSpan={roles.length + 1} className="px-4 py-1.5 text-2xs font-semibold uppercase tracking-wide text-faint">{mod}</td></tr>
                {list.map((p) => (
                  <tr key={p.code} className="border-b border-line/60">
                    <td className="px-4 py-2 text-ink-2">{p.description}</td>
                    {roles.map((r) => {
                      const on = r.code === 'super_admin' || draft[r.id]?.has(p.code)
                      return <td key={r.id} className="px-3 py-2 text-center">
                        <input type="checkbox" checked={!!on} disabled={r.code === 'super_admin'} onChange={() => toggle(r.id, p.code)} className="h-4 w-4 accent-[rgb(var(--brand-strong))]" aria-label={`${r.name}: ${p.description}`} />
                      </td>
                    })}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <FormModal open={creating} onClose={() => setCreating(false)} title="Create custom role" description="Start empty and tick permissions in the matrix."
        fields={[{ name: 'name', label: 'Role name', required: true }, { name: 'description', label: 'Description' }]}
        onSubmit={async (v) => { await api.post('/admin/roles', { ...v, permissions: [] }); toast.success('Role created'); reload() }} />
    </Card>
  )
}

export default function UsersPage() {
  const { can } = useAuth()
  const [tab, setTab] = useState(can('admin.users') ? 'users' : 'roles')
  const [q, setQ] = useState('')
  const [role, setRole] = useState('')
  const [page, setPage] = useState(1)
  const [sel, setSel] = useState(null)
  const dq = useDebounced(q)
  const users = useApi(can('admin.users') ? '/admin/users' : null, { q: dq || undefined, role: role || undefined, page, page_size: 25 })
  const roles = useApi(can('admin.roles') ? '/admin/roles' : null)
  const perms = useApi(can('admin.roles') ? '/admin/permissions' : null)
  const STANDARD = [['super_admin', 'Super Admin / CEO'], ['hr_admin', 'HR / Admin'], ['project_manager', 'Project Manager'], ['employee', 'Employee']]
  const roleList = roles.data || STANDARD.map(([code, name]) => ({ id: code, code, name, permissions: [] }))
  return (
    <>
      <PageHeader title="Users & Roles" description="Manage sign-in access, roles and fine-grained permissions." />
      <Tabs className="mb-5" value={tab} onChange={setTab} tabs={[{ value: 'users', label: 'Users', hidden: !can('admin.users') }, { value: 'roles', label: 'Roles & permissions', hidden: !can('admin.roles') }]} />
      {tab === 'users' && (
        <div className="card overflow-hidden">
          <Toolbar>
            <SearchInput value={q} onChange={(v) => { setQ(v); setPage(1) }} placeholder="Search name or email" className="sm:w-72" />
            <Select value={role} onChange={(e) => { setRole(e.target.value); setPage(1) }} placeholder="All roles" className="sm:w-48"
              options={[{ value: 'super_admin', label: 'Super Admin' }, { value: 'hr_admin', label: 'HR / Admin' }, { value: 'project_manager', label: 'Project Manager' }, { value: 'employee', label: 'Employee' }]} />
          </Toolbar>
          <DataTable loading={users.loading} error={users.error} onRetry={users.reload} rows={users.data?.items} onRowClick={setSel}
            empty={<EmptyState title="No users found" description="Logins are created from an employee’s profile." />}
            columns={[
              { key: 'u', header: 'User', mobile: 'title', render: (u) => <PersonCell name={u.employee?.full_name || u.email} subtitle={u.email} fileId={u.employee?.photo_file_id} /> },
              { key: 'role', header: 'Role', render: (u) => <Badge tone={u.role.code === 'super_admin' ? 'brand' : 'neutral'}>{u.role.name}</Badge> },
              { key: 'ov', header: 'Overrides', render: (u) => u.overrides.length || '—' },
              { key: 'login', header: 'Last sign-in', render: (u) => u.last_login_at ? fmtDateTime(u.last_login_at) : 'Never' },
              { key: 'st', header: 'Status', render: (u) => u.locked ? <Badge tone="danger" dot>Locked</Badge> : <StatusBadge status={u.is_active ? 'active' : 'inactive'} /> },
            ]} />
          <Pagination page={page} pages={users.data?.pages} total={users.data?.total} pageSize={25} onChange={setPage} />
        </div>
      )}
      {tab === 'roles' && (roles.error ? <ErrorState message={roles.error} onRetry={roles.reload} /> : !roles.data || !perms.data ? <Skeleton className="h-96" /> : <RolesMatrix roles={roleList} perms={perms.data} reload={roles.reload} />)}
      {can('admin.users') && <UserDrawer user={sel} roles={roleList} perms={perms.data || []} onClose={() => setSel(null)} onSaved={() => users.reload({ silent: true })} />}
    </>
  )
}
