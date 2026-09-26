import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AGENTS, api, type Otherwise, type Profile, type ProfileData, type Role } from '../api'
import { ChipInput, useLoad, useToast } from '../components/ui'

const MODES = [
  { v: 'local', label: 'Local judge', text: 'Qwen on each Mac decides. Private and works offline.' },
  { v: 'corporate', label: 'Corporate judge', text: 'The company model decides, with company context.' },
  { v: 'local_then_corporate', label: 'Local, then corporate', text: 'Local first; escalates only when unsure.' },
  { v: 'none', label: 'No AI judge', text: 'Anything unclear is asked about.' },
] as const
const OTHERWISE: { v: Otherwise; label: string }[] = [{ v: 'judge', label: 'Let the judge decide' }, { v: 'ask', label: 'Ask first' }, { v: 'block', label: 'Block' }, { v: 'allow', label: 'Allow' }]
const FEATURES: [string, string, string][] = [
  ['undo', 'Undo snapshots', 'Keep an instant copy of files before an agent deletes or overwrites them.'],
  ['honeytokens', 'Decoy secrets', 'Planted fake keys; any agent that touches one is stopped at once.'],
  ['injection_scan', 'Prompt-injection warnings', 'Warn the agent when a file or page it read tries to give it orders.'],
  ['scope_contract', 'Task scope', 'Work out the sites a task needs from the prompt and allow them without asking.'],
  ['sandbox', 'Sandbox', 'Run agents inside an OS sandbox that enforces these file and network limits.'],
]

function Section({ id, title, lead, children }: { id: string; title: string; lead?: string; children: React.ReactNode }) {
  return <section className="panel" id={id} aria-labelledby={`${id}-h`}><div><h2 id={`${id}-h`}>{title}</h2>{lead && <p className="small muted" style={{ marginTop: 4 }}>{lead}</p>}</div>{children}</section>
}
function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <div className="field"><span>{label}</span>{children}{hint && <span className="hint">{hint}</span>}</div>
}
function Other({ value, onChange, label }: { value: Otherwise; onChange: (v: Otherwise) => void; label: string }) {
  return <select aria-label={label} value={value} onChange={e => onChange(e.target.value as Otherwise)}>{OTHERWISE.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}</select>
}

