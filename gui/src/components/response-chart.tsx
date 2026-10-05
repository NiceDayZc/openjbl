import { useMemo } from "react"

import type { FilterSpec } from "@/lib/api"
import { CHART_MAX_HZ, CHART_MIN_HZ, formatHz, logSpace, responseCurve } from "@/lib/eq"

const WIDTH = 860
const HEIGHT = 220
const PAD = { left: 36, right: 12, top: 12, bottom: 24 }
const GRID_HZ = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
const POINTS = logSpace(240)

function x(frequency: number): number {
  const t = (Math.log10(frequency) - Math.log10(CHART_MIN_HZ)) / (Math.log10(CHART_MAX_HZ) - Math.log10(CHART_MIN_HZ))
  return PAD.left + t * (WIDTH - PAD.left - PAD.right)
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
}

export function ResponseChart({ gains, frequencies, shape, reference }: ResponseChartProps) {
  const curve = useMemo(() => responseCurve(gains, frequencies, shape, POINTS), [gains, frequencies, shape])
  // Dots sit on the response itself, not at the slider value: a shelf reaches
  // only half its gain at its own corner frequency, and the chart should not hide that.
  const dots = useMemo(() => responseCurve(gains, frequencies, shape, frequencies), [gains, frequencies, shape])
  const refCurve = useMemo(
    () => (reference && reference.length === gains.length ? responseCurve(reference, frequencies, shape, POINTS) : null),
    [reference, gains.length, frequencies, shape],
  )

  // Symmetric about 0 dB and never tighter than +/-12, so small curves keep their scale.
  const extent = Math.max(12, ...curve.map(Math.abs), ...(refCurve ?? []).map(Math.abs))
  const range = Math.ceil(extent / 6) * 6
  const y = (db: number) => PAD.top + ((range - db) / (2 * range)) * (HEIGHT - PAD.top - PAD.bottom)
  const gridDb = Array.from({ length: (2 * range) / 6 + 1 }, (_, i) => range - i * 6)
  const area = `${path(curve, y)}L${x(CHART_MAX_HZ)},${y(0)}L${x(CHART_MIN_HZ)},${y(0)}Z`

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full select-none" role="img" aria-label="EQ frequency response">
      <defs>
        <linearGradient id="response-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.14" />
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
      <path d={area} fill="url(#response-fill)" className="text-foreground" />
      {refCurve && (
        <path d={path(refCurve, y)} fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 4" className="text-muted-foreground" />
      )}
      <path d={path(curve, y)} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" className="text-foreground" />
      {frequencies.map((f, i) => (
        <circle key={f} cx={x(Math.min(Math.max(f, CHART_MIN_HZ), CHART_MAX_HZ))} cy={y(dots[i] ?? 0)} r="3.5" className="fill-background stroke-foreground" strokeWidth="1.5" />
      ))}
    </svg>
  )
}
