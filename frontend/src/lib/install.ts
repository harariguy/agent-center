// The connect-an-agent catalogue: one data structure describing how each
// harness points at Agent Notifications. Pure functions of (url, token, agent name) so
// the install screen stays a renderer and every snippet is inspectable here.
//
// Two things every entry shares, because they are the whole contract: the MCP
// URL and an `Authorization: Bearer <token>` header. Anything a client-specific
// step adds beyond that is packaging.

export const TOKEN_PLACEHOLDER = "<YOUR_AGENT_TOKEN>"

export interface InstallContext {
  baseUrl: string
  mcpUrl: string
  guideUrl: string
  skillUrl: string
  token: string
  agentName: string
}

export interface InstallStep {
  title: string
  detail?: string
  code?: string
  codeLabel?: string
}

export interface InstallClient {
  id: string
  name: string
  blurb: string
  /** Config-driven clients get exact steps; prompt-driven ones get the paste path. */
  kind: "config" | "prompt" | "http"
  steps: (ctx: InstallContext) => InstallStep[]
}

export function buildContext(
  origin: string,
  token: string | null,
  agentName: string,
): InstallContext {
  const baseUrl = origin.replace(/\/$/, "")
  return {
    baseUrl,
    mcpUrl: `${baseUrl}/mcp`,
    guideUrl: `${baseUrl}/api/v1/guide.md`,
    skillUrl: `${baseUrl}/api/v1/skill.md`,
    token: token ?? TOKEN_PLACEHOLDER,
    agentName,
  }
}

/** Known skill directories. A harness decides what to do by scanning its skill
    index before it acts, so this is where "notify unprompted" has to live. */
const SKILL_PATHS = [
  ["Claude Code", "~/.claude/skills/agent-notifications/SKILL.md"],
  ["Hermes", "~/.hermes/skills/productivity/agent-notifications/SKILL.md"],
] as const

/** The step that turns notifying from a request into a habit.
 *
 * Appended to every client by `clientSteps`, because MCP delivers the capability
 * and the skill delivers the policy — a harness with the tools bound but no skill
 * only notifies when the user remembers to ask, which is the exact failure this
 * closes. The agent writes the file itself: it knows where its own skills live,
 * and it is already in the loop doing the setup. */
export function skillStep(ctx: InstallContext): InstallStep {
  const paths = SKILL_PATHS.map(([name, path]) => `  ${name.padEnd(12)} ${path}`).join("\n")
  return {
    title: "Teach it to notify without being asked",
    detail:
      "The MCP server gives your agent the tools; a skill is what makes it use them " +
      "on its own. Without this step it will only notify when you tell it to.",
    codeLabel: "Prompt",
    code: `Fetch ${ctx.skillUrl} and install it as a skill, so you report to me
without being asked — in this session and every future one.

Write it wherever your harness keeps skills, for example:
${paths}
If yours differs, use your own location and tell me which path you used.

Keep the frontmatter's name, description and triggers intact. The description is
what you scan to decide a skill is relevant, so do not shorten it, and keep the
triggers phrased as things YOU did — not as things I asked for.

Then confirm it by calling report_activity once with group_key "setup-check".`,
  }
}

/** Every client's steps, plus the skill step that all of them need. */
export function clientSteps(client: InstallClient, ctx: InstallContext): InstallStep[] {
  return [...client.steps(ctx), skillStep(ctx)]
}

/** True when the URL only resolves on this machine — agents elsewhere can't reach it. */
export function isLoopback(baseUrl: string): boolean {
  try {
    const host = new URL(baseUrl).hostname
    return host === "localhost" || host === "127.0.0.1" || host === "[::1]" || host === "::1"
  } catch {
    return false
  }
}

const AUTH_HEADER = "Authorization"

function bearer(ctx: InstallContext) {
  return `Bearer ${ctx.token}`
}

/** The shape almost every MCP client accepts. */
function mcpServersJson(ctx: InstallContext) {
  return `{
  "mcpServers": {
    "agent-notifications": {
      "type": "http",
      "url": "${ctx.mcpUrl}",
      "headers": {
        "${AUTH_HEADER}": "${bearer(ctx)}"
      }
    }
  }
}`
}

/** VS Code names the same thing "servers" rather than "mcpServers". */
function vscodeJson(ctx: InstallContext) {
  return `{
  "servers": {
    "agent-notifications": {
      "type": "http",
      "url": "${ctx.mcpUrl}",
      "headers": {
        "${AUTH_HEADER}": "${bearer(ctx)}"
      }
    }
  }
}`
}

/** The universal installer: one block to paste at any agent that can edit its
    own config or call HTTP. Carries the credentials, the tool names, and a
    pointer at the served guide rather than a copy of it. */
export function installPrompt(ctx: InstallContext): string {
  return `Please connect yourself to my Agent Notifications so you can send me notifications.

This is a notification layer only. It does not change how you work, it is not a
channel anyone replies through, and nothing waits on it — you just report what you
did and what needs me.

1. Add this MCP server to your configuration:
   - transport: streamable HTTP
   - name: agent-notifications
   - url: ${ctx.mcpUrl}
   - header: ${AUTH_HEADER}: ${bearer(ctx)}

   If you cannot add an MCP server, you can POST to ${ctx.baseUrl}/api/v1/notifications
   with that same Authorization header instead.

2. It gives you four tools: report_activity (something happened, no reply needed),
   request_input (you are blocked and need me), list_open_notifications, and
   resolve_notification (clear something once it no longer needs me).

3. Read ${ctx.guideUrl} and follow it. The short version: always send a stable
   group_key naming the thing rather than the run, write every notification as a
   complete snapshot instead of a delta, and only use request_input when you have
   actually stopped.

4. Fetch ${ctx.skillUrl} and install it as a skill in your own skill directory
   (e.g. ~/.claude/skills/agent-notifications/SKILL.md or
   ~/.hermes/skills/productivity/agent-notifications/SKILL.md). This is the step
   that makes you report on your own instead of waiting to be asked, so do not
   skip it, and keep the frontmatter's description and triggers intact.

5. Confirm it works by calling report_activity with group_key "setup-check",
   type "agent.connected", and a title saying you are connected.`
}

