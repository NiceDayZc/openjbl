import { motion, useReducedMotion } from "motion/react"

// Resting heights, as a fraction of the mark: a small equalizer.
const REST = [0.45, 0.8, 0.55, 0.95, 0.6]
// Each bar breathes on its own period so the motion never visibly loops.
const PERIOD = [1.3, 0.9, 1.6, 1.1, 1.4]

/**
 * The OpenJBL mark: still while idle, alive while a speaker is connected,
 * quicker while something is running. The bars scale rather than change
 * height, so the loop costs the compositor and nothing else.
 */
export function LogoMark({ live, busy }: { live: boolean; busy: boolean }) {
  const reduce = useReducedMotion()
  const moving = (live || busy) && !reduce
  return (
    <div className="flex size-8 items-center justify-center rounded-lg bg-foreground text-background" aria-hidden>
      <div className="flex h-4 items-center gap-[2px]">
        {REST.map((rest, i) => (
          <motion.span
            key={i}
            className="h-full w-[2px] origin-center rounded-full bg-current will-change-transform"
            initial={{ scaleY: rest }}
            animate={moving ? { scaleY: [rest, Math.max(0.25, rest - 0.35), 1, rest] } : { scaleY: rest }}
            transition={
              moving
                ? { duration: PERIOD[i] * (busy ? 0.55 : 1), repeat: Infinity, ease: "easeInOut" }
                : { duration: 0.3 }
            }
          />
        ))}
      </div>
    </div>
  )
}
