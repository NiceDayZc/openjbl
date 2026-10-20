import { memo, useEffect, useRef, useState } from "react"
import { ChevronDownIcon } from "lucide-react"

import { Card, CardAction, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import type { ActivityEvent } from "@/lib/api"
import { cn } from "@/lib/utils"

const MARKERS: Record<ActivityEvent["level"], string> = {
  info: "border border-muted-foreground/60",
  success: "bg-foreground",
  warning: "border border-foreground",
  error: "bg-destructive",
}

// The log can run to hundreds of lines over a session; the page only needs the tail.
const VISIBLE = 200

function time(event: ActivityEvent): string {
  return new Date(event.time * 1000).toLocaleTimeString([], { hour12: false })
}

export const ActivityLog = memo(function ActivityLog({ events }: { events: ActivityEvent[] }) {
  // Most people never need the packets, so the log starts folded to its latest line.
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const latest = events[events.length - 1]

  // Scroll the log itself, never the page.
  useEffect(() => {
    if (open) box.current?.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" })
  }, [events.length, open])

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Activity</CardTitle>
        <CardDescription className="truncate">
          {latest ? (
            <span className="font-mono text-[11px]">{latest.message.trim().split("\n")[0]}</span>
          ) : (
            "Every packet, reply and verification"
          )}
        </CardDescription>
        <CardAction>
          <Button variant="ghost" size="icon-sm" aria-expanded={open} aria-label={open ? "Hide activity" : "Show activity"} onClick={() => setOpen(!open)}>
            <ChevronDownIcon className={cn("transition-transform duration-300 ease-out", open && "rotate-180")} />
          </Button>
        </CardAction>
      </CardHeader>
      {/* grid-rows 0fr -> 1fr animates to the content's natural height in CSS alone. */}
      <div className={cn("grid transition-[grid-template-rows] duration-300 ease-out", open ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
        <div className="min-h-0 overflow-hidden px-(--card-spacing)">
          <div
            ref={box}
            className="h-72 overflow-y-auto rounded-lg border bg-muted/30 p-2 font-mono text-[11px] leading-relaxed"
            aria-live="polite"
          >
            {events.length === 0 && <p className="p-2 text-muted-foreground">Nothing yet.</p>}
            {events.slice(-VISIBLE).map((event) => (
              <div key={event.seq} className="flex animate-in gap-2 rounded px-1 py-0.5 duration-300 fade-in-0 slide-in-from-bottom-1">
                <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", MARKERS[event.level])} />
                <span className="shrink-0 text-muted-foreground tabular-nums">{time(event)}</span>
                <span className={cn("min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]", event.level === "error" && "text-destructive")}>
                  {event.message.trim()}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  )
})
