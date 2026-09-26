// Senti plugin for OpenCode: every tool call is checked by the local Senti engine before it runs.
// Installed by `senti install opencode`. Fails closed: if Senti can't be reached, the tool call is blocked.
// Senti shows a macOS dialog itself when it needs your decision (OpenCode has no native "ask" for plugins).
import type { Plugin } from "@opencode-ai/plugin"

const HOOK = "__SENTI_HOOK__"

async function senti(body: Record<string, unknown>, event: "pre" | "prompt" | "post"): Promise<any> {
  try {
    const proc = Bun.spawn([HOOK, "opencode", event], { stdin: "pipe", stdout: "pipe", stderr: "ignore" })
    proc.stdin.write(JSON.stringify({ ...body, event }))
    proc.stdin.end()
    const out = await new Response(proc.stdout).text()
    await proc.exited
    return out.trim() ? JSON.parse(out) : { verdict: event === "pre" ? "block" : "allow", reason: "Senti: empty reply" }
  } catch (e) {
    return { verdict: event === "pre" ? "block" : "allow", reason: `Senti: I couldn't check this action (${e}), so I'm not letting it run.` }
  }
}

export const SentiPlugin: Plugin = async ({ directory, worktree }) => {
  const cwd = worktree || directory
  return {
    "chat.message": async (input: any, output: any) => {
      const text = (output?.parts ?? []).filter((p: any) => p.type === "text").map((p: any) => p.text).join("\n")
      if (text) await senti({ sessionID: input.sessionID, prompt: text, cwd }, "prompt")
    },
    "tool.execute.before": async (input: any, output: any) => {
      const r = await senti({ tool: input.tool, args: output.args, sessionID: input.sessionID, cwd }, "pre")
      if (r.verdict !== "allow") throw new Error(r.reason || "Senti: I stopped this.")
    },
    "tool.execute.after": async (input: any, output: any) => {
      const r = await senti({ tool: input.tool, args: input.args, sessionID: input.sessionID, cwd, output: output?.output }, "post")
      if (r.context && typeof output?.output === "string") output.output = `${output.output}\n\n${r.context}`
    },
  }
}
