import { useState } from 'react'
import { ago, api } from '../api'
import { Link } from 'react-router-dom'
import { Icon, VerdictPill, useLiveEvent, useLoad, useToast } from '../components/ui'

interface RoleRules {
  description: string; notes: string
  files: { read: string[]; write: string[]; deny: string[] }
  commands: { allow: string[] }
  database: { read_tables: string[]; write_tables: string[]; deny_columns: string[] }
}
interface Example { role: string; tool: string; arg: string; expected: string; got: string; reason: string; ok: boolean; why: string }
interface Draft { text: string; compiled: { roles: Record<string, RoleRules> }; examples: Example[]; warnings: string[]; compiled_at: number }
interface Active { text: string; compiled: { roles: Record<string, RoleRules> }; version: number; approved_at: number; approved_by: string }
interface Sources { folders: string[]; databases: string[]; db_names: Record<string, string>; configured: boolean; share: string; options: { folders: string[]; databases: string[] }; error?: string | null }
interface PolicyState { draft: Draft | null; active: Active | null; inventory: string }
interface Agent { id: string; name: string; role: string; created_at: number; last_used: number; calls: number; revoked: boolean }
interface NewAgent extends Agent { token: string; url: string; claude_code: string; bridge_command: string; mcp_json: unknown }
interface GwEvent { id: number; ts: number; agent: string; role: string; tool: string; target: string; verdict: string; layer: string; reason: string }

const EXAMPLE = `Support agents can read tickets and customer names and emails, and write notes in tickets/notes. They must never see card numbers or anything in payments.
The analytics agent can query the orders and customers tables but not emails or card numbers, and can read reports/. It can't change anything.`

