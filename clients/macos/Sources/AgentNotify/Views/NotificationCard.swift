import SwiftUI

/// One notification. The card carries a priority accent only while unread, so a
/// triaged feed goes visually quiet instead of staying loud.
struct NotificationCard: View {
    let item: Item
    @Environment(Store.self) private var store
    @State private var hovered = false

    var body: some View {
        HStack(spacing: 0) {
            accentBar

            VStack(alignment: .leading, spacing: DS.xs + 2) {
                topRow
                titleText
                bodyText
                if !item.tags.isEmpty { tagRow }
                footer
            }
            .padding(DS.sm + 2)
        }
        .background(
            RoundedRectangle(cornerRadius: DS.cardRadius)
                .fill(DS.surface(unread: item.isUnread, hovered: hovered))
        )
        .overlay(
            RoundedRectangle(cornerRadius: DS.cardRadius)
                .strokeBorder(DS.border(hovered: hovered), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: DS.cardRadius))
        .contentShape(Rectangle())
        .onTapGesture { store.open(item) }
        .onHover { hovered = $0 }
        .animation(.easeOut(duration: 0.12), value: hovered)
    }

    private var accentBar: some View {
        Rectangle()
            .fill(DS.accent(item.priority))
            .frame(width: 3)
            .opacity(item.isUnread ? 1 : 0)
    }

    private var topRow: some View {
        HStack(spacing: DS.xs + 1) {
            Chip(text: item.agentName, systemImage: "sparkle")

            if let sourceApp = distinctSourceApp {
                Chip(text: sourceApp, systemImage: DS.glyph(sourceApp))
            }

            // Source and agent are separate facts: Linear may be where the work
            // lives, while the agent name says who surfaced it.
            if item.needsYou {
                Chip(text: "NEEDS YOU", prominent: true)
            }

            if item.occurrences > 1 {
                Text("×\(item.occurrences)")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.tertiary)
                    .help("Raised \(item.occurrences) times since \(DS.relative(item.firstSeenAt))")
            }

            Spacer(minLength: DS.xs)

            Text(DS.relative(item.lastSeenAt))
                .font(DS.meta)
                .foregroundStyle(.tertiary)
                .help(item.lastSeenAt.formatted(date: .abbreviated, time: .shortened))
        }
    }

    private var distinctSourceApp: String? {
        guard let sourceApp = item.sourceApp,
              !sourceApp.isEmpty,
              sourceApp.localizedCaseInsensitiveCompare(item.agentName) != .orderedSame
        else { return nil }
        return sourceApp
    }

    private var titleText: some View {
        Text(item.title)
            .font(DS.title.weight(item.isUnread ? .semibold : .regular))
            .foregroundStyle(item.isUnread ? .primary : .secondary)
            .multilineTextAlignment(.leading)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private var bodyText: some View {
        if !item.body.isEmpty {
            Text(item.body)
                .font(DS.body)
                .foregroundStyle(.secondary)
                .lineLimit(hovered ? 5 : 2)
                .fixedSize(horizontal: false, vertical: true)
                .animation(.easeOut(duration: 0.12), value: hovered)
        }
    }

    private var tagRow: some View {
        HStack(spacing: DS.xs) {
            ForEach(item.tags.prefix(4), id: \.self) { Chip(text: $0) }
        }
    }

    private var footer: some View {
        HStack(spacing: DS.sm) {
            ForEach(Array(item.actions.prefix(2).enumerated()), id: \.offset) { index, action in
                Button(action.label) { store.open(action, on: item) }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(index == 0 ? Color.accentColor : Color.secondary)
            }

            Spacer(minLength: 0)

            // Triage controls stay hidden until the pointer is on the card, so
            // a resting feed is only content.
            if hovered {
                HStack(spacing: 1) {
                    IconButton(systemImage: item.isUnread ? "envelope.open" : "envelope",
                               help: item.isUnread ? "Mark as read" : "Mark as unread") {
                        store.toggleRead(item)
                    }
                    snoozeMenu
                    IconButton(systemImage: "archivebox", help: "Archive") {
                        store.archive(item)
                    }
                }
                .transition(.opacity)
            }
        }
        .frame(height: 20)
    }

    private var snoozeMenu: some View {
        Menu {
            Button("For 1 hour") { store.snooze(item, until: Date().addingTimeInterval(3600)) }
            Button("For 3 hours") { store.snooze(item, until: Date().addingTimeInterval(3 * 3600)) }
            Button("Until tomorrow") { store.snooze(item, until: tomorrowMorning) }
        } label: {
            Image(systemName: "clock")
                .font(.system(size: 11, weight: .medium))
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .frame(width: 22, height: 20)
        .foregroundStyle(.secondary)
        .help("Snooze")
    }

    private var tomorrowMorning: Date {
        let calendar = Calendar.current
        let tomorrow = calendar.date(byAdding: .day, value: 1, to: Date()) ?? Date()
        return calendar.date(bySettingHour: 9, minute: 0, second: 0, of: tomorrow) ?? tomorrow
    }
}
