import { useEffect, useState } from 'react'
import { Download, RefreshCw, X } from 'lucide-react'
import { useRegisterSW } from 'virtual:pwa-register/react'

/** Install prompt + "new version available" banner for the PWA. */
export default function PwaPrompt() {
  const [installEvent, setInstallEvent] = useState(null)
  const [dismissed, setDismissed] = useState(() => { try { return sessionStorage.getItem('eo-install-dismissed') === '1' } catch { return false } })
  const { needRefresh: [needRefresh, setNeedRefresh], updateServiceWorker } = useRegisterSW()

  useEffect(() => {
    const h = (e) => { e.preventDefault(); setInstallEvent(e) }
    window.addEventListener('beforeinstallprompt', h)
    return () => window.removeEventListener('beforeinstallprompt', h)
  }, [])

  if (needRefresh) {
    return (
      <Banner icon={RefreshCw} text="A new version of ECHOUTRA ONE is available." action="Update" onAction={() => updateServiceWorker(true)} onClose={() => setNeedRefresh(false)} />
    )
  }
  if (installEvent && !dismissed) {
    return (
      <Banner
        icon={Download}
        text="Install ECHOUTRA ONE for quick access and a full-screen experience."
        action="Install"
        onAction={async () => { installEvent.prompt(); await installEvent.userChoice; setInstallEvent(null) }}
        onClose={() => { setDismissed(true); try { sessionStorage.setItem('eo-install-dismissed', '1') } catch { /* ignore */ } }}
      />
    )
  }
  return null
}

function Banner({ icon: Icon, text, action, onAction, onClose }) {
  return (
    <div className="fixed inset-x-3 bottom-20 z-[95] mx-auto flex max-w-md animate-fade-up items-center gap-3 rounded-xl border border-night-line bg-night p-3 pl-4 text-white shadow-pop lg:bottom-5">
      <Icon className="h-5 w-5 shrink-0 text-brand" />
      <p className="flex-1 text-[13px] text-[#C8D5DC]">{text}</p>
      <button onClick={onAction} className="h-8 rounded-lg bg-brand px-3 text-xs font-semibold text-[#03211D]">{action}</button>
      <button onClick={onClose} className="rounded p-1 text-[#6F8792] hover:text-white" aria-label="Dismiss"><X className="h-4 w-4" /></button>
    </div>
  )
}
