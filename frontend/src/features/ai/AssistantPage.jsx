import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { Lock, MessageSquarePlus, Send, Sparkles, Trash2 } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { Avatar, Button, Card, EmptyState, IconButton, PageHeader, Skeleton } from '../../components/ui'
import { fromNow } from '../../lib/format'

/** Minimal, safe markdown: paragraphs, bullet lists, **bold**, `code`, and pipe tables. No raw HTML. */
function Markdown({ text }) {
  const inline = (s, k) => s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((p, i) =>
    p.startsWith('**') ? <strong key={`${k}-${i}`} className="font-semibold text-ink">{p.slice(2, -2)}</strong>
      : p.startsWith('`') ? <code key={`${k}-${i}`} className="rounded bg-surface-2 px-1 text-[12px]">{p.slice(1, -1)}</code> : p)
  const blocks = text.split(/\n{2,}/)
  return (
    <div className="space-y-3 text-sm leading-relaxed text-ink-2">
      {blocks.map((b, bi) => {
        const lines = b.split('\n')
        if (lines.length > 1 && lines.every((l) => l.trim().startsWith('|'))) {
          const rows = lines.filter((l) => !/^\|\s*-/.test(l.trim())).map((l) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim()))
          return (
            <div key={bi} className="scrollbar-thin overflow-x-auto"><table className="w-full text-[13px]">
              <thead><tr className="border-b border-line">{rows[0].map((c, i) => <th key={i} className="px-2 py-1.5 text-left font-semibold text-ink">{inline(c, i)}</th>)}</tr></thead>
              <tbody>{rows.slice(1).map((r, ri) => <tr key={ri} className="border-b border-line/60">{r.map((c, i) => <td key={i} className="px-2 py-1.5">{inline(c, i)}</td>)}</tr>)}</tbody>
            </table></div>
          )
        }
        if (lines.every((l) => /^\s*([-*•]|\d+\.)\s/.test(l))) {
          return <ul key={bi} className="list-disc space-y-1 pl-5">{lines.map((l, i) => <li key={i}>{inline(l.replace(/^\s*([-*•]|\d+\.)\s/, ''), i)}</li>)}</ul>
        }
        return <p key={bi} className="whitespace-pre-wrap">{lines.map((l, i) => <span key={i}>{i > 0 && <br />}{inline(l.replace(/^#+\s/, ''), i)}</span>)}</p>
      })}
    </div>
  )
}

export default function AssistantPage() {
  const { user, employee } = useAuth()
  const status = useApi('/ai/status')
  const convs = useApi('/ai/conversations')
  const [convId, setConvId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy])

  const open = async (id) => {
    setConvId(id); setErr(null)
    const { data } = await api.get(`/ai/conversations/${id}`)
    setMessages(data.messages)
  }
  const ask = async (text) => {
    const msg = (text ?? input).trim()
    if (!msg || busy) return
    setInput(''); setErr(null)
    setMessages((m) => [...m, { role: 'user', content: msg }])
    setBusy(true)
    try {
      const { data } = await api.post('/ai/chat', { message: msg, conversation_id: convId })
      setConvId(data.conversation_id)
      setMessages((m) => [...m, { role: 'model', content: data.answer }])
      convs.reload({ silent: true })
    } catch (e) {
      setErr(errorMessage(e))
      setMessages((m) => m.slice(0, -1))
      setInput(msg)
    } finally { setBusy(false) }
  }
  const configured = status.data?.configured
  const name = employee?.full_name || user.email

  return (
    <>
      <PageHeader title="AI Assistant" description="Ask about attendance, projects, clients and HR — answers use only data you’re allowed to see." />
      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <Card padded={false} className="hidden h-[calc(100vh-220px)] flex-col lg:flex">
          <div className="p-3"><Button variant="secondary" className="w-full" icon={MessageSquarePlus} onClick={() => { setConvId(null); setMessages([]); setErr(null) }}>New chat</Button></div>
          <div className="scrollbar-thin flex-1 overflow-y-auto px-2 pb-2">
            {convs.data?.map((c) => (
              <div key={c.id} className={clsx('group flex items-center gap-1 rounded-lg px-2 py-2', convId === c.id ? 'bg-surface-2' : 'hover:bg-surface-2')}>
                <button className="min-w-0 flex-1 text-left" onClick={() => open(c.id)}><p className="truncate text-[13px] font-medium">{c.title}</p><p className="text-2xs text-faint">{fromNow(c.updated_at)}</p></button>
                <IconButton icon={Trash2} size="sm" variant="danger" label="Delete conversation" className="opacity-0 group-hover:opacity-100"
                  onClick={async () => { await api.delete(`/ai/conversations/${c.id}`); if (convId === c.id) { setConvId(null); setMessages([]) } convs.reload() }} />
              </div>
            ))}
            {convs.data?.length === 0 && <p className="px-2 py-4 text-xs text-muted">No conversations yet.</p>}
          </div>
        </Card>

        <Card padded={false} className="flex h-[calc(100vh-220px)] min-h-[480px] flex-col">
          <div className="scrollbar-thin flex-1 overflow-y-auto p-5">
            {status.loading ? <Skeleton className="h-40" /> : !configured ? (
              <EmptyState icon={Lock} title="The AI assistant isn’t configured yet" description="An administrator needs to add a Google Gemini API key (GEMINI_API_KEY) to the server configuration. Everything else in ECHOUTRA ONE works without it." />
            ) : messages.length === 0 ? (
              <div className="mx-auto flex max-w-xl flex-col items-center py-10 text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-night text-brand"><Sparkles className="h-6 w-6" /></span>
                <h2 className="mt-4 text-lg font-semibold">How can I help, {name.split(' ')[0]}?</h2>
                <p className="mt-1 text-sm text-muted">I can summarise attendance, flag delayed projects, recap client communication and answer HR questions within your permissions.</p>
                <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
                  {status.data.suggestions.map((s) => <button key={s} onClick={() => ask(s)} className="rounded-xl border border-line px-3.5 py-3 text-left text-[13px] text-ink-2 transition-colors hover:border-brand hover:bg-brand-soft/40">{s}</button>)}
                </div>
              </div>
            ) : (
              <div className="mx-auto max-w-3xl space-y-6">
                {messages.map((m, i) => (
                  <div key={i} className={clsx('flex gap-3', m.role === 'user' && 'flex-row-reverse')}>
                    {m.role === 'user' ? <Avatar name={name} fileId={employee?.photo_file_id} size="sm" />
                      : <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-night text-brand"><Sparkles className="h-4 w-4" /></span>}
                    <div className={clsx('min-w-0 max-w-[85%] rounded-2xl px-4 py-3', m.role === 'user' ? 'bg-brand-soft text-ink' : 'border border-line bg-surface')}>
                      {m.role === 'user' ? <p className="whitespace-pre-wrap text-sm">{m.content}</p> : <Markdown text={m.content} />}
                    </div>
                  </div>
                ))}
                {busy && (
                  <div className="flex gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-full bg-night text-brand"><Sparkles className="h-4 w-4 animate-pulse" /></span>
                    <div className="flex items-center gap-1 rounded-2xl border border-line px-4 py-3">{[0, 1, 2].map((d) => <span key={d} className="h-1.5 w-1.5 animate-bounce rounded-full bg-faint" style={{ animationDelay: `${d * 120}ms` }} />)}</div></div>
                )}
                <div ref={endRef} />
              </div>
            )}
          </div>
          {configured && (
            <div className="border-t border-line p-3">
              {err && <p className="mb-2 rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">{err}</p>}
              <form onSubmit={(e) => { e.preventDefault(); ask() }} className="mx-auto flex max-w-3xl items-end gap-2">
                <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={1} placeholder="Ask about your company…"
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() } }}
                  className="input max-h-40 min-h-[44px] flex-1 resize-none py-2.5" />
                <Button type="submit" size="lg" icon={Send} loading={busy} disabled={!input.trim()} aria-label="Send" />
              </form>
              <p className="mt-2 text-center text-2xs text-faint">AI answers can be wrong. Verify important figures in the relevant module.</p>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
