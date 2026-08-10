import { useState } from "react"
import { Check, Copy } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { copyText } from "@/lib/clipboard"
import { cn } from "@/lib/utils"

/** A copyable snippet. Wide content scrolls inside the block rather than
    stretching the dialog, so a long curl can't widen the whole screen. */
export function CodeBlock({
  code,
  label,
  wrap = false,
  className,
}: {
  code: string
  label?: string
  /** Prose meant to be pasted wraps; a shell command scrolls, since a wrapped
      command line reads as two commands. */
  wrap?: boolean
  className?: string
}) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    if (!(await copyText(code))) {
      toast.error("Couldn't copy — select the text and copy it manually")
      return
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <div className={cn("min-w-0 overflow-hidden rounded-xl bg-secondary/70", className)}>
      <div className="flex items-center justify-between gap-2 px-2.5 py-1">
        <span className="truncate text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label ?? "Snippet"}
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="size-6 shrink-0 rounded-md"
          onClick={copy}
          aria-label={`Copy ${label ?? "snippet"}`}
        >
          {copied ? <Check className="size-3.5 text-green" /> : <Copy className="size-3.5" />}
        </Button>
      </div>
      <pre
        className={cn(
          "nc-scroll px-3 pb-2.5 pt-0.5",
          wrap ? "whitespace-pre-wrap break-words" : "overflow-x-auto",
        )}
      >
        <code className="font-mono text-[11.5px] leading-relaxed">{code}</code>
      </pre>
    </div>
  )
}
