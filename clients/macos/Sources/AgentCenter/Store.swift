import AppKit
import Foundation
import Observation

/// Outcome of the Settings window's "Test connection".
enum SettingsResult: Equatable {
    case success(String)
    case failure(String)
}

@MainActor
@Observable
final class Store {
    static let shared = Store()

    enum Filter: String, CaseIterable, Identifiable {
        case all, attention, activity
        var id: String { rawValue }
        var title: String {
            switch self {
            case .all: "All"
            case .attention: "Needs you"
            case .activity: "Activity"
            }
        }
    }

    private(set) var items: [Item] = []
    private(set) var counts: Counts = .zero
    private(set) var lastUpdated: Date?
    private(set) var isRefreshing = false
    private(set) var error: APIError?
    private(set) var hasLoadedOnce = false
    private(set) var consecutiveFailures = 0

    /// Three misses in a row is an outage, not a blip. Only then does the UI
    /// admit the feed is stale, so a single dropped poll never flashes the icon.
    var isDegraded: Bool { consecutiveFailures >= 3 }

    var filter: Filter = .all
    /// Panel visibility drives the poll cadence — open means the user is
    /// looking, so refresh faster. Re-arming rather than just refreshing also
    /// cuts short any backoff wait: looking at the panel forces a retry now.
    var isPanelOpen = false {
        didSet { if isPanelOpen && !oldValue { restartPolling() } }
    }

    let preferences = Preferences()
    let notifier = Notifier()

    private let client = APIClient()
    private var seenLastFire: [String: Date] = [:]
    private var seeded = false
    private var pollTask: Task<Void, Never>?
    private var wakeObserver: NSObjectProtocol?

    var visibleItems: [Item] {
        switch filter {
        case .all: items
        case .attention: items.filter(\.needsYou)
        case .activity: items.filter { !$0.needsYou }
        }
    }

    var badgeCount: Int {
        preferences.showBadgeCount ? counts.unread : 0
    }

    // MARK: - lifecycle

    func start() {
        observeWake()
        Task {
            await notifier.requestAuthorization()
            await applyPreferences()
            restartPolling()
        }
    }

    func stop() {
        pollTask?.cancel()
        if let wakeObserver { NSWorkspace.shared.notificationCenter.removeObserver(wakeObserver) }
        wakeObserver = nil
    }

    /// (Re)arm the poll loop: poll immediately, then keep polling forever.
    /// `refresh()` never throws, so nothing a tick does can end the loop —
    /// failures only stretch the next interval.
    private func restartPolling() {
        pollTask?.cancel()
        let previous = pollTask
        pollTask = Task { [weak self] in
            // Let the cancelled loop unwind first: its in-flight refresh has
            // to release `isRefreshing`, or the immediate poll below would be
            // skipped by the reentrancy guard.
            await previous?.value
            while !Task.isCancelled {
                await self?.refresh()
                guard let seconds = self?.nextInterval else { return }
                try? await Task.sleep(for: .seconds(seconds))
            }
        }
    }

