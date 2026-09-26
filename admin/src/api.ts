// Thin client for the Senti org backend admin API.
export type Verdict = 'allow' | 'ask' | 'block'

export interface EventRow {
  id: string; ts: number; device_id: string; hostname: string; user: string; agent: string; event: string; tool: string
  verdict: Verdict | null; layer: string; rule: string; severity: string; reason: string; profile: string; session: string
  task: string; cwd: string; input: Record<string, string>; ms: number
}
export interface Overview {
  org: string; devices: { total: number; online: number }; users: number; profiles: number; events_24h: number
  by_verdict: Record<Verdict, number>; by_agent: Record<string, number>; by_layer: Record<string, number>; llm_share: number
  latency_ms: { p50: number; p95: number }; top_rules: [string, number][]; timeline: { start: number; hours: number[]; blocks: number[] }
  pending_approvals: number; recent_blocks: EventRow[]
}
export type Otherwise = 'allow' | 'ask' | 'block' | 'judge'
export interface ProfileData {
  applies_to: { roles: string[]; agents: string[] }
  rules: {
    files: { allow: string[]; deny: string[]; ask: string[]; write?: 'allow' | 'ask' | 'block' | null; outside_allow?: 'ask' | 'block' | 'allow' | null }
    network: { allow: string[]; deny: string[]; otherwise: Otherwise }
    shell: { allow: string[]; deny: string[]; ask: string[]; otherwise: Otherwise }
    mcp: { allow: string[]; deny: string[]; otherwise: Otherwise }
    packages: 'check_supply_chain' | 'allow' | 'ask' | 'block'
  }
  judge: { mode: 'local' | 'corporate' | 'local_then_corporate' | 'none'; instructions: string; send_to_corporate: 'metadata_only' | 'with_redacted_content' | 'full' }
  on_backend_unreachable: 'strict_local' | 'cached'
  approvals: { ask_goes_to: string }
  features: Record<string, boolean>
  agent_overrides: Record<string, any>
}
export interface Profile { id: string; name: string; description: string; priority: number; version: number; data: ProfileData; updated_at: number; updated_by: string }
export interface Role { id: string; name: string; description: string; users: number }
export interface User { id: number; email: string; name: string; role_id: string; agent_profiles: Record<string, string>; devices: number; online: boolean; created_at: number }
export interface Device {
  id: string; user: string; hostname: string; platform: string; enrolled_at: number; last_seen: number; online: boolean; revoked: boolean
  engine_version?: string; local_judge?: string; profiles_source?: string; bundle_version?: number; stats: Record<string, number>
}
export interface Approval {
  id: string; device_id: string; hostname: string; user: string; agent: string; tool: string; summary: string; input: Record<string, string>
  cwd: string; profile_id: string; rule: string; status: 'pending' | 'approved' | 'denied' | 'expired'; created_at: number; decided_at: number; decided_by: string; note: string
}
export interface Code { code: string; role_id: string; uses_left: number; expires_at: number; note: string; created_at?: number }
export interface Change { id: number; ts: number; actor: string; action: string; target: string; detail: Record<string, unknown> }
export interface JudgeOut { verdict: Verdict; reason: string; p: Record<string, number>; model: string; ms: number }

const KEY = 'senti.token'
export const token = { get: () => localStorage.getItem(KEY) ?? '', set: (t: string) => localStorage.setItem(KEY, t), clear: () => localStorage.removeItem(KEY) }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method: opts.method ?? 'GET',
    headers: { 'Content-Type': 'application/json', ...(token.get() ? { Authorization: `Bearer ${token.get()}` } : {}) },
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  })
  if (res.status === 401 && !path.startsWith('/auth/login')) {
    token.clear()
    window.dispatchEvent(new Event('senti:logout'))
  }
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: any) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ') : msg
    } catch { /* not JSON */ }
    throw new ApiError(res.status, msg)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const AGENTS = [
  { id: 'claude', name: 'Claude Code' },
  { id: 'codex', name: 'Codex' },
  { id: 'opencode', name: 'OpenCode' },
]
export const agentName = (id: string) => AGENTS.find(a => a.id === id)?.name ?? (id === 'generic' ? 'Other agents' : id || 'Agent')

export function ago(ts: number): string {
  if (!ts) return 'never'
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return new Date(ts * 1000).toLocaleDateString()
}
export const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
export const what = (inp: Record<string, string> = {}) => inp.command ?? inp.file_path ?? inp.filePath ?? inp.url ?? inp.path ?? inp.pattern ?? Object.values(inp)[0] ?? ''
