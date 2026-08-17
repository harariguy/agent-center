import { Check, ChevronDown } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { FacetValue } from "@/lib/api"
import { cn } from "@/lib/utils"

/** One filter property: shows the property name until something is chosen,
    then the chosen value. Renders nothing when there's nothing to filter by. */
export function FilterMenu({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: FacetValue[]
  value: string | null
  onChange: (value: string | null) => void
}) {
  if (options.length === 0) return null

  const selected = options.find((o) => o.value === value)
  const active = !!value

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn(
            "h-7 gap-1 rounded-full border border-border/60 bg-card/60 px-2.5 text-[12px] font-medium",
            "hover:bg-card",
            active &&
              "border-primary/30 bg-primary/10 text-primary hover:bg-primary/15",
          )}
        >
          {active ? (selected?.label ?? selected?.value ?? value) : label}
          <ChevronDown className="size-3 opacity-60" aria-hidden />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent
        align="start"
        className="glass-heavy max-h-72 min-w-48 overflow-y-auto rounded-xl border-none"
      >
        <DropdownMenuItem onClick={() => onChange(null)} className="text-[12px]">
          <span className={cn("flex-1", !active && "font-semibold")}>
            Any {label.toLowerCase()}
          </span>
          {!active && <Check className="size-3.5" />}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {options.map((o) => (
          <DropdownMenuItem
            key={o.value}
            onClick={() => onChange(o.value)}
            className="text-[12px]"
          >
            <span className={cn("flex-1 truncate", o.value === value && "font-semibold")}>
              {o.label ?? o.value}
            </span>
            <span className="tabular-nums text-muted-foreground">{o.count}</span>
            {o.value === value && <Check className="size-3.5" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
