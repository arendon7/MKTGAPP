import Darwin
import Foundation

@inline(__always)
func fail(_ message: String, code: Int32) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(code)
}

let executableURL = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL
let macOSURL = executableURL.deletingLastPathComponent()
let contentsURL = macOSURL.deletingLastPathComponent()
let resourcesURL = contentsURL.appendingPathComponent("Resources", isDirectory: true)
let pythonURL = resourcesURL.appendingPathComponent("runtime/python/bin/python3")
let bootstrapURL = resourcesURL.appendingPathComponent("background_agent.py")
let keychainURL = macOSURL.appendingPathComponent("binario-meta-keychain")
let fileManager = FileManager.default

guard fileManager.isExecutableFile(atPath: pythonURL.path) else {
    fail("background scheduler embedded Python missing", code: 5)
}
guard fileManager.fileExists(atPath: bootstrapURL.path) else {
    fail("background scheduler bootstrap missing", code: 5)
}
guard fileManager.isExecutableFile(atPath: keychainURL.path) else {
    fail("background scheduler Keychain helper missing", code: 5)
}

var environment = ProcessInfo.processInfo.environment
environment["BINARIO_META_KEYCHAIN_HELPER"] = keychainURL.path
environment["PYTHONNOUSERSITE"] = "1"
environment["PYTHONDONTWRITEBYTECODE"] = "1"
environment.removeValue(forKey: "PYTHONHOME")
environment.removeValue(forKey: "PYTHONPATH")

let process = Process()
process.executableURL = pythonURL
process.arguments = ["-I", "-B", bootstrapURL.path]
process.environment = environment
process.standardInput = FileHandle.standardInput
process.standardOutput = FileHandle.standardOutput
process.standardError = FileHandle.standardError

do {
    try process.run()
    process.waitUntilExit()
} catch {
    fail("background scheduler could not launch embedded runtime", code: 6)
}

if process.terminationReason != .exit {
    fail("background scheduler runtime terminated abnormally", code: 7)
}
exit(process.terminationStatus)
