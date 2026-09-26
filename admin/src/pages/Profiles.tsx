import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { agentName, ago, api, type Profile, type Role } from '../api'
import { Icon, useLoad, useToast } from '../components/ui'

export const MODE_LABEL: Record<string, string> = {
  local: 'Local judge', corporate: 'Corporate judge', local_then_corporate: 'Local, then corporate', none: 'No AI judge',
}
const OTHER: Record<string, string> = { allow: 'allowed', ask: 'asks first', block: 'blocked', judge: 'judged by AI' }

export default function Profiles() {
  const { data } = useLoad<Profile[]>(() => api('/admin/profiles'))
  const { data: roles } = useLoad<Role[]>(() => api('/admin/roles'))
  const nav = useNavigate()
  const toast = useToast()
  const [name, setName] = useState('')
  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const p = await api<Profile>('/admin/profiles', { method: 'POST', body: { name } })
      nav(`/profiles/${p.id}`)
    } catch (err: any) { toast(err.message, true) }
  }
  const roleName = (id: string) => roles?.find(r => r.id === id)?.name ?? id
  return (
    <div className="page">
      <div className="page-head">
        <div className="grow"><h1>Profiles</h1>
          <p>A profile is what an agent may do on someone’s behalf: files, websites, shell commands, packages, and who decides the unclear cases. Each role gets a profile; agents never get more than their person.</p></div>
      </div>
      <div className="plist">
        {(data ?? []).map(p => {
          const r = p.data.rules
          return (
            <Link to={`/profiles/${p.id}`} className="pcard" key={p.id}>
              <div className="row" style={{ justifyContent: 'space-between' }}><h2>{p.name}</h2><span className="pill neutral">{MODE_LABEL[p.data.judge.mode]}</span></div>
              <p className="small muted">{p.description}</p>
              <div className="rules">
                <span>For {p.data.applies_to.roles?.length ? p.data.applies_to.roles.map(roleName).join(', ') : 'every role'}; agents: {p.data.applies_to.agents?.length ? p.data.applies_to.agents.map(agentName).join(', ') : 'all'}</span>
                <span>Unknown websites: {OTHER[r.network.otherwise]}. Unclear commands: {OTHER[r.shell.otherwise]}.</span>
                <span>{r.files.deny.length} protected paths, {r.network.allow.length} allowed sites{Object.keys(p.data.agent_overrides ?? {}).length ? `, stricter limits for ${Object.keys(p.data.agent_overrides).map(agentName).join(', ')}` : ''}.</span>
              </div>
              <span className="small muted">Version {p.version}, changed {ago(p.updated_at)} by {p.updated_by}</span>
            </Link>
          )
        })}
        <form className="pcard" onSubmit={create} style={{ borderStyle: 'dashed', justifyContent: 'center' }}>
          <h3>New profile</h3>
          <label className="field"><span>Name</span><input value={name} onChange={e => setName(e.target.value)} placeholder="Contractors" required /></label>
          <button className="btn" type="submit"><Icon name="plus" size={16} />Create profile</button>
        </form>
      </div>
    </div>
  )
}
