import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"

import { AgentsDialog } from "@/components/AgentsDialog"
import { FilterBar } from "@/components/FilterBar"
import { InstallDialog, type InstallSeed } from "@/components/InstallDialog"
import { LoginScreen } from "@/components/LoginScreen"
import { MenuBar } from "@/components/MenuBar"
import { NotificationFeed } from "@/components/NotificationFeed"
import { Wallpaper } from "@/components/Wallpaper"
import { useFacets } from "@/hooks/use-notifications"
import { useTheme } from "@/hooks/use-theme"
import { logout, setUnauthorizedHandler } from "@/lib/api"
import {
  activeFilterCount,
  buildFilters,
  NO_FILTERS,
  type PropertyFilters,
  type View,
} from "@/lib/filters"

export default function App() {
  const [locked, setLocked] = useState(false)
  const [view, setView] = useState<View>("all")
  const [filters, setFilters] = useState<PropertyFilters>(NO_FILTERS)
  const [searchInput, setSearchInput] = useState("")
  const [q, setQ] = useState("")
  const [managingAgents, setManagingAgents] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [installSeed, setInstallSeed] = useState<InstallSeed | null>(null)

  const { theme, cycle } = useTheme()
  const queryClient = useQueryClient()
  const liveFacets = useFacets(false)
  const archivedFacets = useFacets(true)

  // Any 401 from any request drops the app to the lock screen.
  useEffect(() => {
    setUnauthorizedHandler(() => setLocked(true))
  }, [])

  // Debounced search, like typing into Spotlight.
  useEffect(() => {
    const t = setTimeout(() => setQ(searchInput.trim()), 250)
    return () => clearTimeout(t)
  }, [searchInput])

  if (locked) {
    return (
      <>
        <Wallpaper />
        <LoginScreen
          onSuccess={() => {
            setLocked(false)
            queryClient.invalidateQueries()
          }}
        />
      </>
    )
  }

  const narrowed = activeFilterCount(filters) > 0 || !!q
  const feedFilters = buildFilters(view, filters, q)
  const facets = view === "archived" ? archivedFacets : liveFacets

  return (
    <>
      <Wallpaper />
      <MenuBar
        query={searchInput}
        onQuery={setSearchInput}
        theme={theme}
        onCycleTheme={cycle}
        onManageAgents={() => setManagingAgents(true)}
        onConnect={() => {
          setInstallSeed(null)
          setConnecting(true)
        }}
        onLogout={async () => {
          await logout().catch(() => {})
          queryClient.clear()
          setLocked(true)
        }}
      />

      <main className="mx-auto flex h-dvh w-full max-w-145 flex-col px-5 pt-14">
        <FilterBar
          view={view}
          onView={setView}
          filters={filters}
          onFilters={setFilters}
          facets={facets.data}
          liveFacets={liveFacets.data}
          feedFilters={feedFilters}
        />

        <div className="nc-scroll -mx-2 flex-1 overflow-y-auto px-2 pb-10 pt-1">
          <NotificationFeed
            filters={feedFilters}
            view={view}
            narrowed={narrowed}
            onClearFilters={() => {
              setFilters(NO_FILTERS)
              setSearchInput("")
            }}
          />
        </div>
      </main>

      <AgentsDialog
        open={managingAgents}
        onOpenChange={setManagingAgents}
        onConnect={(seed) => {
          setInstallSeed(seed)
          setManagingAgents(false)
          setConnecting(true)
        }}
      />
      <InstallDialog open={connecting} onOpenChange={setConnecting} seed={installSeed} />
    </>
  )
}
