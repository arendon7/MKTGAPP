import Foundation
import Security

private let service = "com.sistemabinario.marketing.meta"
private let account = "user-access-token"

private enum KeychainFailure: Error {
    case status(OSStatus)
    case invalidUTF8
    case emptySecret
}

private func baseQuery() -> [String: Any] {
    [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: service,
        kSecAttrAccount as String: account,
        kSecUseDataProtectionKeychain as String: true,
    ]
}

private func readSecret() throws -> String? {
    var query = baseQuery()
    query[kSecReturnData as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound { return nil }
    guard status == errSecSuccess else { throw KeychainFailure.status(status) }
    guard let data = result as? Data, let value = String(data: data, encoding: .utf8) else {
        throw KeychainFailure.invalidUTF8
    }
    return value
}

private func writeSecret(_ value: String) throws {
    let clean = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !clean.isEmpty else { throw KeychainFailure.emptySecret }
    guard let data = clean.data(using: .utf8) else { throw KeychainFailure.invalidUTF8 }
    let query = baseQuery()
    let update: [String: Any] = [kSecValueData as String: data]
    let updateStatus = SecItemUpdate(query as CFDictionary, update as CFDictionary)
    if updateStatus == errSecSuccess { return }
    guard updateStatus == errSecItemNotFound else { throw KeychainFailure.status(updateStatus) }
    var add = query
    add[kSecValueData as String] = data
    add[kSecAttrLabel as String] = "BINARIO Marketing · Meta Access Token"
    let addStatus = SecItemAdd(add as CFDictionary, nil)
    guard addStatus == errSecSuccess else { throw KeychainFailure.status(addStatus) }
}

private func deleteSecret() throws {
    let status = SecItemDelete(baseQuery() as CFDictionary)
    guard status == errSecSuccess || status == errSecItemNotFound else {
        throw KeychainFailure.status(status)
    }
}

private func stdinText() -> String {
    String(data: FileHandle.standardInput.readDataToEndOfFile(), encoding: .utf8) ?? ""
}

private func fail(_ error: Error) -> Never {
    switch error {
    case KeychainFailure.status(let status):
        fputs("keychain status \(status)\n", stderr)
    case KeychainFailure.invalidUTF8:
        fputs("invalid UTF-8 secret\n", stderr)
    case KeychainFailure.emptySecret:
        fputs("empty secret\n", stderr)
    default:
        fputs("keychain operation failed\n", stderr)
    }
    exit(2)
}

let command = CommandLine.arguments.dropFirst().first ?? "status"
do {
    switch command {
    case "get":
        if let value = try readSecret() {
            FileHandle.standardOutput.write(Data(value.utf8))
            exit(0)
        }
        exit(3)
    case "set":
        try writeSecret(stdinText())
        print("ok")
    case "delete":
        try deleteSecret()
        print("ok")
    case "status":
        print((try readSecret()) == nil ? "missing" : "configured")
    default:
        fputs("usage: meta-keychain-helper [get|set|delete|status]\n", stderr)
        exit(64)
    }
} catch {
    fail(error)
}
