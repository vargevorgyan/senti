import { useEffect, useState } from 'react'
import { api, type JudgeOut, type Profile } from '../api'
import { Icon, useLoad, useToast } from '../components/ui'

interface Corp { url: string; model: string; enabled: boolean; api_key_set: boolean }

export default function Judge() {
  const toast = useToast()
  const { data: profiles } = useLoad<Profile[]>(() => api('/admin/profiles'))
  const status = useLoad<{ reachable: boolean; models?: string[]; model_present?: boolean; error?: string }>(() => api('/admin/corporate-model/status'))
  const [cfg, setCfg] = useState<Corp | null>(null)
  const [key, setKey] = useState('')
  const [t, setT] = useState({ profile_id: 'developer', task: 'Fix the failing signup test', tool: 'Bash', command: 'psql -h billing.prod.corp.internal -c "select * from customers"', content: '' })
  const [out, setOut] = useState<JudgeOut | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api<Corp>('/admin/settings/corporate-model').then(setCfg) }, [])
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!cfg) return
    try {
      const r = await api<Corp>('/admin/settings/corporate-model', { method: 'PUT', body: { url: cfg.url, model: cfg.model, enabled: cfg.enabled, api_key: key ? key : null } })
      setCfg(r); setKey(''); toast('Saved. The next unclear action uses this model.'); status.reload()
    } catch (err: any) { toast(err.message, true) }
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
  return (
    <div className="page">
      <div className="page-head"><div className="grow"><h1>Corporate judge</h1>
        <p>The company model that decides unclear actions for profiles set to “Corporate judge” or “Local, then corporate”. Any OpenAI-compatible endpoint works: the bundled Ollama, vLLM, or a hosted model.</p></div></div>
      <div className="grid2">
        <form className="panel" onSubmit={save}>
          <div className="panel-head"><h2>Model</h2>
            {s ? (s.reachable ? <span className={`pill ${s.model_present ? 'allow' : 'ask'}`}>{s.model_present ? 'Ready' : 'Model not pulled yet'}</span> : <span className="pill block">Unreachable</span>) : null}</div>
          {s && !s.reachable && <p className="small muted">{s.error}</p>}
          {cfg && <>
            <label className="field"><span>Endpoint</span><input className="mono" value={cfg.url} onChange={e => setCfg({ ...cfg, url: e.target.value })} /></label>
            <label className="field"><span>Model</span><input className="mono" value={cfg.model} onChange={e => setCfg({ ...cfg, model: e.target.value })} list="models" /></label>
            <datalist id="models">{(s?.models ?? []).map(m => <option key={m} value={m} />)}</datalist>
            <label className="field"><span>API key</span><input type="password" placeholder={cfg.api_key_set ? 'A key is saved; type to replace it' : 'Not needed for Ollama'} value={key} onChange={e => setKey(e.target.value)} /></label>
            <label className="toggle"><input type="checkbox" checked={cfg.enabled} onChange={e => setCfg({ ...cfg, enabled: e.target.checked })} /><span>Use the corporate judge. When off, Macs fall back to their local judge.</span></label>
            <div className="row"><button className="btn primary" type="submit">Save</button><button className="btn ghost" type="button" onClick={status.reload}>Check connection</button></div>
          </>}
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
