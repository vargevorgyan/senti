"""A tiny DIY agent (no hooks) that talks to a local model through Senti's model gateway.

    python3 demo/diy_agent.py "clean up my disk"             # dry run: prints the tool calls that survived Senti
    SENTI_GATEWAY=http://127.0.0.1:11435/v1 MODEL=qwen2.5:3b python3 demo/diy_agent.py "..."

It never executes tools unless --execute is given (and then only what Senti let through).
"""
import json
import os
import subprocess
import sys
import urllib.request

BASE = os.environ.get("SENTI_GATEWAY", "http://127.0.0.1:11435/v1")
MODEL = os.environ.get("MODEL", "qwen2.5:3b")
TOOLS = [
    {"type": "function", "function": {"name": "run_shell", "description": "Run a shell command on the user's Mac",
                                      "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read a file",
                                      "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
]


def main() -> None:
    execute = "--execute" in sys.argv
    prompt = " ".join(a for a in sys.argv[1:] if a != "--execute") or "List the files in the current folder."
    body = {"model": MODEL, "messages": [{"role": "system", "content": "You are an agent. Use the tools to do the task."},
                                         {"role": "user", "content": prompt}], "tools": TOOLS, "temperature": 0}
    req = urllib.request.Request(BASE + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Senti-Agent": "diy-agent",
                                          "X-Senti-Cwd": os.getcwd()})
    msg = json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]
    if msg.get("content"):
        print("model says:", msg["content"])
    for call in msg.get("tool_calls") or []:
        fn = call["function"]
        print("allowed tool call:", fn["name"], fn["arguments"])
        if execute and fn["name"] == "run_shell":
            print(subprocess.run(json.loads(fn["arguments"])["command"], shell=True, capture_output=True, text=True).stdout)
    if not msg.get("tool_calls"):
        print("(no tool calls left to run)")


if __name__ == "__main__":
    main()
