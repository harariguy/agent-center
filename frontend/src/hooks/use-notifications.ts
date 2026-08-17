import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query"

import * as api from "@/lib/api"
import type { FeedFilters, FeedPage, Notification } from "@/lib/api"

const REFRESH_MS = 30_000

export function useFeed(filters: FeedFilters) {
  return useInfiniteQuery({
    queryKey: ["feed", filters],
    queryFn: ({ pageParam }) => api.getFeed(filters, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: REFRESH_MS,
  })
}

/** What the feed can be filtered by, plus the tab counts. */
export function useFacets(archived: boolean) {
  return useQuery({
    queryKey: ["facets", archived],
    queryFn: () => api.getFacets(archived),
    refetchInterval: REFRESH_MS,
  })
}

export function useAgents() {
  return useQuery({
    queryKey: ["agents"],
    queryFn: api.listAgents,
    refetchInterval: REFRESH_MS,
  })
}

export function useNotificationDetail(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["notification", id],
    queryFn: () => api.getNotification(id),
    enabled,
  })
}

type FeedData = InfiniteData<FeedPage, string | undefined>

/** Rewrite a notification across every cached feed page (optimistic updates). */
function patchFeeds(
  client: ReturnType<typeof useQueryClient>,
  id: string,
  patch: (n: Notification) => Notification | null,
) {
  client.setQueriesData<FeedData>({ queryKey: ["feed"] }, (data) => {
    if (!data) return data
    return {
      ...data,
      pages: data.pages.map((page) => ({
        ...page,
        items: page.items
          .map((n) => (n.id === id ? patch(n) : n))
          .filter((n): n is Notification => n !== null),
      })),
    }
  })
}

function useFeedMutation<TArg>(
  fn: (arg: TArg) => Promise<unknown>,
  optimistic?: (client: ReturnType<typeof useQueryClient>, arg: TArg) => void,
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onMutate: (arg) => optimistic?.(client, arg),
    onSettled: () => {
      client.invalidateQueries({ queryKey: ["feed"] })
      client.invalidateQueries({ queryKey: ["facets"] })
    },
  })
}

export function useMarkRead() {
  return useFeedMutation(api.markRead, (client, id) =>
    patchFeeds(client, id, (n) => ({ ...n, read_at: new Date().toISOString() })),
  )
}

export function useMarkUnread() {
  return useFeedMutation(api.markUnread, (client, id) =>
    patchFeeds(client, id, (n) => ({ ...n, read_at: null })),
  )
}

export function useArchive() {
  return useFeedMutation(api.archive, (client, id) =>
    patchFeeds(client, id, () => null),
  )
}

export function useUnarchive() {
  return useFeedMutation(api.unarchive, (client, id) =>
    patchFeeds(client, id, () => null),
  )
}

export function useSnooze() {
  return useFeedMutation(api.snooze, (client, { id }) =>
    patchFeeds(client, id, () => null),
  )
}

export function useReadAll(filters: FeedFilters) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.readAll(filters),
    onSettled: () => {
      client.invalidateQueries({ queryKey: ["feed"] })
      client.invalidateQueries({ queryKey: ["facets"] })
    },
  })
}

export function useCreateAgent() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.createAgent,
    onSuccess: () => client.invalidateQueries({ queryKey: ["agents"] }),
  })
}

export function useRotateAgentToken() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.rotateAgentToken,
    onSuccess: () => client.invalidateQueries({ queryKey: ["agents"] }),
  })
}

export function useRevokeAgent() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.revokeAgent,
    onSuccess: () => client.invalidateQueries({ queryKey: ["agents"] }),
  })
}
