// Typed client for the Agent Center API (/api/v1). Mirrors agent_center/schemas.py.

const API = "/api/v1"

export type Category = "activity" | "attention"
export type Priority = "min" | "low" | "normal" | "high" | "urgent"

export interface Action {
  label: string
  url: string
}

export interface Notification {
  id: string
  agent_id: string
  agent_name: string
  group_key: string | null
  category: Category
  type: string
  priority: Priority
  title: string
  body: string
  source_app: string | null
  source_link: string | null
  actions: Action[]
  tags: string[]
  occurrences: number
  first_seen_at: string
  last_seen_at: string
  read_at: string | null
  snoozed_until: string | null
  archived_at: string | null
}

export interface Occurrence {
  id: string
  seen_at: string
  payload_json: Record<string, unknown> | null
}

export interface NotificationDetail extends Notification {
  metadata: Record<string, unknown>
  history: Occurrence[]
}

export interface FeedPage {
  items: Notification[]
  next_cursor: string | null
}

export interface Agent {
  id: string
  name: string
  slug: string
  created_at: string
  last_seen_at: string | null
}

export interface AgentCreated extends Agent {
  token: string
}

export interface FeedFilters {
  category?: Category
  agent?: string
  type?: string
  priority?: Priority
  source_app?: string
  tag?: string
  unread?: boolean
  archived?: boolean
  q?: string
  order?: "recent" | "priority"
}

export interface FacetValue {
  value: string
  label: string | null
  count: number
}

export interface FeedCounts {
  total: number
  unread: number
  attention: number
  attention_unread: number
  activity: number
  activity_unread: number
}

export interface Facets {
  agents: FacetValue[]
  types: FacetValue[]
  priorities: FacetValue[]
  source_apps: FacetValue[]
  tags: FacetValue[]
  counts: FeedCounts
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, title: string, detail: string) {
    super(title)
    this.status = status
    this.detail = detail
  }
}

// The app registers a handler so any 401 anywhere flips it to the lock screen.
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (res.status === 401) {
    onUnauthorized?.()
    throw new ApiError(401, "Unauthorized", "Sign in to view your notifications.")
  }
  if (!res.ok) {
    let title = res.statusText
    let detail = ""
    try {
      const problem = await res.json()
      title = problem.title ?? title
      detail = problem.detail ?? ""
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, title, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export function getFeed(filters: FeedFilters, cursor?: string): Promise<FeedPage> {
  const params = new URLSearchParams({ limit: "50" })
  appendFeedFilters(params, filters)
  if (cursor) params.set("cursor", cursor)
  return request(`/notifications?${params}`)
}

function appendFeedFilters(params: URLSearchParams, filters: FeedFilters) {
  if (filters.category) params.set("category", filters.category)
  if (filters.agent) params.set("agent", filters.agent)
  if (filters.type) params.set("type", filters.type)
  if (filters.priority) params.set("priority", filters.priority)
  if (filters.source_app) params.set("source_app", filters.source_app)
  if (filters.tag) params.set("tag", filters.tag)
  if (filters.unread) params.set("unread", "true")
  if (filters.archived) params.set("archived", "true")
  if (filters.q) params.set("q", filters.q)
  if (filters.order) params.set("order", filters.order)
}

export function getFacets(archived: boolean): Promise<Facets> {
  return request(`/notifications/facets${archived ? "?archived=true" : ""}`)
}

export function getNotification(id: string): Promise<NotificationDetail> {
  return request(`/notifications/${id}`)
}

export function markRead(id: string): Promise<Notification> {
  return request(`/notifications/${id}/read`, { method: "POST" })
}

export function markUnread(id: string): Promise<Notification> {
  return request(`/notifications/${id}/unread`, { method: "POST" })
}

export function archive(id: string): Promise<Notification> {
  return request(`/notifications/${id}/archive`, { method: "POST" })
}

export function unarchive(id: string): Promise<Notification> {
  return request(`/notifications/${id}/unarchive`, { method: "POST" })
}

export function snooze({
  id,
  until,
}: {
  id: string
  until: string
}): Promise<Notification> {
  return request(`/notifications/${id}/snooze`, {
    method: "POST",
    body: JSON.stringify({ until }),
  })
}

export function readAll(filters: FeedFilters): Promise<void> {
  const params = new URLSearchParams()
  appendFeedFilters(params, {
    ...filters,
    archived: undefined,
    unread: undefined,
    order: undefined,
  })
  const query = params.size ? `?${params}` : ""
  return request(`/notifications/read-all${query}`, { method: "POST" })
}

export function listAgents(): Promise<Agent[]> {
  return request("/agents")
}

export function createAgent(name: string): Promise<AgentCreated> {
  return request("/agents", { method: "POST", body: JSON.stringify({ name }) })
}

/** Issues a fresh token and invalidates the old one — the only way back to a
    usable credential, since only the hash is stored. */
export function rotateAgentToken(slug: string): Promise<AgentCreated> {
  return request(`/agents/${slug}/token`, { method: "POST" })
}

export function revokeAgent(slug: string): Promise<void> {
  return request(`/agents/${slug}`, { method: "DELETE" })
}

export function login(password: string): Promise<void> {
  return request("/session", { method: "POST", body: JSON.stringify({ password }) })
}

export function logout(): Promise<void> {
  return request("/session", { method: "DELETE" })
}
