import { useCallback, useEffect, useState } from "react"

export type Theme = "system" | "light" | "dark"

const STORAGE_KEY = "agent-notify-theme"
const media = window.matchMedia("(prefers-color-scheme: dark)")

function apply(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && media.matches)
  document.documentElement.classList.toggle("dark", dark)
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? "system",
  )

  useEffect(() => {
    apply(theme)
    localStorage.setItem(STORAGE_KEY, theme)
    if (theme !== "system") return
    const onChange = () => apply("system")
    media.addEventListener("change", onChange)
    return () => media.removeEventListener("change", onChange)
  }, [theme])

  const cycle = useCallback(() => {
    setTheme((t) => (t === "system" ? "light" : t === "light" ? "dark" : "system"))
  }, [])

  return { theme, setTheme, cycle }
}
