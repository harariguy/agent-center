/** Copy text to the clipboard, reporting success. The async Clipboard API
    only exists in secure contexts, and this app is documented to run over
    plain HTTP on a LAN — there the hidden-textarea + execCommand path is the
    only one that works, so every copy button goes through this helper. */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Denied permission or an unfocused document — the legacy path below
      // may still succeed, so fall through rather than give up.
    }
  }

  const textarea = document.createElement("textarea")
  textarea.value = text
  // Off-view but not display:none — hidden elements can't be selected.
  textarea.style.position = "fixed"
  textarea.style.opacity = "0"
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  try {
    return document.execCommand("copy")
  } catch {
    return false
  } finally {
    textarea.remove()
  }
}
