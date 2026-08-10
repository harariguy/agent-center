import AppKit
import SwiftUI
import UserNotifications

@main
struct AgentNotifyApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @State private var store = Store.shared

    var body: some Scene {
        MenuBarExtra {
            PanelView().environment(store)
        } label: {
            MenuBarLabel(counts: store.counts,
                         showCount: store.preferences.showBadgeCount,
                         degraded: store.isDegraded)
        }
        // .window rather than .menu: the panel is a SwiftUI view we control
        // completely, instead of an NSMenu whose layout belongs to AppKit.
        .menuBarExtraStyle(.window)

        Window("Agent Notify Settings", id: "settings") {
            SettingsView().environment(store)
        }
        .windowResizability(.contentSize)
        .defaultPosition(.center)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)   // menu bar only, no Dock icon
        if Bundle.main.bundleIdentifier != nil {
            UNUserNotificationCenter.current().delegate = self
        }
        MainActor.assumeIsolated { Store.shared.start() }
    }

    func applicationWillTerminate(_ notification: Notification) {
        MainActor.assumeIsolated { Store.shared.stop() }
    }

    /// Banners should appear even while this app happens to be frontmost.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler handler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        handler([.banner, .sound])
    }

    /// A banner is an index entry: acting on it takes you to where the work
    /// actually lives, or clears it.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler handler: @escaping () -> Void
    ) {
        let info = response.notification.request.content.userInfo
        let id = info["id"] as? String

        switch response.actionIdentifier {
        case Notifier.archiveAction:
            if let id { MainActor.assumeIsolated { Store.shared.archive(id: id) } }
        default:
            // The writer only stores parsed links, but banners outlive app
            // versions — re-validate rather than trust stored userInfo.
            if let link = info["link"] as? String, let url = ExternalURL.parse(link) {
                NSWorkspace.shared.open(url)
            }
            if let id {
                MainActor.assumeIsolated {
                    if let item = Store.shared.items.first(where: { $0.id == id }) {
                        Store.shared.markRead(item)
                    }
                }
            }
        }
        handler()
    }
}
