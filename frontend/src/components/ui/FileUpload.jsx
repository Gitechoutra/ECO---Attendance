import { useRef, useState } from 'react'
import clsx from 'clsx'
import { FileText, UploadCloud, X } from 'lucide-react'
import { fmtBytes } from '../../lib/format'

/** Drag-and-drop file picker. Controlled: value = File | null. */
export function FileDrop({ value, onChange, accept, hint = 'PDF, images or Office documents up to 15 MB', error }) {
  const ref = useRef(null)
  const [over, setOver] = useState(false)
  const pick = (files) => { if (files?.[0]) onChange(files[0]) }
  if (value) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-line bg-surface-2 px-3 py-2.5">
        <FileText className="h-5 w-5 shrink-0 text-brand-ink" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{value.name}</p>
          <p className="text-xs text-muted">{fmtBytes(value.size)}</p>
        </div>
        <button type="button" onClick={() => onChange(null)} className="rounded p-1 text-faint hover:text-danger" aria-label="Remove file"><X className="h-4 w-4" /></button>
      </div>
    )
  }
  return (
    <div>
      <button
        type="button"
        onClick={() => ref.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files) }}
        className={clsx('flex w-full flex-col items-center justify-center rounded-lg border border-dashed px-4 py-6 text-center transition-colors',
          over ? 'border-brand bg-brand-soft/50' : error ? 'border-danger' : 'border-line-strong hover:border-faint hover:bg-surface-2')}
      >
        <UploadCloud className="mb-2 h-6 w-6 text-faint" />
        <span className="text-sm font-medium text-ink">Click to upload <span className="font-normal text-muted">or drag and drop</span></span>
        <span className="mt-0.5 text-xs text-muted">{hint}</span>
      </button>
      <input ref={ref} type="file" accept={accept} className="hidden" onChange={(e) => { pick(e.target.files); e.target.value = '' }} />
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  )
}
