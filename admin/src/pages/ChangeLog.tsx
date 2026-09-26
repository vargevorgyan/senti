import { api, type Change } from '../api'
import { useLiveEvent, useLoad } from '../components/ui'

const LABEL: Record<string, string> = {
  'profile.create': 'created profile', 'profile.update': 'changed profile', 'profile.delete': 'deleted profile', 'profile.duplicate': 'duplicated a profile as',
  'role.create': 'created role', 'role.update': 'changed role', 'role.delete': 'deleted role', 'user.create': 'added', 'user.update': 'changed', 'user.delete': 'removed',
  'device.revoke': 'revoked device', 'enrollment_code.create': 'created enrollment code', 'approval.approved': 'allowed request', 'approval.denied': 'blocked request',
  'settings.corporate_model': 'set the corporate model to',
}

export default function ChangeLog() {
  const { data, reload } = useLoad<Change[]>(() => api('/admin/changelog?limit=200'))
  useLiveEvent(m => { if (m.type === 'change' || m.type === 'approval') reload() })
  return (
    <div className="page">
      <div className="page-head"><div className="grow"><h1>Change log</h1><p>Who changed what in this organization. Profile changes reach every enrolled Mac within seconds.</p></div></div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>When</th><th>Who</th><th>What</th><th>Details</th></tr></thead>
          <tbody>
            {(data ?? []).length === 0 && <tr><td colSpan={4}><div className="empty">No changes yet.</div></td></tr>}
            {(data ?? []).map(c => (
              <tr key={c.id}>
                <td className="small muted" style={{ whiteSpace: 'nowrap' }}>{new Date(c.ts * 1000).toLocaleString()}</td>
                <td className="small">{c.actor}</td>
                <td>{LABEL[c.action] ?? c.action} <b>{c.target}</b></td>
                <td className="small muted"><code style={{ fontSize: 12 }}>{Object.keys(c.detail ?? {}).length ? JSON.stringify(c.detail) : ''}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
