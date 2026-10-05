import { useEffect, useRef } from "react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { ActivityEvent } from "@/lib/api"
import { cn } from "@/lib/utils"

const MARKERS: Record<ActivityEvent["level"], string> = {
  info: "border border-muted-foreground/60",
  success: "bg-foreground",
  warning: "border border-foreground",
  error: "bg-destructive",
}

export function ActivityLog({ events }: { events: ActivityEvent[] }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" })
  }, [events.length])

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Activity</CardTitle>
        <CardDescription>Every packet, reply and verification, as it happens</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-72 overflow-y-auto rounded-lg border bg-muted/30 p-2 font-mono text-[11px] leading-relaxed">
          {events.length === 0 && <p className="p-2 text-muted-foreground">Nothing yet.</p>}
          {events.map((event) => (
            <div key={event.seq} className="flex gap-2 px-1 py-0.5">
              <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", MARKERS[event.level])} />
              <span className="shrink-0 text-muted-foreground tabular-nums">
                {new Date(event.time * 1000).toLocaleTimeString([], { hour12: false })}
              </span>
              <span className={cn("min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]", event.level === "error" && "text-destructive")}>
                {event.message.trim()}
              </span>
            </div>
          ))}
          <div ref={end} />
        </div>
      </CardContent>
    </Card>
  )
}
