import { memo } from "react"

import { Slider } from "@/components/ui/slider"
import type { BandSpec } from "@/lib/api"
import { formatDb, formatHz, snapGain } from "@/lib/eq"
import { cn } from "@/lib/utils"

interface BandSlidersProps {
  gains: number[]
  /** What to draw: the same as `gains` at rest, mid-glide while a new profile morphs in. */
  display?: number[]
  frequencies: number[]
  bands: BandSpec[]
  extended: boolean
  disabled?: boolean
  onChange: (gains: number[]) => void
  /** Called once when a drag or key press ends, with the gains it landed on. */
  onCommit?: (gains: number[]) => void
  /** What the speaker last reported; each band shows whether it matches. */
  speaker?: number[] | null
}

// LAB reaches -24 dB on the way down. Upward it stops at +12: past that a boost
// only buys clipping, and anything above +6 still has to be confirmed.
const EXTENDED_MIN = -24
const EXTENDED_MAX = 12

/** A dot per band: filled when the speaker holds exactly this value, a ring when it holds something else. */
function BandMatch({ requested, actual }: { requested: number; actual: number | undefined }) {
  if (actual === undefined) return <span className="size-1.5" />
  const match = Math.abs(actual - requested) < 0.01
  return (
    <span
      title={match ? "The speaker holds this value" : `The speaker holds ${formatDb(actual)} dB`}
      aria-label={match ? "matches the speaker" : "differs from the speaker"}
      className={cn(
        "size-1.5 rounded-full transition-[background-color,box-shadow,transform] duration-300",
        match ? "scale-100 bg-foreground" : "scale-90 bg-transparent ring-1 ring-muted-foreground",
      )}
    />
  )
}

export const BandSliders = memo(function BandSliders({
  gains,
  display = gains,
  frequencies,
  bands,
  extended,
  disabled,
  onChange,
  onCommit,
  speaker,
}: BandSlidersProps) {
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${gains.length}, minmax(0, 1fr))` }}>
      {gains.map((gain, index) => {
        const band = bands[index] ?? { min: -6, max: 6, step: 0.5, neg_step: 0.5 }
        const min = extended ? EXTENDED_MIN : band.min
        const max = extended ? EXTENDED_MAX : band.max
        const shown = Math.min(max, Math.max(min, display[index] ?? gain))
        const gliding = Math.abs(shown - gain) > 1e-6
        const boost = gain > 6
        // Fill from 0 dB rather than from the bottom of the track, so a cut reads as a cut.
        const zero = (max / (max - min)) * 100
        const level = ((max - shown) / (max - min)) * 100
        const next = (value: number) => {
          const values = [...gains]
          values[index] = snapGain(value, band, extended)
          return values
        }
        return (
          <div key={index} className="group/band flex flex-col items-center gap-3">
            <span
              className={cn(
                "w-full rounded-md py-1 text-center font-mono text-xs tabular-nums transition-colors duration-200",
                boost ? "bg-foreground text-background" : gain === 0 ? "text-muted-foreground" : "text-foreground",
              )}
            >
              {/* Mid-glide the label counts through tenths; at rest it shows the exact grid value. */}
              {formatDb(gliding ? Math.round(shown * 10) / 10 : gain)}
            </span>
            <div className="relative flex h-40 w-full justify-center rounded-lg transition-colors duration-200 group-hover/band:bg-muted/40">
              <span
                className="pointer-events-none absolute left-1/2 z-[5] h-px w-4 -translate-x-1/2 bg-muted-foreground/60"
                style={{ top: `${zero}%` }}
              />
              <span
                className="pointer-events-none absolute left-1/2 z-[5] w-1 -translate-x-1/2 rounded-full bg-foreground"
                style={{ top: `${Math.min(zero, level)}%`, height: `${Math.abs(zero - level)}%` }}
              />
              <Slider
                orientation="vertical"
                className="h-40 **:data-[slot=slider-range]:bg-transparent **:data-[slot=slider-thumb]:z-10 **:data-[slot=slider-thumb]:size-3.5 **:data-[slot=slider-thumb]:transition-transform **:data-[slot=slider-thumb]:hover:scale-125 **:data-[slot=slider-thumb]:active:scale-110"
                min={min}
                max={max}
                step={extended ? 0.5 : 0.25}
                value={[shown]}
                disabled={disabled}
                aria-label={`${formatHz(frequencies[index] ?? 0)} Hz gain`}
                onValueChange={([value]) => {
                  const values = next(value)
                  if (values[index] !== gain) onChange(values)
                }}
                onValueCommit={([value]) => onCommit?.(next(value))}
              />
            </div>
            <span className="flex flex-col items-center gap-1 font-mono text-[11px] text-muted-foreground transition-colors group-hover/band:text-foreground">
              {formatHz(frequencies[index] ?? 0)}
              <BandMatch requested={gain} actual={speaker?.[index]} />
            </span>
          </div>
        )
      })}
    </div>
  )
})
