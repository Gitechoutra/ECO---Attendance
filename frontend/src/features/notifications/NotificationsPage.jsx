import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import { Bell, CheckCheck } from 'lucide-react'
import { api } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import { Button, Card, EmptyState, ErrorState, PageHeader, Pagination, Segmented, Skeleton } from '../../components/ui'
import { fmtDateTime, fromNow, titleCase } from '../../lib/format'

export default function NotificationsPage() {
  const nav = useNavigate()
  const [unread, setUnread] = useState(false)
  const [page, setPage] = useState(1)
  const { data, loading, error, reload } = useApi('/notifications', { unread: unread || undefined, page, page_size: 30 })
  if (error) return <ErrorState message={error} onRetry={reload} />
  return (
    <>
      <PageHeader title="Notifications" description={data ? `${data.unread_count} unread` : undefined}
        actions={<Button variant="secondary" icon={CheckCheck} disabled={!data?.unread_count} onClick={async () => { await api.post('/notifications/read-all'); reload() }}>Mark all read</Button>} />
      <Card padded={false}>
        <div className="border-b border-line p-3"><Segmented value={unread} onChange={(v) => { setUnread(v); setPage(1) }} options={[{ value: false, label: 'All' }, { value: true, label: 'Unread' }]} /></div>
        {loading && !data ? <div className="space-y-3 p-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
          : !data.items.length ? <EmptyState icon={Bell} title={unread ? 'No unread notifications' : 'No notifications yet'} />
            : <ul className="divide-y divide-line">{data.items.map((n) => (
              <li key={n.id}>
                <button onClick={async () => { if (!n.is_read) await api.post(`/notifications/${n.id}/read`); if (n.link) nav(n.link); else reload() }}
                  className={clsx('flex w-full gap-3 px-5 py-4 text-left hover:bg-surface-2', !n.is_read && 'bg-brand-soft/30')}>
                  <span className={clsx('mt-1.5 h-2 w-2 shrink-0 rounded-full', n.is_read ? 'bg-transparent' : 'bg-brand')} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-ink">{n.title}</span>
                    {n.body && <span className="mt-0.5 block text-[13px] text-muted">{n.body}</span>}
                    <span className="mt-1 block text-2xs text-faint" title={fmtDateTime(n.created_at)}>{titleCase(n.category)} · {fromNow(n.created_at)}</span>
                  </span>
                </button>
              </li>))}</ul>}
        <Pagination page={page} pages={data?.pages} total={data?.total} pageSize={30} onChange={setPage} />
      </Card>
    </>
  )
}