export default function ProfileEditor() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const { data: roles } = useLoad<Role[]>(() => api('/admin/roles'))
  const [p, setP] = useState<Profile | null>(null)
  const [saved, setSaved] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { api<Profile>(`/admin/profiles/${id}`).then(x => { setP(x); setSaved(JSON.stringify(x)) }).catch(e => toast(e.message, true)) }, [id])
  if (!p) return <div className="page"><p className="muted">Loading…</p></div>
  const d = p.data
  const dirty = JSON.stringify(p) !== saved
  const upd = (fn: (d: ProfileData) => void) => { const n = structuredClone(p); fn(n.data); setP(n) }
  const save = async () => {
    setBusy(true)
    try {
      const r = await api<Profile>(`/admin/profiles/${p.id}`, { method: 'PUT', body: { name: p.name, description: p.description, priority: p.priority, data: p.data } })
      setP(r); setSaved(JSON.stringify(r))
      toast(`Saved version ${r.version}. Enrolled Macs pick it up within seconds.`)
    } catch (e: any) { toast(e.message, true) } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!confirm(`Delete the profile “${p.name}”? Agents using it fall back to their role’s other profiles.`)) return
    try { await api(`/admin/profiles/${p.id}`, { method: 'DELETE' }); toast('Profile deleted.'); nav('/profiles') } catch (e: any) { toast(e.message, true) }
  }
  const duplicate = async () => { const c = await api<Profile>(`/admin/profiles/${p.id}/duplicate`, { method: 'POST' }); nav(`/profiles/${c.id}`) }
  const toggleIn = (arr: string[], v: string) => arr.includes(v) ? arr.filter(x => x !== v) : [...arr, v]
  const ov = (agent: string) => d.agent_overrides?.[agent] ?? {}
  const setOv = (agent: string, fn: (o: any) => void) => upd(x => {
    const o = structuredClone(x.agent_overrides?.[agent] ?? {})
    fn(o)
    const clean = JSON.parse(JSON.stringify(o, (_k, v) => (v === '' || v === null || (Array.isArray(v) && !v.length) ? undefined : v)))
    const prune = (obj: any): any => { for (const k of Object.keys(obj)) { if (obj[k] && typeof obj[k] === 'object' && !Array.isArray(obj[k])) { prune(obj[k]); if (!Object.keys(obj[k]).length) delete obj[k] } } return obj }
    x.agent_overrides = { ...(x.agent_overrides ?? {}) }
    if (Object.keys(prune(clean)).length) x.agent_overrides[agent] = clean; else delete x.agent_overrides[agent]
  })

  return (
    <div className="page">
      <div className="page-head">
        <div className="grow"><Link to="/profiles" className="small">Profiles</Link><h1>{p.name}</h1><p>Version {p.version}. Changes apply to every Mac that uses this profile as soon as you save.</p></div>
        <button className="btn ghost" onClick={duplicate}>Duplicate</button>
        <button className="btn danger" onClick={remove}>Delete</button>
      </div>
      <div className="editor">
        <nav className="toc" aria-label="Profile sections">
          {[['general', 'General'], ['judge', 'Unclear cases'], ['files', 'Files'], ['network', 'Websites'], ['shell', 'Shell commands'], ['tools', 'Tools and packages'], ['agents', 'Per-agent limits'], ['features', 'Protections'], ['approvals', 'Questions and offline']].map(([k, l]) => <a key={k} href={`#${k}`}>{l}</a>)}
        </nav>
        <div className="sections">
          <Section id="general" title="General">
            <div className="grid2">
              <Field label="Name"><input value={p.name} onChange={e => setP({ ...p, name: e.target.value })} /></Field>
              <Field label="Priority" hint="When several profiles fit a person, the higher number wins."><input type="number" value={p.priority} onChange={e => setP({ ...p, priority: Number(e.target.value) })} /></Field>
            </div>
            <Field label="Description"><input value={p.description} onChange={e => setP({ ...p, description: e.target.value })} /></Field>
            <Field label="Roles" hint="People in these roles get this profile. None selected means every role.">
              <div className="checks">{(roles ?? []).map(r => <label key={r.id}><input type="checkbox" checked={d.applies_to.roles?.includes(r.id)} onChange={() => upd(x => { x.applies_to.roles = toggleIn(x.applies_to.roles ?? [], r.id) })} />{r.name}</label>)}</div>
            </Field>
            <Field label="Agents" hint="Which of their agents run under it.">
              <div className="checks">{AGENTS.map(a => <label key={a.id}><input type="checkbox" checked={d.applies_to.agents?.includes(a.id)} onChange={() => upd(x => { x.applies_to.agents = toggleIn(x.applies_to.agents ?? [], a.id) })} />{a.name}</label>)}</div>
            </Field>
          </Section>

          <Section id="judge" title="Who decides unclear cases" lead="Rules settle most actions in a few milliseconds. The rest go to an AI judge, which can never overrule a hard rule.">
            <div className="modes" role="radiogroup" aria-label="Judge mode">
              {MODES.map(m => (
                <button type="button" key={m.v} className="mode" role="radio" aria-checked={d.judge.mode === m.v} aria-pressed={d.judge.mode === m.v} onClick={() => upd(x => { x.judge.mode = m.v })}>
                  <b>{m.label}</b><span>{m.text}</span>
                </button>
              ))}
            </div>
            <Field label="Company instructions for the judge" hint="Plain sentences the judge must respect, for example which hosts are production.">
              <textarea value={d.judge.instructions} onChange={e => upd(x => { x.judge.instructions = e.target.value })} />
            </Field>
            <Field label="What the corporate judge may see" hint="Secrets are always redacted before anything leaves the Mac, except with “Full content”.">
              <select value={d.judge.send_to_corporate} onChange={e => upd(x => { x.judge.send_to_corporate = e.target.value as any })}>
                <option value="metadata_only">Only the action (command, path, site)</option>
                <option value="with_redacted_content">Action and script content, secrets redacted</option>
                <option value="full">Full content</option>
              </select>
            </Field>
          </Section>

          <Section id="files" title="Files" lead="Paths use ~ for the home folder and ** for any depth, for example ~/.ssh/** or **/.env*.">
            <Field label="Never allowed"><ChipInput value={d.rules.files.deny} onChange={v => upd(x => { x.rules.files.deny = v })} placeholder="~/.ssh/**" /></Field>
            <Field label="Ask first"><ChipInput value={d.rules.files.ask} onChange={v => upd(x => { x.rules.files.ask = v })} placeholder="~/Finance/**" /></Field>
            <Field label="Only these folders" hint="Leave empty to allow any folder that isn’t protected."><ChipInput value={d.rules.files.allow} onChange={v => upd(x => { x.rules.files.allow = v })} placeholder="~/code/**" /></Field>
            <div className="grid2">
              <Field label="Changing files"><select value={d.rules.files.write ?? 'allow'} onChange={e => upd(x => { x.rules.files.write = e.target.value as any })}><option value="allow">Allowed</option><option value="ask">Ask first</option><option value="block">Not allowed</option></select></Field>
              <Field label="Outside those folders"><select value={d.rules.files.outside_allow ?? 'ask'} onChange={e => upd(x => { x.rules.files.outside_allow = e.target.value as any })}><option value="ask">Ask first</option><option value="block">Not allowed</option></select></Field>
            </div>
          </Section>

          <Section id="network" title="Websites and network" lead="Use *.example.com to include subdomains.">
            <Field label="Allowed sites"><ChipInput value={d.rules.network.allow} onChange={v => upd(x => { x.rules.network.allow = v })} placeholder="github.com" /></Field>
            <Field label="Blocked sites"><ChipInput value={d.rules.network.deny} onChange={v => upd(x => { x.rules.network.deny = v })} placeholder="pastebin.com" /></Field>
            <Field label="Any other site"><Other label="Any other site" value={d.rules.network.otherwise} onChange={v => upd(x => { x.rules.network.otherwise = v })} /></Field>
          </Section>

          <Section id="shell" title="Shell commands" lead="Patterns match the whole command; * matches anything, for example sudo * or git push --force*.">
            <Field label="Never allowed"><ChipInput value={d.rules.shell.deny} onChange={v => upd(x => { x.rules.shell.deny = v })} placeholder="sudo *" /></Field>
            <Field label="Ask first"><ChipInput value={d.rules.shell.ask} onChange={v => upd(x => { x.rules.shell.ask = v })} placeholder="git push*" /></Field>
            <Field label="Always allowed"><ChipInput value={d.rules.shell.allow} onChange={v => upd(x => { x.rules.shell.allow = v })} placeholder="make test" /></Field>
            <Field label="Anything else"><Other label="Other commands" value={d.rules.shell.otherwise} onChange={v => upd(x => { x.rules.shell.otherwise = v })} /></Field>
          </Section>

          <Section id="tools" title="Tools and packages">
            <div className="grid2">
              <Field label="Allowed MCP tools"><ChipInput value={d.rules.mcp.allow} onChange={v => upd(x => { x.rules.mcp.allow = v })} placeholder="mcp__jira__*" /></Field>
              <Field label="Blocked MCP tools"><ChipInput value={d.rules.mcp.deny} onChange={v => upd(x => { x.rules.mcp.deny = v })} placeholder="mcp__db__drop*" /></Field>
            </div>
            <div className="grid2">
              <Field label="Other MCP tools"><Other label="Other MCP tools" value={d.rules.mcp.otherwise} onChange={v => upd(x => { x.rules.mcp.otherwise = v })} /></Field>
              <Field label="Installing packages">
                <select value={d.rules.packages} onChange={e => upd(x => { x.rules.packages = e.target.value as any })}>
                  <option value="check_supply_chain">Check against known-bad and look-alike names</option>
                  <option value="ask">Ask before every install</option><option value="block">Not allowed</option><option value="allow">Allowed</option>
                </select>
              </Field>
            </div>
          </Section>

          <Section id="agents" title="Per-agent limits" lead="Make one agent stricter than the rest of the profile. An agent can only be narrowed here, never given more.">
            {AGENTS.map(a => {
              const o = ov(a.id)
              const noNet = o.rules?.network?.otherwise === 'block'
              return (
                <div key={a.id} className="tinted" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <h3>{a.name}</h3>
                    <label className="toggle"><input type="checkbox" checked={noNet} onChange={() => setOv(a.id, x => { x.rules = x.rules ?? {}; x.rules.network = noNet ? {} : { otherwise: 'block', allow: [] } })} /><span>No network except allowed sites</span></label>
                  </div>
                  <div className="grid2">
                    <Field label="Judge for this agent">
                      <select value={o.judge?.mode ?? ''} onChange={e => setOv(a.id, x => { x.judge = e.target.value ? { mode: e.target.value } : undefined })}>
                        <option value="">Same as the profile</option>{MODES.map(m => <option key={m.v} value={m.v}>{m.label}</option>)}
                      </select>
                    </Field>
                    <Field label="Extra blocked commands"><ChipInput value={o.rules?.shell?.deny ?? []} onChange={v => setOv(a.id, x => { x.rules = x.rules ?? {}; x.rules.shell = { ...(x.rules.shell ?? {}), deny: v } })} placeholder="git push*" /></Field>
                  </div>
                </div>
              )
            })}
          </Section>

          <Section id="features" title="Protections">
            {FEATURES.map(([k, l, t]) => (
              <label className="toggle" key={k}><input type="checkbox" checked={!!d.features?.[k]} onChange={() => upd(x => { x.features = { ...x.features, [k]: !x.features?.[k] } })} /><span><b>{l}</b><br /><span className="small muted">{t}</span></span></label>
            ))}
          </Section>

          <Section id="approvals" title="Questions and offline behaviour">
            <div className="grid2">
              <Field label="Who answers “ask”" hint="Owner and admin questions appear under Approvals; the agent waits.">
                <select value={d.approvals.ask_goes_to} onChange={e => upd(x => { x.approvals = { ...x.approvals, ask_goes_to: e.target.value } })}>
                  <option value="user">The person at the keyboard</option><option value="owner">The agent’s owner (admin panel)</option><option value="admin">An administrator (admin panel)</option>
                </select>
              </Field>
              <Field label="If this server is unreachable" hint="Hard rules always keep working on the Mac.">
                <select value={d.on_backend_unreachable} onChange={e => upd(x => { x.on_backend_unreachable = e.target.value as any })}>
                  <option value="strict_local">Strict: use the local judge instead of the corporate one</option><option value="cached">Keep the last settings</option>
                </select>
              </Field>
            </div>
          </Section>

          <div className="savebar">
            <button className="btn primary" disabled={!dirty || busy} onClick={save}>{busy ? 'Saving…' : 'Save and push to Macs'}</button>
            {dirty ? <span className="small muted">Unsaved changes</span> : <span className="small muted">All changes saved</span>}
          </div>
        </div>
      </div>
    </div>
  )
}
