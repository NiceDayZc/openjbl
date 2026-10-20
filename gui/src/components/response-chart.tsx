import { memo, useMemo, useRef, useState } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { useTweened } from "@/hooks/use-tweened"
import type { FilterSpec } from "@/lib/api"
import { CHART_MAX_HZ, CHART_MIN_HZ, formatDb, formatHz, logSpace, responseCurve } from "@/lib/eq"
import { EASE_OUT } from "@/lib/motion"

const WIDTH = 860
const HEIGHT = 240
const PAD = { left: 36, right: 12, top: 12, bottom: 24 }
const GRID_HZ = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
const POINTS = logSpace(200)
const LOG_MIN = Math.log10(CHART_MIN_HZ)
const LOG_SPAN = Math.log10(CHART_MAX_HZ) - LOG_MIN

function x(frequency: number): number {
  return PAD.left + ((Math.log10(frequency) - LOG_MIN) / LOG_SPAN) * (WIDTH - PAD.left - PAD.right)
}

function frequencyAt(px: number): number {
  const t = (px - PAD.left) / (WIDTH - PAD.left - PAD.right)
  return Math.pow(10, LOG_MIN + Math.min(1, Math.max(0, t)) * LOG_SPAN)
}

function path(values: number[], y: (db: number) => number): string {
  return values.map((db, i) => `${i ? "L" : "M"}${x(POINTS[i]).toFixed(1)},${y(db).toFixed(1)}`).join("")
}

interface ResponseChartProps {
  gains: number[]
  frequencies: number[]
  shape: FilterSpec[] | null
  /** What the speaker reported on the last read, drawn dashed for comparison. */
  reference?: number[] | null
  /** A profile the pointer is resting on, drawn faintly so it can be compared before choosing it. */
  ghost?: number[] | null
  /** Where `gains` is headed while it glides; the axis is sized for this, not for the frame. */
  target?: number[]
}

