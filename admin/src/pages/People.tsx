import { useState } from 'react'
import { AGENTS, api, type Profile, type Role, type User } from '../api'
import { Icon, useLoad, useToast } from '../components/ui'

export default function People() {
  const users = useLoad<User[]>(() => api('/admin/users'))
  const roles = useLoad<Role[]>(() => api('/admin/roles'))
  const { data: profiles } = useLoad<Profile[]>(() => api('/admin/profiles'))
  const toast = useToast()
  const [nu, setNu] = useState({ email: '', role_id: 'engineering' })
  const [nr, setNr] = useState('')

  const saveUser = async (u: User, patch: Partial<User>) => {
    try {
      await api(`/admin/users/${u.id}`, { method: 'PUT', body: { ...u, ...patch } })
      toast(`Updated ${u.email}. Their Macs get the change within seconds.`)
      users.reload()
    } catch (e: any) { toast(e.message, true) }
  }
  const addUser = async (e: React.FormEvent) => {
    e.preventDefault()
    try { await api('/admin/users', { method: 'POST', body: nu }); setNu({ ...nu, email: '' }); users.reload(); roles.reload(); toast('Person added.') } catch (err: any) { toast(err.message, true) }
  }
  const removeUser = async (u: User) => {
    if (!confirm(`Remove ${u.email}? Their Macs are revoked and stop receiving profiles.`)) return
    await api(`/admin/users/${u.id}`, { method: 'DELETE' }); users.reload(); toast('Removed.')
  }
  const addRole = async (e: React.FormEvent) => {
    e.preventDefault()
    try { await api('/admin/roles', { method: 'POST', body: { name: nr } }); setNr(''); roles.reload() } catch (err: any) { toast(err.message, true) }
  }
  const delRole = async (r: Role) => { try { await api(`/admin/roles/${r.id}`, { method: 'DELETE' }); roles.reload() } catch (e: any) { toast(e.message, true) } }

  return (
    <div className="page">
      <div className="page-head"><div className="grow"><h1>People and roles</h1>
        <p>Each person has a role, and the role decides their agents’ profile. To make one person’s agent stricter, pick a different profile for that agent here.</p></div></div>

      <div className="table-wrap">
        <table>
          <thead><tr><th>Person</th><th>Role</th>{AGENTS.map(a => <th key={a.id}>{a.name}</th>)}<th>Macs</th><th /></tr></thead>
          <tbody>
            {(users.data ?? []).length === 0 && <tr><td colSpan={7}><div className="empty">No people yet. They appear here when they enroll a Mac, or add them below.</div></td></tr>}
            {(users.data ?? []).map(u => (
              <tr key={u.id}>
                <td><b>{u.name || u.email}</b><br /><span className="small muted">{u.email}</span></td>
                <td><select aria-label={`Role for ${u.email}`} value={u.role_id} onChange={e => saveUser(u, { role_id: e.target.value })}>{(roles.data ?? []).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></td>
                {AGENTS.map(a => (
                  <td key={a.id}>
                    <select aria-label={`${a.name} profile for ${u.email}`} value={u.agent_profiles[a.id] ?? ''} onChange={e => saveUser(u, { agent_profiles: { ...u.agent_profiles, [a.id]: e.target.value } })}>
                      <option value="">From role</option>{(profiles ?? []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  </td>
                ))}
                <td><span className={`dot${u.online ? ' on' : ''}`} /> {u.devices}</td>
                <td><button className="btn ghost sm" onClick={() => removeUser(u)}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="row" onSubmit={addUser}>
        <input type="email" required placeholder="name@company.com" value={nu.email} onChange={e => setNu({ ...nu, email: e.target.value })} style={{ maxWidth: 320 }} aria-label="Email" />
        <select value={nu.role_id} onChange={e => setNu({ ...nu, role_id: e.target.value })} style={{ maxWidth: 220 }} aria-label="Role">{(roles.data ?? []).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
        <button className="btn" type="submit"><Icon name="plus" size={16} />Add person</button>
      </form>

      <section className="panel">
        <h2>Roles</h2>
        <div className="table-wrap" style={{ border: 'none' }}>
          <table>
            <thead><tr><th>Role</th><th>Description</th><th>People</th><th /></tr></thead>
            <tbody>{(roles.data ?? []).map(r => (
              <tr key={r.id}><td><b>{r.name}</b><br /><span className="small muted">{r.id}</span></td><td className="small">{r.description}</td><td>{r.users}</td>
                <td><button className="btn ghost sm" onClick={() => delRole(r)} disabled={r.users > 0} title={r.users ? 'Move its people to another role first' : ''}>Delete</button></td></tr>
            ))}</tbody>
          </table>
        </div>
        <form className="row" onSubmit={addRole}>
          <input placeholder="Role name, for example Design" value={nr} onChange={e => setNr(e.target.value)} required style={{ maxWidth: 320 }} aria-label="New role name" />
          <button className="btn" type="submit"><Icon name="plus" size={16} />Add role</button>
        </form>
      </section>
    </div>
  )
}
