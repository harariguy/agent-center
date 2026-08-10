import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { BellOff, Keyboard, Loader2 } from "lucide-react"

import { KeyboardShortcutsDialog } from "@/components/KeyboardShortcutsDialog"
import { NotificationCard } from "@/components/NotificationCard"
import { NotificationStack } from "@/components/NotificationStack"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useFeed } from "@/hooks/use-notifications"
import type { FeedFilters, Notification } from "@/lib/api"
import type { View } from "@/lib/filters"
import { dateGroup } from "@/lib/time"

/** Group the feed into per-agent stacks, ordered by each stack's newest item
    (the feed itself is already newest-first). */
function groupByAgent(items: Notification[]): [string, Notification[]][] {
  const groups = new Map<string, Notification[]>()
  for (const n of items) {
    const list = groups.get(n.agent_name) ?? []
    list.push(n)
    groups.set(n.agent_name, list)
  }
  return [...groups.entries()]
}

export function NotificationFeed({
  filters,
  view,
  narrowed,
  onClearFilters,
}: {
  filters: FeedFilters
  view: View
  narrowed: boolean
  onClearFilters: () => void
}) {
  const feed = useFeed(filters)
  const loadMoreRef = useRef<HTMLDivElement>(null)
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  const items = useMemo(
    () => feed.data?.pages.flatMap((p) => p.items) ?? [],
    [feed.data],
  )
  const groups = useMemo(() => groupByAgent(items), [items])
  const flat = view === "attention" || view === "archived"
  const navigableItems = useMemo(
    () => (flat ? items : groups.map(([, groupItems]) => groupItems[0])),
    [flat, groups, items],
  )

  const focusNotification = useCallback((id: string) => {
    const container = document.querySelector<HTMLElement>(
      `[data-notification-id="${id}"]`,
    )
    const target =
      container?.matches("button, [role=button]")
        ? container
        : container?.querySelector<HTMLElement>("[role=button]")
    target?.focus({ preventScroll: false })
  }, [])

  useEffect(() => {
    if (!navigableItems.length) {
      setFocusedId(null)
    } else if (
      !focusedId ||
      !navigableItems.some((item) => item.id === focusedId)
    ) {
      setFocusedId(navigableItems[0].id)
    }
  }, [focusNotification, focusedId, navigableItems])

  useEffect(() => {
    const sentinel = loadMoreRef.current
    if (!sentinel || !feed.hasNextPage) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !feed.isFetchingNextPage) {
          feed.fetchNextPage()
        }
      },
      { rootMargin: "160px" },
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [feed.fetchNextPage, feed.hasNextPage, feed.isFetchingNextPage])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (
        target?.closest(
          "input, textarea, select, [contenteditable=true], [role=menu], [role=dialog]",
        )
      ) {
        return
      }
      if (event.key === "?") {
        event.preventDefault()
        setShortcutsOpen(true)
        return
      }
      if (!["j", "k", "ArrowDown", "ArrowUp"].includes(event.key)) return
      event.preventDefault()
      if (!navigableItems.length) return
      const current = Math.max(
        0,
        navigableItems.findIndex((item) => item.id === focusedId),
      )
      const delta = event.key === "j" || event.key === "ArrowDown" ? 1 : -1
      const next = Math.min(
        navigableItems.length - 1,
        Math.max(0, current + delta),
      )
      const id = navigableItems[next].id
      setFocusedId(id)
      focusNotification(id)
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [focusedId, navigableItems])

  const focusAfterArchive = (id: string) => {
    const current = items.findIndex((item) => item.id === id)
    const next = items[current + 1] ?? items[current - 1]
    setFocusedId(next?.id ?? null)
    if (next) {
      window.setTimeout(() => focusNotification(next.id), 0)
    }
  }

  if (feed.isPending) {
    return (
      <div className="flex flex-col gap-2" aria-label="Loading notifications">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="glass h-21.5 rounded-[18px]" />
        ))}
      </div>
    )
  }

  if (feed.isError) {
    return (
      <EmptyState
        title="Can’t reach the server"
        hint="The feed will retry automatically. Check that agent-notifications is running."
      />
    )
  }

  if (items.length === 0) {
    return narrowed ? (
      <EmptyState title="Nothing matches these filters">
        <Button
          variant="ghost"
          size="sm"
          onClick={onClearFilters}
          className="mt-1 h-7 rounded-full border border-border/60 bg-card/60 px-3 text-[12px]"
        >
          Clear filters
        </Button>
      </EmptyState>
    ) : (
      <EmptyState
        title={view === "archived" ? "Nothing archived" : "No new notifications"}
        hint={
          view === "archived"
            ? undefined
            : "When an agent posts to /api/v1/notifications, it shows up here."
        }
      />
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {view === "attention" && (
        <div className="mb-0.5 flex items-center gap-2 px-1 text-[11px] text-muted-foreground">
          <span>Sorted by urgency, then time</span>
          <span aria-hidden>·</span>
          <button
            type="button"
            onClick={() => setShortcutsOpen(true)}
            className="inline-flex items-center gap-1 rounded-md hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
          >
            <Keyboard className="size-3" />
            Shortcuts
          </button>
        </div>
      )}

      {flat
        ? items.map((n, index) => {
            const label = dateGroup(n.last_seen_at)
            const previous =
              index > 0 ? dateGroup(items[index - 1].last_seen_at) : null
            return (
              <div key={n.id} className="contents">
                {label !== previous && (
                  <div className="mb-0.5 mt-2 flex items-center gap-2 px-1 first:mt-0">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-foreground/45">
                      {label}
                    </span>
                    <span className="h-px flex-1 bg-border/70" aria-hidden />
                  </div>
                )}
                <NotificationCard
                  n={n}
                  tabIndex={focusedId === n.id ? 0 : -1}
                  onFocus={() => setFocusedId(n.id)}
                  onArchived={() => focusAfterArchive(n.id)}
                />
              </div>
            )
          })
        : groups.map(([agentName, groupItems]) => (
            <NotificationStack
              key={agentName}
              agentName={agentName}
              items={groupItems}
            />
          ))}

      <div ref={loadMoreRef} className="flex h-8 items-center justify-center">
        {feed.isFetchingNextPage && (
          <Loader2
            className="size-4 animate-spin text-muted-foreground"
            aria-label="Loading older notifications"
          />
        )}
      </div>
      <KeyboardShortcutsDialog
        open={shortcutsOpen}
        onOpenChange={setShortcutsOpen}
      />
    </div>
  )
}

function EmptyState({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 pb-10 pt-20 text-center">
      <BellOff className="size-6 text-foreground/25" aria-hidden />
      <p className="text-[15px] font-semibold text-foreground/60">{title}</p>
      {hint && <p className="max-w-72 text-[12px] text-foreground/45">{hint}</p>}
      {children}
    </div>
  )
}
