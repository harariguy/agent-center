import SwiftUI

/// One place for the visual language, so cards, header and empty states can't
/// drift apart. Everything is expressed in semantic colours and materials, so
/// light and dark both come out right without a second palette.
enum DS {
    // MARK: spacing — a 4pt scale, used everywhere

    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 12
    static let lg: CGFloat = 16

    static let cardRadius: CGFloat = 10
    static let chipRadius: CGFloat = 5
    static let panelWidth: CGFloat = 400
    static let panelHeight: CGFloat = 520

    // MARK: type

    static let title = Font.system(size: 13)
    static let body = Font.system(size: 11.5)
    static let meta = Font.system(size: 10.5)
    static let sectionHeader = Font.system(size: 10, weight: .semibold)

    // MARK: colour

    /// Priority reads as urgency, so it earns colour. Everything else is neutral.
    static func accent(_ priority: String) -> Color {
        switch priority {
        case "urgent": .red
        case "high":   .orange
        case "normal": .accentColor
        case "low":    .secondary
        default:       .secondary
        }
    }

    static func surface(unread: Bool, hovered: Bool) -> Color {
        if hovered { return Color.primary.opacity(unread ? 0.085 : 0.06) }
        return Color.primary.opacity(unread ? 0.055 : 0.03)
    }

    static func border(hovered: Bool) -> Color {
        Color.primary.opacity(hovered ? 0.14 : 0.08)
    }

    /// SF Symbol standing in for the source app.
    static func glyph(_ app: String?) -> String {
        switch app?.lowercased() {
        case "github":            "chevron.left.forwardslash.chevron.right"
        case "linear":            "square.stack.3d.up"
        case "slack":             "number"
        case "gmail", "mail":     "envelope"
        case "intercom":          "bubble.left.and.bubble.right"
        case "notion":            "doc.text"
        case "stripe":            "creditcard"
        case "cron", "scheduler": "clock.arrow.circlepath"
        case "sentry":            "exclamationmark.triangle"
        default:                  "sparkle"
        }
    }

    // MARK: time

    static func relative(_ date: Date) -> String {
        let elapsed = Date().timeIntervalSince(date)
        if elapsed < 60 { return "just now" }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    static func dayHeading(_ date: Date) -> String {
        let calendar = Calendar.current
        if calendar.isDateInToday(date) { return "Today" }
        if calendar.isDateInYesterday(date) { return "Yesterday" }
        let formatter = DateFormatter()
        formatter.dateFormat = calendar.isDate(date, equalTo: Date(), toGranularity: .year)
            ? "EEEE, MMM d" : "MMM d, yyyy"
        return formatter.string(from: date)
    }
}

/// Small neutral label used for the origin and for tags.
struct Chip: View {
    var text: String
    var systemImage: String?
    var prominent = false

    var body: some View {
        HStack(spacing: 3) {
            if let systemImage {
                Image(systemName: systemImage).font(.system(size: 9, weight: .medium))
            }
            Text(text)
                .font(.system(size: 10, weight: .medium))
                .lineLimit(1)
        }
        .foregroundStyle(prominent ? AnyShapeStyle(.white) : AnyShapeStyle(.secondary))
        .padding(.horizontal, 5)
        .padding(.vertical, 2)
        .background(
            RoundedRectangle(cornerRadius: DS.chipRadius)
                .fill(prominent ? AnyShapeStyle(Color.orange) : AnyShapeStyle(Color.primary.opacity(0.07)))
        )
    }
}

/// Borderless icon button sized for the card's hover row.
struct IconButton: View {
    var systemImage: String
    var help: String
    var action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 11, weight: .medium))
                .frame(width: 22, height: 20)
                .background(
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.primary.opacity(hovered ? 0.1 : 0))
                )
        }
        .buttonStyle(.plain)
        .foregroundStyle(.secondary)
        .onHover { hovered = $0 }
        .help(help)
    }
}
