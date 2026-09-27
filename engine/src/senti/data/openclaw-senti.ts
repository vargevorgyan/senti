// Senti plugin for OpenClaw: every tool call is checked by the local Senti engine before it runs (before_tool_call).
// Installed by `senti install openclaw`. Fails closed: if Senti can't be reached the call is blocked
// (and OpenClaw itself blocks when this handler throws or times out).
import { spawn } from "node:child_process"

const HOOK = "__SENTI_HOOK__"

function senti(body: Record<string, unknown>, event: "pre" | "post"): Promise<any> {
  const fail = { verdict: event === "pre" ? "block" : "allow", reason: "Senti: I couldn't check this action, so I'm not letting it run." }
  return new Promise(resolve => {
    try {
      const p = spawn(HOOK, ["openclaw", event], { stdio: ["pipe", "pipe", "ignore"], env: process.env })
      let out = ""
      p.stdout.on("data", (d: Buffer) => { out += d.toString() })
      p.on("error", () => resolve(fail))
      p.on("close", () => { try { resolve(out.trim() ? JSON.parse(out) : fail) } catch { resolve(fail) } })
      p.stdin.end(JSON.stringify({ ...body, event }))
    } catch { resolve(fail) }
  })
}

export default {
  id: "senti",
  name: "Senti",
  description: "Checks every tool call with the local Senti engine before it runs.",
  register(api: any) {
    api.on("before_tool_call", async (event: any, ctx: any) => {
      const r = await senti({ tool: event.toolName, args: event.params ?? {}, sessionID: ctx?.sessionId ?? ctx?.sessionKey ?? "",
                              cwd: event.params?.workdir ?? process.cwd() }, "pre")
      if (r.verdict === "block") return { block: true, blockReason: r.reason || "Senti: I stopped this." }
      if (r.verdict === "ask") {
        return { requireApproval: { title: "Senti: should I let this through?", description: r.reason, severity: "warning",
                                    timeoutMs: 240000 } }
      }
      if (r.verdict !== "allow") return { block: true, blockReason: r.reason || "Senti: unexpected answer" }
      if (r.updatedInput && typeof r.updatedInput === "object") return { params: { ...(event.params ?? {}), ...r.updatedInput } }
      return undefined
    }, { timeoutMs: 300000 })
    api.on("after_tool_call", async (event: any, ctx: any) => {
      await senti({ tool: event.toolName, args: event.params ?? {}, sessionID: ctx?.sessionId ?? "", output: event.result }, "post")
      return undefined
    })
  },
}
