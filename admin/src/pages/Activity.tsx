import { Fragment, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AGENTS, agentName, api, clock, what, type EventRow } from '../api'
import { Icon, Seg, VerdictPill, useLiveEvent } from '../components/ui'

const PAGE = 50

export default function Activity() {
  const [params, setParams] = useSearchParams()
  const verdict = params.get('verdict') ?? ''
  const agent = params.get('agent') ?? ''
  const [q, setQ] = useState(params.get('q') ?? '')
  const [rows, setRows] = useState<(EventRow & { fresh?: boolean })[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [open, setOpen] = useState<string>('')
  const [err, setErr] = useState('')
  const qs = (extra: Record<string, string | number> = {}) => new URLSearchParams(
    Object.entries({ verdict, agent, q: params.get('q') ?? '', limit: PAGE, ...extra }).filter(([, v]) => v !== '').map(([k, v]) => [k, String(v)])).toString()

  useEffect(() => {
    setOffset(0)
    api(`/admin/events?${qs()}`).then(r => { setRows(r.items); setTotal(r.total); setErr('') }).catch(e => setErr(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verdict, agent, params.get('q')])

  useLiveEvent(m => {
    if (m.type !== 'event' || !m.event.verdict) return
    const e = m.event as EventRow
    if ((verdict && e.verdict !== verdict) || (agent && e.agent !== agent)) return
    const s = (params.get('q') ?? '').toLowerCase()
    if (s && ![e.reason, e.tool, e.rule, e.task].some(x => (x ?? '').toLowerCase().includes(s))) return
    setRows(r => [{ ...e, fresh: true }, ...r])
    setTotal(t => t + 1)
  })

  const set = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p) }
  const more = () => api(`/admin/events?${qs({ offset: offset + PAGE })}`).then(r => { setRows(x => [...x, ...r.items]); setOffset(offset + PAGE) })
  const exportCsv = async () => {
    const res = await fetch(`/api/v1/admin/events.csv?${qs()}`, { credentials: 'same-origin' })
    const url = URL.createObjectURL(await res.blob())
    Object.assign(document.createElement('a'), { href: url, download: 'senti-events.csv' }).click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="page">
      <div className="page-head">
        <div className="grow"><h1>Activity</h1><p>Every action your agents tried, what I decided and why. New decisions appear at the top as they arrive.</p></div>
        <button className="btn" onClick={exportCsv}><Icon name="download" size={16} />Export CSV</button>
      </div>
      <div className="row">
        <Seg label="Verdict" value={verdict as any} onChange={v => set('verdict', v)}
          options={[{ v: '', label: 'All' }, { v: 'block', label: 'Stopped' }, { v: 'ask', label: 'Asked' }, { v: 'allow', label: 'Allowed' }] as any} />
        <select aria-label="Agent" value={agent} onChange={e => set('agent', e.target.value)} style={{ width: 170 }}>
          <option value="">All agents</option>
          {AGENTS.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <form onSubmit={e => { e.preventDefault(); set('q', q) }} style={{ flex: 1, minWidth: 220 }}>
          <input type="search" placeholder="Search reasons, rules, tools or tasks" value={q} onChange={e => setQ(e.target.value)} aria-label="Search" />
        </form>
        <span className="small muted">{total.toLocaleString()} {total === 1 ? 'decision' : 'decisions'}</span>
      </div>
      {err && <div className="al info"><p>{err}</p></div>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Time</th><th>Decision</th><th>Agent</th><th>Action</th><th>Why</th><th>Who</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6}><div className="empty">No decisions match. Enrolled Macs report here within a few seconds of each action.</div></td></tr>}
            {rows.map(e => (
              <Fragment key={e.id}>
                <tr className={`clickable${open === e.id ? ' expanded' : ''}${e.fresh ? ' fresh' : ''}`} onClick={() => setOpen(open === e.id ? '' : e.id)}
                  tabIndex={0} onKeyDown={k => k.key === 'Enter' && setOpen(open === e.id ? '' : e.id)} aria-expanded={open === e.id}>
                  <td className="small muted" style={{ whiteSpace: 'nowrap' }}>{clock(e.ts)}<br />{new Date(e.ts * 1000).toLocaleDateString()}</td>
                  <td><VerdictPill v={e.verdict} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}>{agentName(e.agent)}<br /><span className="small muted">{e.tool}</span></td>
                  <td className="what"><code title={what(e.input)}>{what(e.input) || '–'}</code></td>
                  <td style={{ maxWidth: 360 }}>{e.reason}</td>
                  <td className="small" style={{ whiteSpace: 'nowrap' }}>{e.user}<br /><span className="muted">{e.hostname}</span></td>
                </tr>
                {open === e.id && (
                  <tr className="expanded"><td colSpan={6}>
                    <dl className="detail">
                      <dt>Task</dt><dd>{e.task || <span className="muted">The agent’s task wasn’t reported.</span>}</dd>
                      <dt>Decided by</dt><dd>{layerName(e.layer)} <span className="muted small">({e.layer}{e.rule ? `, ${e.rule}` : ''})</span></dd>
                      <dt>Profile</dt><dd>{e.profile || '–'}</dd>
                      <dt>Input</dt><dd><pre>{JSON.stringify(e.input, null, 2)}</pre></dd>
                      <dt>Folder</dt><dd><code>{e.cwd}</code></dd>
                      <dt>Check time</dt><dd>{e.ms.toFixed(1)} ms</dd>
                      <dt>Session</dt><dd className="small muted">{e.session}</dd>
                    </dl>
                  </td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length < total && <button className="btn" onClick={more} style={{ alignSelf: 'center' }}>Show {Math.min(PAGE, total - rows.length)} more</button>}
    </div>
  )
}

export function layerName(layer: string): string {
  if (layer.startsWith('L0-honeytoken')) return 'Decoy secret (honeytoken)'
  if (layer.startsWith('L0-cache')) return 'Earlier identical decision'
  if (layer.startsWith('L0-prefetch')) return 'Script checked when it was written'
  if (layer.startsWith('L0-allowlist')) return 'The person chose “Always allow”'
  if (layer.startsWith('L0-scope')) return 'Task scope'
  if (layer.startsWith('L1-profile')) return 'Organization profile rule'
  if (layer.startsWith('L1')) return 'Built-in rule'
  if (layer.startsWith('L2-supply')) return 'Package check'
  if (layer.startsWith('L2-injection')) return 'Prompt-injection scan'
  if (layer.startsWith('L2')) return 'Detector'
  if (layer === 'L3-llm-local') return 'Local AI judge'
  if (layer === 'L3-llm-corporate') return 'Corporate AI judge'
  if (layer.startsWith('approval')) return 'Owner approval'
  if (layer === 'user-dialog') return 'The person, in a dialog'
  if (layer === 'fallback') return 'Safety fallback'
  return layer || '–'
}
