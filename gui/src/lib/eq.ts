import type { BandSpec, FilterSpec } from "@/lib/api"

const SAMPLE_RATE = 48000

// RBJ cookbook biquads: the same filters the speaker's DSP runs, so the curve on
// screen is the response that ships, ripple between bands included.
function biquadDb(filter: FilterSpec, gain: number, frequency: number): number {
  const a = Math.pow(10, gain / 40)
  const w0 = (2 * Math.PI * filter.frequency) / SAMPLE_RATE
  const cos = Math.cos(w0)
  const alpha = Math.sin(w0) / (2 * filter.q)
  let b: number[]
  let d: number[]
  if (filter.type === "low_shelf" || filter.type === "high_shelf") {
    const sa = 2 * Math.sqrt(a) * alpha
    const sign = filter.type === "low_shelf" ? 1 : -1
    b = [
      a * (a + 1 - sign * (a - 1) * cos + sa),
      sign * 2 * a * (a - 1 - sign * (a + 1) * cos),
      a * (a + 1 - sign * (a - 1) * cos - sa),
    ]
    d = [a + 1 + sign * (a - 1) * cos + sa, -sign * 2 * (a - 1 + sign * (a + 1) * cos), a + 1 + sign * (a - 1) * cos - sa]
  } else if (filter.type === "peaking") {
    b = [1 + alpha * a, -2 * cos, 1 - alpha * a]
    d = [1 + alpha / a, -2 * cos, 1 - alpha / a]
  } else {
    return 0
  }
  const w = (2 * Math.PI * frequency) / SAMPLE_RATE
  // |H(e^jw)| with z^-1 = e^-jw.
  const re = (c: number[]) => c[0] + c[1] * Math.cos(w) + c[2] * Math.cos(2 * w)
  const im = (c: number[]) => -c[1] * Math.sin(w) - c[2] * Math.sin(2 * w)
  const num = Math.hypot(re(b), im(b))
  const den = Math.hypot(re(d), im(d))
  return 20 * Math.log10(num / den)
}

export const CHART_MIN_HZ = 40
export const CHART_MAX_HZ = 20000

export function logSpace(count: number, low = CHART_MIN_HZ, high = CHART_MAX_HZ): number[] {
  const a = Math.log10(low)
  const b = Math.log10(high)
  return Array.from({ length: count }, (_, i) => Math.pow(10, a + ((b - a) * i) / (count - 1)))
}

/** The response of the model's real filter chain, or a log-frequency interpolation when its shape is unknown. */
export function responseCurve(
  gains: number[],
  frequencies: number[],
  shape: FilterSpec[] | null,
  points: number[],
): number[] {
  if (shape && shape.length === gains.length) {
    return points.map((f) => shape.reduce((sum, filter, i) => sum + biquadDb(filter, gains[i] ?? 0, f), 0))
  }
  const xs = frequencies.map((f) => Math.log2(f))
  return points.map((f) => {
    const x = Math.log2(f)
    if (x <= xs[0]) return gains[0] ?? 0
    if (x >= xs[xs.length - 1]) return gains[gains.length - 1] ?? 0
    const i = xs.findIndex((value, index) => index < xs.length - 1 && x >= value && x <= xs[index + 1])
    const t = (x - xs[i]) / (xs[i + 1] - xs[i])
    return gains[i] + t * (gains[i + 1] - gains[i])
  })
}

/** Snap a slider value onto the grid this band accepts. */
export function snapGain(value: number, band: BandSpec, extended: boolean): number {
  if (extended) return Math.round(value * 2) / 2
  const step = value < 0 ? band.neg_step : band.step
  const snapped = Math.round(value / step) * step
  return Math.min(band.max, Math.max(band.min, Number(snapped.toFixed(2))))
}

export function formatHz(f: number): string {
  return f >= 1000 ? `${f / 1000 >= 10 ? Math.round(f / 1000) : +(f / 1000).toFixed(1)}k` : `${Math.round(f)}`
}

export function formatDb(value: number): string {
  const rounded = Math.round(value * 100) / 100
  if (rounded === 0) return "0"
  return `${rounded > 0 ? "+" : "−"}${Math.abs(rounded)}`
}
