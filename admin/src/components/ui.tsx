import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { token, type EventRow, type Verdict } from '../api'

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const p: Record<string, ReactNode> = {
    home: <><path d="M3 11 12 4l9 7" /><path d="M5 10v10h14V10" /></>,
    activity: <path d="M3 12h4l3 8 4-16 3 8h4" />,
    approve: <><path d="M12 3.5 22 20.5H2Z" /><path d="M12 10v4" /><path d="M12 17.2v.1" /></>,
    shield: <><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6Z" /></>,
    people: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.8-3.6 3.3-5.5 6.5-5.5s5.7 1.9 6.5 5.5" /><path d="M16 4.8a3.2 3.2 0 0 1 0 6.4M18 14.8c2 .7 3.2 2.4 3.6 5.2" /></>,
    laptop: <><rect x="4" y="5" width="16" height="11" rx="1.5" /><path d="M2 19h20" /></>,
    brain: <><circle cx="12" cy="12" r="8.5" /><path d="M8.5 12h7M12 8.5v7" /></>,
    log: <><path d="M6 3h9l4 4v14H6Z" /><path d="M9 11h7M9 15h7" /></>,
    key: <><circle cx="8" cy="15" r="4" /><path d="m11 12 9-9M17 6l3 3" /></>,
    warn: <><path d="M12 3.5 22 20.5H2Z" /><path d="M12 10v4" /><path d="M12 17.2v.1" /></>,
    check: <path d="M5 12.5 10 17.5 19 7" />,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5.5M12 7.6v.1" /></>,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
    moon: <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" />,
    copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    download: <><path d="M12 4v11M7 10l5 5 5-5" /><path d="M4 20h16" /></>,
  }
  return <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{p[name]}</svg>
}

export function VerdictPill({ v }: { v: Verdict | null | string }) {
  if (!v) return <span className="pill quiet">note</span>
  const label = { allow: 'Allowed', ask: 'Asked', block: 'Blocked' }[v as Verdict] ?? v
  return <span className={`pill ${v}`}>{label}</span>
}

/** Design-system Alert, used for a single decision. */
export function DecisionAlert({ e }: { e: EventRow }) {
  const cmd = e.input?.command ?? e.input?.file_path ?? e.input?.url ?? ''
  if (e.verdict === 'block') {
    return (
      <div className="al block" role="alert">
        <span className="ic"><Icon name="warn" size={22} /></span>
        <div style={{ minWidth: 0 }}>
          <h3>I stopped this</h3>
          <p>{e.reason}{cmd ? <> <code>{cmd.length > 140 ? cmd.slice(0, 140) + '…' : cmd}</code></> : null}</p>
          <div className="meta">{e.user} on {e.hostname || 'a Mac'}, {e.agent}, {new Date(e.ts * 1000).toLocaleString()}</div>
        </div>
      </div>
    )
  }
  return (
    <div className="al ask">
      <span className="ic"><Icon name="warn" size={22} /></span>
      <div style={{ minWidth: 0 }}>
        <h3>I asked first</h3>
        <p>{e.reason}{cmd ? <> <code>{cmd.slice(0, 140)}</code></> : null}</p>
      </div>
    </div>
  )
}

export function ChipInput({ value, onChange, placeholder, id }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string; id?: string }) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const parts = draft.split(/[\n,]/).map(s => s.trim()).filter(Boolean)
    if (parts.length) onChange([...value, ...parts.filter(p => !value.includes(p))])
    setDraft('')
  }
  return (
    <div className="chips" onClick={e => (e.currentTarget.querySelector('input') as HTMLInputElement)?.focus()}>
      {value.map(v => (
        <span className="chip" key={v}>{v}<button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(value.filter(x => x !== v))}>×</button></span>
      ))}
      <input id={id} value={draft} placeholder={value.length ? '' : placeholder} onChange={e => setDraft(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add() }
          if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1))
        }} onBlur={add} />
    </div>
  )
}

