import { useState } from "react"
import { X } from "lucide-react"
import { toast } from "sonner"

import { NotificationCard } from "@/components/NotificationCard"
import { Button } from "@/components/ui/button"
import { useArchive, useUnarchive } from "@/hooks/use-notifications"
import type { Notification } from "@/lib/api"
import { cn } from "@/lib/utils"

/** Notifications from one agent, collapsed into a macOS-style stack: the
    newest card on top, the rest peeking out beneath. Click to fan out. */
export function NotificationStack({
  agentName,
  items,
}: {
  agentName: string
  items: Notification[]
}) {
  const [open, setOpen] = useState(false)
  const archive = useArchive()
  const unarchive = useUnarchive()

  const archiveAll = () => {
    void Promise.all(items.map((n) => archive.mutateAsync(n.id)))
      .then(() => {
        toast(`Archived ${items.length} notifications`, {
          description: agentName,
          action: {
            label: "Undo",
            onClick: () => items.forEach((n) => unarchive.mutate(n.id)),
          },
        })
      })
      .catch(() => {
        // Each mutation reports its API error through the shared mutation cache.
      })
  }

  if (items.length === 1) {
    return <NotificationCard n={items[0]} />
  }

  if (!open) {
    return (
      <div className="group/stack relative">
        {/* clear the whole stack */}
        <button
          type="button"
          aria-label={`Clear all ${items.length} notifications from ${agentName}`}
          onClick={archiveAll}
          className={cn(
            "glass-heavy absolute -left-1.5 -top-1.5 z-10 flex size-6 items-center justify-center rounded-full",
            "text-foreground/80 opacity-55 transition-opacity duration-150",
            "hover:text-foreground hover:opacity-100 group-hover/stack:opacity-100 focus-visible:opacity-100",
            "focus-visible:outline-2 focus-visible:outline-ring",
          )}
        >
          <X className="size-3.5" strokeWidth={2.5} />
        </button>

        <button
          type="button"
          data-notification-id={items[0].id}
          aria-expanded={false}
          aria-label={`${items.length} notifications from ${agentName}. Show more.`}
          onClick={() => setOpen(true)}
          className={cn(
            "relative block w-full cursor-pointer pb-2.5 text-left",
            "transition-transform duration-150 hover:-translate-y-px",
            "focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2 rounded-[18px]",
            "motion-reduce:transition-none motion-reduce:hover:translate-y-0",
          )}
        >
          {/* the cards peeking out underneath — each one steps further down and
              further in, so the stack reads as depth rather than one tall slab */}
          <div
            aria-hidden
            className="glass absolute inset-x-4 top-3 bottom-0 -z-20 rounded-[18px]"
          />
          <div
            aria-hidden
            className="glass absolute inset-x-2 top-1.5 bottom-1 -z-10 rounded-[18px]"
          />
          <NotificationCard n={items[0]} preview />
          <span className="glass-heavy absolute -right-1 -top-1 z-10 flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px] font-semibold tabular-nums text-foreground/80">
            {items.length}
          </span>
        </button>
      </div>
    )
  }

  return (
    <section aria-label={`Notifications from ${agentName}`}>
      <div className="mb-1.5 flex items-center gap-2 px-1">
        <h3 className="text-[13px] font-semibold tracking-tight text-foreground/70">
          {agentName}
        </h3>
        <div className="ml-auto flex gap-1.5">
          <Button
            size="sm"
            variant="ghost"
            className="h-6 rounded-full border border-border/60 bg-card/60 px-2.5 text-[11px] font-medium"
            onClick={() => setOpen(false)}
          >
            Show less
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 rounded-full border border-border/60 bg-card/60 px-2.5 text-[11px] font-medium"
            onClick={archiveAll}
          >
            <X className="size-3" /> Clear all
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {items.map((n, i) => (
          <NotificationCard
            key={n.id}
            n={n}
            className="animate-in fade-in slide-in-from-top-2 fill-mode-backwards duration-200 motion-reduce:animate-none"
            style={{ animationDelay: `${Math.min(i * 35, 280)}ms` }}
          />
        ))}
      </div>
    </section>
  )
}
