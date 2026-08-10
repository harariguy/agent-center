import SwiftUI

struct PanelView: View {
    @Environment(Store.self) private var store
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        @Bindable var store = store

        VStack(spacing: 0) {
            PanelHeader(openSettings: openSettings)

            if let error = store.error, store.preferences.isConfigured || !error.isCredentialProblem {
                ErrorStrip(error: error, openSettings: openSettings)
            }

            Divider()

            content
        }
        .frame(width: DS.panelWidth, height: DS.panelHeight)
        .onAppear {
            store.isPanelOpen = true
            Task { await store.notifier.refreshStatus() }
        }
        .onDisappear { store.isPanelOpen = false }
    }

    @ViewBuilder
    private var content: some View {
        if !store.preferences.isConfigured {
            NotConnectedView(openSettings: openSettings)
        } else if store.visibleItems.isEmpty {
            if store.hasLoadedOnce {
                AllClearView(filter: store.filter)
            } else {
                ProgressView()
                    .controlSize(.small)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        } else {
            feed
        }
    }

    private var feed: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: DS.md, pinnedViews: [.sectionHeaders]) {
                ForEach(sections, id: \.heading) { section in
                    Section {
                        ForEach(section.items) { item in
                            NotificationCard(item: item)
                                .transition(.opacity.combined(with: .move(edge: .leading)))
                        }
                    } header: {
                        Text(section.heading.uppercased())
                            .font(DS.sectionHeader)
                            .foregroundStyle(.tertiary)
                            .padding(.vertical, DS.xs)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(.background.opacity(0.92))
                    }
                }
            }
            .padding(.horizontal, DS.md)
            .padding(.vertical, DS.sm)
            .animation(.easeOut(duration: 0.18), value: store.visibleItems)
        }
        .scrollIndicators(.automatic)
    }

    private struct FeedSection {
        let heading: String
        let items: [Item]
    }

    /// Feed arrives newest-first; keep that order and just cut it into days.
    private var sections: [FeedSection] {
        var order: [String] = []
        var buckets: [String: [Item]] = [:]
        for item in store.visibleItems {
            let heading = DS.dayHeading(item.lastSeenAt)
            if buckets[heading] == nil { order.append(heading) }
            buckets[heading, default: []].append(item)
        }
        return order.map { FeedSection(heading: $0, items: buckets[$0] ?? []) }
    }

    private func openSettings() {
        NSApp.activate(ignoringOtherApps: true)
        openWindow(id: "settings")
    }
}

// MARK: - header

struct PanelHeader: View {
    @Environment(Store.self) private var store
    var openSettings: () -> Void

    var body: some View {
        @Bindable var store = store

        VStack(spacing: DS.sm) {
            HStack(spacing: DS.sm) {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Notifications")
                        .font(.system(size: 14, weight: .semibold))
                    Text(subtitle)
                        .font(DS.meta)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                if store.isRefreshing {
                    ProgressView().controlSize(.small).scaleEffect(0.7).frame(width: 20)
                } else {
                    IconButton(systemImage: "arrow.clockwise", help: "Refresh now") {
                        Task { await store.refresh() }
                    }
                }

                Menu {
                    Button("Mark all as read") { store.markAllRead() }
                        .disabled(store.counts.unread == 0)
                    Divider()
                    Button("Settings…") { openSettings() }
                    Button("Quit") { NSApplication.shared.terminate(nil) }
                        .keyboardShortcut("q")
                } label: {
                    Image(systemName: "ellipsis.circle").font(.system(size: 13))
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .frame(width: 22)
                .foregroundStyle(.secondary)
            }

            Picker("", selection: $store.filter) {
                ForEach(Store.Filter.allCases) { option in
                    Text(label(for: option)).tag(option)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
        }
        .padding(.horizontal, DS.md)
        .padding(.top, DS.md)
        .padding(.bottom, DS.sm)
    }

    private func label(for filter: Store.Filter) -> String {
        let count = switch filter {
        case .all: store.counts.unread
        case .attention: store.counts.attentionUnread
        case .activity: store.counts.activityUnread
        }
        return count > 0 ? "\(filter.title) (\(count))" : filter.title
    }

    private var subtitle: String {
        if store.counts.attentionUnread > 0 {
            return "\(store.counts.attentionUnread) waiting on you"
        }
        if let updated = store.lastUpdated {
            return "Updated \(DS.relative(updated))"
        }
        return "Connecting…"
    }
}

// MARK: - error strip

struct ErrorStrip: View {
    let error: APIError
    var openSettings: () -> Void
    @Environment(Store.self) private var store

    var body: some View {
        HStack(spacing: DS.sm) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
                .font(.system(size: 11))

            Text(message)
                .font(DS.meta)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

            Spacer(minLength: DS.xs)

            if error.isCredentialProblem {
                Button("Settings") { openSettings() }
                    .buttonStyle(.plain).font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Color.accentColor)
            } else {
                Button("Retry") { Task { await store.refresh() } }
                    .buttonStyle(.plain).font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Color.accentColor)
            }
        }
        .padding(.horizontal, DS.md)
        .padding(.vertical, DS.sm)
        .background(Color.orange.opacity(0.1))
    }

    /// After repeated misses the transport detail is noise. Say what matters:
    /// we're still retrying, and how old what you're looking at is.
    private var message: String {
        guard store.isDegraded else { return error.localizedDescription }
        guard let updated = store.lastUpdated else { return "Can't reach the server — retrying." }
        return "Can't reach the server — retrying. Last update \(DS.relative(updated))."
    }
}

// MARK: - empty states

struct AllClearView: View {
    let filter: Store.Filter

    var body: some View {
        VStack(spacing: DS.sm) {
            Image(systemName: "checkmark.circle")
                .font(.system(size: 28, weight: .light))
                .foregroundStyle(.tertiary)
            Text(headline).font(.system(size: 13, weight: .medium))
            Text(detail).font(DS.body).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var headline: String {
        switch filter {
        case .all: "All clear"
        case .attention: "Nothing waiting on you"
        case .activity: "No activity"
        }
    }

    private var detail: String {
        switch filter {
        case .all: "Agents will show up here as they report in."
        case .attention: "Anything an agent is blocked on will land here."
        case .activity: "Routine reports from your agents appear here."
        }
    }
}

struct NotConnectedView: View {
    var openSettings: () -> Void

    var body: some View {
        VStack(spacing: DS.md) {
            Image(systemName: "bell.slash")
                .font(.system(size: 28, weight: .light))
                .foregroundStyle(.tertiary)
            VStack(spacing: DS.xs) {
                Text("Not connected").font(.system(size: 13, weight: .medium))
                Text("Point this at your Agent Notify server and add a viewer token.")
                    .font(DS.body).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            Button("Open Settings", action: openSettings)
                .controlSize(.small)
        }
        .padding(.horizontal, 40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - menu bar

struct MenuBarLabel: View {
    let counts: Counts
    let showCount: Bool
    let degraded: Bool

    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: symbol)
            if showCount && counts.unread > 0 {
                Text("\(counts.unread)")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
            }
        }
    }

    /// The slashed bell is the app's established "no connection" glyph (see
    /// NotConnectedView); in the menu bar it warns the count may be stale.
    private var symbol: String {
        if degraded { return "bell.slash" }
        return counts.attentionUnread > 0 ? "bell.badge.fill" : "bell"
    }
}