export const ResponseChart = memo(function ResponseChart({ gains, frequencies, shape, reference, ghost, target }: ResponseChartProps) {
  const svg = useRef<SVGSVGElement>(null)
  const reduce = useReducedMotion()
  const [hover, setHover] = useState<number | null>(null)
  const curve = useMemo(() => responseCurve(gains, frequencies, shape, POINTS), [gains, frequencies, shape])
  // Dots sit on the response itself, not at the slider value: a shelf reaches
  // only half its gain at its own corner frequency, and the chart should not hide that.
  const dots = useMemo(() => responseCurve(gains, frequencies, shape, frequencies), [gains, frequencies, shape])
  const refCurve = useMemo(
    () => (reference && reference.length === gains.length ? responseCurve(reference, frequencies, shape, POINTS) : null),
    [reference, gains.length, frequencies, shape],
  )
  const ghostCurve = useMemo(
    () => (ghost && ghost.length === gains.length ? responseCurve(ghost, frequencies, shape, POINTS) : null),
    [ghost, gains.length, frequencies, shape],
  )

  const targetCurve = useMemo(
    () => (target && target.length === gains.length ? responseCurve(target, frequencies, shape, POINTS) : null),
    [target, gains.length, frequencies, shape],
  )
  // Sized for where the curve is going rather than for the current frame, so a
  // morph never rescales the axis halfway; when the scale does change it glides.
  const extent = Math.max(
    12,
    ...(targetCurve ?? curve).map(Math.abs),
    ...(refCurve ?? []).map(Math.abs),
    ...(ghostCurve ?? []).map(Math.abs),
  )
  const targetRange = Math.ceil(extent / 6) * 6
  const [range] = useTweened([targetRange], targetRange)
  const y = (db: number) => PAD.top + ((range - db) / (2 * range)) * (HEIGHT - PAD.top - PAD.bottom)
  const top = Math.floor(range / 6) * 6
  const gridDb = Array.from({ length: (2 * top) / 6 + 1 }, (_, i) => top - i * 6)
  const area = `${path(curve, y)}L${x(CHART_MAX_HZ)},${y(0)}L${x(CHART_MIN_HZ)},${y(0)}Z`

  const readout = useMemo(() => {
    if (hover === null) return null
    const [value] = responseCurve(gains, frequencies, shape, [hover])
    const [speaker] = reference && reference.length === gains.length ? responseCurve(reference, frequencies, shape, [hover]) : [null]
    return { value, speaker }
  }, [hover, gains, frequencies, shape, reference])

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const box = svg.current?.getBoundingClientRect()
    if (!box) return
    const px = ((event.clientX - box.left) / box.width) * WIDTH
    setHover(px < PAD.left || px > WIDTH - PAD.right ? null : frequencyAt(px))
  }

  const hx = hover === null ? 0 : x(hover)
  const labelRight = hx > WIDTH - 170

  return (
    <svg
      ref={svg}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="h-auto w-full touch-none select-none"
      role="img"
      aria-label="EQ frequency response"
      onPointerMove={onPointerMove}
      onPointerLeave={() => setHover(null)}
    >
      <defs>
        <linearGradient id="response-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.16" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <g className="text-border" stroke="currentColor" strokeWidth="1">
        {gridDb.map((db) => (
          <line key={db} x1={PAD.left} x2={WIDTH - PAD.right} y1={y(db)} y2={y(db)} strokeDasharray={db === 0 ? undefined : "2 4"} />
        ))}
        {GRID_HZ.map((f) => (
          <line key={f} x1={x(f)} x2={x(f)} y1={PAD.top} y2={HEIGHT - PAD.bottom} strokeDasharray="2 4" />
        ))}
      </g>
      <g className="fill-muted-foreground font-mono text-[10px]">
        {gridDb.map((db) => (
          <text key={db} x={PAD.left - 6} y={y(db) + 3} textAnchor="end">
            {db > 0 ? `+${db}` : db}
          </text>
        ))}
        {GRID_HZ.map((f) => (
          <text key={f} x={x(f)} y={HEIGHT - 6} textAnchor="middle">
            {formatHz(f)}
          </text>
        ))}
      </g>
      <motion.path
        d={area}
        fill="url(#response-fill)"
        className="text-foreground"
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.1, ease: EASE_OUT }}
      />
      <AnimatePresence>
        {refCurve && (
          <motion.path
            key="reference"
            d={path(refCurve, y)}
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            className="text-muted-foreground"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
          />
        )}
        {ghostCurve && (
          <motion.path
            key="ghost"
            d={path(ghostCurve, y)}
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            className="text-foreground/35"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
          />
        )}
      </AnimatePresence>
      <motion.path
        d={path(curve, y)}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        className="text-foreground"
        initial={reduce ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.6, ease: EASE_OUT }}
      />
      {frequencies.map((f, i) => (
        <motion.circle
          key={f}
          cx={x(Math.min(Math.max(f, CHART_MIN_HZ), CHART_MAX_HZ))}
          cy={y(dots[i] ?? 0)}
          r="3.5"
          className="fill-background stroke-foreground"
          strokeWidth="1.5"
          initial={reduce ? false : { opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.15 + i * 0.03, type: "spring", stiffness: 600, damping: 30 }}
          style={{ transformBox: "fill-box", transformOrigin: "center" }}
        />
      ))}
      {readout && hover !== null && (
        <g pointerEvents="none">
          <line x1={hx} x2={hx} y1={PAD.top} y2={HEIGHT - PAD.bottom} className="stroke-foreground/40" strokeWidth="1" />
          <circle cx={hx} cy={y(readout.value)} r="4" className="fill-foreground" />
          {readout.speaker !== null && <circle cx={hx} cy={y(readout.speaker)} r="3" className="fill-muted-foreground" />}
          <g transform={`translate(${labelRight ? hx - 10 : hx + 10}, ${PAD.top + 4})`}>
            <rect
              x={labelRight ? -150 : 0}
              width="150"
              height={readout.speaker !== null ? 46 : 32}
              rx="6"
              className="fill-popover stroke-border"
            />
            <text x={labelRight ? -140 : 10} y="14" className="fill-muted-foreground font-mono text-[10px]">
              {formatHz(hover)} Hz
            </text>
            <text x={labelRight ? -140 : 10} y="27" className="fill-foreground font-mono text-[11px] font-medium">
              {formatDb(Math.round(readout.value * 10) / 10)} dB this curve
            </text>
            {readout.speaker !== null && (
              <text x={labelRight ? -140 : 10} y="40" className="fill-muted-foreground font-mono text-[10px]">
                {formatDb(Math.round(readout.speaker * 10) / 10)} dB on speaker
              </text>
            )}
          </g>
        </g>
      )}
    </svg>
  )
})
