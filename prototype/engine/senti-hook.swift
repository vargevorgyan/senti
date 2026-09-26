// senti-hook: the tiny program an agent runs for every action.
// Reads the hook JSON from stdin, asks Senti over a Unix socket, prints the decision.
// If Senti is not running or too slow, it fails closed ("ask"), never open.
import Darwin

let sockPath = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "/tmp/senti.sock"
let timeoutSec = 30

func failClosed(_ why: String) -> Never {
    let msg = "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"Senti unavailable (\(why)), asking to be safe\"}}"
    print(msg)
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
if fd < 0 { failClosed("socket") }
var addr = sockaddr_un()
addr.sun_family = sa_family_t(AF_UNIX)
withUnsafeMutableBytes(of: &addr.sun_path) { p in
    let bytes = Array(sockPath.utf8)
    for i in 0..<min(bytes.count, p.count - 1) { p[i] = bytes[i] }
}
let ok = withUnsafePointer(to: &addr) {
    $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) }
}
if ok != 0 { failClosed("not running") }
var tv = timeval(tv_sec: timeoutSec, tv_usec: 0)
setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))

var sent = 0
while sent < input.count {
    let n = input.withUnsafeBytes { write(fd, $0.baseAddress! + sent, input.count - sent) }
    if n <= 0 { failClosed("write") }
    sent += n
}
shutdown(fd, SHUT_WR)

var reply = [UInt8]()
while true {
    let n = read(fd, &buf, buf.count)
    if n < 0 { failClosed("timeout") }
    if n == 0 { break }
    reply.append(contentsOf: buf[0..<n])
}
close(fd)
if reply.isEmpty { failClosed("empty reply") }
print(String(decoding: reply, as: UTF8.self))
