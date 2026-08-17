import Foundation

enum APIError: LocalizedError, Equatable {
    case notConfigured
    case unauthorized
    case unreachable(String)
    case http(Int)

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            "Not connected yet."
        case .unauthorized:
            "Credentials rejected. Check the viewer token or admin password."
        case .unreachable(let why):
            "Can't reach the server — \(why)"
        case .http(let code):
            "Server returned HTTP \(code)."
        }
    }

    /// Whether showing this to the user should point them at Settings.
    var isCredentialProblem: Bool {
        self == .unauthorized || self == .notConfigured
    }
}

/// A facets response whose ETag is only accepted after the matching feed has
/// also been fetched successfully.
struct CountsUpdate {
    let counts: Counts
    let eTag: String?
}

/// The read + triage half of the API.
///
/// The poll is built around one property of the server: `/notifications/facets`
/// carries an ETag over its entire payload, counts included. When nothing has
/// changed it answers 304 with no body, so the steady state is nearly free and
/// the feed is only refetched when something actually moved.
actor APIClient {
    private var baseURL: URL?
    private var viewerToken = ""
    private var adminPassword = ""

    private let session: URLSession
    private var facetsETag: String?
    private var haveSession = false

    init() {
        let config = URLSessionConfiguration.default
        config.httpCookieStorage = .shared
        config.httpShouldSetCookies = true
        // Fail fast rather than wait for connectivity. A request parked in
        // waitsForConnectivity ignores timeoutIntervalForRequest and sits on
        // the resource default of seven days — after a sleep or VPN flap that
        // parked await wedged the poll loop for good. The Store's backoff
        // owns retries, so a quick failure costs one tick, not the app.
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 60
        config.waitsForConnectivity = false
        // URLSession must not run its own cache. With a URLCache installed it
        // performs its own conditional revalidation and returns a synthesized
        // 200 from cache, so our If-None-Match never surfaces as a 304 and the
        // ETag optimisation silently does nothing.
        config.urlCache = nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: config)
    }

    func configure(url: String, viewerToken: String, adminPassword: String) {
        let newBase = URL(string: url.trimmingCharacters(in: .whitespacesAndNewlines))
        let changed = newBase != baseURL
            || viewerToken != self.viewerToken
            || adminPassword != self.adminPassword
        guard changed else { return }
        baseURL = newBase
        self.viewerToken = viewerToken
        self.adminPassword = adminPassword
        facetsETag = nil
        haveSession = false
    }

    /// Force the next poll to fetch rather than short-circuit on 304.
    func invalidate() { facetsETag = nil }

    // MARK: - plumbing

    private func makeRequest(_ path: String, method: String = "GET") throws -> URLRequest {
        guard !viewerToken.isEmpty || !adminPassword.isEmpty else { throw APIError.notConfigured }
        guard let base = baseURL, let url = URL(string: path, relativeTo: base) else {
            throw APIError.notConfigured
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        if !viewerToken.isEmpty {
            request.setValue("Bearer \(viewerToken)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else { throw APIError.http(0) }
            return (data, http)
        } catch let error as URLError {
            throw APIError.unreachable(error.localizedDescription)
        }
    }

    /// A viewer token authenticates per-request; the admin password is exchanged
    /// once for a session cookie that URLSession then carries.
    private func ensureSession() async throws {
        guard viewerToken.isEmpty else { return }
        guard !haveSession else { return }
        guard !adminPassword.isEmpty else { throw APIError.notConfigured }

        var request = try makeRequest("/api/v1/session", method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["password": adminPassword])

        let (_, http) = try await send(request)
        guard http.statusCode == 204 || http.statusCode == 200 else { throw APIError.unauthorized }
        haveSession = true
    }

    // MARK: - reads

    /// nil means "304 — nothing changed since the last completed poll".
    ///
    /// The returned ETag is deliberately not stored here. The caller accepts it
    /// only after fetching the corresponding feed, so a failed feed request
    /// cannot make every later poll short-circuit on 304.
    func pollCounts() async throws -> CountsUpdate? {
        try await ensureSession()
        var request = try makeRequest("/api/v1/notifications/facets")
        if let tag = facetsETag { request.setValue(tag, forHTTPHeaderField: "If-None-Match") }

        let (data, http) = try await send(request)
        switch http.statusCode {
        case 304:
            return nil
        case 200:
            let counts = try ServerDate.decoder.decode(Facets.self, from: data).counts
            return CountsUpdate(counts: counts, eTag: http.value(forHTTPHeaderField: "ETag"))
        case 401:
            haveSession = false
            throw APIError.unauthorized
        default:
            throw APIError.http(http.statusCode)
        }
    }

    func accept(_ update: CountsUpdate) {
        facetsETag = update.eTag
    }

    func fetchFeed(pageSize: Int = 200) async throws -> [Item] {
        try await ensureSession()
        let limit = min(max(pageSize, 1), 200)
        var items: [Item] = []
        var cursor: String?

        repeat {
            var path = "/api/v1/notifications?limit=\(limit)"
            if let cursor {
                path += "&cursor=\(cursor)"
            }

            let (data, http) = try await send(try makeRequest(path))
            if http.statusCode == 401 { haveSession = false; throw APIError.unauthorized }
            guard http.statusCode == 200 else { throw APIError.http(http.statusCode) }

            let page = try ServerDate.decoder.decode(FeedPage.self, from: data)
            items.append(contentsOf: page.items)
            cursor = page.nextCursor
        } while cursor != nil

        return items
    }

    /// Used by Settings to give the user a straight yes/no.
    func verify() async throws -> Counts {
        haveSession = false
        facetsETag = nil
        guard let update = try await pollCounts() else { throw APIError.http(304) }
        return update.counts
    }

    // MARK: - writes

    private func post(_ path: String, body: Data? = nil) async throws {
        // Optimistic UI updates must always be reconciled with the server,
        // including when this write fails.
        facetsETag = nil
        try await ensureSession()
        var request = try makeRequest(path, method: "POST")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (_, http) = try await send(request)
        if http.statusCode == 401 { haveSession = false; throw APIError.unauthorized }
        guard (200...299).contains(http.statusCode) else { throw APIError.http(http.statusCode) }
    }

    func markRead(_ id: String) async throws { try await post("/api/v1/notifications/\(id)/read") }
    func markUnread(_ id: String) async throws { try await post("/api/v1/notifications/\(id)/unread") }
    func archive(_ id: String) async throws { try await post("/api/v1/notifications/\(id)/archive") }
    func markAllRead() async throws { try await post("/api/v1/notifications/read-all") }

    func snooze(_ id: String, until: Date) async throws {
        let body = try JSONEncoder().encode(["until": ServerDate.iso(until)])
        try await post("/api/v1/notifications/\(id)/snooze", body: body)
    }
}