function List({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null
  return <div className="rulelist small"><b>{label}</b><div className="chips">{items.map(i => <code key={i}>{i}</code>)}</div></div>
}

function RoleCard({ name, r }: { name: string; r: RoleRules }) {
  return (
    <div className="panel" style={{ margin: 0 }}>
      <h3 style={{ marginTop: 0 }}>{name}</h3>
      {r.description && <p className="small muted">{r.description}</p>}
      <List label="Can read" items={r.files.read} />
      <List label="Can write" items={r.files.write} />
      <List label="Never" items={r.files.deny} />
      <List label="Commands" items={r.commands.allow} />
      <List label="Tables (read)" items={r.database.read_tables} />
      <List label="Tables (write)" items={r.database.write_tables} />
      <List label="Hidden columns" items={r.database.deny_columns} />
      {r.notes && <p className="small muted">Supervisor note: {r.notes}</p>}
    </div>
  )
}

/** What agents can reach: folders and SQLite files inside the host folder shared with Senti (several of each). */
function SourcesPanel({ onSaved }: { onSaved: () => void }) {
  const src = useLoad<Sources>(() => api('/admin/gateway/sources'))
  const toast = useToast()
  const [pick, setPick] = useState<{ folders: string[]; databases: string[] } | null>(null)
  const s = src.data
  const cur = pick ?? (s ? { folders: s.folders, databases: s.databases } : { folders: [], databases: [] })
  const same = (a: string[], b: string[]) => a.length === b.length && a.every(x => b.includes(x))
  const changed = !!s && (!same(cur.folders, s.folders) || !same(cur.databases, s.databases) || !s.configured)
  const whole = cur.folders.includes('.')
  // a folder whose parent is chosen is already included
  const coveredBy = (f: string) => whole && f !== '.' ? '.' : cur.folders.find(p => p !== '.' && f !== p && f.startsWith(p + '/'))
  const toggle = (key: 'folders' | 'databases', v: string) => setPick({ ...cur, [key]: cur[key].includes(v) ? cur[key].filter(x => x !== v) : [...cur[key], v] })
  const dbName = (rel: string) => s?.db_names[rel] ?? rel.split('/').pop()!.replace(/\.(db|sqlite3?|sqlite)$/i, '')
  const save = async () => {
    // drop folders already covered by a chosen parent, so the saved list says what it means
    const folders = cur.folders.filter(f => !coveredBy(f))
    try {
      await api('/admin/gateway/sources', { method: 'PUT', body: { folders, databases: cur.databases } })
      setPick(null); src.reload(); onSaved()
      toast('Saved. Agents now reach these folders and databases. Regenerate the rules if paths or tables changed.')
    } catch (e: any) { toast(e.message, true) }
  }
  return (
    <section className="panel">
      <div className="panel-head"><h2>What agents can reach</h2>
        <button className="btn ghost sm" type="button" onClick={() => { setPick(null); src.reload() }}>Refresh</button></div>
      <p className="small muted">Everything below is inside <code>{s?.share ?? '…'}</code> on the server. Agents see only what you tick here; the rules below decide what each role may do with it. Paths in the policy start from this folder, like <code>support/tickets/**</code>.</p>
      {s?.error && <p className="small"><span className="pill block">Runner unavailable</span> {s.error}</p>}
      {s && (
        <div className="grid2 sources">
          <fieldset className="field"><legend>Folders <span className="muted small">{cur.folders.filter(f => !coveredBy(f)).length} chosen</span></legend>
            <div className="picklist" role="group" aria-label="Folders">
              {s.options.folders.map(f => {
                const by = coveredBy(f)
                const depth = f === '.' ? 0 : f.split('/').length
                return (
                  <label key={f} className={`pickrow${by ? ' covered' : ''}`} style={{ paddingLeft: 10 + depth * 16 }}>
                    <input type="checkbox" checked={!!by || cur.folders.includes(f)} disabled={!!by} onChange={() => toggle('folders', f)} />
                    <span className="mono">{f === '.' ? 'Everything in the shared folder' : f.split('/').pop()}</span>
                    {by && <span className="small muted">included</span>}
                  </label>
                )
              })}
            </div>
          </fieldset>
          <fieldset className="field"><legend>Databases (SQLite) <span className="muted small">{cur.databases.length} chosen</span></legend>
            <div className="picklist" role="group" aria-label="Databases">
              {s.options.databases.length ? s.options.databases.map(d => (
                <label key={d} className="pickrow">
                  <input type="checkbox" checked={cur.databases.includes(d)} onChange={() => toggle('databases', d)} />
                  <span className="mono">{d}</span>
                  {cur.databases.includes(d) && cur.databases.length > 1 && <span className="small muted">agents call it “{dbName(d)}”</span>}
                </label>
              )) : <p className="small muted" style={{ padding: 10 }}>No .db / .sqlite files in the shared folder.</p>}
            </div>
            <span className="hint">With several databases, agents name one in <code>query_db</code> and rules can say <code>crm.customers</code>. Database files are never readable as files.</span>
          </fieldset>
        </div>
      )}
      <div className="row">
        <button className="btn primary" type="button" onClick={save} disabled={!changed || (!cur.folders.length && !cur.databases.length)}>Save</button>
        {s && !s.configured && <span className="small muted">Not chosen yet: using the install default.</span>}
      </div>
      <p className="small muted">To share a different folder of the server, run <code>./senti-server install --gateway-dir /path/to/folder</code> on it (your files keep their owner).</p>
    </section>
  )
}

export default function Gateway() {
  const policy = useLoad<PolicyState>(() => api('/admin/gateway/policy'))
  const agents = useLoad<Agent[]>(() => api('/admin/gateway/agents'))
  const events = useLoad<GwEvent[]>(() => api('/admin/gateway/events?limit=50'))
  const toast = useToast()
  const [text, setText] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [na, setNa] = useState({ name: '', role: '' })
  const [shown, setShown] = useState<NewAgent | null>(null)
  useLiveEvent(m => { if (m.type === 'gateway_event') { events.reload(); agents.reload() } })

  const draft = policy.data?.draft ?? null
  const active = policy.data?.active ?? null
  const value = text ?? draft?.text ?? active?.text ?? ''
  const roles = Object.keys(active?.compiled.roles ?? {})
  const copy = (t: string) => navigator.clipboard.writeText(t).then(() => toast('Copied.'))

  const compile = async () => {
    setBusy(true)
    try { await api('/admin/gateway/policy/compile', { method: 'POST', body: { text: value } }); setText(null); policy.reload(); toast('Rules generated. Check them below before approving.') }
    catch (e: any) { toast(e.message, true) } finally { setBusy(false) }
  }
  const approve = async () => {
    try { const a = await api<Active>('/admin/gateway/policy/approve', { method: 'POST' }); policy.reload(); toast(`Policy version ${a.version} is live for every agent.`) }
    catch (e: any) { toast(e.message, true) }
  }
  const addAgent = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const a = await api<NewAgent>('/admin/gateway/agents', { method: 'POST', body: { name: na.name, role: na.role || roles[0], base_url: window.location.origin } })
      setShown(a); setNa({ name: '', role: na.role }); agents.reload()
    } catch (err: any) { toast(err.message, true) }
  }
  const revoke = async (a: Agent) => {
    if (!confirm(`Revoke ${a.name}? Its token stops working immediately.`)) return
    await api(`/admin/gateway/agents/${a.id}`, { method: 'DELETE' }); agents.reload()
  }
  const pending = draft && (!active || draft.compiled_at > active.approved_at)

  return (
    <div className="page">
      <div className="page-head"><div className="grow"><h1>Server gateway</h1>
        <p>AI agents reach this server’s files, commands and database only through Senti. Describe who may do what in plain English; Senti turns it into rules, checks every call, and lets a supervisor model decide anything the rules don’t cover.</p></div></div>

      <SourcesPanel onSaved={policy.reload} />

      <section className="panel">
        <h2>Policy in plain English</h2>
        <textarea aria-label="Server access policy" rows={6} value={value} placeholder={EXAMPLE} onChange={e => setText(e.target.value)} style={{ width: '100%' }} />
        <div className="row">
          <button className="btn" onClick={compile} disabled={busy || value.trim().length < 10}><Icon name="brain" size={16} />{busy ? 'Generating rules…' : 'Generate rules'}</button>
          {!value && <button className="btn ghost sm" onClick={() => setText(EXAMPLE)}>Use an example</button>}
          {active && <span className="small muted">Live: version {active.version}, approved by {active.approved_by} {ago(active.approved_at)}</span>}
        </div>
        <details className="small"><summary>What the server shares</summary><pre className="mono">{policy.data?.inventory}</pre></details>
      </section>

      {pending && draft && (
        <section className="panel" aria-live="polite">
          <h2>Review before it goes live</h2>
          {draft.warnings.length > 0 && <div className="small" style={{ marginBottom: 12 }}>{draft.warnings.map(w => <div key={w}><Icon name="warn" size={14} /> {w}</div>)}</div>}
          <div className="grid3">{Object.entries(draft.compiled.roles).map(([n, r]) => <RoleCard key={n} name={n} r={r} />)}</div>
          <h3>What would happen</h3>
          <div className="table-wrap" style={{ border: 'none' }}>
            <table>
              <thead><tr><th>Role</th><th>Action</th><th>Policy says</th><th>Senti does</th><th /></tr></thead>
              <tbody>{draft.examples.map((x, i) => (
                <tr key={i}><td>{x.role}</td><td className="small"><code>{x.tool}</code> {x.arg}</td><td><VerdictPill v={x.expected} /></td>
                  <td>{x.got === 'supervisor' ? <span className="pill neutral">Supervisor decides</span> : <VerdictPill v={x.got} />}<br /><span className="small muted">{x.reason}</span></td>
                  <td>{x.ok ? <Icon name="check" size={16} /> : x.got === 'supervisor' ? '' : <span title="The rules disagree with the example"><Icon name="warn" size={16} /></span>}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <div className="row"><button className="btn" onClick={approve}><Icon name="check" size={16} />Approve and go live</button><span className="small muted">Edit the text and generate again if something is wrong.</span></div>
        </section>
      )}

      <section className="panel">
        <h2>Who can connect</h2>
        <p className="small"><b>People’s AI assistants</b> (Claude Code, Claude Desktop, Cursor, Codex, OpenCode) connect through their Mac: pick their server role on <Link to="/people">People and roles</Link>, and their assistants get these tools after <code>senti connect</code> (part of setting up their Mac). No tokens or certificates to handle.</p>
        <p className="small"><b>Bots and services</b> without a person get their own token below; the token decides the role and is shown once.</p>
        <div className="table-wrap" style={{ border: 'none' }}>
          <table>
            <thead><tr><th>Agent</th><th>Role</th><th>Calls</th><th>Last used</th><th /></tr></thead>
            <tbody>
              {(agents.data ?? []).length === 0 && <tr><td colSpan={5}><div className="empty">No agents yet.</div></td></tr>}
              {(agents.data ?? []).map(a => (
                <tr key={a.id} style={a.revoked ? { opacity: .55 } : undefined}><td><b>{a.name}</b></td><td>{a.role}</td><td>{a.calls}</td><td className="small">{ago(a.last_used)}</td>
                  <td>{a.revoked ? <span className="small muted">revoked</span> : <button className="btn ghost sm" onClick={() => revoke(a)}>Revoke</button>}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <form className="row" onSubmit={addAgent}>
          <input required placeholder="Agent name, e.g. helpdesk-bot" value={na.name} onChange={e => setNa({ ...na, name: e.target.value })} style={{ maxWidth: 280 }} aria-label="Agent name" />
          <select value={na.role || roles[0] || ''} onChange={e => setNa({ ...na, role: e.target.value })} style={{ maxWidth: 200 }} aria-label="Agent role" disabled={!roles.length}>
            {roles.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
          <button className="btn" type="submit" disabled={!roles.length}><Icon name="plus" size={16} />Add agent</button>
          {!roles.length && <span className="small muted">Approve a policy first.</span>}
        </form>
        {shown && (
          <div style={{ marginTop: 12 }}>
            <p className="small muted">Connect <b>{shown.name}</b> ({shown.role}). This token is shown only now. The first option is for clients that accept this server’s certificate; the others go through Senti’s local bridge, which pins the certificate.</p>
            <div className="copy"><pre className="mono">{shown.claude_code}</pre><button className="btn" onClick={() => copy(shown.claude_code)}><Icon name="copy" size={16} />Copy</button></div>
            <div className="copy" style={{ marginTop: 8 }}><pre className="mono">{shown.bridge_command}</pre><button className="btn" onClick={() => copy(shown.bridge_command)}><Icon name="copy" size={16} />Copy</button></div>
            <div className="copy" style={{ marginTop: 8 }}><pre className="mono">{JSON.stringify(shown.mcp_json, null, 2)}</pre><button className="btn" onClick={() => copy(JSON.stringify(shown.mcp_json, null, 2))}><Icon name="copy" size={16} />Copy</button></div>
            <button className="btn ghost sm" onClick={() => setShown(null)}>Done</button>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Activity</h2>
        <div className="table-wrap" style={{ border: 'none' }}>
          <table>
            <thead><tr><th>When</th><th>Agent</th><th>Action</th><th>Decision</th><th>Why</th></tr></thead>
            <tbody>
              {(events.data ?? []).length === 0 && <tr><td colSpan={5}><div className="empty">No calls yet.</div></td></tr>}
              {(events.data ?? []).map(e => (
                <tr key={e.id}><td className="small">{ago(e.ts)}</td><td>{e.agent}<br /><span className="small muted">{e.role}</span></td>
                  <td className="small"><code>{e.tool}</code> {e.target.slice(0, 120)}</td><td><VerdictPill v={e.verdict} /><br /><span className="small muted">{e.layer}</span></td>
                  <td className="small">{e.reason}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
