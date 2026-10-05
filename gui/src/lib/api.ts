// Every call carries the per-launch token the server wrote into the page. Other
// pages in the browser cannot read it, so they cannot drive the speaker.
const token =
  document.querySelector<HTMLMetaElement>('meta[name="openjbl-token"]')?.content ??
  import.meta.env.VITE_OPENJBL_TOKEN ??
  ""

export class ApiError extends Error {
  status: number
  body: Record<string, unknown>

  constructor(status: number, message: string, body: Record<string, unknown>) {
    super(message)
    this.status = status
    this.body = body
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: {
      "X-OpenJBL-Token": token,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = (await response.json().catch(() => ({}))) as Record<string, unknown>
  if (!response.ok) {
    throw new ApiError(response.status, String(data.error ?? response.statusText), data)
  }
  return data as T
}

export interface Target {
  address: string
  pid: string
  name: string
  model: string
  firmware: string
  eq_path: string
  supported: string[]
  services: number
}

export interface AppState {
  version: string
  build: string
  address: string
  pid: string
  verified: boolean
  target: Target | null
  busy: string | null
  event_seq: number
}

export interface Device {
  address: string
  name: string
  rssi: number | null
  live: boolean
  is_jbl: boolean
  model: string | null
  pid: string | null
  confidence: string | null
}

export interface ScanResult {
  devices: Device[]
  candidate: string | null
  reason: string
  target?: Target | null
}

export interface ModelSummary {
  pid: string
  name: string
  bands: number
}

export interface BandSpec {
  min: number
  max: number
  step: number
  neg_step: number
}

export interface FilterSpec {
  type: string
  frequency: number
  q: number
}

export interface ModelControls {
  pid: string
  name: string
  eq_path: string
  count: number
  frequencies: number[]
  shape: FilterSpec[] | null
  decibels: boolean
  extended_allowed: boolean
  bands: BandSpec[]
}

export interface Profile {
  key: string
  name: string
  description: string
  curve: number[]
  gains: number[] | null
  error: string | null
  extended: boolean
  boosts: boolean
  tags: string[]
}

export interface ProfileTiers {
  standard: Profile[]
  lab: Profile[]
  user: Profile[]
}

export interface Verification {
  status: string
  source: string
  expected: number[]
  actual: number[] | null
  deltas: number[] | null
  message: string
}

export interface WriteOutcome {
  transaction_id: string
  path: string
  ack: string
  precheck: Verification
  verification: Verification
  reconnects: number
  elapsed_ms: number
  result: "verified" | "ack-issue" | "mismatch" | "unverified"
  outcome: string
  title: string
  message: string
  severity: "information" | "warning" | "error"
  frames: string[]
}

export interface ActivityEvent {
  seq: number
  time: number
  level: "info" | "success" | "warning" | "error"
  message: string
}

export interface Preview {
  path: string
  frames: string[]
  gains: number[]
  dangerous: boolean
}

export const api = {
  state: () => request<AppState>("GET", "/state"),
  models: () => request<ModelSummary[]>("GET", "/models"),
  model: (pid: string) => request<ModelControls>("GET", `/model/${encodeURIComponent(pid)}`),
  profiles: (pid: string) => request<ProfileTiers>("GET", `/profiles?pid=${encodeURIComponent(pid)}`),
  events: (after: number) => request<ActivityEvent[]>("GET", `/events?after=${after}`),
  setup: () => request<ScanResult>("POST", "/setup"),
  scan: () => request<ScanResult>("POST", "/scan"),
  connect: (address: string, pid: string) => request<Target>("POST", "/connect", { address, pid }),
  disconnect: () => request<AppState>("POST", "/disconnect"),
  read: () => request<{ path: string; gains: number[] | null; source: string; replies: number }>("POST", "/read"),
  preview: (profile: string, gains: number[]) => request<Preview>("POST", "/preview", { profile, gains }),
  apply: (profile: string, gains: number[], confirmDanger = false) =>
    request<WriteOutcome>("POST", "/apply", { profile, gains, confirm_danger: confirmDanger }),
  saveProfile: (name: string, pid: string, gains: number[]) =>
    request<Profile>("POST", "/profiles", { name, pid, gains }),
  deleteProfile: (key: string) => request<{ deleted: boolean }>("DELETE", `/profiles/${encodeURIComponent(key)}`),
}
