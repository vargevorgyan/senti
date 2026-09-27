import { useEffect, useState } from 'react'
import { api, type JudgeOut, type Profile } from '../api'
import { Icon, Seg, useLoad, useToast } from '../components/ui'

type Kind = 'local' | 'api' | 'off'
interface Corp { url: string; model: string; enabled: boolean; api_key_set: boolean; kind: 'local' | 'api' }
interface LocalModel { name: string; size_gb: number }
interface Rec { model: string; ram_gb: number; download_gb: number; note: string }
interface LocalStatus {
  running: boolean; url: string; models: LocalModel[]; recommended: Rec[]; error?: string
  memory: { total_gb?: number; available_gb?: number }
  pulling: { model: string; status: string; completed: number; total: number; done?: boolean; error?: string } | null
}

// Cloud providers with an OpenAI-compatible API. Prices are approximate, per million tokens (in / out).
const PROVIDERS = [
  { id: 'openrouter', name: 'OpenRouter', url: 'https://openrouter.ai/api/v1', keyHint: 'sk-or-…',
    picks: [
      { model: 'qwen/qwen3-235b-a22b-2507', price: '$0.09 / $0.35', note: 'Strong and cheap. Recommended' },
      { model: 'mistralai/mistral-small-3.2-24b-instruct', price: '$0.09 / $0.25', note: 'Cheap, fast' },
      { model: 'openai/gpt-4o-mini', price: '$0.15 / $0.60', note: 'Reliable JSON' },
    ] },
  { id: 'openai', name: 'OpenAI', url: 'https://api.openai.com/v1', keyHint: 'sk-…',
    picks: [{ model: 'gpt-4o-mini', price: '$0.15 / $0.60', note: 'Cheap, reliable' }, { model: 'gpt-4.1-mini', price: '$0.40 / $1.60', note: 'Smarter' }] },
  { id: 'deepseek', name: 'DeepSeek', url: 'https://api.deepseek.com/v1', keyHint: 'sk-…',
    picks: [{ model: 'deepseek-chat', price: '$0.27 / $1.10', note: 'Non-reasoning chat model' }] },
  { id: 'groq', name: 'Groq', url: 'https://api.groq.com/openai/v1', keyHint: 'gsk_…',
    picks: [{ model: 'llama-3.3-70b-versatile', price: '$0.59 / $0.79', note: 'Very fast' }] },
  { id: 'custom', name: 'Other', url: '', keyHint: 'if your endpoint needs one', picks: [] },
]
const providerOf = (url: string) => PROVIDERS.find(p => p.url && url.startsWith(p.url))?.id ?? 'custom'

