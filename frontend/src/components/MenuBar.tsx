import { Bot, Laptop, LogOut, Moon, Plug, Search, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { Theme } from "@/hooks/use-theme"

const THEME_ICONS: Record<Theme, typeof Sun> = {
  system: Laptop,
  light: Sun,
  dark: Moon,
}

export function MenuBar({
  query,
  onQuery,
  theme,
  onCycleTheme,
  onManageAgents,
  onConnect,
  onLogout,
}: {
  query: string
  onQuery: (q: string) => void
  theme: Theme
  onCycleTheme: () => void
  onManageAgents: () => void
  onConnect: () => void
  onLogout: () => void
}) {
  const ThemeIcon = THEME_ICONS[theme]

  return (
    <header className="glass-heavy fixed inset-x-0 top-0 z-40 flex h-11 items-center gap-3 rounded-none border-x-0 border-t-0 px-4">
      <span className="flex shrink-0 items-center gap-2 whitespace-nowrap text-[13px] font-semibold tracking-tight">
        <span aria-hidden className="size-2 rounded-full bg-primary" />
        Agent Center
      </span>

      <div className="relative ml-auto min-w-0 flex-1 sm:absolute sm:left-1/2 sm:ml-0 sm:w-64 sm:-translate-x-1/2">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          type="search"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Search notifications"
          aria-label="Search notifications"
          className="h-7 rounded-full border-none bg-secondary pl-8 text-[13px] shadow-none focus-visible:ring-2"
        />
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-0.5">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-7 rounded-lg"
              onClick={onConnect}
              aria-label="Connect an agent"
            >
              <Plug className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Connect an agent</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-7 rounded-lg"
              onClick={onManageAgents}
              aria-label="Manage agents"
            >
              <Bot className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Manage agents</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-7 rounded-lg"
              onClick={onCycleTheme}
              aria-label={`Appearance: ${theme}. Click to change.`}
            >
              <ThemeIcon className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Appearance: {theme}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-7 rounded-lg"
              onClick={onLogout}
              aria-label="Sign out"
            >
              <LogOut className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Sign out</TooltipContent>
        </Tooltip>
      </div>
    </header>
  )
}
