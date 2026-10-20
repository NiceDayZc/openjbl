import { useEffect, useRef, useState } from "react"
import { animate, useReducedMotion } from "motion/react"

import { EASE_SNAP } from "@/lib/motion"

/**
 * Glide a list of numbers to a new target whenever `key` changes.
 *
 * Choosing a profile morphs the curve and the sliders from the old shape to the
 * new one. Dragging a slider must not: it keeps the same key, so the value lands
 * immediately and the thumb stays under the pointer. Keep the component that
 * calls this small -- it re-renders on every frame of the glide.
 */
export function useTweened(target: number[], key: unknown, duration = 0.34): number[] {
  const reduce = useReducedMotion()
  const [frame, setFrame] = useState<number[] | null>(null)
  const displayed = useRef(target)
  const lastKey = useRef(key)

  // eslint-disable-next-line react-hooks/refs -- the previous frame is the glide's starting point
  const morphing = key !== lastKey.current && !reduce && displayed.current.length === target.length

  useEffect(() => {
    if (key === lastKey.current) return
    lastKey.current = key
    const from = displayed.current
    if (reduce || from.length !== target.length) return
    const controls = animate(0, 1, {
      duration,
      ease: EASE_SNAP,
      onUpdate: (t) => setFrame(from.map((value, i) => value + (target[i] - value) * t)),
      onComplete: () => setFrame(null),
    })
    return () => {
      controls.stop()
      setFrame(null)
    }
  }, [key, target, reduce, duration])

  // Until the first animation frame lands, hold the old shape rather than
  // flashing the new one for a frame.
  // eslint-disable-next-line react-hooks/refs -- see above
  const value = frame ?? (morphing ? displayed.current : target)
  // eslint-disable-next-line react-hooks/refs -- recorded for the next glide
  displayed.current = value
  return value
}
