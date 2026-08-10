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

    func post(_ item: Item) {
        guard status.isGranted else { return }

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