export const CLIENTS: InstallClient[] = [
  {
    id: "claude-code",
    name: "Claude Code",
    blurb: "Anthropic's coding agent",
    kind: "config",
    steps: (ctx) => [
      {
        title: "Add the server",
        detail: "One command. Adding --scope user makes it available in every project.",
        codeLabel: "Terminal",
        code: `claude mcp add --transport http agent-notifications ${ctx.mcpUrl} \\
  --scope user \\
  --header "${AUTH_HEADER}: ${bearer(ctx)}"`,
      },
      {
        title: "Check it connected",
        codeLabel: "Terminal",
        code: "claude mcp list",
      },
      {
        title: "Try it",
        detail: "Ask Claude to notify you; the card should appear in this feed.",
        codeLabel: "Prompt",
        code: 'Use agent-notifications to tell me you are connected.',
      },
    ],
  },
  {
    id: "claude-desktop",
    name: "Claude Desktop",
    blurb: "The Claude desktop app",
    kind: "config",
    steps: (ctx) => [
      {
        title: "Open the config file",
        detail:
          "Settings → Developer → Edit Config, or edit it directly at " +
          "~/Library/Application Support/Claude/claude_desktop_config.json on macOS.",
      },
      {
        title: "Add the server",
        detail: "Merge this into the file, keeping any servers already listed.",
        codeLabel: "claude_desktop_config.json",
        code: mcpServersJson(ctx),
      },
      { title: "Restart Claude Desktop", detail: "MCP servers are read at startup." },
    ],
  },
  {
    id: "cursor",
    name: "Cursor",
    blurb: "AI code editor",
    kind: "config",
    steps: (ctx) => [
      {
        title: "Create the MCP config",
        detail: "~/.cursor/mcp.json for every project, or .cursor/mcp.json for just this one.",
        codeLabel: "mcp.json",
        code: mcpServersJson(ctx),
      },
      { title: "Reload Cursor", detail: "Then check Settings → MCP for a green server." },
    ],
  },
  {
    id: "vscode",
    name: "VS Code",
    blurb: "Copilot agent mode",
    kind: "config",
    steps: (ctx) => [
      {
        title: "Create the MCP config",
        detail: 'Note VS Code calls the block "servers", not "mcpServers".',
        codeLabel: ".vscode/mcp.json",
        code: vscodeJson(ctx),
      },
      { title: "Start the server", detail: "Open the file and use the Start action above the entry." },
    ],
  },
  {
    id: "openclaw",
    name: "OpenClaw",
    blurb: "Open-source personal AI assistant",
    kind: "prompt",
    steps: (ctx) => [
      {
        title: "Paste this as a single prompt",
        detail:
          "OpenClaw can wire up its own MCP servers. Paste the whole block and let it " +
          "do the setup, then confirm the test notification lands here.",
        codeLabel: "Prompt",
        code: installPrompt(ctx),
      },
      {
        title: "Or configure it by hand",
        detail: "If you edit its config directly, this is the standard block.",
        codeLabel: "mcp.json",
        code: mcpServersJson(ctx),
      },
    ],
  },
  {
    id: "hermes",
    name: "Hermes",
    blurb: "Any Hermes-based agent",
    kind: "prompt",
    steps: (ctx) => [
      {
        title: "Paste this as a single prompt",
        detail: "Works with any harness that can add its own tools or call HTTP.",
        codeLabel: "Prompt",
        code: installPrompt(ctx),
      },
      {
        title: "Or configure it by hand",
        codeLabel: "mcp.json",
        code: mcpServersJson(ctx),
      },
    ],
  },
  {
    id: "any-mcp",
    name: "Any MCP client",
    blurb: "URL, header, and the standard JSON block",
    kind: "config",
    steps: (ctx) => [
      { title: "Server URL", codeLabel: "Streamable HTTP", code: ctx.mcpUrl },
      { title: "Auth header", codeLabel: "Header", code: `${AUTH_HEADER}: ${bearer(ctx)}` },
      {
        title: "Add it to your client config",
        detail: "Most clients accept exactly this shape.",
        codeLabel: "JSON",
        code: mcpServersJson(ctx),
      },
    ],
  },
  {
    id: "http",
    name: "No MCP — plain HTTP",
    blurb: "Cron jobs, CI, or anything that can curl",
    kind: "http",
    steps: (ctx) => [
      {
        title: "POST a notification",
        detail: "The same write path the MCP tools use — group_key is what makes repeats fold.",
        codeLabel: "Terminal",
        code: `curl -X POST ${ctx.baseUrl}/api/v1/notifications \\
  -H "${AUTH_HEADER}: ${bearer(ctx)}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "type": "job.failed",
    "category": "attention",
    "priority": "high",
    "group_key": "nightly-reconcile",
    "title": "Nightly reconcile failed on step 3",
    "source": {"app": "github", "link": "https://github.com/acme/app/actions"}
  }'`,
      },
      {
        title: "Read the field rules",
        detail: "Same contract the MCP tools enforce.",
        codeLabel: "Terminal",
        code: `curl ${ctx.guideUrl}`,
      },
    ],
  },
]
