import { useState } from 'react'
import { agentName, ago, api, type Approval } from '../api'
import { VerdictPill, useLiveEvent, useLoad, useToast } from '../components/ui'

export default function Approvals() {
  const { data, reload, error } = useLoad<Approval[]>(() => api('/admin/approvals'))
  const toast = useToast()
  const [busy, setBusy] = useState('')
  useLiveEvent(m => { if (m.type === 'approval') reload() })
  const decide = async (a: Approval, decision: 'approve' | 'deny') => {
    setBusy(a.id)
    try {
      await api(`/admin/approvals/${a.id}/decide`, { method: 'POST', body: { decision } })
      toast(decision === 'approve' ? `Allowed once for ${agentName(a.agent)}.` : `Blocked. ${agentName(a.agent)} was told no.`)
      reload()
    } catch (e: any) { toast(e.message, true) } finally { setBusy('') }
  }
  const pending = (data ?? []).filter(a => a.status === 'pending')
  const done = (data ?? []).filter(a => a.status !== 'pending')
  return (
    <div className="page">
      <div className="page-head"><div className="grow"><h1>Approvals</h1>
        <p>When a profile sends questions to the owner instead of the person at the keyboard, they land here. The agent waits for your answer; if nobody answers in time, I block it.</p></div></div>
      {error && <div className="al info"><p>{error}</p></div>}
      {pending.length === 0 ? (
        <div className="al ok"><p>Nothing is waiting for you.</p></div>
      ) : (
        <div className="grid2">
          {pending.map(a => (
            <div className="pop" role="alertdialog" aria-labelledby={`ap-${a.id}`} key={a.id}>
              <div className="hd">
                <img src={`${import.meta.env.BASE_URL}senti-app-icon.svg`} alt="Senti" />
                <div><div className="who">Senti · {agentName(a.agent)} on {a.hostname || 'a Mac'} ({a.user}) · {ago(a.created_at)}</div>
                  <h2 id={`ap-${a.id}`}>Should I let this through?</h2></div>
              </div>
              <p>{a.summary}</p>
              <pre>{a.input.command ?? a.input.file_path ?? a.input.url ?? JSON.stringify(a.input, null, 1)}</pre>
              <div className="rule">Profile: {a.profile_id || '–'}{a.rule ? `, rule: ${a.rule.replaceAll('_', ' ')}` : ''}. Folder: {a.cwd}</div>
              <div className="btns">
                <button className="btn primary" disabled={busy === a.id} onClick={() => decide(a, 'deny')}>Block</button>
                <button className="btn" disabled={busy === a.id} onClick={() => decide(a, 'approve')}>Allow once</button>
              </div>
            </div>
          ))}
        </div>
      )}
      <section className="panel">
        <h3>Answered</h3>
        {done.length === 0 ? <p className="muted small">Answered and expired requests are listed here.</p> : (
          <div className="table-wrap" style={{ border: 'none' }}>
            <table>
              <thead><tr><th>Asked</th><th>Agent</th><th>Request</th><th>Answer</th><th>By</th></tr></thead>
              <tbody>{done.map(a => (
                <tr key={a.id}>
                  <td className="small muted">{ago(a.created_at)}</td><td>{agentName(a.agent)}<br /><span className="small muted">{a.user}</span></td>
                  <td style={{ maxWidth: 420 }}>{a.summary}</td>
                  <td><VerdictPill v={a.status === 'approved' ? 'allow' : 'block'} />{a.status === 'expired' && <span className="small muted"> expired</span>}</td>
                  <td className="small">{a.decided_by}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
