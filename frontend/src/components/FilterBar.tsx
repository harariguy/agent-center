import { CheckCheck, CircleDot, X } from "lucide-react"

import { FilterMenu } from "@/components/FilterMenu"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useReadAll } from "@/hooks/use-notifications"
import type { Facets, FeedFilters, Priority } from "@/lib/api"
import {
  activeFilterCount,
  NO_FILTERS,
  type PropertyFilters,
  type View,
} from "@/lib/filters"
import { cn } from "@/lib/utils"

const VIEWS: { id: View; label: string }[] = [
  { id: "all", label: "All" },
  { id: "attention", label: "Needs you" },
  { id: "activity", label: "Activity" },
  { id: "archived", label: "Archived" },
]

const PRIORITY_RANK: Priority[] = ["urgent", "high", "normal", "low", "min"]

function unreadBadge(view: View, facets?: Facets): number {
  if (!facets || view === "archived") return 0
  if (view === "attention") return facets.counts.attention_unread
  if (view === "activity") return facets.counts.activity_unread
  return facets.counts.unread
}

export function FilterBar({
  view,
  onView,
  filters,
  onFilters,
  facets,
  liveFacets,
  feedFilters,
}: {
  view: View
  onView: (v: View) => void
  filters: PropertyFilters
  onFilters: (f: PropertyFilters) => void
  facets?: Facets
  liveFacets?: Facets
  feedFilters: FeedFilters
}) {
  const readAll = useReadAll(feedFilters)
  const activeCount = activeFilterCount(filters)
  const set = <K extends keyof PropertyFilters>(
    key: K,
    value: PropertyFilters[K],
  ) => onFilters({ ...filters, [key]: value })

  // Priorities read in severity order, not by how many happen to carry each.
  const priorities = [...(facets?.priorities ?? [])].sort(
    (a, b) =>
      PRIORITY_RANK.indexOf(a.value as Priority) -
      PRIORITY_RANK.indexOf(b.value as Priority),
  )

  return (
    <div className="space-y-2 pb-3">
      <div className="flex items-center gap-2">
        {/* the strip scrolls on narrow screens rather than widening the page */}
        <Tabs
          value={view}
          onValueChange={(v) => onView(v as View)}
          className="nc-scroll min-w-0 flex-1 overflow-x-auto"
        >
          <TabsList className="h-8 w-max rounded-full border border-border/60 bg-card/60 p-0.5">
            {VIEWS.map((v) => {
              const badge = unreadBadge(v.id, liveFacets)
              return (
                <TabsTrigger
                  key={v.id}
                  value={v.id}
                  className={cn(
                    "h-7 gap-1.5 rounded-full border-none px-3 text-[12px] font-medium",
                    "data-[state=active]:bg-primary data-[state=active]:text-primary-foreground",
                    "dark:data-[state=active]:bg-primary dark:data-[state=active]:text-primary-foreground",
                    "data-[state=active]:shadow-sm",
                  )}
                >
                  {v.label}
                  {badge > 0 && (
                    <span
                      className={cn(
                        "rounded-full px-1 text-[10px] font-semibold tabular-nums",
                        view === v.id
                          ? "bg-primary-foreground/25"
                          : "bg-primary/15 text-primary",
                      )}
                    >
                      {badge}
                    </span>
                  )}
                </TabsTrigger>
              )
            })}
          </TabsList>
        </Tabs>

        <div className="ml-auto flex shrink-0 gap-1">
          {view !== "archived" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-pressed={filters.unread}
                  aria-label="Show unread only"
                  onClick={() => set("unread", !filters.unread)}
                  className={cn(
                    "size-8 rounded-full border border-border/60 bg-card/60 text-foreground/70",
                    filters.unread &&
                      "border-primary/30 bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary",
                  )}
                >
                  <CircleDot className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Unread only</TooltipContent>
            </Tooltip>
          )}

          {view !== "archived" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Mark notifications in this view as read"
                  onClick={() => readAll.mutate()}
                  className="size-8 rounded-full border border-border/60 bg-card/60 text-foreground/70"
                >
                  <CheckCheck className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Mark this view as read</TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <FilterMenu
          label="Agent"
          options={facets?.agents ?? []}
          value={filters.agent}
          onChange={(v) => set("agent", v)}
        />
        <FilterMenu
          label="Type"
          options={facets?.types ?? []}
          value={filters.type}
          onChange={(v) => set("type", v)}
        />
        <FilterMenu
          label="Priority"
          options={priorities}
          value={filters.priority}
          onChange={(v) => set("priority", v as Priority | null)}
        />
        <FilterMenu
          label="App"
          options={facets?.source_apps ?? []}
          value={filters.source_app}
          onChange={(v) => set("source_app", v)}
        />
        <FilterMenu
          label="Tag"
          options={facets?.tags ?? []}
          value={filters.tag}
          onChange={(v) => set("tag", v)}
        />

        {activeCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onFilters(NO_FILTERS)}
            className="h-7 gap-1 rounded-full px-2 text-[12px] text-muted-foreground"
          >
            <X className="size-3" />
            Clear {activeCount} filter{activeCount === 1 ? "" : "s"}
          </Button>
        )}
      </div>
    </div>
  )
}
