import Foundation

/// Reads the `SleepDisabled` value from `pmset -g` output. Returns nil if the line is missing.
func parseSleepDisabled(_ output: String) -> Bool? {
    for line in output.split(separator: "\n") {
        let fields = line.split(whereSeparator: \.isWhitespace)
        if fields.count >= 2, fields[0] == "SleepDisabled" {
            return fields[1] == "1"
        }
    }
    return nil
}

enum Pmset {
    /// Current system state. nil if it could not be read.
    static func sleepDisabled() -> Bool? {
        run("/usr/bin/pmset", ["-g"]).flatMap(parseSleepDisabled)
    }

    /// Needs the sudoers rule written by install.sh. Returns true on success.
    static func setSleepDisabled(_ on: Bool) -> Bool {
        run("/usr/bin/sudo", ["-n", "/usr/bin/pmset", "-a", "disablesleep", on ? "1" : "0"]) != nil
    }

    /// Runs a command and returns its stdout, or nil if it failed.
    private static func run(_ path: String, _ args: [String]) -> String? {
        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: path)
        process.arguments = args
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        guard (try? process.run()) != nil else { return nil }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return process.terminationStatus == 0 ? String(decoding: data, as: UTF8.self) : nil
    }
}
