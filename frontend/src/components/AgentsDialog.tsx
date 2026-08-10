import { useState } from "react"
import { ArrowLeft, Check, Copy, Plug, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { AgentIcon } from "@/components/AgentIcon"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { useAgents, useCreateAgent, useRevokeAgent } from "@/hooks/use-notifications"
import type { AgentCreated } from "@/lib/api"
import { copyText } from "@/lib/clipboard"
import { relTime } from "@/lib/time"
import { cn } from "@/lib/utils"

/** Manage who may post to Agent Center: register agents, read the one-time
    token, revoke access. */
export function AgentsDialog({
  open,
  onOpenChange,
  onConnect,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Hands off to the install screen — with the fresh token when we have one. */
  onConnect: (seed: { slug: string; token?: string }) => void
}) {
  const agents = useAgents()
  const create = useCreateAgent()
  const revoke = useRevokeAgent()
  const [name, setName] = useState("")
  const [created, setCreated] = useState<AgentCreated | null>(null)
  const [copied, setCopied] = useState(false)
  // Slug of the agent whose Revoke is armed — revoking kills a working
  // credential for good, so one click arms and a second click confirms.
  const [confirmingRevoke, setConfirmingRevoke] = useState<string | null>(null)

  const close = (next: boolean) => {
    onOpenChange(next)
    if (!next) reset()
  }

  const reset = () => {
    setName("")
    setCreated(null)
    setCopied(false)
    setConfirmingRevoke(null)
    create.reset()
  }

  const doRevoke = (slug: string) => {
    revoke.mutate(slug)
    setConfirmingRevoke(null)
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    create.mutate(name.trim(), { onSuccess: setCreated })
  }

  const copyToken = async () => {
    if (!created) return
    // The token is shown exactly once, so a silent copy failure here means a
    // dead credential — always tell the user which outcome they got.
    if (!(await copyText(created.token))) {
      toast.error("Couldn't copy — select the token and copy it manually")
      return
    }
    setCopied(true)
    toast.success("Token copied")
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="glass-heavy rounded-[20px] border-none sm:max-w-md">
        {created ? (
          <>
            <DialogHeader>
              <DialogTitle>{created.name} is registered</DialogTitle>
              <DialogDescription>
                This bearer token is shown once — store it where the agent runs.
              </DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded-lg bg-secondary px-2.5 py-2 font-mono text-[11px] leading-relaxed">
                {created.token}
              </code>
              <Button
                variant="secondary"
                size="icon"
                className="size-8 shrink-0 rounded-lg"
                onClick={copyToken}
                aria-label="Copy token"
              >
                {copied ? (
                  <Check className="size-4 text-green" />
                ) : (
                  <Copy className="size-4" />
                )}
              </Button>
            </div>
            <div className="flex justify-between">
              <Button
                variant="ghost"
                className="h-8 rounded-full px-3 text-[12px]"
                onClick={reset}
              >
                <ArrowLeft className="size-3.5" /> All agents
              </Button>
              <div className="flex gap-1.5">
                <Button
                  variant="ghost"
                  className="h-8 rounded-full px-3 text-[12px]"
                  onClick={() => close(false)}
                >
                  Done
                </Button>
                <Button
                  className="h-8 gap-1.5 rounded-full px-3.5 text-[12px]"
                  onClick={() => onConnect({ slug: created.slug, token: created.token })}
                >
                  <Plug className="size-3.5" /> Connect it
                </Button>
              </div>
            </div>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Agents</DialogTitle>
              <DialogDescription>
                Every agent posts with its own token, so you can revoke one
                without touching the others.
              </DialogDescription>
            </DialogHeader>

            {agents.data?.length ? (
              <ul className="-mx-1 max-h-64 overflow-y-auto">
                {agents.data.map((a) => (
                  <li
                    key={a.id}
                    className="group/agent flex items-center gap-2.5 rounded-xl px-1 py-1.5"
                  >
                    <AgentIcon name={a.name} className="size-7 rounded-[28%] text-[11px]" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium leading-tight">
                        {a.name}
                      </span>
                      <span className="block text-[11px] text-muted-foreground">
                        {a.last_seen_at
                          ? `last posted ${relTime(a.last_seen_at)}`
                          : "never posted"}
                      </span>
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onConnect({ slug: a.slug })}
                      className="h-7 gap-1 rounded-full px-2 text-[11px] text-muted-foreground hover:text-foreground"
                    >
                      <Plug className="size-3.5" /> Connect
                    </Button>
                    <Button
                      variant={confirmingRevoke === a.slug ? "destructive" : "ghost"}
                      size="sm"
                      disabled={revoke.isPending}
                      onClick={() =>
                        confirmingRevoke === a.slug
                          ? doRevoke(a.slug)
                          : setConfirmingRevoke(a.slug)
                      }
                      // Moving on disarms it, so a stale first click can't turn
                      // some later click into the destructive one.
                      onBlur={() => setConfirmingRevoke(null)}
                      className={cn(
                        "h-7 gap-1 rounded-full px-2 text-[11px]",
                        confirmingRevoke !== a.slug &&
                          "text-muted-foreground opacity-0 group-hover/agent:opacity-100 focus-visible:opacity-100 hover:text-destructive",
                      )}
                    >
                      <Trash2 className="size-3.5" />{" "}
                      {confirmingRevoke === a.slug ? "Revoke?" : "Revoke"}
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] text-muted-foreground">
                No agents yet. Register one to get a posting token.
              </p>
            )}

            <form onSubmit={submit} className="flex gap-2 border-t border-border pt-3">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="New agent name"
                aria-label="New agent name"
                maxLength={120}
                className="h-8 rounded-lg bg-secondary text-[13px]"
              />
              <Button
                type="submit"
                className="h-8 shrink-0 rounded-full px-3 text-[12px]"
                disabled={!name.trim() || create.isPending}
              >
                Create agent
              </Button>
            </form>
            {create.isError && (
              <p className="text-[12px] text-destructive" role="alert">
                {create.error.message}
              </p>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
