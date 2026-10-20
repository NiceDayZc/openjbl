import { memo } from "react"
import { AnimatePresence, motion } from "motion/react"

import { BandSliders } from "@/components/band-sliders"
import { ResponseChart } from "@/components/response-chart"
import { Badge } from "@/components/ui/badge"
import { useTweened } from "@/hooks/use-tweened"
import type { ModelControls } from "@/lib/api"
import { formatDb } from "@/lib/eq"
import { pop, swap } from "@/lib/motion"

interface EqSurfaceProps {
  controls: ModelControls
  title: string
  gains: number[]
  /** Changes whenever a whole new curve arrives; the surface glides into it. */
  morphKey: number
  edited: boolean
  extended: boolean
  speakerGains: number[] | null
  ghost: number[] | null
  ghostName: string | null
  onChange: (gains: number[]) => void
  onCommit: (gains: number[]) => void
}

/**
 * The chart and the sliders. Its own component on purpose: the glide between
 * profiles re-renders on every frame, and only this needs to.
 */
export const EqSurface = memo(function EqSurface({
  controls,
  title,
  gains,
  morphKey,
  edited,
  extended,
  speakerGains,
  ghost,
  ghostName,
  onChange,
  onCommit,
}: EqSurfaceProps) {
  const display = useTweened(gains, morphKey)
  const boosting = gains.some((g) => g > 6)
  const range = gains.length ? `${formatDb(Math.min(...gains))} … ${formatDb(Math.max(...gains))} dB` : "—"

  return (
    <div className="flex flex-col gap-4 rounded-xl border bg-card p-4">
      <div className="flex min-h-6 flex-wrap items-center gap-2">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span key={title} className="text-sm font-medium" {...swap}>
            {title}
          </motion.span>
        </AnimatePresence>
        <AnimatePresence initial={false}>
          {edited && (
            <motion.span key="edited" className="inline-flex" {...pop}>
              <Badge variant="secondary">Edited</Badge>
            </motion.span>
          )}
          {extended && (
            <motion.span key="lab" className="inline-flex" {...pop}>
              <Badge variant="outline">LAB</Badge>
            </motion.span>
          )}
          {boosting && (
            <motion.span key="boost" className="inline-flex" {...pop}>
              <Badge>Boost &gt; +6 dB</Badge>
            </motion.span>
          )}
        </AnimatePresence>
        <span className="ml-auto font-mono text-xs text-muted-foreground">{range}</span>
      </div>

      <ResponseChart
        gains={display}
        target={gains}
        frequencies={controls.frequencies}
        shape={controls.shape}
        reference={speakerGains}
        ghost={ghost}
      />

      <div className="flex min-h-4 flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded-full bg-foreground" /> This curve on {controls.shape ? "the speaker's real filters" : "its bands"}
        </span>
        <AnimatePresence initial={false}>
          {speakerGains && (
            <motion.span key="speaker" className="flex items-center gap-1.5" {...swap}>
              <span className="w-4 border-t-[1.5px] border-dashed border-muted-foreground" /> On the speaker now
            </motion.span>
          )}
          {ghostName && (
            <motion.span key="ghost" className="flex items-center gap-1.5 text-foreground" {...swap}>
              <span className="h-0.5 w-4 rounded-full bg-foreground/35" /> Preview: {ghostName}
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      <BandSliders
        gains={gains}
        display={display}
        frequencies={controls.frequencies}
        bands={controls.bands}
        extended={extended}
        onChange={onChange}
        onCommit={onCommit}
        speaker={speakerGains}
      />
    </div>
  )
})