export default function Judge() {
  const toast = useToast()
  const { data: profiles } = useLoad<Profile[]>(() => api('/admin/profiles'))
  const status = useLoad<{ reachable: boolean; models?: string[]; model_present?: boolean; error?: string }>(() => api('/admin/corporate-model/status'))
  const local = useLoad<LocalStatus>(() => api('/admin/corporate-model/local'))
  const [cfg, setCfg] = useState<Corp | null>(null)
  const [kind, setKind] = useState<Kind>('api')
  const [provider, setProvider] = useState('openrouter')
  const [apiUrl, setApiUrl] = useState('')
  const [apiModel, setApiModel] = useState('')
  const [localModel, setLocalModel] = useState('')
  const [key, setKey] = useState('')
  const [t, setT] = useState({ profile_id: 'developer', task: 'Fix the failing signup test', tool: 'Bash', command: 'psql -h billing.prod.corp.internal -c "select * from customers"', content: '' })
  const [out, setOut] = useState<JudgeOut | null>(null)
  const [busy, setBusy] = useState(false)

  const apply = (c: Corp) => {
    setCfg(c)
    setKind(c.enabled ? c.kind : 'off')
    if (c.kind === 'local') setLocalModel(c.model)
    else { setApiUrl(c.url); setApiModel(c.model); setProvider(providerOf(c.url)) }
  }
  useEffect(() => { api<Corp>('/admin/settings/corporate-model').then(apply) }, [])
  // follow a model download while it runs
  const pulling = local.data?.pulling && !local.data.pulling.done
  useEffect(() => {
    if (!pulling) return
    const id = window.setInterval(local.reload, 2000)
    return () => window.clearInterval(id)
  }, [pulling])

  const pickProvider = (id: string) => {
    const p = PROVIDERS.find(x => x.id === id)!
    setProvider(id)
    if (p.url) setApiUrl(p.url)
    if (p.picks[0] && !p.picks.some(x => x.model === apiModel)) setApiModel(p.picks[0].model)
  }
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!cfg) return
    const body = kind === 'local'
      ? { kind: 'local', model: localModel || cfg.model, enabled: true }
      : kind === 'api'
        ? { kind: 'api', url: apiUrl, model: apiModel, enabled: true, api_key: key ? key : null }
        : { kind: cfg.kind, url: cfg.url, model: cfg.model, enabled: false }
    try {
      const r = await api<Corp>('/admin/settings/corporate-model', { method: 'PUT', body })
      apply(r); setKey('')
      toast(kind === 'off' ? 'Company AI is off. Unclear actions will be asked about.' : 'Saved. The next unclear action uses this model.')
      status.reload()
    } catch (err: any) { toast(err.message, true) }
  }
  const pull = async (model: string) => {
    try { await api('/admin/corporate-model/local/pull', { method: 'POST', body: { model } }); toast(`Downloading ${model}…`); local.reload() }
    catch (err: any) { toast(err.message, true) }
  }
  const run = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setOut(null)
    try {
      const input = t.tool === 'Bash' ? { command: t.command } : t.tool === 'WebFetch' ? { url: t.command } : { file_path: t.command }
      setOut(await api<JudgeOut>('/admin/judge/playground', { method: 'POST', body: { profile_id: t.profile_id, task: t.task, tool: t.tool, input, content: t.content || null } }))
    } catch (err: any) { toast(err.message, true) } finally { setBusy(false) }
  }
  const s = status.data
  const ld = local.data
  return (
    <div className="page">
      <div className="page-head"><div className="grow"><h1>Corporate judge</h1>
        <p>The company AI that decides unclear actions for profiles set to “Corporate judge” or “Local, then corporate”. Run a private model on this server, or use a cloud API.</p></div></div>
      <div className="grid2">
        <form className="panel" onSubmit={save}>
          <div className="panel-head"><h2>Where the AI runs</h2>
            {kind !== 'off' && cfg && (cfg.enabled ? cfg.kind : 'off') === kind && s ? (s.reachable
              ? <span className={`pill ${s.model_present ? 'allow' : 'ask'}`}>{s.model_present ? 'Ready' : kind === 'local' ? 'Model not downloaded' : 'Model not found'}</span>
              : <span className="pill block">Unreachable</span>) : null}</div>
          <div className="modes modes3" role="radiogroup" aria-label="Where the AI runs">
            {([['local', 'On this server', 'A private model in Docker. Nothing leaves your server.'],
               ['api', 'Cloud API', 'OpenRouter, OpenAI or any compatible API. Best quality per dollar.'],
               ['off', 'Off', 'No AI: unclear actions are asked about or blocked.']] as [Kind, string, string][]).map(([v, label, text]) => (
              <button type="button" key={v} className="mode" role="radio" aria-checked={kind === v} aria-pressed={kind === v} onClick={() => setKind(v)}>
                <b>{label}</b><span>{text}</span>
              </button>
            ))}
          </div>

          {kind === 'local' && (<>
            {ld && !ld.running && (
              <div className="al info" role="status"><span className="ic"><Icon name="warn" size={20} /></span><div>
                <h3>The model service isn’t running on this server</h3>
                <p>Start it once on the server: <code>./senti-server install --ai local</code>. It keeps your people, Macs and settings.</p>
              </div></div>
            )}
            {ld?.memory?.total_gb ? <p className="small muted">This server: {ld.memory.total_gb} GB memory, {ld.memory.available_gb} GB free right now. No GPU is needed, but answers take seconds on a CPU.</p> : null}
            {ld?.running && (<>
              <div className="field"><span>Downloaded models</span>
                {ld.models.length ? (
                  <div className="modelist" role="radiogroup" aria-label="Local model">
                    {ld.models.map(m => (
                      <label key={m.name} className="modelrow"><input type="radio" name="localmodel" checked={localModel === m.name} onChange={() => setLocalModel(m.name)} />
                        <span className="mono">{m.name}</span><span className="muted small">{m.size_gb} GB</span></label>
                    ))}
                  </div>
                ) : <p className="small muted">None yet. Download one below.</p>}
              </div>
              <div className="field"><span>Download a model</span>
                <div className="modelist">
                  {ld.recommended.map(r => {
                    const have = ld.models.some(m => m.name === r.model)
                    const tight = (ld.memory.available_gb ?? 99) < r.ram_gb
                    const busyThis = ld.pulling && !ld.pulling.done && ld.pulling.model === r.model
                    return (
                      <div key={r.model} className="modelrow">
                        <span className="mono">{r.model}</span>
                        <span className="small muted grow">{r.note}. Needs about {r.ram_gb} GB, {r.download_gb} GB download.{tight ? ' More than is free now.' : ''}</span>
                        {have ? <span className="pill allow">Downloaded</span>
                          : <button type="button" className="btn ghost sm" disabled={!!pulling} onClick={() => pull(r.model)}>{busyThis ? 'Downloading…' : 'Download'}</button>}
                      </div>
                    )
                  })}
                </div>
              </div>
              {ld.pulling && (
                <div className="small" role="status">
                  {ld.pulling.done
                    ? (ld.pulling.error ? <span className="pill block">Download failed</span> : <span className="pill allow">Downloaded {ld.pulling.model}</span>)
                    : <>Downloading {ld.pulling.model}: {ld.pulling.status}{ld.pulling.total ? ` ${Math.round(ld.pulling.completed / ld.pulling.total * 100)}%` : ''}</>}
                  {ld.pulling.total > 0 && !ld.pulling.done && <div className="bar"><i style={{ width: `${Math.round(ld.pulling.completed / ld.pulling.total * 100)}%` }} /></div>}
                  {ld.pulling.error && <p className="muted">{ld.pulling.error}</p>}
                </div>
              )}
            </>)}
          </>)}

          {kind === 'api' && (<>
            <div className="field"><span>Provider</span>
              <Seg label="Provider" value={provider} onChange={pickProvider} options={PROVIDERS.map(p => ({ v: p.id, label: p.name }))} />
            </div>
            <label className="field"><span>API address</span>
              <input className="mono" value={apiUrl} placeholder="https://…/v1" onChange={e => { setApiUrl(e.target.value); setProvider(providerOf(e.target.value)) }} />
              <span className="hint">Any OpenAI-compatible address (it ends in /v1), including your company’s own vLLM or LiteLLM.</span></label>
            <label className="field"><span>Model</span>
              <input className="mono" value={apiModel} onChange={e => setApiModel(e.target.value)} list="models" placeholder="provider/model" />
              <span className="hint">Choose a model without step-by-step “reasoning”: the judge answers in one short line.</span></label>
            <datalist id="models">{(s?.models ?? []).map(m => <option key={m} value={m} />)}</datalist>
            {(PROVIDERS.find(p => p.id === provider)?.picks.length ?? 0) > 0 && (
              <div className="modelist">
                {PROVIDERS.find(p => p.id === provider)!.picks.map(p => (
                  <label key={p.model} className="modelrow"><input type="radio" name="apimodel" checked={apiModel === p.model} onChange={() => setApiModel(p.model)} />
                    <span className="mono">{p.model}</span><span className="small muted grow">{p.note}</span><span className="small muted">{p.price}</span></label>
                ))}
                <p className="small muted">Prices per million tokens, in / out. One decision is about 1,000 tokens: well under a cent.</p>
              </div>
            )}
            <label className="field"><span>API key</span>
              <input type="password" autoComplete="off" placeholder={cfg?.api_key_set && cfg.kind === 'api' ? 'A key is saved; type to replace it' : PROVIDERS.find(p => p.id === provider)?.keyHint} value={key} onChange={e => setKey(e.target.value)} />
              <span className="hint">Stored on this server only. Scripts are sent with secrets removed.</span></label>
          </>)}

          {kind === 'off' && <p className="small muted">Macs still decide clear cases with their rules in milliseconds. Unclear actions are asked about in the agent, or blocked when nobody can answer. Generating server-gateway rules needs a model.</p>}

          <p className="small muted">This model also turns your server-gateway policy into rules (unless <code>SENTI_POLICY_MODEL_URL</code> is set).</p>
          <div className="row"><button className="btn primary" type="submit" disabled={kind === 'local' && !localModel}>Save</button>
            <button className="btn ghost" type="button" onClick={() => { status.reload(); local.reload() }}>Check connection</button></div>
          {s && !s.reachable && kind !== 'off' && cfg && (cfg.enabled ? cfg.kind : 'off') === kind && <p className="small muted">{s.error}</p>}
        </form>
        <form className="panel" onSubmit={run}>
          <h2>Try it</h2>
          <p className="small muted">Ask the corporate model about one action, with a profile’s company instructions.</p>
          <div className="grid2">
            <label className="field"><span>Profile</span><select value={t.profile_id} onChange={e => setT({ ...t, profile_id: e.target.value })}>{(profiles ?? []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
            <label className="field"><span>Kind of action</span><select value={t.tool} onChange={e => setT({ ...t, tool: e.target.value })}><option value="Bash">Shell command</option><option value="Read">Read a file</option><option value="Write">Write a file</option><option value="WebFetch">Open a website</option></select></label>
          </div>
          <label className="field"><span>The person’s task</span><input value={t.task} onChange={e => setT({ ...t, task: e.target.value })} /></label>
          <label className="field"><span>{t.tool === 'Bash' ? 'Command' : t.tool === 'WebFetch' ? 'URL' : 'Path'}</span><input className="mono" value={t.command} onChange={e => setT({ ...t, command: e.target.value })} /></label>
          <label className="field"><span>Script content (optional)</span><textarea className="mono" value={t.content} onChange={e => setT({ ...t, content: e.target.value })} placeholder="Paste a script to see how it is judged" /></label>
          <button className="btn primary" type="submit" disabled={busy}><Icon name="brain" size={16} />{busy ? 'Asking the model…' : 'Ask the corporate judge'}</button>
          {out && (
            <div className={`al ${out.verdict === 'block' ? 'block' : out.verdict === 'ask' ? 'ask' : 'ok'}`} role="status">
              <span className="ic"><Icon name={out.verdict === 'allow' ? 'check' : 'warn'} size={20} /></span>
              <div>
                <h3>{out.verdict === 'block' ? 'It would stop this' : out.verdict === 'ask' ? 'It would ask first' : 'It would allow this'}</h3>
                <p>{out.reason || 'No reason given.'}</p>
                <div className="meta">{out.model}, {out.ms} ms{Object.keys(out.p).length > 1 ? `, allow ${(out.p.allow * 100).toFixed(0)}%, ask ${(out.p.ask * 100).toFixed(0)}%, block ${(out.p.block * 100).toFixed(0)}%` : ''}</div>
              </div>
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
