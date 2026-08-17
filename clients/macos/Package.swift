// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AgentCenter",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "AgentCenter",
            path: "Sources/AgentCenter",
            // Swift 5 language mode: the app is single-actor by construction
            // (everything UI-facing is @MainActor) and v6's Sendable checking
            // buys little here. Revisit if background work grows.
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
