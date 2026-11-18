import { useEffect, useState } from 'react'
import { api } from '../api/client'

const cache = new Map()

/** Cached lookup lists for pickers. kind: departments | designations | employees | clients | leaveTypes | projects */
const URLS = {
  departments: ['/departments', (d) => d.map((x) => ({ value: x.id, label: x.name }))],
  designations: ['/designations', (d) => d.map((x) => ({ value: x.id, label: x.title, department_id: x.department_id }))],
  employees: ['/employees/directory', (d) => d.map((x) => ({ value: x.id, label: `${x.full_name} (${x.employee_code})`, name: x.full_name, raw: x }))],
  clients: ['/clients/options', (d) => d.map((x) => ({ value: x.id, label: x.name }))],
  leaveTypes: ['/leave/types', (d) => d.filter((x) => x.is_active).map((x) => ({ value: x.id, label: x.name, raw: x }))],
  projects: ['/projects', (d) => d.items.map((x) => ({ value: x.id, label: `${x.name} (${x.code})`, raw: x })), { page_size: 200 }],
  expenseCategories: ['/expenses/categories', (d) => d.filter((x) => x.is_active).map((x) => ({ value: x.id, label: x.name, raw: x }))],
}

export function invalidateOptions(kind) {
  if (kind) cache.delete(kind)
  else cache.clear()
}

export function useOptions(kind, enabled = true) {
  const [opts, setOpts] = useState(cache.get(kind)?.value || [])
  useEffect(() => {
    if (!enabled) return
    const [url, map, params] = URLS[kind]
    let entry = cache.get(kind)
    if (!entry || Date.now() - entry.at > 60000) {
      entry = { at: Date.now(), promise: api.get(url, { params }).then((r) => map(r.data)) }
      cache.set(kind, entry)
      entry.promise.then((v) => { entry.value = v }).catch(() => cache.delete(kind))
    }
    let alive = true
    entry.promise.then((v) => alive && setOpts(v)).catch(() => {})
    return () => { alive = false }
  }, [kind, enabled])
  return opts
}
