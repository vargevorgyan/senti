import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ago, agentName, api, clock, what, type EventRow, type GatewayOverview, type Overview as O } from '../api'
import { BarkWave, DecisionAlert, VerdictPill, useLiveEvent, useLoad } from '../components/ui'

const fmt = (n: number) => n.toLocaleString()
const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`

export default function Overview() {
  const { data: o, reload, error } = useLoad<O>(() => api('/admin/overview'))
  const [feed, setFeed] = useState<(EventRow & { fresh?: boolean })[]>([])
  useLiveEvent(m => {
    if (m.type === 'event' && m.event.verdict) {
      setFeed(f => [{ ...m.event, fresh: true }, ...f].slice(0, 12))
      window.clearTimeout((window as any).__sentiOv)
      ;(window as any).__sentiOv = window.setTimeout(reload, 1500)
    }
    if (m.type === 'approval' || m.type === 'device_enrolled') reload()
    if (m.type === 'gateway_event') {
      window.clearTimeout((window as any).__sentiGw)
      ;(window as any).__sentiGw = window.setTimeout(reload, 1500)
    }
  })
  if (error) return <div className="page"><div className="al info"><p>I couldn’t load the overview: {error}</p></div></div>
  if (!o) return <div className="page"><p className="muted">Loading…</p></div>
  const v = o.by_verdict
  const max = Math.max(1, ...o.timeline.hours)
  const agents = Object.entries(o.by_agent)
  const agentMax = Math.max(1, ...agents.map(a => a[1]))
  const quiet = o.events_24h === 0
  const g = o.gateway
  return (
    <div className="page">
      {o.default_password && (
        <div className="al ask" role="alert">
          <div><h3>Change the default admin password</h3><p>This panel still uses the password it shipped with. Use “Change password” at the bottom of the sidebar before anyone else can reach it.</p></div>
        </div>
      )}
      {o.demo_code_active && (
        <div className="al info" role="status"><p>The shared demo enrollment code is active. Anyone who knows it can enroll a Mac; delete it on the Devices page when the demo is over.</p></div>
      )}
      <section className="watch">
        <div>
          {quiet ? (
            <h1>All quiet. No agent has asked me anything in the last 24 hours.</h1>
          ) : (
            <h1>In the last 24 hours I checked <span className="n">{fmt(o.events_24h)}</span> actions, stopped <span className="n">{fmt(v.block)}</span> and asked about <span className="n">{fmt(v.ask)}</span>.</h1>
          )}
          <p className="sub">
            {plural(o.devices.online, 'Mac is', 'Macs are')} online out of {fmt(o.devices.total)} enrolled.{' '}
            {Math.round(o.llm_share * 100)}% of decisions needed an AI judge; the rest were settled by rules
            {o.latency_ms.p50 ? ` in about ${o.latency_ms.p50 < 10 ? o.latency_ms.p50.toFixed(1) : Math.round(o.latency_ms.p50)} ms` : ''}.
            {g && g.calls_24h > 0 ? <> The server gateway handled {plural(g.calls_24h, 'agent call', 'agent calls')} and stopped {fmt(g.blocked)}.</> : null}
            {o.pending_approvals ? <> <Link to="/approvals">{plural(o.pending_approvals, 'request waits', 'requests wait')} for your answer.</Link></> : null}
          </p>
        </div>
        <BarkWave className="wave" />
      </section>

      <div className="facts">
        <div><b>{fmt(v.allow)}</b><span>allowed quietly</span></div>
        <div><b>{fmt(v.ask)}</b><span>asked the person first</span></div>
        <div><b>{fmt(v.block)}</b><span>stopped</span></div>
        <div><b>{o.latency_ms.p95 ? `${Math.round(o.latency_ms.p95)} ms` : '–'}</b><span>slowest 5% of checks</span></div>
      </div>

      <div className="grid2 wide-left">
        <section className="panel" aria-labelledby="t-hours">
          <div className="panel-head"><h3 id="t-hours">Actions per hour</h3><span className="small muted">green: checked, red: stopped</span></div>
          <div className="chart" role="img" aria-label="Actions and blocks per hour over the last 24 hours">
            {o.timeline.hours.map((h, i) => (
              <div className="col" key={i} title={`${h} actions, ${o.timeline.blocks[i]} stopped`}>
                <i className="b" style={{ height: `${(o.timeline.blocks[i] / max) * 100}%` }} />
                <i className="a" style={{ height: `${((h - o.timeline.blocks[i]) / max) * 100}%` }} />
              </div>
            ))}
          </div>
          <div className="axis"><span>24 h ago</span><span>12 h ago</span><span>now</span></div>
        </section>
        <section className="panel" aria-labelledby="t-agents">
          <div className="panel-head"><h3 id="t-agents">By agent</h3></div>
          {agents.length ? (
            <div className="bars">
              {agents.map(([a, n]) => (
                <div className="b" key={a}><span>{agentName(a)}</span><div className="track"><div className="fill" style={{ width: `${(n / agentMax) * 100}%` }} /></div><span className="num">{fmt(n)}</span></div>
              ))}
            </div>
          ) : <p className="muted small">No agent activity yet.</p>}
          {o.top_rules.length > 0 && <>
            <h3 style={{ marginTop: 8 }}>What I stepped in for</h3>
            <div className="bars">
              {o.top_rules.map(([r, n]) => (
                <div className="b" key={r}><span className="small" title={r} style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.replaceAll('_', ' ')}</span><div className="track"><div className="fill" style={{ width: `${(n / o.top_rules[0][1]) * 100}%`, background: 'var(--terracotta)' }} /></div><span className="num">{n}</span></div>
              ))}
            </div>
          </>}
        </section>
      </div>

      {g && <GatewayPanel g={g} />}

      <div className="grid2">
        <section className="panel" aria-labelledby="t-blocks">
          <div className="panel-head"><h3 id="t-blocks">Recently stopped</h3><Link to="/activity?verdict=block" className="small">See all</Link></div>
          {o.recent_blocks.length ? o.recent_blocks.slice(0, 4).map(e => <DecisionAlert key={e.id} e={e} />)
            : <div className="al ok"><p>Nothing stopped yet. When I block something it shows up here.</p></div>}
        </section>
        <section className="panel" aria-labelledby="t-feed">
          <div className="panel-head"><h3 id="t-feed">Live</h3><Link to="/activity" className="small">Open activity</Link></div>
          {feed.length ? (
            <div className="feed" aria-live="polite">
              {feed.map(e => (
                <div className={`it${e.fresh ? ' fresh' : ''}`} key={e.id}>
                  <span className="t">{clock(e.ts)}</span><VerdictPill v={e.verdict} />
                  <div style={{ minWidth: 0 }}><code>{what(e.input) || e.tool}</code><span className="small muted">{agentName(e.agent)}, {e.user}</span></div>
                </div>
              ))}
            </div>
          ) : <p className="muted small">Decisions from every enrolled Mac appear here as they happen.</p>}
        </section>
      </div>
    </div>
  )
}

const LAYER: Record<string, string> = { 'hard-rule': 'fixed rules', 'role-rule': 'role rules', supervisor: 'supervisor model' }

/** The server gateway: AI agents' calls on the company server (not the Macs' hooks). */
function GatewayPanel({ g }: { g: GatewayOverview }) {
  const max = Math.max(1, ...g.timeline.hours)
  const agents = Object.entries(g.by_agent)
  const agentMax = Math.max(1, ...agents.map(a => a[1]))
  const layers = Object.entries(g.by_layer)
  return (
    <section className="panel" aria-labelledby="t-gw">
      <div className="panel-head"><h3 id="t-gw">Server gateway</h3><span className="small muted">agents using the company server, last 24 hours</span><Link to="/gateway" className="small">Open</Link></div>
      {g.calls_24h ? (<>
        <div className="facts gwfacts">
          <div><b>{fmt(g.calls_24h)}</b><span>calls</span></div>
          <div><b>{fmt(g.allowed)}</b><span>allowed</span></div>
          <div><b>{fmt(g.blocked)}</b><span>stopped</span></div>
          <div><b>{g.latency_ms.p50 ? `${Math.round(g.latency_ms.p50)} ms` : '–'}</b><span>typical decision</span></div>
        </div>
        <div className="grid2 wide-left">
          <div>
            <div className="chart" role="img" aria-label="Server gateway calls and blocks per hour over the last 24 hours">
              {g.timeline.hours.map((h, i) => (
                <div className="col" key={i} title={`${h} calls, ${g.timeline.blocks[i]} stopped`}>
                  <i className="b" style={{ height: `${(g.timeline.blocks[i] / max) * 100}%` }} />
                  <i className="a" style={{ height: `${((h - g.timeline.blocks[i]) / max) * 100}%` }} />
                </div>
              ))}
            </div>
            <div className="axis"><span>24 h ago</span><span>12 h ago</span><span>now</span></div>
            <p className="small muted">Decided by {layers.map(([l, n], i) => <span key={l}>{i ? ', ' : ''}{LAYER[l] ?? l} {fmt(n)}</span>)}.</p>
          </div>
          <div>
            <div className="bars">
              {agents.map(([a, n]) => (
                <div className="b" key={a}><span>{a}</span><div className="track"><div className="fill" style={{ width: `${(n / agentMax) * 100}%` }} /></div><span className="num">{fmt(n)}</span></div>
              ))}
            </div>
          </div>
        </div>
        {g.recent_blocks.length > 0 && (
          <div className="gwblocks">
            <h3>Recently stopped on the server</h3>
            {g.recent_blocks.map(e => (
              <div className="gwrow" key={e.id}>
                <VerdictPill v="block" />
                <div className="gwwhat"><code>{e.tool} {e.target}</code><span className="small muted">{e.agent} ({e.role}), {ago(e.ts)}, by {LAYER[e.layer] ?? e.layer}: {e.reason}</span></div>
              </div>
            ))}
          </div>
        )}
      </>) : <p className="muted small">No agent has used the server gateway in the last 24 hours. Connect one on the <Link to="/gateway">Server gateway</Link> page.</p>}
    </section>
  )
}
