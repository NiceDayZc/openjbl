import type { Transition, Variants } from "motion/react"

// One motion vocabulary for the whole page, so nothing moves on its own terms.
//
// Everything here animates opacity and transform only. Those run on the
// compositor; blur filters, heights and colours repaint every frame and were
// what made the first version stutter.
export const EASE_OUT = [0.22, 1, 0.36, 1] as const
// Quick off the mark, soft landing: for things the user just asked for.
export const EASE_SNAP = [0.32, 0.72, 0, 1] as const

export const spring: Transition = { type: "spring", stiffness: 560, damping: 40, mass: 0.6 }

export const rise: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.32, ease: EASE_OUT } },
}

export const riseSmall: Variants = {
  hidden: { opacity: 0, y: 4 },
  show: { opacity: 1, y: 0, transition: { duration: 0.2, ease: EASE_OUT } },
}

export function stagger(step = 0.04, delay = 0): Variants {
  return { hidden: {}, show: { transition: { staggerChildren: step, delayChildren: delay } } }
}

export const swap = {
  initial: { opacity: 0, y: 4 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: 0.16, ease: EASE_OUT },
} as const

export const pop = {
  initial: { opacity: 0, scale: 0.85 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.85 },
  transition: spring,
} as const
