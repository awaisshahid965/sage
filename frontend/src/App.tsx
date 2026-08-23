import { AssistantRuntimeProvider, useLocalRuntime } from '@assistant-ui/react'
import { useCallback, useMemo, useState } from 'react'

import { RestartNotice } from '@/components/restart-notice'
import { Thread } from '@/components/thread'
import { TooltipProvider } from '@/components/ui/tooltip'
import { createSageAdapter } from '@/lib/sage-adapter'
import { serverHistoryAdapter } from '@/lib/server-history'

export default function App() {
  const [restarted, setRestarted] = useState(false)

  const handleRestart = useCallback(() => setRestarted(true), [])

  // Memoised on a stable callback, so the runtime is built once. Rebuilding it
  // would drop the thread on every render.
  const chatModel = useMemo(
    () => createSageAdapter({ onConversationRestarted: handleRestart }),
    [handleRestart],
  )

  // Two adapters, and between them the whole integration: one is how a
  // question reaches Sage, the other is how the thread is recovered after a
  // reload. Everything else on screen is assistant-ui's.
  const runtime = useLocalRuntime(chatModel, {
    adapters: { history: serverHistoryAdapter },
  })

  return (
    <TooltipProvider>
      <AssistantRuntimeProvider runtime={runtime}>
        <div className="flex h-dvh flex-col">
          {restarted && <RestartNotice onDismiss={() => setRestarted(false)} />}
          <div className="min-h-0 flex-1">
            <Thread />
          </div>
        </div>
      </AssistantRuntimeProvider>
    </TooltipProvider>
  )
}