export function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: { v: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(o => <button type="button" key={o.v} aria-pressed={value === o.v} onClick={() => onChange(o.v)}>{o.label}</button>)}
    </div>
  )
}

type Toast = { msg: string; err?: boolean } | null
const ToastCtx = createContext<(msg: string, err?: boolean) => void>(() => {})
export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<Toast>(null)
  const timer = useRef<number | undefined>(undefined)
  const show = useCallback((msg: string, err = false) => {
    setT({ msg, err })
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setT(null), 4200)
  }, [])
  return <ToastCtx.Provider value={show}>{children}{t && <div className={`toast${t.err ? ' err' : ''}`} role="status">{t.msg}</div>}</ToastCtx.Provider>
}
export const useToast = () => useContext(ToastCtx)

type LiveMsg = { type: string; [k: string]: any }
const LiveCtx = createContext<{ connected: boolean; subscribe: (fn: (m: LiveMsg) => void) => () => void }>({ connected: false, subscribe: () => () => {} })

/** One EventSource for the whole app; pages subscribe to the messages they care about. */
export function LiveProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false)
  const subs = useRef(new Set<(m: LiveMsg) => void>())
  useEffect(() => {
    let es: EventSource | null = null
    let retry: number | undefined
    let stopped = false
    const open = async () => {
      if (stopped) return
      let ticket = ''
      try {
        const r = await fetch('/api/v1/auth/stream-ticket', { method: 'POST', headers: { Authorization: `Bearer ${token.get()}` } })
        if (r.status === 401) { token.clear(); window.dispatchEvent(new Event('senti:logout')); return }
        ticket = (await r.json()).ticket
      } catch { retry = window.setTimeout(open, 3000); return }
      es = new EventSource(`/api/v1/admin/stream?token=${encodeURIComponent(ticket)}`)
      es.onopen = () => setConnected(true)
      es.onmessage = ev => { try { const m = JSON.parse(ev.data); subs.current.forEach(fn => fn(m)) } catch { /* keepalive */ } }
      es.onerror = () => { setConnected(false); es?.close(); retry = window.setTimeout(open, 3000) }
    }
    open()
    return () => { stopped = true; es?.close(); window.clearTimeout(retry) }
  }, [])
  const subscribe = useCallback((fn: (m: LiveMsg) => void) => { subs.current.add(fn); return () => { subs.current.delete(fn) } }, [])
  return <LiveCtx.Provider value={{ connected, subscribe }}>{children}</LiveCtx.Provider>
}
export const useLive = () => useContext(LiveCtx)
export function useLiveEvent(fn: (m: LiveMsg) => void) {
  const { subscribe } = useLive()
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => subscribe(m => ref.current(m)), [subscribe])
}

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string>('')
  const [n, setN] = useState(0)
  useEffect(() => {
    let live = true
    fn().then(d => { if (live) { setData(d); setError('') } }).catch(e => live && setError(String(e.message ?? e)))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, n])
  return { data, error, reload: () => setN(x => x + 1), setData }
}

export function BarkWave({ className }: { className?: string }) {
  // The one recurring motif from the brand book: concentric sage arcs from a terracotta dot.
  return (
    <svg className={className} viewBox="0 0 260 180" aria-hidden="true">
      <circle cx="40" cy="90" r="12" fill="var(--terracotta)" />
      <path d="M72 58 A46 46 0 0 1 72 122" fill="none" stroke="var(--sage)" strokeWidth="8" strokeLinecap="round" />
      <path d="M98 34 A78 78 0 0 1 98 146" fill="none" stroke="var(--sage)" strokeWidth="8" strokeLinecap="round" />
      <path d="M124 10 A110 110 0 0 1 124 170" fill="none" stroke="var(--sage)" strokeWidth="8" strokeLinecap="round" opacity=".55" />
    </svg>
  )
}
