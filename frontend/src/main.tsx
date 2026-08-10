import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { toast, Toaster } from "sonner"

import App from "@/App"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ApiError } from "@/lib/api"

import "./index.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.status === 401) && failureCount < 2,
      staleTime: 5_000,
    },
  },
  mutationCache: new MutationCache({
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) return
      toast.error(error.message, {
        description: error instanceof ApiError ? error.detail : undefined,
      })
    },
  }),
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={400}>
        <App />
        <Toaster
          position="top-right"
          offset={{ top: 52, right: 16 }}
          toastOptions={{
            className:
              "glass-heavy !rounded-[16px] !border-none !bg-transparent !text-foreground",
          }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
)
