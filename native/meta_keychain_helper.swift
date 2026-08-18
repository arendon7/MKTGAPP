import Foundation
import Security

private struct SecretSlot {
    let service: String
    let account: String
    let label: String
}

private let slots: [String: SecretSlot] = [
    "meta": SecretSlot(
        service: "com.sistemabinario.marketing.meta",
        account: "user-access-token",
        label: "BINARIO Marketing · Meta Access Token"
    ),
    "openai": SecretSlot(
        service: "com.sistemabinario.marketing.ai.openai",
        account: "api-key",
        label: "BINARIO Marketing · OpenAI API Key"
    ),
    "anthropic": SecretSlot(
        service: "com.sistemabinario.marketing.ai.anthropic",
        account: "api-key",
        label: "BINARIO Marketing · Anthropic API Key"
    ),
    "gemini": SecretSlot(
        service: "com.sistemabinario.marketing.ai.gemini",
        account: "api-key",
        label: "BINARIO Marketing · Gemini API Key"
    ),
]
private let metaSlot = slots["meta"]!

private enum Backend {
    case dataProtection
    case legacy
}

private enum KeychainFailure: Error {
    case status(OSStatus)
    case invalidUTF8
    case emptySecret
    case invalidNamespace
}

private func baseQuery(_ backend: Backend, slot: SecretSlot) -> [String: Any] {
    var query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: slot.service,
        kSecAttrAccount as String: slot.account,
    ]
    if case .dataProtection = backend {
        query[kSecUseDataProtectionKeychain as String] = true
    }
    return query
}

private func readSecret(_ backend: Backend, slot: SecretSlot) throws -> String? {
    var query = baseQuery(backend, slot: slot)
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

private func readSecret(_ slot: SecretSlot) throws -> String? {
    do {
        if let value = try readSecret(.dataProtection, slot: slot) { return value }
    } catch KeychainFailure.status(let status) where status == errSecMissingEntitlement {
        return try readSecret(.legacy, slot: slot)
    }
    return try readSecret(.legacy, slot: slot)
}

private func writeSecret(_ value: String, backend: Backend, slot: SecretSlot) throws {
    guard let data = value.data(using: .utf8) else { throw KeychainFailure.invalidUTF8 }
    let query = baseQuery(backend, slot: slot)
    let update: [String: Any] = [kSecValueData as String: data]
    let updateStatus = SecItemUpdate(query as CFDictionary, update as CFDictionary)
    if updateStatus == errSecSuccess { return }
    guard updateStatus == errSecItemNotFound else { throw KeychainFailure.status(updateStatus) }
    var add = query
    add[kSecValueData as String] = data
    add[kSecAttrLabel as String] = slot.label
    let addStatus = SecItemAdd(add as CFDictionary, nil)
    guard addStatus == errSecSuccess else { throw KeychainFailure.status(addStatus) }
}

private func deleteSecret(_ backend: Backend, slot: SecretSlot) throws {
    let status = SecItemDelete(baseQuery(backend, slot: slot) as CFDictionary)
    guard status == errSecSuccess || status == errSecItemNotFound else {
        throw KeychainFailure.status(status)
    }
}

private func writeSecret(_ value: String, slot: SecretSlot) throws {
    let clean = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !clean.isEmpty else { throw KeychainFailure.emptySecret }
    do {
        try writeSecret(clean, backend: .dataProtection, slot: slot)
        try? deleteSecret(.legacy, slot: slot)
    } catch KeychainFailure.status(let status) where status == errSecMissingEntitlement {
        try writeSecret(clean, backend: .legacy, slot: slot)
    }
}

private func deleteSecret(_ slot: SecretSlot) throws {
    do {
        try deleteSecret(.dataProtection, slot: slot)
    } catch KeychainFailure.status(let status) where status == errSecMissingEntitlement {
        // Ad-hoc standalone helpers may not have a data-protection access group.
    }
    try deleteSecret(.legacy, slot: slot)
}

// Historical Meta wrappers are intentionally retained as executable code, not comments.
// This keeps the original data-protection-first contract byte-visible to source guards
// while AI namespaces use the same implementation through the slot-aware overloads.
private func readSecret(_ backend: Backend) throws -> String? {
    try readSecret(backend, slot: metaSlot)
}

private func writeSecret(_ value: String, backend: Backend) throws {
    try writeSecret(value, backend: backend, slot: metaSlot)
}

private func deleteSecret(_ backend: Backend) throws {
    try deleteSecret(backend, slot: metaSlot)
}

private func readMetaSecret() throws -> String? {
    do {
        if let value = try readSecret(.dataProtection) { return value }
    } catch KeychainFailure.status(let status) where status == errSecMissingEntitlement {
        return try readSecret(.legacy)
    }
    return try readSecret(.legacy)
}

private func writeMetaSecret(_ value: String) throws {
    let clean = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !clean.isEmpty else { throw KeychainFailure.emptySecret }
    do {
        try writeSecret(clean, backend: .dataProtection)
        try? deleteSecret(.legacy)
    } catch KeychainFailure.status(let status) where status == errSecMissingEntitlement {
        try writeSecret(clean, backend: .legacy)
    }
}

private func deleteMetaSecret() throws {
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
    case KeychainFailure.invalidNamespace:
        fputs("invalid secret namespace\n", stderr)
    default:
        fputs("keychain operation failed\n", stderr)
    }
    exit(2)
}

let arguments = Array(CommandLine.arguments.dropFirst())
let command = arguments.first ?? "status"
let namespace = arguments.count > 1 ? arguments[1].lowercased() : "meta"
guard let slot = slots[namespace] else { fail(KeychainFailure.invalidNamespace) }

do {
    switch command {
    case "get":
        let value = namespace == "meta" ? try readMetaSecret() : try readSecret(slot)
        if let value {
            FileHandle.standardOutput.write(Data(value.utf8))
            exit(0)
        }
        exit(3)
    case "set":
        if namespace == "meta" {
            try writeMetaSecret(stdinText())
        } else {
            try writeSecret(stdinText(), slot: slot)
        }
        print("ok")
    case "delete":
        if namespace == "meta" {
            try deleteMetaSecret()
        } else {
            try deleteSecret(slot)
        }
        print("ok")
    case "status":
        let value = namespace == "meta" ? try readMetaSecret() : try readSecret(slot)
        print(value == nil ? "missing" : "configured")
    default:
        fputs("usage: binario-keychain-helper [get|set|delete|status] [meta|openai|anthropic|gemini]\n", stderr)
        exit(64)
    }
} catch {
    fail(error)
}
