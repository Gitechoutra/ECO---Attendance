import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || '/api/v1'
const RT_KEY = 'eo-rt'

let accessToken = null
let refreshPromise = null
let onSessionEnd = () => {}

export const tokenStore = {
  get access() { return accessToken },
  set(access, refresh) {
    accessToken = access
    try { if (refresh) localStorage.setItem(RT_KEY, refresh) } catch { /* storage unavailable */ }
  },
  get refresh() {
    try { return localStorage.getItem(RT_KEY) } catch { return null }
  },
  clear() {
    accessToken = null
    try { localStorage.removeItem(RT_KEY) } catch { /* ignore */ }
  },
  onSessionEnd(fn) { onSessionEnd = fn },
}

export const api = axios.create({ baseURL: BASE, timeout: 60000 })

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

export async function refreshSession() {
  const rt = tokenStore.refresh
  if (!rt) throw new Error('no refresh token')
  if (!refreshPromise) {
    refreshPromise = axios
      .post(`${BASE}/auth/refresh`, { refresh_token: rt })
      .then(({ data }) => {
        tokenStore.set(data.access_token, data.refresh_token)
        return data.access_token
      })
      .finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { config, response } = error
    const isAuthCall = config?.url?.includes('/auth/login') || config?.url?.includes('/auth/refresh')
    if (response?.status === 401 && !config._retried && !isAuthCall && tokenStore.refresh) {
      config._retried = true
      try {
        await refreshSession()
        config.headers.Authorization = `Bearer ${accessToken}`
        return api(config)
      } catch {
        tokenStore.clear()
        onSessionEnd()
      }
    }
    return Promise.reject(error)
  },
)

/** Human-readable error message from any API failure. */
export function errorMessage(err, fallback = 'Something went wrong') {
  if (!err) return fallback
  if (err.code === 'ECONNABORTED') return 'The request timed out. Check your connection and try again.'
  if (!err.response) return navigator.onLine === false
    ? 'You are offline. Reconnect to continue.'
    : 'Cannot reach the server. Please try again shortly.'
  const d = err.response.data
  if (d instanceof Blob) return fallback
  if (typeof d?.detail === 'string') return d.detail
  if (Array.isArray(d?.detail)) return d.detail[0]?.msg || fallback
  return fallback
}

/** Download a protected file/export as a browser download. */
export async function downloadFile(url, params, fallbackName = 'download') {
  const res = await api.get(url, { params, responseType: 'blob' })
  const disp = res.headers['content-disposition'] || ''
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disp)
  const name = m ? decodeURIComponent(m[1] || m[2]) : fallbackName
  const href = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = href
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(href), 2000)
}

/** Fetch a protected file as an object URL (for previews / avatars). */
const blobCache = new Map()
export async function fileObjectUrl(fileId) {
  if (blobCache.has(fileId)) return blobCache.get(fileId)
  const p = api.get(`/files/${fileId}`, { responseType: 'blob' }).then((r) => URL.createObjectURL(r.data))
  blobCache.set(fileId, p)
  p.catch(() => blobCache.delete(fileId))
  return p
}
