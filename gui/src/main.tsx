import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { ThemeProvider } from "next-themes"
import { MotionConfig } from "motion/react"
import "@fontsource-variable/geist-mono"

import "./index.css"
import App from "./App.tsx"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
      {/* "user": follow the system's Reduce motion setting everywhere at once. */}
      <MotionConfig reducedMotion="user">
        <TooltipProvider>
          <App />
          {/* Top, under the header: at the bottom they covered the Apply bar. */}
          <Toaster position="top-right" offset={{ top: 68 }} mobileOffset={{ top: 64 }} />
        </TooltipProvider>
      </MotionConfig>
    </ThemeProvider>
  </StrictMode>,
)
