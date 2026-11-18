import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import clsx from 'clsx'

/** Reads the validated chart tokens for the active theme (SVG attributes can't use CSS variables). */
export function useChartTheme() {
  const read = () => {
    const cs = getComputedStyle(document.documentElement)
    const g = (n) => cs.getPropertyValue(n).trim()
    return { c1: g('--chart-1') || '#0E9F8A', c2: g('--chart-2') || '#5B5BD6', grid: g('--chart-grid') || '#E6EAED', axis: g('--chart-axis') || '#8A98A2' }
  }
  const [t, setT] = useState(read)
  useEffect(() => {
    const obs = new MutationObserver(() => setT(read()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [])
  return t
}

function ChartTooltip({ active, payload, label, format = (v) => v, labelFormat = (l) => l }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-pop">
      <p className="mb-1 font-semibold text-ink">{labelFormat(label)}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-ink-2">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />
          {p.name}: <span className="num font-semibold text-ink">{format(p.value)}</span>
        </p>
      ))}
    </div>
  )
}

/** Vertical bars over time/categories. series: [{key, name}] (max 2, colors in fixed order). */
export function ColumnChart({ data, xKey, series, height = 240, format, axisFormat, labelFormat, tickFormat }) {
  const t = useChartTheme()
  const colors = [t.c1, t.c2]
  return (
    <div>
      {series.length > 1 && (
        <div className="mb-3 flex flex-wrap gap-4 text-xs text-muted">
          {series.map((s, i) => (
            <span key={s.key} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: colors[i] }} />{s.name}</span>
          ))}
        </div>
      )}
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -16 }} barGap={2} barCategoryGap="28%">
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis dataKey={xKey} tickLine={false} axisLine={false} tick={{ fill: t.axis, fontSize: 11 }} tickFormatter={tickFormat} interval="preserveStartEnd" minTickGap={12} />
            <YAxis tickLine={false} axisLine={false} tick={{ fill: t.axis, fontSize: 11 }} allowDecimals={false} width={axisFormat ? 64 : 48} tickFormatter={axisFormat || format} />
            <Tooltip cursor={{ fill: t.grid, opacity: 0.5 }} content={<ChartTooltip format={format} labelFormat={labelFormat} />} />
            {series.map((s, i) => (
              <Bar key={s.key} dataKey={s.key} name={s.name} fill={colors[i]} radius={[4, 4, 0, 0]} maxBarSize={28} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/** Accessible horizontal bar list (single hue, labels in text ink, value right-aligned). */
export function BarList({ items, format = (v) => v, max, className, emptyLabel = 'No data yet' }) {
  const t = useChartTheme()
  const top = max ?? Math.max(...items.map((i) => i.value), 0)
  if (!items.length) return <p className="py-6 text-center text-sm text-muted">{emptyLabel}</p>
  return (
    <ul className={clsx('space-y-2.5', className)}>
      {items.map((i) => (
        <li key={i.label} className="group" title={`${i.label}: ${format(i.value)}`}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
            <span className="truncate text-ink-2">{i.label}</span>
            <span className="num font-semibold text-ink">{format(i.value)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-line/70">
            <div className="h-full rounded-full transition-[width] duration-500 group-hover:brightness-110" style={{ width: `${top ? (i.value / top) * 100 : 0}%`, background: t.c1 }} />
          </div>
        </li>
      ))}
    </ul>
  )
}
