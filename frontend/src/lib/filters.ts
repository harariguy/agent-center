import type { FeedFilters, Priority } from "@/lib/api"

export type View = "all" | "attention" | "activity" | "archived"

/** Everything the feed can be narrowed by, held as one object so "clear all"
    and "is anything active?" stay one-liners. */
export interface PropertyFilters {
  agent: string | null
  type: string | null
  priority: Priority | null
  source_app: string | null
  tag: string | null
  unread: boolean
}

export const NO_FILTERS: PropertyFilters = {
  agent: null,
  type: null,
  priority: null,
  source_app: null,
  tag: null,
  unread: false,
}

export function activeFilterCount(f: PropertyFilters): number {
  return (
    Number(!!f.agent) +
    Number(!!f.type) +
    Number(!!f.priority) +
    Number(!!f.source_app) +
    Number(!!f.tag) +
    Number(f.unread)
  )
}

export function buildFilters(
  view: View,
  props: PropertyFilters,
  q: string,
): FeedFilters {
  return {
    ...(view === "attention" && { category: "attention" as const }),
    ...(view === "attention" && { order: "priority" as const }),
    ...(view === "activity" && { category: "activity" as const }),
    ...(view === "archived" && { archived: true }),
    ...(props.agent && { agent: props.agent }),
    ...(props.type && { type: props.type }),
    ...(props.priority && { priority: props.priority }),
    ...(props.source_app && { source_app: props.source_app }),
    ...(props.tag && { tag: props.tag }),
    ...(props.unread && { unread: true }),
    ...(q && { q }),
  }
}
