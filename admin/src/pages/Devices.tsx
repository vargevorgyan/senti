import { useState } from 'react'
import { ago, api, type Code, type Device, type Role } from '../api'
import { Icon, useLiveEvent, useLoad, useToast } from '../components/ui'

export default function Devices() {
  const devices = useLoad<Device[]>(() => api('/admin/devices'))
  const codes = useLoad<Code[]>(() => api('/admin/enrollment-codes'))
  const { data: roles } = useLoad<Role[]>(() => api('/admin/roles'))
  const toast = useToast()
  const [role, setRole] = useState('engineering')
  useLiveEvent(m => { if (m.type === 'device_enrolled') { devices.reload(); codes.reload() } })
  const backend = `${window.location.protocol}//${window.location.hostname}:8000`
  const code = codes.data?.[0]?.code ?? 'SENTI-DEMO'
  const cmd = `senti enroll --backend ${backend} --code ${code} --email you@company.com`
  const copy = (t: string) => navigator.clipboard.writeText(t).then(() => toast('Copied.'))
  const newCode = async () => { await api('/admin/enrollment-codes', { method: 'POST', body: { role_id: role, uses: 10, days: 7 } }); codes.reload(); toast('New code created. It works 10 times within 7 days.') }
  const revoke = async (d: Device) => {
    if (!confirm(`Revoke ${d.hostname}? It stops receiving profiles and its reports are refused.`)) return
    await api(`/admin/devices/${d.id}/revoke`, { method: 'POST' }); devices.reload()
  }
  return (
    <div className="page">
      <div className="page-head"><div className="grow"><h1>Devices</h1><p>Macs running the Senti engine for this organization. Each one keeps a signed copy of its profiles, so it stays protected even when it can’t reach this server.</p></div></div>
      <section className="panel">
        <h2>Enroll a Mac</h2>
        <p className="small muted">On the Mac, install the engine and run this command. The person’s role comes from the code.</p>
        <div className="copy"><pre className="mono">{cmd}</pre><button className="btn" onClick={() => copy(cmd)}><Icon name="copy" size={16} />Copy</button></div>
        <div className="row">
          <select value={role} onChange={e => setRole(e.target.value)} style={{ maxWidth: 220 }} aria-label="Role for new code">{(roles ?? []).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
          <button className="btn" onClick={newCode}><Icon name="key" size={16} />New enrollment code</button>
        </div>
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
          <thead><tr><th>Mac</th><th>Person</th><th>Status</th><th>Local judge</th><th>Profiles</th><th>Decisions</th><th /></tr></thead>
          <tbody>
            {(devices.data ?? []).length === 0 && <tr><td colSpan={7}><div className="empty">No Macs enrolled yet. Run the command above on a Mac.</div></td></tr>}
            {(devices.data ?? []).map(d => (
              <tr key={d.id} style={d.revoked ? { opacity: .55 } : undefined}>
                <td><b>{d.hostname || 'Unnamed Mac'}</b><br /><span className="small muted">{d.platform}{d.engine_version ? `, engine ${d.engine_version}` : ''}</span></td>
                <td className="small">{d.user}</td>
                <td>{d.revoked ? <span className="pill block">Revoked</span> : d.online ? <span className="pill allow">Online</span> : <span className="pill quiet">Seen {ago(d.last_seen)}</span>}</td>
                <td className="small">{d.local_judge ?? '–'}</td>
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
