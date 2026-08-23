import { XIcon } from 'lucide-react'

/**
 * Shown when Sage started a new conversation because the old one had expired.
 *
 * The messages above stay on screen on purpose. Two things could be done with
 * them instead, and both are worse:
 *
 * - Clearing them takes away something the reader can still perfectly well
 *   read, to make the UI agree with a server that has simply forgotten.
 * - Replaying them into the new conversation would mean the client asserting
 *   what the assistant said, which is exactly the tampering that keeping
 *   conversations server-side removes. Convenience is not worth that.
 *
 * So they stay, and this says why — otherwise the next few answers look like a
 * bug rather than an explained event.
 */
export function RestartNotice({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      role="status"
      className="bg-muted text-muted-foreground flex items-start gap-3 border-b px-4 py-2.5 text-sm"
    >
      <p className="flex-1">
        This conversation expired, so Sage started a new one. The messages above
        are still here to read, but Sage no longer remembers them.
      </p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="hover:text-foreground -mr-1 shrink-0 rounded p-1"
      >
        <XIcon className="size-4" />
      </button>
    </div>
  )
}
