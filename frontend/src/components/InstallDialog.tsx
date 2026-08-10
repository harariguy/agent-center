import { useEffect, useMemo, useState } from "react"
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Copy,
  EyeOff,
  Globe,
  RefreshCw,
  TriangleAlert,
} from "lucide-react"
import { toast } from "sonner"

import { AgentIcon } from "@/components/AgentIcon"
import { CodeBlock } from "@/components/CodeBlock"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { useAgents, useCreateAgent, useRotateAgentToken } from "@/hooks/use-notifications"
import { copyText } from "@/lib/clipboard"
import {
  buildContext,
  CLIENTS,
  clientSteps,
  installPrompt,
  isLoopback,
  TOKEN_PLACEHOLDER,
} from "@/lib/install"

export interface InstallSeed {
  slug: string
  /** Present only when we just minted it — otherwise the token must be rotated. */
  token?: string
}

/** Connect an agent harness to Agent Notify.
 *
 * One MCP URL plus one bearer header is the whole contract; everything below is
 * packaging per client. The token is the interesting constraint — only its hash
 * is stored, so a revisited install screen has nothing to show and rotating is
 * the only honest way back to a working credential. */
export function InstallDialog({
  open,
  onOpenChange,
  seed,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  seed?: InstallSeed | null
}) {
  const agents = useAgents()
  const create = useCreateAgent()
  const rotate = useRotateAgentToken()

  const [slug, setSlug] = useState<string | null>(seed?.slug ?? null)
  // Plaintext tokens live only in this component's memory, for this session.
  const [tokens, setTokens] = useState<Record<string, string>>(
    seed?.token ? { [seed.slug]: seed.token } : {},
  )
  const [clientId, setClientId] = useState<string | null>(null)
  const [confirmingRotate, setConfirmingRotate] = useState(false)
  const [newName, setNewName] = useState("")
  const [promptCopied, setPromptCopied] = useState(false)

  // Opening from "connect this agent" jumps straight to that agent's steps.
  useEffect(() => {
    if (!open || !seed) return
    setSlug(seed.slug)
    const fresh = seed.token
    if (fresh) setTokens((t) => ({ ...t, [seed.slug]: fresh }))
  }, [open, seed])

  const list = agents.data ?? []
  const agent = list.find((a) => a.slug === slug) ?? null
  const client = CLIENTS.find((c) => c.id === clientId) ?? null

  const ctx = useMemo(
    () => buildContext(window.location.origin, agent ? tokens[agent.slug] ?? null : null,
                       agent?.name ?? "my-agent"),
    [agent, tokens],
  )
  const hasToken = ctx.token !== TOKEN_PLACEHOLDER
  const steps = client ? clientSteps(client, ctx) : []

  const close = (next: boolean) => {
    onOpenChange(next)
    if (!next) {
      setClientId(null)
      setConfirmingRotate(false)
      setPromptCopied(false)
    }
  }

  const back = () => {
    if (client) return setClientId(null)
    setSlug(null)
  }

  const doRotate = () => {
    if (!agent) return
    rotate.mutate(agent.slug, {
      onSuccess: (fresh) => {
        setTokens((t) => ({ ...t, [fresh.slug]: fresh.token }))
        setConfirmingRotate(false)
        toast.success("New token issued — the old one no longer works")
      },
    })
  }

  const submitNew = (e: React.FormEvent) => {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    create.mutate(name, {
      onSuccess: (created) => {
        setTokens((t) => ({ ...t, [created.slug]: created.token }))
        setSlug(created.slug)
        setNewName("")
      },
    })
  }

  const copyPrompt = async () => {
    if (!(await copyText(installPrompt(ctx)))) {
      toast.error("Couldn't copy — select the prompt text and copy it manually")
      return
    }
    setPromptCopied(true)
    toast.success("Setup prompt copied")
    setTimeout(() => setPromptCopied(false), 1800)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="glass-heavy nc-scroll max-h-[86dvh] overflow-y-auto rounded-[20px] border-none sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {(agent || client) && (
              <Button
                variant="ghost"
                size="icon"
                className="-ml-1.5 size-6 rounded-md"
                onClick={back}
                aria-label="Back"
              >
                <ArrowLeft className="size-4" />
              </Button>
            )}
            {client ? client.name : agent ? `Connect ${agent.name}` : "Connect an agent"}
          </DialogTitle>
          <DialogDescription>
            {client
              ? client.blurb
              : agent
                ? "One MCP URL and one auth header — the rest is per-client packaging."
                : "Notifications only — connecting a harness doesn't change how it works. Pick the agent it will post as; each one gets its own token, so you can revoke one without touching the others."}
          </DialogDescription>
        </DialogHeader>

        {/* Step 1 — which agent is this? */}
        {/* min-w-0: DialogContent is a grid, whose items default to
            min-width:auto — without this a long line in a code block widens the
            track past the dialog and gets clipped rather than scrolling. */}
        {!agent ? (
          <div className="min-w-0 space-y-3">
            {list.length > 0 && (
              <ul className="-mx-1 space-y-0.5">
                {list.map((a) => (
                  <li key={a.id}>
                    <button
                      onClick={() => setSlug(a.slug)}
                      className="flex w-full items-center gap-2.5 rounded-xl px-1.5 py-1.5 text-left hover:bg-secondary"
                    >
                      <AgentIcon name={a.name} className="size-7 rounded-[28%] text-[11px]" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium leading-tight">
                          {a.name}
                        </span>
                        <span className="block text-[11px] text-muted-foreground">
                          {tokens[a.slug] ? "token ready" : "token hidden — regenerate to connect"}
                        </span>
                      </span>
                      <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <form onSubmit={submitNew} className="flex gap-2 border-t border-border pt-3">
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Or register a new agent"
                aria-label="New agent name"
                maxLength={120}
                className="h-8 rounded-lg bg-secondary text-[13px]"
              />
              <Button
                type="submit"
                className="h-8 shrink-0 rounded-full px-3 text-[12px]"
                disabled={!newName.trim() || create.isPending}
              >
                Register
              </Button>
            </form>
            {create.isError && (
              <p className="text-[12px] text-destructive" role="alert">
                {create.error.message}
              </p>
            )}
          </div>
        ) : (
          <div className="min-w-0 space-y-4">
            {/* Credentials — the two things every client needs. */}
            <div className="min-w-0 space-y-2">
              <CodeBlock code={ctx.mcpUrl} label="MCP server URL (streamable HTTP)" />
              {hasToken ? (
                <CodeBlock code={`Authorization: Bearer ${ctx.token}`} label="Auth header" />
              ) : (
                <div className="flex items-start gap-2.5 rounded-xl bg-secondary/70 px-3 py-2.5">
                  <EyeOff className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-medium leading-snug">
                      This agent's token is hidden
                    </p>
                    <p className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">
                      Only a hash is stored, so it can't be shown again. Regenerate to get a
                      working one — {agent.name} will need the new token
                      {agent.last_seen_at ? ", and its current token stops working" : ""}.
                    </p>
                  </div>
                  <Button
                    variant={confirmingRotate ? "default" : "secondary"}
                    className="h-7 shrink-0 gap-1.5 rounded-full px-2.5 text-[11.5px]"
                    disabled={rotate.isPending}
                    onClick={() => (confirmingRotate ? doRotate() : setConfirmingRotate(true))}
                  >
                    <RefreshCw className={`size-3.5 ${rotate.isPending ? "animate-spin" : ""}`} />
                    {confirmingRotate ? "Confirm" : "Regenerate"}
                  </Button>
                </div>
              )}

              {isLoopback(ctx.baseUrl) && (
                <p className="flex items-start gap-1.5 px-0.5 text-[11.5px] leading-snug text-muted-foreground">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                  <span>
                    This URL only resolves on this machine. An agent running anywhere else
                    needs a reachable host — bind the server to your LAN address or put a
                    tunnel in front of it.
                  </span>
                </p>
              )}
            </div>

            {/* Step 2 — which client? */}
            {!client ? (
              <div className="space-y-2">
                <p className="px-0.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Choose your harness
                </p>
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {CLIENTS.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => setClientId(c.id)}
                      className="glass flex items-center gap-2 rounded-xl px-2.5 py-2 text-left transition hover:brightness-105"
                    >
                      <Globe className="size-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12.5px] font-medium leading-tight">
                          {c.name}
                        </span>
                        <span className="block truncate text-[11px] text-muted-foreground">
                          {c.blurb}
                        </span>
                      </span>
                      <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="min-w-0 space-y-3">
                {/* The universal escape hatch: hand the whole setup to the agent. */}
                <div className="flex items-center justify-between gap-3 rounded-xl bg-secondary/70 px-3 py-2">
                  <p className="text-[11.5px] leading-snug text-muted-foreground">
                    Or skip the steps — paste the whole setup to the agent as one prompt.
                  </p>
                  <Button
                    variant="secondary"
                    className="h-7 shrink-0 gap-1.5 rounded-full px-2.5 text-[11.5px]"
                    onClick={copyPrompt}
                  >
                    {promptCopied ? (
                      <Check className="size-3.5 text-green" />
                    ) : (
                      <Copy className="size-3.5" />
                    )}
                    Copy prompt
                  </Button>
                </div>

                <ol className="space-y-3">
                  {steps.map((step, i) => (
                    <li key={step.title} className="flex gap-2.5">
                      <span
                        aria-hidden
                        className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-secondary text-[10.5px] font-semibold tabular-nums"
                      >
                        {i + 1}
                      </span>
                      <div className="min-w-0 flex-1 space-y-1.5">
                        <p className="text-[12.5px] font-medium leading-snug">{step.title}</p>
                        {step.detail && (
                          <p className="text-[11.5px] leading-snug text-muted-foreground">
                            {step.detail}
                          </p>
                        )}
                        {step.code && (
                          <CodeBlock
                            code={step.code}
                            label={step.codeLabel}
                            wrap={step.codeLabel === "Prompt"}
                          />
                        )}
                      </div>
                    </li>
                  ))}
                </ol>

                {!hasToken && (
                  <p className="text-[11.5px] leading-snug text-destructive">
                    These snippets contain a placeholder, not a token. Regenerate above before
                    copying them.
                  </p>
                )}

                <p className="text-[11.5px] leading-snug text-muted-foreground">
                  Every harness gets the same field rules on connect, served from{" "}
                  <code className="font-mono text-[11px]">/api/v1/guide.md</code>.
                </p>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
