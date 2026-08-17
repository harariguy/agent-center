import SwiftUI

struct SettingsView: View {
    @Environment(Store.self) private var store

    var body: some View {
        TabView {
            ConnectionSettings().tabItem { Label("Connection", systemImage: "network") }
            GeneralSettings().tabItem { Label("General", systemImage: "gearshape") }
        }
        .frame(width: 460)
        .padding(DS.lg)
    }
}

private struct ConnectionSettings: View {
    @Environment(Store.self) private var store
    @State private var testResult: SettingsResult?
    @State private var testing = false

    var body: some View {
        @Bindable var preferences = store.preferences

        Form {
            Section {
                TextField("Server URL", text: $preferences.serverURL,
                          prompt: Text("https://notifications.example.com"))
                    .textContentType(.URL)
            } footer: {
                Text("The same address you open in the browser.")
                    .font(DS.meta).foregroundStyle(.secondary)
            }

            Section {
                Picker("Authenticate with", selection: $preferences.authenticationMethod) {
                    ForEach(AuthenticationMethod.allCases, id: \.self) {
                        Text($0.title).tag($0)
                    }
                }
                .pickerStyle(.segmented)

                switch preferences.authenticationMethod {
                case .viewerToken:
                    SecureField("Viewer token", text: $preferences.viewerToken,
                                prompt: Text("anv_…"))
                case .adminPassword:
                    SecureField("Admin password", text: $preferences.adminPassword,
                                prompt: Text("ADMIN_PASSWORD"))
                }
            } footer: {
                Text(preferences.authenticationMethod == .viewerToken
                     ? "Preferred. Mint one on the server host with `agent-center viewer add <label>`, and revoke it there without touching anything else."
                     : "Works, but this is the credential that administers the server. Prefer a viewer token where you can.")
                    .font(DS.meta).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Section {
                HStack(spacing: DS.sm) {
                    Button("Apply & test") { test() }
                        .disabled(testing || !store.preferences.isConfigured)

                    if testing {
                        ProgressView().controlSize(.small).scaleEffect(0.7)
                    }

                    switch testResult {
                    case .success(let message):
                        Label(message, systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green).font(DS.meta)
                    case .failure(let message):
                        Label(message, systemImage: "xmark.circle.fill")
                            .foregroundStyle(.red).font(DS.meta)
                            .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                    case nil:
                        EmptyView()
                    }

                    Spacer()
                }
            }
        }
        .formStyle(.grouped)
    }

    private func test() {
        testing = true
        testResult = nil
        Task {
            let result = await store.testConnection()
            testing = false
            testResult = result
        }
    }
}

private struct GeneralSettings: View {
    @Environment(Store.self) private var store

    var body: some View {
        @Bindable var preferences = store.preferences

        Form {
            Section {
                Picker("Check for new notifications", selection: $preferences.pollInterval) {
                    Text("Every 10 seconds").tag(10)
                    Text("Every 20 seconds").tag(20)
                    Text("Every minute").tag(60)
                    Text("Every 5 minutes").tag(300)
                }
            } footer: {
                Text("Polls that find nothing new cost a 304 with no body, so a short interval is cheap. The app halves it while the panel is open and backs off in Low Power Mode.")
                    .font(DS.meta).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Section {
                Toggle("Banner for routine activity", isOn: $preferences.notifyOnActivity)
                Toggle("Show unread count in the menu bar", isOn: $preferences.showBadgeCount)
            } footer: {
                Text("Items an agent is blocked on always raise a banner.")
                    .font(DS.meta).foregroundStyle(.secondary)
            }

            Section {
                Toggle("Launch at login", isOn: $preferences.launchAtLogin)
                if let error = preferences.launchAtLoginError {
                    Text(error).font(DS.meta).foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }

                LabeledContent("Notifications") {
                    HStack(spacing: DS.sm) {
                        Text(store.notifier.status.description)
                            .font(DS.meta).foregroundStyle(.secondary)
                        if !store.notifier.status.isGranted {
                            Button("Open System Settings") {
                                let url = URL(string: "x-apple.systempreferences:com.apple.preference.notifications")!
                                NSWorkspace.shared.open(url)
                            }
                            .controlSize(.small)
                        }
                    }
                }
            }

            Section {
                LabeledContent("Version", value: version)
            }
        }
        .formStyle(.grouped)
        .task { await store.notifier.refreshStatus() }
    }

    private var version: String {
        let short = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        return "\(short ?? "dev") (\(build ?? "0"))"
    }
}
