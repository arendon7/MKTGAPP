import Foundation
import ServiceManagement

private let plistName = "com.sistemabinario.marketing.background.plist"

private func statusName(_ status: SMAppService.Status) -> String {
    switch status {
    case .notRegistered:
        return "not-registered"
    case .enabled:
        return "enabled"
    case .requiresApproval:
        return "requires-approval"
    case .notFound:
        return "not-found"
    @unknown default:
        return "unknown"
    }
}

private func emit(_ payload: [String: Any], code: Int32 = 0) -> Never {
    do {
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))
        exit(code)
    } catch {
        FileHandle.standardError.write(Data("background service helper JSON failure\n".utf8))
        exit(3)
    }
}

if #available(macOS 13.0, *) {
    let service = SMAppService.agent(plistName: plistName)
    let command = CommandLine.arguments.dropFirst().first ?? "status"
    do {
        switch command {
        case "status":
            emit([
                "supported": true,
                "status": statusName(service.status),
                "requires_approval": service.status == .requiresApproval
            ])
        case "register":
            try service.register()
            emit([
                "supported": true,
                "status": statusName(service.status),
                "requires_approval": service.status == .requiresApproval
            ])
        case "unregister":
            try service.unregister()
            emit([
                "supported": true,
                "status": statusName(service.status),
                "requires_approval": service.status == .requiresApproval
            ])
        case "open-settings":
            SMAppService.openSystemSettingsLoginItems()
            emit([
                "supported": true,
                "status": statusName(service.status),
                "requires_approval": service.status == .requiresApproval,
                "settings_opened": true
            ])
        default:
            emit(["supported": true, "error": "unsupported command"], code: 2)
        }
    } catch {
        emit([
            "supported": true,
            "status": statusName(service.status),
            "requires_approval": service.status == .requiresApproval,
            "error": String(describing: error)
        ], code: 4)
    }
} else {
    emit([
        "supported": false,
        "status": "unsupported",
        "requires_approval": false
    ])
}
