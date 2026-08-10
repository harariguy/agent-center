import Foundation

// Wire types — mirror agent_notifications/schemas.py.

enum ExternalURL {
    /// Agent-supplied links leave the app, so only ordinary web URLs are safe
    /// to hand to NSWorkspace. In particular, reject file: and custom schemes.
    static func parse(_ raw: String) -> URL? {
        guard let url = URL(string: raw),
              let scheme = url.scheme?.lowercased(),
              scheme == "https" || scheme == "http",
              url.host != nil
        else { return nil }
        return url
    }
}

struct Action: Decodable, Hashable {
    let label: String
    let url: String

    var parsedURL: URL? { ExternalURL.parse(url) }
}

struct Item: Decodable, Identifiable, Hashable {
    let id: String
    let agentName: String
    let groupKey: String?
    let category: String       // activity | attention
    let type: String
    let priority: String       // min | low | normal | high | urgent
    let title: String
    let body: String
    let sourceApp: String?
    let sourceLink: String?
    let actions: [Action]
    let tags: [String]
    let occurrences: Int
    let firstSeenAt: Date
    let lastSeenAt: Date
    let readAt: Date?
    let snoozedUntil: Date?
    let archivedAt: Date?

    var isUnread: Bool { readAt == nil }
    var needsYou: Bool { category == "attention" }

    var primaryLink: URL? {
        if let link = sourceLink, let url = ExternalURL.parse(link) { return url }
        return actions.first?.parsedURL
    }

    /// What to show as the origin chip when no source app was supplied.
    var originLabel: String { sourceApp ?? agentName }

    func with(readAt newValue: Date?) -> Item {
        Item(id: id, agentName: agentName, groupKey: groupKey, category: category,
             type: type, priority: priority, title: title, body: body,
             sourceApp: sourceApp, sourceLink: sourceLink, actions: actions, tags: tags,
             occurrences: occurrences, firstSeenAt: firstSeenAt, lastSeenAt: lastSeenAt,
             readAt: newValue, snoozedUntil: snoozedUntil, archivedAt: archivedAt)
    }
}

struct FeedPage: Decodable {
    let items: [Item]
    let nextCursor: String?
}

struct FacetValue: Decodable, Hashable {
    let value: String
    let label: String?
    let count: Int
}

struct Counts: Decodable, Hashable {
    let total: Int
    let unread: Int
    let attention: Int
    let attentionUnread: Int
    let activity: Int
    let activityUnread: Int

    static let zero = Counts(total: 0, unread: 0, attention: 0,
                             attentionUnread: 0, activity: 0, activityUnread: 0)
}

struct Facets: Decodable {
    let agents: [FacetValue]
    let types: [FacetValue]
    let priorities: [FacetValue]
    let sourceApps: [FacetValue]
    let tags: [FacetValue]
    let counts: Counts
}

// MARK: - Timestamps

/// The server stores timestamps as timezone-aware UTC, but SQLite hands them
/// back *naive* ("2026-08-05T19:05:50.569219" — no offset). Read literally,
/// Foundation would treat those as local time and every relative time would be
/// wrong by the UTC offset. Pin them to UTC, matching the web client's
/// `frontend/src/lib/time.ts`.
enum ServerDate {
    static func parse(_ raw: String) -> Date? {
        var s = raw

        // ISO8601DateFormatter is unreliable past millisecond precision.
        if let dot = s.firstIndex(of: ".") {
            let start = s.index(after: dot)
            var end = start
            while end < s.endIndex, s[end].isNumber { end = s.index(after: end) }
            if s.distance(from: start, to: end) > 3 {
                let keep = s[start..<s.index(start, offsetBy: 3)]
                s.replaceSubrange(start..<end, with: keep)
            }
        }

        let hasZone = s.hasSuffix("Z") || s.hasSuffix("z")
            || s.range(of: "[+-][0-9]{2}:?[0-9]{2}$", options: .regularExpression) != nil
        if !hasZone { s += "Z" }

        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: s) { return date }

        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        return plain.date(from: s)
    }

    static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { d in
            let raw = try d.singleValueContainer().decode(String.self)
            guard let date = parse(raw) else {
                throw DecodingError.dataCorrupted(
                    .init(codingPath: d.codingPath,
                          debugDescription: "unparseable timestamp: \(raw)"))
            }
            return date
        }
        return decoder
    }

    static func iso(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: date)
    }
}
