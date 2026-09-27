// Senti plugin for OpenCode: every tool call is checked by the local Senti engine before it runs.
// Installed by `senti install opencode`. Fails closed: if Senti can't be reached, the tool call is blocked.
// Senti shows a macOS dialog itself when it needs your decision (OpenCode has no native "ask" for plugins).
import { spawn } from "node:child_process"
import { appendFileSync } from "node:fs"
import { homedir } from "node:os"

const HOOK = "__SENTI_HOOK__"

function note(msg: string) {
  try { appendFileSync(`${homedir()}/.senti-opencode-plugin.log`, `${new Date().toISOString()} ${msg}\n`) } catch { /* ignore */ }
}

function senti(body: Record<string, unknown>, event: "pre" | "prompt" | "post"): Promise<any> {
  const failVerdict = event === "pre" ? "block" : "allow"
  return new Promise(resolve => {
    try {
      const p = spawn(HOOK, ["opencode", event], { stdio: ["pipe", "pipe", "ignore"], env: process.env })
      let out = ""
      p.stdout.on("data", (d: Buffer) => { out += d.toString() })
      p.on("error", (e: Error) => { note(`spawn error: ${e.message}`); resolve({ verdict: failVerdict, reason: `Senti: I couldn't check this action (${e.message}), so I'm not letting it run.` }) })
      p.on("close", () => {
        try { resolve(out.trim() ? JSON.parse(out) : { verdict: failVerdict, reason: "Senti: empty reply" }) }
        catch (e) { note(`bad reply: ${out.slice(0, 200)}`); resolve({ verdict: failVerdict, reason: "Senti: unreadable reply" }) }
      })
      p.stdin.end(JSON.stringify({ ...body, event }))
    } catch (e) {
      note(`error: ${e}`)
      resolve({ verdict: failVerdict, reason: `Senti: I couldn't check this action (${e}), so I'm not letting it run.` })
    }
  })
}

export const SentiPlugin = async ({ directory, worktree }: any) => {
  const cwd = worktree || directory
  note(`loaded for ${cwd}`)
  return {
    "chat.message": async (input: any, output: any) => {
      const text = (output?.parts ?? []).filter((p: any) => p.type === "text").map((p: any) => p.text).join("\n")
      if (text) await senti({ sessionID: input?.sessionID, prompt: text, cwd }, "prompt")
    },
    "tool.execute.before": async (input: any, output: any) => {
      const r = await senti({ tool: input.tool, args: output.args, sessionID: input.sessionID, cwd }, "pre")
      if (r.verdict !== "allow") throw new Error(r.reason || "Senti: I stopped this.")
      if (r.updatedInput && typeof r.updatedInput === "object") Object.assign(output.args, r.updatedInput)
    },
    "tool.execute.after": async (input: any, output: any) => {
      const r = await senti({ tool: input.tool, args: input.args, sessionID: input.sessionID, cwd, output: output?.output }, "post")
      if (r.context && typeof output?.output === "string") output.output = `${output.output}\n\n${r.context}`
    },
  }
}
