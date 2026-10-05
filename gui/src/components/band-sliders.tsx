import { Slider } from "@/components/ui/slider"
import type { BandSpec } from "@/lib/api"
import { formatDb, formatHz, snapGain } from "@/lib/eq"
import { cn } from "@/lib/utils"

interface BandSlidersProps {
  gains: number[]
  frequencies: number[]
  bands: BandSpec[]
  extended: boolean
  disabled?: boolean
  onChange: (gains: number[]) => void
}

// LAB reaches -24 dB on the way down. Upward it stops at +12: past that a boost
// only buys clipping, and anything above +6 still has to be confirmed.
const EXTENDED_MIN = -24
const EXTENDED_MAX = 12

export function BandSliders({ gains, frequencies, bands, extended, disabled, onChange }: BandSlidersProps) {
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${gains.length}, minmax(0, 1fr))` }}>
      {gains.map((gain, index) => {
        const band = bands[index] ?? { min: -6, max: 6, step: 0.5, neg_step: 0.5 }
        const min = extended ? EXTENDED_MIN : band.min
        const max = extended ? EXTENDED_MAX : band.max
        const boost = gain > 6
        // Fill from 0 dB rather than from the bottom of the track, so a cut reads as a cut.
        const zero = (max / (max - min)) * 100
        const level = ((max - Math.min(max, Math.max(min, gain))) / (max - min)) * 100
        return (
          <div key={index} className="flex flex-col items-center gap-3">
            <span
              className={cn(
                "w-full rounded-md py-1 text-center font-mono text-xs tabular-nums",
                boost ? "bg-foreground text-background" : gain === 0 ? "text-muted-foreground" : "text-foreground",
              )}
            >
              {formatDb(gain)}
            </span>
            <div className="relative flex h-40 w-full justify-center">
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
                className="h-40 **:data-[slot=slider-range]:bg-transparent **:data-[slot=slider-thumb]:z-10 **:data-[slot=slider-thumb]:size-3.5"
                min={min}
                max={max}
                step={extended ? 0.5 : 0.25}
                value={[Math.min(max, Math.max(min, gain))]}
                disabled={disabled}
                aria-label={`${formatHz(frequencies[index] ?? 0)} Hz gain`}
                onValueChange={([value]) => {
                  const next = [...gains]
                  next[index] = snapGain(value, band, extended)
                  if (next[index] !== gain) onChange(next)
                }}
              />
            </div>
            <span className="font-mono text-[11px] text-muted-foreground">{formatHz(frequencies[index] ?? 0)}</span>
          </div>
        )
      })}
    </div>
  )
}
