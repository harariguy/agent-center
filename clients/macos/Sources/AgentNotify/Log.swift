import OSLog

/// Unified-logging channels. Inspect a running copy with:
///
///     log stream --predicate 'subsystem == "ai.tydra.agent-notify"' --level debug
///
/// or, for what already happened:
///
///     log show --last 5m --predicate 'subsystem == "ai.tydra.agent-notify"'
enum Log {
    private static let subsystem = "ai.tydra.agent-notify"

    static let poll = Logger(subsystem: subsystem, category: "poll")
    static let triage = Logger(subsystem: subsystem, category: "triage")
    static let notify = Logger(subsystem: subsystem, category: "notify")

    /// `AN_VERBOSE=1 make run` mirrors the same events to stderr. Unified
    /// logging drops info/debug unless you ask for them just so, which makes it
    /// a poor first stop when something isn't working.
    static let verbose = ProcessInfo.processInfo.environment["AN_VERBOSE"] == "1"

    static func echo(_ message: @autoclosure () -> String) {
        guard verbose else { return }
        FileHandle.standardError.write(Data((message() + "\n").utf8))
    }
}
