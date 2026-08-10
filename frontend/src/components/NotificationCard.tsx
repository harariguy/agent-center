import { useState } from "react"
import {
  Archive,
  ArrowUpRight,
  CalendarClock,
  Check,
  CheckCheck,
  CircleDot,
  Ellipsis,
  RotateCcw,
  X,
} from "lucide-react"
import { toast } from "sonner"

import { AgentIcon } from "@/components/AgentIcon"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import {
  useArchive,
  useMarkRead,
  useMarkUnread,
  useNotificationDetail,
  useSnooze,
  useUnarchive,
} from "@/hooks/use-notifications"
import type { Notification } from "@/lib/api"
import { fullTime, relTime, snoozeLabel } from "@/lib/time"
import { cn, isWebUrl } from "@/lib/utils"

/** One notification, in the anatomy of a macOS banner: icon, title, body,
    timestamp — with clear (⊗) and options (…) revealed on hover.

    `preview` renders the card as pure decoration: the top of a collapsed stack
    already sits inside the stack's own button, so its controls would nest
    interactive elements and offer keyboard users dead targets. */
export function NotificationCard({
  n,
  preview = false,
  className,
  style,
  tabIndex = 0,
  onFocus,
  onArchived,
}: {
  n: Notification
  preview?: boolean
  className?: string
  style?: React.CSSProperties
  tabIndex?: number
  onFocus?: () => void
  onArchived?: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const markRead = useMarkRead()
  const markUnread = useMarkUnread()
  const archive = useArchive()
  const unarchive = useUnarchive()
  const snooze = useSnooze()
  const detail = useNotificationDetail(n.id, expanded)

  const unread = !n.read_at
  const archived = !!n.archived_at
  const needsYou = n.category === "attention"

  const toggle = () => {
    const opening = !expanded
    setExpanded(opening)
    if (opening && unread && !archived && !needsYou) markRead.mutate(n.id)
  }

  // Every render of an action goes through this one list, so filtering here
  // covers the buttons, the dropdown item, and the "o" shortcut alike. The
  // server rejects non-http(s) URLs at ingest; this guards rows written
  // before that rule existed.
  const actions = (
    n.actions.length
      ? n.actions
      : n.source_link
        ? [{ label: `Open in ${n.source_app ?? "source"}`, url: n.source_link }]
        : []
  ).filter((a) => isWebUrl(a.url))

  const archiveWithUndo = () => {
    onArchived?.()
    archive.mutate(n.id, {
      onSuccess: () =>
        toast("Archived", {
          description: n.title,
          action: {
            label: "Undo",
            onClick: () => unarchive.mutate(n.id),
          },
        }),
    })
  }

  const snoozeUntil = (until: Date) => {
    snooze.mutate(
      { id: n.id, until: until.toISOString() },
      {
        onSuccess: () =>
          toast("Snoozed", {
            description: `Returns ${snoozeLabel(until.toISOString())}, or sooner if it changes.`,
          }),
      },
    )
  }

  const tomorrowMorning = () => {
    const tomorrow = new Date()
    tomorrow.setDate(tomorrow.getDate() + 1)
    tomorrow.setHours(9, 0, 0, 0)
    return tomorrow
  }

  const nextWeek = () => {
    const date = new Date()
    date.setDate(date.getDate() + 7)
    date.setHours(9, 0, 0, 0)
    return date
  }

  return (
    <div
      className={cn("group relative", className)}
      style={style}
      data-notification-id={preview ? undefined : n.id}
    >
      {/* clear — the macOS ⊗, floating off the top-left corner on hover */}
      {!archived && !preview && (
        <button
          type="button"
          aria-label={`Clear “${n.title}”`}
          onClick={(e) => {
            e.stopPropagation()
            archiveWithUndo()
          }}
          data-archive-action
          className={cn(
            "glass-heavy absolute -left-1.5 -top-1.5 z-10 flex size-6 items-center justify-center rounded-full",
            "text-foreground/80 opacity-55 transition-opacity duration-150",
            "hover:text-foreground hover:opacity-100 group-hover:opacity-100 focus-visible:opacity-100",
            "focus-visible:outline-2 focus-visible:outline-ring",
          )}
        >
          <X className="size-3.5" strokeWidth={2.5} />
        </button>
      )}

      <div
        {...(preview
          ? {}
          : {
              role: "button",
              tabIndex,
              "aria-expanded": expanded,
              onClick: toggle,
              onFocus,
              onKeyDown: (e: React.KeyboardEvent) => {
                // Keydowns bubble up from the nested buttons and links; acting
                // on those would toggle the card when the user meant "Done".
                if (e.target !== e.currentTarget) return
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  toggle()
                } else if (e.key.toLowerCase() === "e" && !archived) {
                  e.preventDefault()
                  archiveWithUndo()
                } else if (e.key.toLowerCase() === "u" && !archived) {
                  e.preventDefault()
                  if (unread) markRead.mutate(n.id)
                  else markUnread.mutate(n.id)
                } else if (e.key.toLowerCase() === "o" && actions[0]) {
                  e.preventDefault()
                  window.open(actions[0].url, "_blank", "noopener,noreferrer")
                }
              },
            })}
        className={cn(
          "glass w-full rounded-[18px] border-l-[3px] p-3 text-left",
          n.priority === "urgent"
            ? "border-l-destructive"
            : n.priority === "high"
              ? "border-l-orange"
              : "border-l-transparent",
          !unread && !archived && "opacity-80 hover:opacity-100 focus:opacity-100",
          !preview && [
            "cursor-pointer transition-[transform,box-shadow] duration-150 hover:-translate-y-px",
            "focus-visible:outline-2 focus-visible:outline-ring",
            "motion-reduce:transition-none motion-reduce:hover:translate-y-0",
          ],
        )}
      >
        <div className="flex gap-2.5">
          <AgentIcon name={n.agent_name} />

          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <span className="flex min-w-0 items-center gap-1.5 text-[13px] font-semibold leading-tight">
                {unread && !archived && (
                  <span
                    className="size-2 shrink-0 rounded-full bg-primary"
                    role="img"
                    aria-label="Unread"
                  />
                )}
                <span className="truncate">{n.title}</span>
              </span>

              <span
                className={cn(
                  "ml-auto shrink-0 pl-1 text-[11px] text-muted-foreground",
                  !preview && "pr-7",
                )}
              >
                {relTime(n.last_seen_at)}
              </span>
            </div>

            <p
              className={cn(
                "text-[13px] leading-snug text-foreground/75",
                !expanded && "line-clamp-2",
              )}
            >
              {n.body || <span className="text-muted-foreground">{n.type}</span>}
            </p>

            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className="font-medium">{n.agent_name}</span>
              {n.source_app && (
                <>
                  <span aria-hidden>·</span>
                  <span>{n.source_app}</span>
                </>
              )}
              {needsYou && (
                <Badge className="h-4 rounded-full bg-destructive/15 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-destructive">
                  needs you
                </Badge>
              )}
              {(n.priority === "high" || n.priority === "urgent") && (
                <Badge className="h-4 rounded-full bg-orange/15 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-orange">
                  {n.priority}
                </Badge>
              )}
              {n.occurrences > 1 && (
                <Badge
                  variant="secondary"
                  className="h-4 rounded-full px-1.5 text-[10px] font-semibold tabular-nums"
                >
                  ×{n.occurrences}
                </Badge>
              )}
              {n.tags.slice(0, 3).map((tag) => (
                <span
                  key={tag}
                  className="rounded-full bg-secondary/70 px-1.5 font-medium text-foreground/55"
                >
                  #{tag}
                </span>
              ))}
              {n.tags.length > 3 && <span>+{n.tags.length - 3}</span>}
              {n.snoozed_until && (
                <Badge
                  variant="secondary"
                  className="h-4 rounded-full px-1.5 text-[10px] font-semibold"
                >
                  <CalendarClock className="size-2.5" />
                  snooze ended
                </Badge>
              )}
            </div>
          </div>
        </div>

        {!preview && !expanded && (needsYou || archived) && (
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5 pl-12.5">
            {needsYou && !archived && actions[0] && (
              <Button
                asChild
                size="sm"
                variant="secondary"
                className="h-7 rounded-full px-3 text-[12px] font-medium"
                onClick={(e) => e.stopPropagation()}
              >
                <a
                  href={actions[0].url}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-primary-action
                >
                  {actions[0].label}
                  <ArrowUpRight className="size-3.5" />
                </a>
              </Button>
            )}
            {needsYou && !archived && (
              <Button
                size="sm"
                className="h-7 rounded-full px-3 text-[12px] font-semibold"
                onClick={(e) => {
                  e.stopPropagation()
                  archiveWithUndo()
                }}
                data-archive-action
              >
                <CheckCheck className="size-3.5" />
                Done
              </Button>
            )}
            {archived && (
              <Button
                size="sm"
                variant="secondary"
                className="h-7 rounded-full px-3 text-[12px] font-medium"
                onClick={(e) => {
                  e.stopPropagation()
                  unarchive.mutate(n.id)
                }}
              >
                <RotateCcw className="size-3.5" />
                Restore
              </Button>
            )}
          </div>
        )}

        {expanded && (
          <div className="mt-2.5 animate-in fade-in duration-200">
            <Separator className="mb-2.5 bg-border" />

            {actions.length > 0 && (
              <div className="mb-2.5 flex flex-wrap gap-1.5">
                {actions.map((a) => (
                  <Button
                    key={a.url + a.label}
                    asChild
                    size="sm"
                    variant="secondary"
                    className="h-7 rounded-full px-3 text-[12px] font-medium"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <a
                      href={a.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      data-primary-action={a === actions[0] ? "" : undefined}
                    >
                      {a.label}
                      <ArrowUpRight className="size-3.5" />
                    </a>
                  </Button>
                ))}
              </div>
            )}

            {detail.isPending ? (
              <Skeleton className="h-4 w-48 rounded-md" />
            ) : detail.data ? (
              <div className="space-y-0.5 text-[11px] leading-relaxed text-muted-foreground">
                <div>
                  <span className="font-semibold text-foreground/70">
                    {detail.data.history.length}
                  </span>{" "}
                  occurrence{detail.data.history.length === 1 ? "" : "s"}
                  {n.group_key && (
                    <>
                      {" · grouped by "}
                      <span className="font-mono text-foreground/70">{n.group_key}</span>
                    </>
                  )}
                </div>
                {detail.data.history
                  .slice(-5)
                  .reverse()
                  .map((o) => (
                    <div key={o.id} className="tabular-nums">
                      {fullTime(o.seen_at)}
                    </div>
                  ))}
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* options — appears where the timestamp was, on hover */}
      {!preview && (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Options for “${n.title}”`}
            onClick={(e) => e.stopPropagation()}
            className={cn(
              "absolute right-2 top-2 size-6 rounded-full text-muted-foreground",
              "opacity-55 transition-opacity duration-150",
              "hover:opacity-100 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100",
            )}
          >
            <Ellipsis className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          className="glass-heavy min-w-44 rounded-xl border-none"
          onClick={(e) => e.stopPropagation()}
        >
          {unread ? (
            <DropdownMenuItem onClick={() => markRead.mutate(n.id)}>
              <Check /> Mark as read
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem onClick={() => markUnread.mutate(n.id)}>
              <CircleDot /> Mark as unread
            </DropdownMenuItem>
          )}
          {actions[0] && (
            <DropdownMenuItem asChild>
              <a href={actions[0].url} target="_blank" rel="noopener noreferrer">
                <ArrowUpRight /> {actions[0].label}
              </a>
            </DropdownMenuItem>
          )}
          {!archived && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => snoozeUntil(new Date(Date.now() + 60 * 60 * 1000))}
              >
                <CalendarClock /> Snooze for 1 hour
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => snoozeUntil(tomorrowMorning())}>
                <CalendarClock /> Snooze until tomorrow
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => snoozeUntil(nextWeek())}>
                <CalendarClock /> Snooze for 1 week
              </DropdownMenuItem>
            </>
          )}
          {!archived && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                onClick={archiveWithUndo}
              >
                <Archive /> Archive
              </DropdownMenuItem>
            </>
          )}
          {archived && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => unarchive.mutate(n.id)}>
                <RotateCcw /> Restore to feed
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      )}
    </div>
  )
}
