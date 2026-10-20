import { memo } from "react"
import { CheckIcon, DownloadIcon, EyeIcon, Loader2Icon, SaveIcon, Trash2Icon, ZapIcon } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { EASE_OUT, swap } from "@/lib/motion"

export type LiveStatus = "idle" | "writing" | "done" | "error"

interface ActionBarProps {
  verified: boolean
  busy: string | null
  title: string
  live: boolean
  liveStatus: LiveStatus
  canApply: boolean
  canDelete: boolean
  justVerified: boolean
  onLiveChange: (live: boolean) => void
  onRead: () => void
  onPreview: () => void
  onSave: () => void
  onDelete: () => void
  onApply: () => void
}

function IconAction({ label, disabled, onClick, children }: { label: string; disabled: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button variant="ghost" size="icon" aria-label={label} disabled={disabled} onClick={onClick}>
            {children}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

const STATUS: Record<LiveStatus, string> = {
  idle: "Pick a profile to hear it",
  writing: "Writing to the speaker…",
  done: "On the speaker, verified",
  error: "Last write did not verify",
}

/**
 * Pinned to the bottom of the window, so Apply is never a scroll away from the
 * profile that was just picked.
 */
export const ActionBar = memo(function ActionBar({
  verified,
  busy,
  title,
  live,
  liveStatus,
  canApply,
  canDelete,
  justVerified,
  onLiveChange,
  onRead,
  onPreview,
  onSave,
  onDelete,
  onApply,
}: ActionBarProps) {
  const writing = busy === "Writing EQ"
  const idle = busy === null
  return (
    <div className="sticky bottom-4 z-20">
      <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-background/85 p-2 shadow-lg ring-1 ring-foreground/5 backdrop-blur-md">
        <div className="flex items-center">
          <IconAction label="Read current" disabled={!verified || !idle} onClick={onRead}>
            <DownloadIcon />
          </IconAction>
          <IconAction label="Preview" disabled={!verified || !idle || !canApply} onClick={onPreview}>
            <EyeIcon />
          </IconAction>
          <IconAction label="Save as" disabled={!idle} onClick={onSave}>
            <SaveIcon />
          </IconAction>
          {canDelete && (
            <IconAction label="Delete" disabled={!idle} onClick={onDelete}>
              <Trash2Icon />
            </IconAction>
          )}
        </div>

        <div className="mx-1 h-6 w-px bg-border" />

        <div className="flex items-center gap-2 px-1">
          <Switch id="instant-apply" checked={live} onCheckedChange={onLiveChange} disabled={!verified} />
          <Label htmlFor="instant-apply" className="cursor-pointer text-sm">
            Instant apply
          </Label>
        </div>

        <div className="ml-auto flex min-w-0 items-center gap-3">
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={live ? liveStatus : title}
              className="hidden truncate text-xs text-muted-foreground sm:block"
              {...swap}
            >
              {live && verified ? STATUS[liveStatus] : title}
            </motion.span>
          </AnimatePresence>
          <Button className="relative min-w-44 overflow-hidden" disabled={!verified || !idle || !canApply} onClick={onApply}>
            {writing && (
              // A highlight sweeping across the button while the write and its readback run.
              <motion.span
                className="pointer-events-none absolute inset-y-0 -left-1/2 w-1/2 bg-gradient-to-r from-transparent via-primary-foreground/25 to-transparent"
                animate={{ x: ["0%", "300%"] }}
                transition={{ duration: 1, repeat: Infinity, ease: "easeInOut" }}
              />
            )}
            <AnimatePresence mode="popLayout" initial={false}>
              <motion.span
                key={writing ? "writing" : justVerified ? "verified" : "idle"}
                className="relative inline-flex items-center gap-1.5"
                initial={{ y: 12, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: -12, opacity: 0 }}
                transition={{ duration: 0.2, ease: EASE_OUT }}
              >
                {writing ? (
                  <>
                    <Loader2Icon className="size-4 animate-spin" />
                    Writing & verifying…
                  </>
                ) : justVerified ? (
                  <>
                    <CheckIcon className="size-4" />
                    Verified on speaker
                  </>
                ) : (
                  <>
                    <ZapIcon className="size-4" />
                    Apply to speaker
                  </>
                )}
              </motion.span>
            </AnimatePresence>
          </Button>
        </div>
      </div>
    </div>
  )
})
