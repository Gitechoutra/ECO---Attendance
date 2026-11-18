import { useEffect, useState } from 'react'
import { Button } from './Button'
import { Checkbox, Field, Input, Select, Textarea } from './Form'

/** Searchable checklist used by the 'multiselect' field type. */
function MultiSelect({ options, value, onChange }) {
  const [q, setQ] = useState('')
  const sel = new Set(value)
  const list = options.filter((o) => o.label.toLowerCase().includes(q.toLowerCase())).slice(0, 100)
  return (
    <div className="rounded-lg border border-line-strong">
      <div className="flex items-center gap-2 border-b border-line p-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…" className="h-8 flex-1 bg-transparent px-1 text-sm outline-none placeholder:text-faint" />
        <span className="num text-xs text-muted">{value.length} selected</span>
      </div>
      <div className="scrollbar-thin max-h-48 overflow-y-auto p-1">
        {list.map((o) => (
          <label key={o.value} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] hover:bg-surface-2">
            <input type="checkbox" checked={sel.has(o.value)} onChange={() => onChange(sel.has(o.value) ? value.filter((x) => x !== o.value) : [...value, o.value])} className="accent-[rgb(var(--brand-strong))]" />
            {o.label}
          </label>
        ))}
        {!list.length && <p className="px-2 py-3 text-xs text-muted">No matches</p>}
      </div>
    </div>
  )
}
import { Modal } from './Overlay'
import { errorMessage } from '../../api/client'

/**
 * Schema-driven create/edit form.
 * fields: [{ name, label, type: text|email|number|date|time|datetime-local|textarea|select|checkbox|color,
 *            required, options:[{value,label}], placeholder, hint, span: 1|2, min, max, step, validate?(v, values) }]
 */
export function FormModal({ open, onClose, title, description, fields, initial, onSubmit, submitLabel = 'Save', size = 'md' }) {
  const [values, setValues] = useState({})
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    const v = {}
    fields.forEach((f) => {
      const raw = initial?.[f.name]
      v[f.name] = raw ?? f.default ?? (f.type === 'checkbox' ? false : f.type === 'multiselect' ? [] : '')
    })
    setValues(v)
    setErrors({})
    setFormError(null)
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (name, val) => {
    setValues((p) => ({ ...p, [name]: val }))
    setErrors((e) => ({ ...e, [name]: undefined }))
  }

  const submit = async (e) => {
    e.preventDefault()
    const errs = {}
    fields.forEach((f) => {
      if (f.hidden?.(values)) return
      const v = values[f.name]
      if (f.required && (v === '' || v === null || v === undefined)) errs[f.name] = `${f.label} is required`
      else if (f.validate) { const m = f.validate(v, values); if (m) errs[f.name] = m }
    })
    setErrors(errs)
    if (Object.keys(errs).length) return
    const payload = {}
    fields.forEach((f) => {
      if (f.hidden?.(values)) return
      let v = values[f.name]
      if (f.type === 'number') v = v === '' ? null : Number(v)
      else if (f.type === 'select' && f.numeric) v = v === '' ? null : Number(v)
      else if (v === '' && !f.keepEmpty) v = null
      payload[f.name] = v
    })
    setBusy(true)
    setFormError(null)
    try {
      await onSubmit(payload)
      onClose()
    } catch (err) {
      setFormError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={busy ? undefined : onClose}
      title={title}
      description={description}
      size={size}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" form="form-modal" loading={busy}>{submitLabel}</Button>
        </>
      }
    >
      <form id="form-modal" onSubmit={submit} noValidate className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {formError && <div className="rounded-lg border border-danger/30 bg-danger-soft px-3 py-2.5 text-[13px] text-danger sm:col-span-2">{formError}</div>}
        {fields.map((f) => {
          if (f.hidden?.(values)) return null
          const common = { id: `f-${f.name}`, value: values[f.name] ?? '', error: errors[f.name], placeholder: f.placeholder, disabled: f.disabled }
          const span = f.span === 1 ? '' : 'sm:col-span-2'
          if (f.type === 'checkbox') {
            return (
              <div key={f.name} className={span}>
                <Checkbox label={f.label} description={f.hint} checked={!!values[f.name]} onChange={(e) => set(f.name, e.target.checked)} />
              </div>
            )
          }
          let control
          if (f.type === 'multiselect') control = <MultiSelect options={f.options || []} value={values[f.name] || []} onChange={(v) => set(f.name, v)} />
          else if (f.type === 'textarea') control = <Textarea {...common} rows={f.rows || 3} onChange={(e) => set(f.name, e.target.value)} />
          else if (f.type === 'select') control = <Select {...common} placeholder={f.placeholder ?? 'Select…'} options={f.options} onChange={(e) => set(f.name, e.target.value)} />
          else control = <Input {...common} type={f.type || 'text'} min={f.min} max={f.max} step={f.step} onChange={(e) => set(f.name, e.target.value)} />
          return (
            <Field key={f.name} label={f.label} required={f.required} error={errors[f.name]} hint={f.hint} className={span} htmlFor={common.id}>
              {control}
            </Field>
          )
        })}
      </form>
    </Modal>
  )
}
