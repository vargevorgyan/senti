// senti-key: this Mac's device key in the Secure Enclave.
//
// The private key is created inside the Secure Enclave and never leaves it. What is saved to disk is an encrypted handle
// that only this Mac's Secure Enclave can use, so copying the file to another computer gives an attacker nothing.
// Every request the Senti engine sends to the company server is signed with this key.
//
//   senti-key create PATH   create a new key, save its handle to PATH (mode 600), print the public key (base64 DER)
//   senti-key public PATH   print the public key again
//   senti-key sign PATH     sign stdin (ECDSA P-256 / SHA-256), print the signature (base64 DER)
//
// Exit codes: 0 ok, 2 usage, 3 no Secure Enclave on this Mac, 4 key error.
import CryptoKit
import Foundation

func fail(_ code: Int32, _ msg: String) -> Never {
    FileHandle.standardError.write(Data("senti-key: \(msg)\n".utf8))
    exit(code)
}

let args = CommandLine.arguments
guard args.count == 3 else { fail(2, "usage: senti-key create|public|sign PATH") }
let path = args[2]

func load() -> SecureEnclave.P256.Signing.PrivateKey {
    guard let blob = FileManager.default.contents(atPath: path) else { fail(4, "no key at \(path)") }
    do { return try SecureEnclave.P256.Signing.PrivateKey(dataRepresentation: blob) } catch { fail(4, "unusable key: \(error)") }
}

switch args[1] {
case "create":
    guard SecureEnclave.isAvailable else { fail(3, "this Mac has no Secure Enclave") }
    do {
        let key = try SecureEnclave.P256.Signing.PrivateKey()
        let tmp = path + ".tmp"
        FileManager.default.createFile(atPath: tmp, contents: key.dataRepresentation, attributes: [.posixPermissions: 0o600])
        _ = try FileManager.default.replaceItemAt(URL(fileURLWithPath: path), withItemAt: URL(fileURLWithPath: tmp))
        print(key.publicKey.derRepresentation.base64EncodedString())
    } catch { fail(4, "could not create a key: \(error)") }
case "public":
    print(load().publicKey.derRepresentation.base64EncodedString())
case "sign":
    let message = FileHandle.standardInput.readDataToEndOfFile()
    do { print(try load().signature(for: message).derRepresentation.base64EncodedString()) } catch { fail(4, "signing failed: \(error)") }
default:
    fail(2, "usage: senti-key create|public|sign PATH")
}
