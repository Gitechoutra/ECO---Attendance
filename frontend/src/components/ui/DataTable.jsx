import clsx from 'clsx'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { EmptyState, ErrorState, Skeleton } from './Display'

/**
 * columns: [{ key, header, render?(row), className?, align?, hideOnMobile? , mobile?: 'title'|'subtitle'|'meta' }]
 * On small screens rows collapse into stacked cards using `mobile` hints.
 */
export function DataTable({ columns, rows, loading, error, onRetry, onRowClick, empty, rowKey = 'id', dense }) {
  if (error) return <ErrorState message={error} onRetry={onRetry} />
  const cell = (c, r) => (c.render ? c.render(r) : r[c.key] ?? '—')
  const titleCol = columns.find((c) => c.mobile === 'title') || columns[0]
  const subCols = columns.filter((c) => c !== titleCol && c.mobile !== 'hide')

  return (
    <>
      {/* desktop */}
      <div className="scrollbar-thin hidden overflow-x-auto md:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line">
              {columns.map((c) => (
                <th key={c.key} className={clsx('whitespace-nowrap px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-faint', c.align === 'right' && 'text-right', c.className)}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && !rows?.length
              ? Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-b border-line/70">
                  {columns.map((c) => <td key={c.key} className="px-4 py-3.5"><Skeleton className="h-4 w-3/4" /></td>)}
                </tr>
              ))
              : rows?.map((r) => (
                <tr
                  key={r[rowKey]}
                  onClick={onRowClick ? () => onRowClick(r) : undefined}
                  className={clsx('border-b border-line/70 last:border-0 transition-colors', onRowClick && 'cursor-pointer hover:bg-surface-2', loading && 'opacity-60')}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={clsx('px-4 align-middle text-ink-2', dense ? 'py-2' : 'py-3', c.align === 'right' && 'text-right num', c.className)}>
                      {cell(c, r)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {/* mobile */}
      <div className="divide-y divide-line md:hidden">
        {loading && !rows?.length
          ? Array.from({ length: 4 }).map((_, i) => <div key={i} className="space-y-2 p-4"><Skeleton className="h-4 w-1/2" /><Skeleton className="h-3 w-3/4" /></div>)
          : rows?.map((r) => (
            <div key={r[rowKey]} onClick={onRowClick ? () => onRowClick(r) : undefined} className={clsx('p-4', onRowClick && 'active:bg-surface-2')}>
              <div className="mb-2">{cell(titleCol, r)}</div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                {subCols.map((c) => (
                  <div key={c.key} className={clsx('min-w-0', c.mobile === 'full' && 'col-span-2')}>
                    <div className="text-2xs font-medium uppercase tracking-wide text-faint">{c.header}</div>
                    <div className="mt-0.5 truncate text-[13px] text-ink-2">{cell(c, r)}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
      </div>
      {!loading && rows && rows.length === 0 && (empty || <EmptyState title="No records found" description="Try adjusting your filters." />)}
    </>
  )
}

export function Pagination({ page, pages, total, onChange, pageSize }) {
  if (!total) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-[13px] text-muted">
      <span className="num">{from}–{to} of {total}</span>
      <div className="flex items-center gap-1">
        <button disabled={page <= 1} onClick={() => onChange(page - 1)} className="flex h-8 w-8 items-center justify-center rounded-lg border border-line text-ink-2 hover:bg-surface-2 disabled:opacity-40" aria-label="Previous page">
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="num px-2">Page {page} of {pages || 1}</span>
        <button disabled={page >= pages} onClick={() => onChange(page + 1)} className="flex h-8 w-8 items-center justify-center rounded-lg border border-line text-ink-2 hover:bg-surface-2 disabled:opacity-40" aria-label="Next page">
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
