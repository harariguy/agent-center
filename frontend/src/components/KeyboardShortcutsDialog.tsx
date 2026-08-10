import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

const SHORTCUTS = [
  ["J / ↓", "Next notification"],
  ["K / ↑", "Previous notification"],
  ["Enter", "Expand or collapse"],
  ["E", "Archive"],
  ["U", "Toggle read"],
  ["O", "Open primary action"],
  ["?", "Show these shortcuts"],
]

export function KeyboardShortcutsDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass-heavy max-w-sm rounded-[20px] border-none">
        <DialogHeader>
          <DialogTitle>Review from the keyboard</DialogTitle>
          <DialogDescription>
            Shortcuts work when the cursor is outside a search field or menu.
          </DialogDescription>
        </DialogHeader>
        <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2">
          {SHORTCUTS.map(([keys, action]) => (
            <div className="contents" key={keys}>
              <dt>
                <kbd className="inline-flex min-w-10 justify-center rounded-md border border-border/80 bg-secondary px-2 py-1 font-mono text-[11px] font-semibold shadow-sm">
                  {keys}
                </kbd>
              </dt>
              <dd className="text-[13px] text-foreground/75">{action}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  )
}
