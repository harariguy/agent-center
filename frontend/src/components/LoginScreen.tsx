import { useState } from "react"
import { Bell } from "lucide-react"

import { login } from "@/lib/api"

/** The macOS lock screen: wallpaper, avatar, one password field. */
export function LoginScreen({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState("")
  const [pending, setPending] = useState(false)
  const [failures, setFailures] = useState(0)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (pending) return
    setPending(true)
    try {
      await login(password)
      onSuccess()
    } catch {
      setFailures((n) => n + 1)
      setPassword("")
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6">
      <div
        aria-hidden
        className="flex size-16 items-center justify-center rounded-full bg-gradient-to-br from-sky-400 to-blue-600 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.35),0_8px_24px_rgba(0,0,0,0.25)]"
      >
        <Bell className="size-7" />
      </div>

      <h1 className="text-[17px] font-semibold">Agent Notify</h1>

      <form onSubmit={submit} key={failures} className={failures > 0 ? "animate-login-shake" : undefined}>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Enter Password"
          aria-label="Admin password"
          aria-invalid={failures > 0}
          autoFocus
          disabled={pending}
          className="glass-heavy h-8 w-52 rounded-full px-4 text-center text-[13px] placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring"
        />
      </form>

      <p className="h-4 text-[12px] text-foreground/60" role="alert">
        {failures > 0 ? "Wrong password. Try again." : "Press Return to sign in."}
      </p>
    </div>
  )
}
