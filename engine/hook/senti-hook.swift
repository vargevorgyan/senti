// senti-hook: the tiny program an agent runs for every action.
//
//   senti-hook <agent> [pre|prompt|post]
//   agent = claude | codex | opencode | cursor | cline | hermes | openclaw | generic
//
// Reads the agent's hook JSON from stdin, sends it to the local Senti engine over a Unix socket
// (HTTP/1.1, POST /v1/hook/<agent>), and prints the engine's reply for the agent.
// Fail closed: if Senti is not running, too slow, or replies with an error, the action is NOT allowed
// ("ask" for Claude Code, an explicit "deny" for Codex, which would otherwise fail open).
// POSIX only (no Foundation) so start-up stays ~1-3 ms.
import Darwin

let args = CommandLine.arguments
let agent = args.count > 1 ? args[1] : "claude"
let event = args.count > 2 ? args[2] : "pre"

func env(_ name: String) -> String? {
    guard let v = getenv(name) else { return nil }
    return String(cString: v)
}

let home = env("HOME") ?? "/tmp"
var sockPath = env("SENTI_SOCKET") ?? ((env("SENTI_HOME") ?? home + "/.senti") + "/senti.sock")
if sockPath.utf8.count > 100 { sockPath = "/tmp/senti-\(getuid()).sock" }
let timeoutSec = Int(env("SENTI_HOOK_TIMEOUT") ?? "") ?? 290
let sentiHome = env("SENTI_HOME") ?? home + "/.senti"

// Per-install secret the engine requires on every request (~/.senti/hook.token).
func readToken() -> String {
    let fd = open(sentiHome + "/hook.token", O_RDONLY)
    if fd < 0 { return "" }
    var b = [UInt8](repeating: 0, count: 256)
    let n = read(fd, &b, b.count)
    close(fd)
    if n <= 0 { return "" }
    return String(decoding: b[0..<n], as: UTF8.self).filter { !$0.isWhitespace && !$0.isNewline }
}
let token = readToken()

func writeErr(_ s: String) {
    let b = Array(s.utf8)
    _ = b.withUnsafeBytes { write(2, $0.baseAddress, b.count) }
}

func failClosed(_ why: String) -> Never {
    let reason = "Senti: I couldn't check this action (\(why)), so I'm not letting it run without you."
    if event != "pre" {
        // prompt / post-tool events carry no permission decision; never block the user's prompt,
        // but answer in the shape agents that validate output expect
        switch agent {
        case "cursor": print(event == "prompt" ? "{\"continue\":true}" : "{}")
        case "cline": print("{\"cancel\":false}")
        case "hermes": print("{}")
        default: break
        }
        exit(0)
    }
    switch agent {
    case "codex":
        print("{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"\(reason)\"}}")
    case "opencode", "openclaw", "generic":
        print("{\"verdict\":\"block\",\"reason\":\"\(reason)\",\"layer\":\"hook\"}")
    case "cursor":
        print("{\"permission\":\"deny\",\"user_message\":\"\(reason)\",\"agent_message\":\"\(reason)\"}")
        exit(2)  // Cursor: exit 2 = deny even if the JSON were ignored
    case "cline":
        print("{\"cancel\":true,\"errorMessage\":\"\(reason)\"}")
    case "hermes":
        print("{\"decision\":\"block\",\"reason\":\"\(reason)\"}")
        exit(2)
    default:
        print("{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"\(reason)\"}}")
    }
    exit(0)
}

var input = [UInt8]()
var buf = [UInt8](repeating: 0, count: 65536)
while true {
    let n = read(0, &buf, buf.count)
    if n <= 0 { break }
    input.append(contentsOf: buf[0..<n])
}

let fd = socket(AF_UNIX, SOCK_STREAM, 0)
if fd < 0 { failClosed("socket error") }
var addr = sockaddr_un()
addr.sun_family = sa_family_t(AF_UNIX)
withUnsafeMutableBytes(of: &addr.sun_path) { p in
    let bytes = Array(sockPath.utf8)
    for i in 0..<min(bytes.count, p.count - 1) { p[i] = bytes[i] }
}
let ok = withUnsafePointer(to: &addr) {
    $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) }
}
if ok != 0 { failClosed("Senti is not running") }
var tv = timeval(tv_sec: timeoutSec, tv_usec: 0)
setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))

let header = "POST /v1/hook/\(agent) HTTP/1.1\r\nHost: senti\r\nContent-Type: application/json\r\nX-Senti-Event: \(event)\r\nX-Senti-Token: \(token)\r\nContent-Length: \(input.count)\r\nConnection: close\r\n\r\n"
let request = Array(header.utf8) + input
var sent = 0
while sent < request.count {
    let n = request.withUnsafeBytes { write(fd, $0.baseAddress! + sent, request.count - sent) }
    if n <= 0 { failClosed("write failed") }
    sent += n
}

var reply = [UInt8]()
while true {
    let n = read(fd, &buf, buf.count)
    if n < 0 { failClosed("timed out") }
    if n == 0 { break }
    reply.append(contentsOf: buf[0..<n])
}
close(fd)

// split headers / body
var split = -1
if reply.count >= 4 {
    for i in 0...(reply.count - 4) where reply[i] == 13 && reply[i + 1] == 10 && reply[i + 2] == 13 && reply[i + 3] == 10 {
        split = i
        break
    }
}
if split < 0 { failClosed("bad reply") }
let head = String(decoding: reply[0..<split], as: UTF8.self)
if !head.hasPrefix("HTTP/1.1 200") && !head.hasPrefix("HTTP/1.0 200") { failClosed("engine error") }
let body = Array(reply[(split + 4)...])
if body.isEmpty {
    if event == "pre" && agent != "codex" { failClosed("empty reply") }
    exit(0)  // Codex: empty output = no objection; prompt/post: nothing to add
}
let out = String(decoding: body, as: UTF8.self)
print(out)
