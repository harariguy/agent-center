import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** True only for absolute http(s) URLs. Agent-supplied links render as
    click-outs, so anything else — javascript:, data:, file:, relative —
    must never become an href or reach window.open. The URL constructor
    normalises the tricks a prefix check would miss (whitespace, embedded
    newlines in the scheme). */
export function isWebUrl(url: string): boolean {
  try {
    const { protocol } = new URL(url)
    return protocol === "http:" || protocol === "https:"
  } catch {
    return false
  }
}
