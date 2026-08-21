import { AssistantRuntimeProvider, useLocalRuntime } from '@assistant-ui/react'

import { Thread } from '@/components/thread'
import { TooltipProvider } from '@/components/ui/tooltip'
import { localHistoryAdapter } from '@/lib/local-history'
import { sageModelAdapter } from '@/lib/sage-adapter'

export default function App() {
  // Two adapters, and between them they are the whole integration: one is how
  // a question reaches Sage, the other is where the conversation lives between
  // reloads. Everything else on screen — the thread, the composer, streaming,
  // markdown, scroll behaviour, cancellation — is assistant-ui's.
  const runtime = useLocalRuntime(sageModelAdapter, {
    adapters: { history: localHistoryAdapter },
  })

  return (
    <TooltipProvider>
      <AssistantRuntimeProvider runtime={runtime}>
        <div className="h-dvh">
          <Thread />
        </div>
      </AssistantRuntimeProvider>
    </TooltipProvider>
  )
}
