import Foundation
import Security

private let service = "com.sistemabinario.marketing.meta"
private let account = "user-access-token"

private enum Backend {
    case dataProtection
    case legacy
}

private enum KeychainFailure: Error {
    case status(OSStatus)
    case invalidUTF8
    case emptySecret
}

private func baseQuery(_ backend: Backend) -> [String: Any] {
    var query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: service,
        kSecAttrAccount as String: account,
    ]
    if case .dataProtection = backend {
        query[kSecUseDataProtectionKeychain as String] = true
    }
    return query
}

private func readSecret(_ backend: Backend) throws -> String? {
    var query = baseQuery(backend)
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

private func readSecret() throws -> String? {
    do {
        if let value = try readSecret(.dataProtection) { return value }
    } catch KeychainFailure.status(let status) where status == errSecMissingEntitlement {
        return try readSecret(.legacy)
    }
    return try readSecret(.legacy)
}

private func writeSecret(_ value: String, backend: Backend) throws {
    guard let data = value.data(using: .utf8) else { throw KeychainFailure.invalidUTF8 }
    let query = baseQuery(backend)
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

private func deleteSecret(_ backend: Backend) throws {
    let status = SecItemDelete(baseQuery(backend) as CFDictionary)
    guard status == errSecSuccess || status == errSecItemNotFound else {
        throw KeychainFailure.status(status)
    }
}

private func writeSecret(_ value: String) throws {
    let clean = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !clean.isEmpty else { throw KeychainFailure.emptySecret }
    do {
        try writeSecret(clean, backend: .dataProtection)
        try? deleteSecret(.legacy)
    } catch KeychainFailure.status(let status) where status == errSecMissingEntitlement {
        try writeSecret(clean, backend: .legacy)
    }
}

private func deleteSecret() throws {
    do {
        try deleteSecret(.dataProtection)
    } catch KeychainFailure.status(let status) where status == errSecMissingEntitlement {
        // Ad-hoc standalone helpers may not have a data-protection access group.
    }
    try deleteSecret(.legacy)
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
