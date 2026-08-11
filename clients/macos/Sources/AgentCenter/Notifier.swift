import Foundation
import UserNotifications

/// The only file that talks to UNUserNotificationCenter. Everything else calls
/// `post(_:)`, so replacing system banners with a custom panel later touches
/// exactly one type.
@MainActor
final class Notifier {
    enum Status: Equatable {
        case unknown
        case unavailable(String)
        case denied
        case granted

        var isGranted: Bool { self == .granted }

        var description: String {
            switch self {
            case .unknown: "not requested yet"
            case .unavailable(let why): why
            case .denied: "denied — enable in System Settings › Notifications"
            case .granted: "enabled"
            }
        }
    }

    private(set) var status: Status = .unknown

    static let archiveAction = "ARCHIVE_ACTION"
    static let categoryIdentifier = "AGENT_NOTIFICATION"

    /// Minimum gap between two banners. A poll that brings four new items would
    /// otherwise hand all four to the system in the same instant, which macOS
    /// collapses into one stack — the user sees "4 notifications" instead of
    /// four things worth reading. Spacing them lets each land on its own.
    private static let spacing = Duration.seconds(1)

    private var pending: [Item] = []
    private var drainTask: Task<Void, Never>?
    private var lastPostedAt: ContinuousClock.Instant?

    func requestAuthorization() async {
        // UNUserNotificationCenter traps outright when the process isn't a
        // bundled app, which is what happens under `swift run`.
        guard Bundle.main.bundleIdentifier != nil else {
            status = .unavailable("run the packaged .app, not the bare binary")
            return
        }

        let center = UNUserNotificationCenter.current()
        let category = UNNotificationCategory(
            identifier: Self.categoryIdentifier,
            actions: [UNNotificationAction(identifier: Self.archiveAction,
                                           title: "Archive",
                                           options: [])],
            intentIdentifiers: [])
        center.setNotificationCategories([category])

        do {
            let granted = try await center.requestAuthorization(options: [.alert, .sound, .badge])
            status = granted ? .granted : .denied
        } catch {
            status = .unavailable(error.localizedDescription)
        }
    }

    func refreshStatus() async {
        guard Bundle.main.bundleIdentifier != nil else { return }
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral: status = .granted
        case .denied: status = .denied
        case .notDetermined: status = .unknown
        @unknown default: status = .unknown
        }
    }

    /// Queue a banner. The first one goes out immediately; anything behind it
    /// waits its turn, so callers can post a whole batch in a loop.
    func post(_ item: Item) {
        guard status.isGranted else { return }
        pending.append(item)
        guard drainTask == nil else { return }
        drainTask = Task { [weak self] in await self?.drainPending() }
    }

    /// One at a time, never closer together than `spacing`. The gap is measured
    /// from the last banner actually posted rather than slept between each, so
    /// a burst split across two polls stays spaced instead of the second poll's
    /// first item landing on top of the previous poll's last.
    private func drainPending() async {
        let clock = ContinuousClock()
        while !pending.isEmpty {
            if let last = lastPostedAt {
                let due = last.advanced(by: Self.spacing)
                if clock.now < due { try? await clock.sleep(until: due) }
            }
            // Teardown cancels us; don't flush the remainder in one burst.
            if Task.isCancelled { break }
            deliver(pending.removeFirst())
            lastPostedAt = clock.now
        }
        drainTask = nil
    }

    private func deliver(_ item: Item) {
        let content = UNMutableNotificationContent()
        content.title = item.title
        content.subtitle = item.needsYou
            ? "Needs you · \(item.originLabel)"
            : item.originLabel
        if item.occurrences > 1 { content.subtitle += " · ×\(item.occurrences)" }
        content.body = item.body
        content.categoryIdentifier = Self.categoryIdentifier
        content.sound = item.needsYou ? .default : nil
        // Grouping in Notification Center follows the server's grouping.
        content.threadIdentifier = item.groupKey ?? item.id
        content.interruptionLevel = switch item.priority {
        case "urgent": .timeSensitive     // degrades to .active without the entitlement
        case "high":   .active
        default:       item.needsYou ? .active : .passive
        }
        content.userInfo = [
            "id": item.id,
            "link": item.primaryLink?.absoluteString ?? "",
        ]

        // Occurrence in the identifier so a regrouped re-fire alerts again
        // rather than being coalesced away as a duplicate.
        let request = UNNotificationRequest(identifier: "\(item.id)#\(item.occurrences)",
                                            content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
        Log.notify.info("banner posted for \(item.groupKey ?? item.id, privacy: .public)")
    }
}
