import { Link } from 'react-router-dom'
import { ago, api, type Code, type Device, type Role } from '../api'
import { Icon, useLiveEvent, useLoad } from '../components/ui'

export default function Devices() {
  const devices = useLoad<Device[]>(() => api('/admin/devices'))
  const codes = useLoad<Code[]>(() => api('/admin/enrollment-codes'))
  const { data: roles } = useLoad<Role[]>(() => api('/admin/roles'))
  useLiveEvent(m => { if (m.type === 'device_enrolled') { devices.reload(); codes.reload() } })
  const revoke = async (d: Device) => {
    if (!confirm(`Revoke ${d.hostname}? It stops receiving profiles and its reports are refused.`)) return
    await api(`/admin/devices/${d.id}/revoke`, { method: 'POST' }); devices.reload()
  }
  return (
    <div className="page">
      <div className="page-head"><div className="grow"><h1>Devices</h1><p>Macs running the Senti engine for this organization. Each one keeps a signed copy of its profiles, so it stays protected even when it can’t reach this server.</p></div></div>
      <section className="panel">
        <h2>Enroll a Mac</h2>
        <p className="small muted">Macs join with a personal invite: add the person on <Link to="/people">People and roles</Link> and send them the invite link shown there. Each invite works once, on one Mac, and expires, so a leaked message can't let anyone else in.</p>
        <Link className="btn" to="/people"><Icon name="key" size={16} />Invite someone</Link>
        {(codes.data ?? []).length > 0 && (
          <div className="table-wrap" style={{ border: 'none' }}>
            <table>
              <thead><tr><th>Code</th><th>Role</th><th>Uses left</th><th>Expires</th><th /></tr></thead>
              <tbody>{(codes.data ?? []).map(c => (
                <tr key={c.code}><td><code>{c.code}</code></td><td>{roles?.find(r => r.id === c.role_id)?.name ?? c.role_id}</td><td>{c.uses_left}</td>
                  <td className="small">{c.expires_at ? new Date(c.expires_at * 1000).toLocaleDateString() : 'never'}</td>
                  <td><button className="btn ghost sm" onClick={async () => { await api(`/admin/enrollment-codes/${c.code}`, { method: 'DELETE' }); codes.reload() }}>Delete</button></td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Mac</th><th>Person</th><th>Status</th><th>Device key</th><th>Profiles</th><th>Decisions</th><th /></tr></thead>
          <tbody>
            {(devices.data ?? []).length === 0 && <tr><td colSpan={7}><div className="empty">No Macs enrolled yet. Invite someone from People and roles.</div></td></tr>}
            {(devices.data ?? []).map(d => (
              <tr key={d.id} style={d.revoked ? { opacity: .55 } : undefined}>
                <td><b>{d.hostname || 'Unnamed Mac'}</b><br /><span className="small muted">{d.platform}{d.engine_version ? `, engine ${d.engine_version}` : ''}</span></td>
                <td className="small">{d.user}</td>
                <td>{d.revoked ? <span className="pill block">Revoked</span> : d.online ? <span className="pill allow">Online</span> : <span className="pill quiet">Seen {ago(d.last_seen)}</span>}</td>
                <td className="small">{d.key_type === 'secure-enclave' ? <span className="pill allow" title="The key can't leave this Mac's Secure Enclave">Secure Enclave</span>
                  : d.key_type === 'software' ? <span className="pill quiet" title="This Mac has no Secure Enclave; the key is a file readable only by its user">Software key</span>
                  : <span className="pill block" title="Joined before device keys: its requests are refused until it joins again">None: join again</span>}
                  {(d.assistants?.unprotected ?? []).length > 0 && <><br /><span className="muted">Not yet protected: {d.assistants!.unprotected.join(', ')}</span></>}</td>
                <td className="small">{d.profiles_source ? `${d.profiles_source}, v${d.bundle_version}` : '–'}</td>
                <td className="small">{d.stats?.decisions ?? 0}<span className="muted"> ({d.stats?.block ?? 0} stopped)</span></td>
                <td>{!d.revoked && <button className="btn ghost sm" onClick={() => revoke(d)}>Revoke</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
