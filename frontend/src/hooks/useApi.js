import { useCallback, useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../api/client'

/**
 * GET data with loading/error state. Re-fetches when url or params change.
 * Returns { data, loading, error, reload, setData }.
 */
export function useApi(url, params, { enabled = true, initial = null } = {}) {
  const [data, setData] = useState(initial)
  const [loading, setLoading] = useState(Boolean(url) && enabled)
  const [error, setError] = useState(null)
  const key = JSON.stringify(params || {})
  const reqId = useRef(0)

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!url || !enabled) return
    const id = ++reqId.current
    if (!silent) setLoading(true)
    setError(null)
    try {
      const res = await api.get(url, { params: JSON.parse(key) })
      if (id === reqId.current) setData(res.data)
    } catch (e) {
      if (id === reqId.current) setError(errorMessage(e))
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [url, key, enabled])

  useEffect(() => { load() }, [load])

  return { data, loading, error, reload: load, setData }
}

/** Wrap a mutating call with busy state + toast feedback. */
export function useAction(toast) {
  const [busy, setBusy] = useState(false)
  const run = useCallback(async (fn, { success, errorTitle } = {}) => {
    setBusy(true)
    try {
      const r = await fn()
      if (success) toast.success(success)
      return r
    } catch (e) {
      toast.apiError(e, errorTitle)
      throw e
    } finally {
      setBusy(false)
    }
  }, [toast])
  return [run, busy]
}

export function useDebounced(value, delay = 300) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return v
}
