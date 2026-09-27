import { Fragment, useState } from 'react'
import { AGENTS, agentName, ago, api, type NewInvite, type Profile, type Role, type User } from '../api'
import { Icon, useLiveEvent, useLoad, useToast } from '../components/ui'

export default function People() {
  const users = useLoad<User[]>(() => api('/admin/users'))
  const roles = useLoad<Role[]>(() => api('/admin/roles'))
  const { data: profiles } = useLoad<Profile[]>(() => api('/admin/profiles'))
  const toast = useToast()
  const [nu, setNu] = useState({ email: '', role_id: 'engineering' })
  const [nr, setNr] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const [shown, setShown] = useState<{ user: User; invite: NewInvite } | null>(null)
  const { data: tls } = useLoad<{ enabled: boolean; https_port: number }>(() => api('/admin/tls'))
  const backend = tls?.enabled ? `https://${window.location.hostname}:${tls.https_port}` : `${window.location.protocol}//${window.location.host}`
  useLiveEvent(m => { if (m.type === 'device_enrolled') users.reload() })
  const copy = (t: string) => navigator.clipboard.writeText(t).then(() => toast('Copied. Send it to them privately.'))
  const invite = async (u: User) => {
    if (u.invite?.status === 'pending' && !confirm(`${u.email} already has an unused invite. Replace it? The old key stops working.`)) return
    try {
      const inv = await api<NewInvite>(`/admin/users/${u.id}/invites`, { method: 'POST', body: { backend } })
      setShown({ user: u, invite: inv }); users.reload()
    } catch (e: any) { toast(e.message, true) }
  }
  const revokeInvite = async (id: string) => { await api(`/admin/invites/${id}`, { method: 'DELETE' }); setShown(null); users.reload(); toast('Invite revoked.') }
  const access = (u: User) => {
    const i = u.invite
    if (!i) return u.devices ? `${u.devices} Mac${u.devices > 1 ? 's' : ''}` : 'Not invited'
    if (i.status === 'pending') return `Invite sent, expires ${new Date(i.expires_at * 1000).toLocaleString()}`
    if (i.status === 'used') return `Joined from ${i.used_hostname || 'a Mac'} ${ago(i.used_at)}`
    return i.status === 'expired' ? 'Invite expired' : 'Invite revoked'
  }
  const profileName = (id: string) => profiles?.find(p => p.id === id)?.name ?? id
  const summary = (u: User) => {
    const o = Object.entries(u.agent_profiles ?? {}).filter(([, v]) => v)
    return o.length ? o.map(([a, pid]) => `${agentName(a)} → ${profileName(pid)}`).join(', ') : 'Every agent uses the role’s profile'
  }

  const saveUser = async (u: User, patch: Partial<User>) => {
    try {
      await api(`/admin/users/${u.id}`, { method: 'PUT', body: { ...u, ...patch } })
      toast(`Updated ${u.email}. Their Macs get the change within seconds.`)
      users.reload()
    } catch (e: any) { toast(e.message, true) }
  }
  const addUser = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const u = await api<User>('/admin/users', { method: 'POST', body: nu })
      setNu({ ...nu, email: '' }); roles.reload(); await invite(u)
    } catch (err: any) { toast(err.message, true) }
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
          <thead><tr><th>Person</th><th>Role</th><th>Agent profiles</th><th>Mac access</th><th /></tr></thead>
          <tbody>
            {(users.data ?? []).length === 0 && <tr><td colSpan={5}><div className="empty">No people yet. Add someone below and send them their invite.</div></td></tr>}
            {(users.data ?? []).map(u => (
              <Fragment key={u.id}>
                <tr>
                  <td><b>{u.name || u.email}</b><br /><span className="small muted">{u.email}</span></td>
                  <td style={{ minWidth: 170 }}><select aria-label={`Role for ${u.email}`} value={u.role_id} onChange={e => saveUser(u, { role_id: e.target.value })}>{(roles.data ?? []).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></td>
                  <td className="small" style={{ maxWidth: 420 }}>{summary(u)}</td>
                  <td className="small"><span className={`dot${u.online ? ' on' : ''}`} /> {access(u)}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button className="btn sm" onClick={() => invite(u)}><Icon name="key" size={16} />{u.invite ? 'New invite' : 'Invite'}</button>
                    <button className="btn sm" onClick={() => setOpen(open === u.id ? null : u.id)} aria-expanded={open === u.id}>{open === u.id ? 'Done' : 'Edit agents'}</button>
                    <button className="btn ghost sm" onClick={() => removeUser(u)}>Remove</button>
                  </td>
                </tr>
                {open === u.id && (
                  <tr className="expanded"><td colSpan={5}>
                    <p className="small muted" style={{ marginBottom: 12 }}>Pick a different profile for one of {u.name || u.email}’s agents. “From role” keeps the role’s profile.</p>
                    <div className="grid3">
                      {AGENTS.map(a => (
                        <label className="field" key={a.id}><span>{a.name}</span>
                          <select value={u.agent_profiles[a.id] ?? ''} onChange={e => saveUser(u, { agent_profiles: { ...u.agent_profiles, [a.id]: e.target.value } })}>
                            <option value="">From role</option>{(profiles ?? []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                          </select>
                        </label>
                      ))}
                    </div>
                  </td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <form className="row" onSubmit={addUser}>
        <input type="email" required placeholder="name@company.com" value={nu.email} onChange={e => setNu({ ...nu, email: e.target.value })} style={{ maxWidth: 320 }} aria-label="Email" />
        <select value={nu.role_id} onChange={e => setNu({ ...nu, role_id: e.target.value })} style={{ maxWidth: 220 }} aria-label="Role">{(roles.data ?? []).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
        <button className="btn" type="submit"><Icon name="plus" size={16} />Add person and invite</button>
      </form>
      {shown && (
        <section className="panel" aria-live="polite">
          <h2>Invite for {shown.user.name || shown.user.email}</h2>
          <p className="small muted">Send this command to {shown.user.email} privately. It is shown only now, works once on one Mac, and expires {new Date(shown.invite.expires_at * 1000).toLocaleString()}. If they report that it was already used, revoke their Mac on the Devices page and send a new invite.</p>
          <div className="copy"><pre className="mono">{shown.invite.command}</pre><button className="btn" onClick={() => copy(shown.invite.command)}><Icon name="copy" size={16} />Copy</button></div>
          <div className="row"><button className="btn ghost sm" onClick={() => revokeInvite(shown.invite.id)}>Revoke this invite</button><button className="btn ghost sm" onClick={() => setShown(null)}>Done</button></div>
        </section>
      )}

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
