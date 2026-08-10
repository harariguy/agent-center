import { cn } from "@/lib/utils"

// macOS-app-icon-style gradients, assigned deterministically per agent name
// so an agent keeps its identity across sessions and views.
const GRADIENTS = [
  "from-sky-400 to-blue-600",
  "from-violet-400 to-purple-600",
  "from-pink-400 to-rose-600",
  "from-amber-400 to-orange-600",
  "from-teal-400 to-cyan-600",
  "from-lime-400 to-green-600",
  "from-indigo-400 to-blue-700",
  "from-fuchsia-400 to-pink-600",
]

function hash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

export function agentInitials(name: string): string {
  const words = name.trim().split(/[\s_-]+/).filter(Boolean)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

export function AgentIcon({
  name,
  className,
}: {
  name: string
  className?: string
}) {
  return (
    <div
      aria-hidden
      className={cn(
        "flex size-9 shrink-0 select-none items-center justify-center rounded-[24%]",
        "bg-gradient-to-br text-[13px] font-semibold text-white",
        "shadow-[inset_0_1px_0_rgba(255,255,255,0.35),0_1px_3px_rgba(0,0,0,0.25)]",
        GRADIENTS[hash(name) % GRADIENTS.length],
        className,
      )}
    >
      {agentInitials(name)}
    </div>
  )
}