    /// Waking from sleep is the worst case for staleness and the moment the
    /// network comes back — poll right away instead of sitting out the
    /// remainder of a pre-sleep interval or its backoff.
    private func observeWake() {
        wakeObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didWakeNotification, object: nil, queue: .main
        ) { _ in
            Task { @MainActor in Store.shared.restartPolling() }
        }
    }

    /// Push the current settings into the client and force a fetch.
    func applyPreferences() async {
        await client.configure(url: preferences.serverURL,
                               viewerToken: preferences.activeViewerToken,
                               adminPassword: preferences.activeAdminPassword)
        seeded = false
        seenLastFire.removeAll()
        await refresh()
    }

    /// Straight yes/no for the Settings window, and it re-arms the poll loop
    /// with whatever was just typed.
    func testConnection() async -> SettingsResult {
        await client.configure(url: preferences.serverURL,
                               viewerToken: preferences.activeViewerToken,
                               adminPassword: preferences.activeAdminPassword)
        do {
            let counts = try await client.verify()
            seeded = false
            seenLastFire.removeAll()
            await refresh()
            return .success("Connected — \(counts.total) open, \(counts.unread) unread")
        } catch let apiError as APIError {
            return .failure(apiError.localizedDescription)
        } catch {
            return .failure(error.localizedDescription)
        }
    }

    private var currentInterval: Int {
        // Demo escape hatch: a fixed cadence below the 10s floor, ignoring the
        // panel-open and Low Power adjustments so the interval is predictable.
        if let raw = ProcessInfo.processInfo.environment["AN_POLL_INTERVAL"],
           let seconds = Int(raw), seconds > 0 {
            return seconds
        }
        let base = max(10, preferences.pollInterval)
        if isPanelOpen { return max(8, base / 2) }
        if ProcessInfo.processInfo.isLowPowerModeEnabled { return base * 3 }
        return base
    }

    /// Success keeps the user's cadence. While the server is unreachable the
    /// gap doubles per miss toward a two-minute cap: the first retry stays
    /// prompt, a dead server isn't hammered, and recovery is never far away.
    private var nextInterval: Int {
        guard consecutiveFailures > 0 else { return currentInterval }
        return min(currentInterval << min(consecutiveFailures - 1, 3), 120)
    }

    // MARK: - polling

    func refresh() async {
        guard preferences.isConfigured else {
            error = .notConfigured
            // Unconfigured is its own state with its own UI, not an outage.
            consecutiveFailures = 0
            Log.echo("poll: not configured (url \(preferences.serverURL.isEmpty ? "unset" : "set"), credential \(preferences.hasCredential ? "present" : "missing"))")
            Log.poll.notice("""
                not configured — url=\(self.preferences.serverURL.isEmpty ? "unset" : "set", privacy: .public) \
                credential=\(self.preferences.hasCredential ? "present" : "missing", privacy: .public)
                """)
            return
        }
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }

        do {
            guard let update = try await client.pollCounts() else {
                // 304 — nothing changed anywhere, don't touch the feed.
                Log.poll.debug("304 not modified")
                Log.echo("poll: 304 not modified")
                error = nil
                lastUpdated = Date()
                consecutiveFailures = 0
                return
            }
            let fetched = try await client.fetchFeed()
            await client.accept(update)
            counts = update.counts
            notifyOnChanges(in: fetched)
            items = fetched
            error = nil
            lastUpdated = Date()
            hasLoadedOnce = true
            consecutiveFailures = 0
            Log.echo("poll: 200 changed — \(fetched.count) items, \(update.counts.unread) unread")
            Log.poll.info("""
                200 changed — \(fetched.count, privacy: .public) items, \
                \(update.counts.unread, privacy: .public) unread, \
                \(update.counts.attentionUnread, privacy: .public) need you
                """)
        } catch let apiError as APIError {
            recordFailure(apiError)
        } catch {
            recordFailure(.unreachable(error.localizedDescription))
        }
    }

    /// A failed tick must never end the loop: record it, keep the last good
    /// feed on screen, and let the caller stretch the next interval.
    private func recordFailure(_ apiError: APIError) {
        // A cancelled tick is the loop being re-armed (panel open, wake,
        // settings change), not the server failing — don't count it.
        guard !Task.isCancelled else { return }
        error = apiError
        consecutiveFailures += 1
        Log.echo("poll: FAILED ×\(consecutiveFailures) — \(apiError.localizedDescription)")
        Log.poll.error("""
            poll failed ×\(self.consecutiveFailures, privacy: .public): \
            \(apiError.localizedDescription, privacy: .public)
            """)
    }

    /// Alert for genuinely new items and for grouped re-fires (last_seen_at
    /// advanced). The first successful load seeds silently — otherwise
    /// connecting the app dumps the whole backlog into Notification Center.
    private func notifyOnChanges(in fetched: [Item]) {
        defer {
            seenLastFire = Dictionary(fetched.map { ($0.id, $0.lastSeenAt) },
                                      uniquingKeysWith: { a, _ in a })
            seeded = true
        }
        guard seeded else { return }

        // The feed is newest-first, and the notifier posts in the order it is
        // handed items — so walk it backwards. The newest banner is then the
        // last to arrive and sits at the top of the stack, the way every other
        // notification on the system does.
        for item in fetched.reversed() where item.isUnread {
            if !item.needsYou && !preferences.notifyOnActivity { continue }
            if let previous = seenLastFire[item.id] {
                if item.lastSeenAt > previous { notifier.post(item) }
            } else {
                notifier.post(item)
            }
        }
    }

    // MARK: - triage
    //
    // Applied locally first so the UI responds immediately, then written back.
    // A failed write is surfaced and corrected by the next poll.

    func open(_ item: Item) {
        if let url = item.primaryLink { NSWorkspace.shared.open(url) }
        markRead(item)
    }

    func open(_ action: Action, on item: Item) {
        if let url = action.parsedURL { NSWorkspace.shared.open(url) }
        markRead(item)
    }

    func markRead(_ item: Item) {
        guard item.isUnread else { return }
        replace(item.with(readAt: Date()))
        write { try await $0.markRead(item.id) }
    }

    func markUnread(_ item: Item) {
        replace(item.with(readAt: nil))
        write { try await $0.markUnread(item.id) }
    }

    func toggleRead(_ item: Item) {
        item.isUnread ? markRead(item) : markUnread(item)
    }

    func archive(_ item: Item) {
        items.removeAll { $0.id == item.id }
        adjustCounts()
        write { try await $0.archive(item.id) }
    }

    /// Banner entry point. Banners in Notification Center outlive restarts and
    /// feed refreshes, so the id may no longer be in `items` — archive it
    /// server-side anyway and let the follow-up poll reconcile the counts.
    func archive(id: String) {
        if let item = items.first(where: { $0.id == id }) {
            archive(item)
        } else {
            write { try await $0.archive(id) }
        }
    }

    func snooze(_ item: Item, until: Date) {
        items.removeAll { $0.id == item.id }
        adjustCounts()
        write { try await $0.snooze(item.id, until: until) }
    }

    func markAllRead() {
        items = items.map { $0.with(readAt: Date()) }
        adjustCounts()
        write { try await $0.markAllRead() }
    }

    private func write(_ operation: @escaping (APIClient) async throws -> Void) {
        Task {
            do {
                try await operation(client)
            } catch let apiError as APIError {
                error = apiError
            } catch {
                self.error = .unreachable(error.localizedDescription)
            }
            await refresh()
        }
    }

    private func replace(_ item: Item) {
        guard let index = items.firstIndex(where: { $0.id == item.id }) else { return }
        items[index] = item
        adjustCounts()
    }

    /// Keep the badge honest between the optimistic edit and the next poll.
    private func adjustCounts() {
        counts = Counts(
            total: items.count,
            unread: items.filter(\.isUnread).count,
            attention: items.filter(\.needsYou).count,
            attentionUnread: items.filter { $0.needsYou && $0.isUnread }.count,
            activity: items.filter { !$0.needsYou }.count,
            activityUnread: items.filter { !$0.needsYou && $0.isUnread }.count)
    }
}
