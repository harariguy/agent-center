// Relative times in the Agent Notifications dialect: "now", "5m ago", "yesterday".

/** API timestamps are UTC, but SQLite hands them back without an offset —
    and `new Date` reads offset-less strings as local time. Pin those to UTC. */
export function parseTimestamp(iso: string): Date {
  return new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + "Z")
}

export function relTime(iso: string): string {
  const seconds = (Date.now() - parseTimestamp(iso).getTime()) / 1000
  if (seconds < 60) return "now"
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 2 * 86400) return "yesterday"
  if (seconds < 7 * 86400) return `${Math.floor(seconds / 86400)}d ago`
  return parseTimestamp(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  })
}

export function fullTime(iso: string): string {
  return parseTimestamp(iso).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

export function dateGroup(iso: string): string {
  const date = parseTimestamp(iso)
  const today = new Date()
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const days = Math.round((startToday.getTime() - startDate.getTime()) / 86_400_000)
  if (days === 0) return "Today"
  if (days === 1) return "Yesterday"
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  })
}

export function snoozeLabel(iso: string): string {
  return parseTimestamp(iso).toLocaleString(undefined, {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  })
}
