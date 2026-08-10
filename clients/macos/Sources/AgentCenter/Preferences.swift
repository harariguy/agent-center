import Foundation
import Observation
import ServiceManagement

enum AuthenticationMethod: String, CaseIterable {
    case viewerToken
    case adminPassword

    var title: String {
        switch self {
        case .viewerToken: "Viewer token"
        case .adminPassword: "Admin password"
        }
    }
}

/// Everything the user can configure. Secrets go to the Keychain; the rest to
/// UserDefaults. Environment variables win on launch so a scripted run
/// (`AN_URL=… AN_VIEWER_TOKEN=… make run`) needs no UI at all.
@MainActor
@Observable
final class Preferences {
    var serverURL: String {
        didSet { defaults.set(serverURL, forKey: "serverURL") }
    }

    var pollInterval: Int {
        didSet { defaults.set(pollInterval, forKey: "pollInterval") }
    }

    var notifyOnActivity: Bool {
        didSet { defaults.set(notifyOnActivity, forKey: "notifyOnActivity") }
    }

    var showBadgeCount: Bool {
        didSet { defaults.set(showBadgeCount, forKey: "showBadgeCount") }
    }

    var authenticationMethod: AuthenticationMethod {
        didSet { defaults.set(authenticationMethod.rawValue, forKey: "authenticationMethod") }
    }

    /// Not persisted here — SMAppService is the source of truth.
    var launchAtLogin: Bool {
        didSet { applyLaunchAtLogin() }
    }

    var launchAtLoginError: String?

    var viewerToken: String {
        didSet { Keychain.set(viewerToken, account: "viewer-token") }
    }

    var adminPassword: String {
        didSet { Keychain.set(adminPassword, account: "admin-password") }
    }

    private let defaults = UserDefaults.standard

    var activeViewerToken: String {
        authenticationMethod == .viewerToken ? viewerToken : ""
    }

    var activeAdminPassword: String {
        authenticationMethod == .adminPassword ? adminPassword : ""
    }

    var hasCredential: Bool {
        !activeViewerToken.isEmpty || !activeAdminPassword.isEmpty
    }

    var isConfigured: Bool { hasCredential && URL(string: serverURL) != nil }

    init() {
        defaults.register(defaults: [
            "pollInterval": 20,
            "notifyOnActivity": true,
            "showBadgeCount": true,
        ])

        let env = ProcessInfo.processInfo.environment
        serverURL = env["AN_URL"] ?? defaults.string(forKey: "serverURL") ?? ""
        pollInterval = defaults.integer(forKey: "pollInterval")
        notifyOnActivity = defaults.bool(forKey: "notifyOnActivity")
        showBadgeCount = defaults.bool(forKey: "showBadgeCount")
        let loadedViewerToken = env["AN_VIEWER_TOKEN"] ?? Keychain.get(account: "viewer-token")
        let loadedAdminPassword = env["AN_ADMIN_PASSWORD"] ?? Keychain.get(account: "admin-password")
        viewerToken = loadedViewerToken
        adminPassword = loadedAdminPassword
        if env["AN_VIEWER_TOKEN"] != nil {
            authenticationMethod = .viewerToken
        } else if env["AN_ADMIN_PASSWORD"] != nil {
            authenticationMethod = .adminPassword
        } else if let stored = AuthenticationMethod(
            rawValue: defaults.string(forKey: "authenticationMethod") ?? ""
        ) {
            authenticationMethod = stored
        } else {
            authenticationMethod = loadedViewerToken.isEmpty && !loadedAdminPassword.isEmpty
                ? .adminPassword : .viewerToken
        }
        launchAtLogin = SMAppService.mainApp.status == .enabled

        // Property observers don't run during init. Rewrite every credential we
        // could read so environment values persist and legacy items created with
        // the old permissive ACL are migrated to the standard restricted ACL.
        if env["AN_URL"] != nil { defaults.set(serverURL, forKey: "serverURL") }
        if !viewerToken.isEmpty {
            Keychain.set(viewerToken, account: "viewer-token")
        }
        if !adminPassword.isEmpty {
            Keychain.set(adminPassword, account: "admin-password")
        }
    }

    private func applyLaunchAtLogin() {
        do {
            if launchAtLogin {
                if SMAppService.mainApp.status != .enabled { try SMAppService.mainApp.register() }
            } else {
                if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() }
            }
            launchAtLoginError = nil
        } catch {
            // Unsigned / ad-hoc builds are commonly refused here. Report it
            // rather than leaving the toggle silently lying.
            launchAtLoginError = error.localizedDescription
            launchAtLogin = SMAppService.mainApp.status == .enabled
        }
    }
}
