// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AgentNotifications",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "AgentNotifications",
            path: "Sources/AgentNotifications",
            // Swift 5 language mode: the app is single-actor by construction
            // (everything UI-facing is @MainActor) and v6's Sendable checking
            // buys little here. Revisit if background work grows.
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
