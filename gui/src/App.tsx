import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { flushSync } from "react-dom"
import { BluetoothSearchingIcon, Loader2Icon, LockIcon, MoonIcon, SunIcon } from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useTheme } from "next-themes"
import { toast } from "sonner"

import { ActionBar, type LiveStatus } from "@/components/action-bar"
import { ActivityLog } from "@/components/activity-log"
import { DevicePanel } from "@/components/device-panel"
import { EqSurface } from "@/components/eq-surface"
import { LogoMark } from "@/components/logo-mark"
import { displayName, ProfilePicker, type Tier } from "@/components/profile-picker"
import { WriteResult } from "@/components/write-result"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  api,
  ApiError,
  type ActivityEvent,
  type AppState,
  type Device,
  type ModelControls,
  type ModelSummary,
  type Preview,
  type Profile,
  type ProfileTiers,
  type WriteOutcome,
} from "@/lib/api"
import { formatDb } from "@/lib/eq"
import { EASE_OUT, pop, rise, stagger, swap } from "@/lib/motion"

const STORAGE_KEY = "openjbl.eq"
const TIERS: Tier[] = ["standard", "lab", "user"]

interface Prefs {
  tier?: Tier
  profile?: string
  live?: boolean
}

function remembered(): Prefs {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}")
  } catch {
    return {}
  }
}

function remember(update: Prefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...remembered(), ...update }))
  } catch {
    // Private windows can refuse storage; the page works without it.
  }
}

function fail(error: unknown, title = "Something went wrong") {
  toast.error(title, { description: error instanceof Error ? error.message : String(error) })
}

function sameGains(a: number[] | null | undefined, b: number[] | null | undefined): boolean {
  return !!a && !!b && a.length === b.length && a.every((value, i) => Math.abs(value - b[i]) < 0.01)
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const reduce = useReducedMotion()
  const dark = resolvedTheme !== "light"

  // The new theme spreads out in a circle from the button. View Transitions
  // snapshot the page, so the switch itself has to land inside the callback.
  const toggle = (event: React.MouseEvent<HTMLButtonElement>) => {
    const next = dark ? "light" : "dark"
    const apply = () => {
      flushSync(() => setTheme(next))
      document.documentElement.classList.toggle("dark", next === "dark")
      document.documentElement.style.colorScheme = next
    }
    if (reduce || !document.startViewTransition) {
      apply()
      return
    }
    const { left, top, width, height } = event.currentTarget.getBoundingClientRect()
    const x = left + width / 2
    const y = top + height / 2
    const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))
    document.startViewTransition(apply).ready.then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: 550, easing: "cubic-bezier(0.22, 1, 0.36, 1)", pseudoElement: "::view-transition-new(root)" },
      )
    })
  }

  return (
    <Button variant="ghost" size="icon" aria-label="Toggle theme" onClick={toggle}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={dark ? "sun" : "moon"}
          className="inline-flex"
          initial={{ rotate: -90, scale: 0.5, opacity: 0 }}
          animate={{ rotate: 0, scale: 1, opacity: 1 }}
          exit={{ rotate: 90, scale: 0.5, opacity: 0 }}
          transition={{ duration: 0.2, ease: EASE_OUT }}
        >
          {dark ? <SunIcon /> : <MoonIcon />}
        </motion.span>
      </AnimatePresence>
    </Button>
  )
}

/** A live dot: steady when idle, with a ring that keeps rippling out while the link is up. */
function LiveDot({ live }: { live: boolean }) {
  const reduce = useReducedMotion()
  return (
    <span className="relative flex size-1.5">
      {live && !reduce && (
        <motion.span
          className="absolute inset-0 rounded-full bg-primary-foreground"
          animate={{ scale: [1, 2.8], opacity: [0.7, 0] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
        />
      )}
      <span className={live ? "relative size-1.5 rounded-full bg-primary-foreground" : "relative size-1.5 rounded-full border border-current"} />
    </span>
  )
}

export default function App() {
  const [state, setState] = useState<AppState | null>(null)
  const [devices, setDevices] = useState<Device[]>([])
  const [models, setModels] = useState<ModelSummary[]>([])
  const [controls, setControls] = useState<ModelControls | null>(null)
  const [tiers, setTiers] = useState<ProfileTiers | null>(null)
  const [tier, setTier] = useState<Tier>(remembered().tier ?? "lab")
  const [profile, setProfile] = useState<Profile | null>(null)
  const [gains, setGains] = useState<number[]>([])
  const [edited, setEdited] = useState(false)
  const [hovered, setHovered] = useState<Profile | null>(null)
  const [speakerGains, setSpeakerGains] = useState<number[] | null>(null)
  const [outcome, setOutcome] = useState<WriteOutcome | null>(null)
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [pending, setPending] = useState<string | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState("")
  const [danger, setDanger] = useState<{ key: string; gains: number[] } | null>(null)
  const [live, setLive] = useState(remembered().live ?? false)
  const [liveStatus, setLiveStatus] = useState<LiveStatus>("idle")
  // Bumped whenever a whole new curve arrives, so the chart and sliders glide
  // into it rather than jumping. Dragging a slider does not bump it.
  const [morph, setMorph] = useState(0)
  const [justVerified, setJustVerified] = useState(false)
  const lastSeq = useRef(0)
  // Set after a connect: the next read should select whatever is on the speaker.
  const followSpeaker = useRef(false)
  // The instant-apply queue. Only the newest request matters, so it is one slot.
  const queued = useRef<{ key: string; gains: number[] } | null>(null)
  const draining = useRef(false)

  const verified = state?.verified ?? false
  const pid = state?.target?.pid ?? state?.pid ?? ""
  const busy = state?.busy ?? pending

  // Stable callbacks read the latest values from here instead of closing over
  // them, so the memoised panels do not re-render every time anything changes.
  const latest = useRef({ profile, gains, tier, live, verified, tiers })
  useLayoutEffect(() => {
    latest.current = { profile, gains, tier, live, verified, tiers }
  })

  const refreshState = useCallback(async () => {
    try {
      const next = await api.state()
      // Polled every two seconds: keep the old object when nothing changed so
      // the poll does not re-render the page in the middle of an animation.
      setState((previous) => (previous && JSON.stringify(previous) === JSON.stringify(next) ? previous : next))
    } catch {
      // The poll retries; a stopped server shows up as stale state, not a toast storm.
    }
  }, [])

  // State and activity are polled: the link can drop at any moment and the lock
  // has to follow it without the user doing anything.
  useEffect(() => {
    refreshState()
    const timer = setInterval(refreshState, 2000)
    return () => clearInterval(timer)
  }, [refreshState])

  useEffect(() => {
    const poll = async () => {
      try {
        const fresh = await api.events(lastSeq.current)
        if (fresh.length) {
          lastSeq.current = fresh[fresh.length - 1].seq
          setEvents((previous) => [...previous, ...fresh].slice(-400))
        }
      } catch {
        // Retried on the next tick.
      }
    }
    poll()
    const timer = setInterval(poll, 1200)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    api.models().then(setModels).catch((error) => fail(error, "Could not load the model list"))
  }, [])

  const loadProfiles = useCallback(async (forPid: string) => {
    const result = await api.profiles(forPid)
    setTiers(result)
    return result
  }, [])

  const choose = useCallback((next: Profile, nextTier: Tier) => {
    setProfile(next)
    setMorph((n) => n + 1)
    setGains(next.gains ?? [])
    setEdited(false)
    remember({ tier: nextTier, profile: next.key })
  }, [])

  // Everything about the EQ surface follows the model: its band count, grid and filters.
  useEffect(() => {
    if (!pid) return
    let cancelled = false
    ;(async () => {
      try {
        const [model, result] = await Promise.all([api.model(pid), loadProfiles(pid)])
        if (cancelled) return
        setControls(model)
        const saved = remembered()
        const wanted: Tier = !model.extended_allowed && saved.tier === "lab" ? "standard" : (saved.tier ?? (model.extended_allowed ? "lab" : "standard"))
        const pool = result[wanted]
        const pick = pool.find((p) => p.key === saved.profile && p.gains) ?? pool.find((p) => p.gains)
        const fallback = result.standard.find((p) => p.key === "balanced")
        const chosenTier = pick ? wanted : "standard"
        const chosen = pick ?? fallback
        setTier(chosenTier)
        if (chosen) choose(chosen, chosenTier)
      } catch (error) {
        fail(error, "Could not load the model")
      }
    })()
    return () => {
      cancelled = true
    }
  }, [pid, loadProfiles, choose])

  // After a connect, show what the speaker is already playing: select the
  // profile its read-back matches, if one does.
  useEffect(() => {
    if (!followSpeaker.current || !speakerGains || !tiers) return
    followSpeaker.current = false
    for (const key of TIERS) {
      const match = tiers[key].find((p) => sameGains(p.gains, speakerGains))
      if (match) {
        setTier(key)
        choose(match, key)
        return
      }
    }
  }, [speakerGains, tiers, choose])

  const run = useCallback(
    async <T,>(label: string, action: () => Promise<T>): Promise<T | undefined> => {
      setPending(label)
      try {
        return await action()
      } catch (error) {
        fail(error, `${label} failed`)
        return undefined
      } finally {
        setPending(null)
        refreshState()
      }
    },
    [refreshState],
  )

  const readSpeaker = useCallback(async () => {
    const result = await api.read()
    if (result.gains) setSpeakerGains(result.gains)
    return result
  }, [])

  const afterConnect = useCallback(
    async (model: string) => {
      toast.success(`${model} connected`, { description: "EQ route verified. Nothing has been written." })
      followSpeaker.current = true
      try {
        await readSpeaker()
      } catch {
        // Not every speaker answers a read; the page simply shows no dashed curve.
      }
    },
    [readSpeaker],
  )

  const setup = useCallback(
    () =>
      run("Auto setup", async () => {
        const result = await api.setup()
        setDevices(result.devices)
        if (result.target) {
          await afterConnect(result.target.model)
        } else {
          const unnamed = result.devices.find((device) => device.is_jbl && device.live && !device.pid)
          toast.warning(unnamed ? "Choose the speaker's model" : "Pick a speaker", {
            description: unnamed
              ? `${unnamed.name || "A JBL speaker"} did not say which model it is. Pick the model under it, then press Connect.`
              : `Found ${result.devices.length} device(s); ${result.reason}.`,
          })
        }
      }),
    [run, afterConnect],
  )

  const scan = useCallback(
    () =>
      run("Scanning", async () => {
        const result = await api.scan()
        setDevices(result.devices)
        toast(`${result.devices.length} device(s) found`)
      }),
    [run],
  )

  const connect = useCallback(
    (address: string, devicePid: string) =>
      run("Connecting", async () => {
        const target = await api.connect(address, devicePid)
        await afterConnect(target.model)
      }),
    [run, afterConnect],
  )

  const onConnect = useCallback((device: Device, devicePid: string) => connect(device.address, devicePid), [connect])
  const target = state?.target
  const onReverify = useCallback(() => {
    if (target) connect(target.address, target.pid)
  }, [connect, target])
  const disconnect = useCallback(() => run("Disconnecting", () => api.disconnect()), [run])

  /** One verified write. Returns true when the speaker read back exactly what was sent. */
  const write = useCallback(
    async (key: string, values: number[], { confirmDanger = false, quiet = false } = {}): Promise<boolean> => {
      setPending("Writing EQ")
      try {
        const result = await api.apply(key, values, confirmDanger)
        if (result.verification.actual) setSpeakerGains(result.verification.actual)
        const ok = result.result === "verified"
        // Instant apply writes on every pick; a toast and a table for each one
        // would bury the page. Only a write that did not verify speaks up.
        if (!quiet || !ok) {
          setOutcome(result)
          const show = result.severity === "information" ? toast.success : result.severity === "warning" ? toast.warning : toast.error
          show(result.title, { description: result.message })
        }
        if (ok) {
          setJustVerified(true)
          setTimeout(() => setJustVerified(false), 1600)
        }
        return ok
      } catch (error) {
        if (error instanceof ApiError && error.status === 428) {
          setDanger({ key, gains: values })
        } else {
          fail(error, "Write failed")
        }
        return false
      } finally {
        setPending(null)
        refreshState()
      }
    },
    [refreshState],
  )

  // Instant apply: picks queue into one slot and are written in order, so
  // clicking through profiles quickly ends on the last one, never on a stale one.
  const drain = useCallback(async () => {
    if (draining.current) return
    draining.current = true
    setLiveStatus("writing")
    let ok = true
    try {
      while (queued.current) {
        const job = queued.current
        queued.current = null
        ok = await write(job.key, job.gains, { quiet: true })
      }
    } finally {
      draining.current = false
      setLiveStatus(ok ? "done" : "error")
    }
  }, [write])

  const requestWrite = useCallback(
    (key: string, values: number[]) => {
      queued.current = { key, gains: values }
      void drain()
    },
    [drain],
  )

  const onSelect = useCallback(
    (next: Profile) => {
      choose(next, latest.current.tier)
      if (latest.current.live && latest.current.verified && next.gains) requestWrite(next.key, next.gains)
    },
    [choose, requestWrite],
  )

  const onTierChange = useCallback(
    (next: Tier) => {
      setTier(next)
      const pool = latest.current.tiers?.[next] ?? []
      const keep = pool.find((p) => p.key === latest.current.profile?.key)
      const pick = keep ?? pool.find((p) => p.gains)
      if (pick) choose(pick, next)
      else remember({ tier: next })
    },
    [choose],
  )

  const onGainsChange = useCallback((next: number[]) => {
    setGains(next)
    setEdited(true)
  }, [])

  const onCommit = useCallback(
    (next: number[]) => {
      const { live: on, verified: up, profile: current } = latest.current
      if (on && up && current) requestWrite(current.key, next)
    },
    [requestWrite],
  )

  const onLiveChange = useCallback(
    (on: boolean) => {
      setLive(on)
      remember({ live: on })
      setLiveStatus("idle")
      const { profile: current, gains: values, verified: up } = latest.current
      if (on && up && current) requestWrite(current.key, values)
    },
    [requestWrite],
  )

  const readCurrent = useCallback(
    () =>
      run("Reading EQ", async () => {
        const result = await readSpeaker()
        if (result.gains) {
          toast("Read the speaker's current EQ", { description: `Shown dashed on the chart · ${result.gains.map(formatDb).join("  ")}` })
        } else {
          toast.warning("The reply could not be decoded")
        }
      }),
    [run, readSpeaker],
  )

  const showPreview = useCallback(
    () =>
      run("Preview", async () => {
        const { profile: current, gains: values } = latest.current
        if (current) setPreview(await api.preview(current.key, values))
      }),
    [run],
  )

  const applyCurrent = useCallback(() => {
    const { profile: current, gains: values } = latest.current
    if (current) void write(current.key, values)
  }, [write])

  const saveProfile = () =>
    run("Save", async () => {
      const saved = await api.saveProfile(saveName.trim(), pid, gains)
      setSaveOpen(false)
      setSaveName("")
      const result = await loadProfiles(pid)
      const fresh = result.user.find((p) => p.key === saved.key) ?? saved
      setTier("user")
      choose(fresh, "user")
      toast.success(`Saved “${saved.name}”`, { description: "Find it under My profiles." })
    })

  const deleteProfile = useCallback(
    () =>
      run("Delete", async () => {
        const current = latest.current.profile
        if (!current) return
        await api.deleteProfile(current.key)
        const result = await loadProfiles(pid)
        const next = result.user[0] ?? result.standard[0]
        const nextTier: Tier = result.user.length ? "user" : "standard"
        setTier(nextTier)
        if (next) choose(next, nextTier)
        toast(`Deleted “${current.name}”`)
      }),
    [run, loadProfiles, pid, choose],
  )

  const openSave = useCallback(() => setSaveOpen(true), [])
  const onHover = useCallback((next: Profile | null) => setHovered(next), [])

  const onSpeaker = useMemo(() => {
    if (!speakerGains || !tiers) return null
    if (profile && sameGains(profile.gains, speakerGains)) return profile.key
    for (const key of TIERS) {
      const match = tiers[key].find((p) => sameGains(p.gains, speakerGains))
      if (match) return match.key
    }
    return null
  }, [speakerGains, tiers, profile])

  const title = profile ? displayName(profile) : "Custom"
  const ghost = hovered && hovered.key !== profile?.key ? hovered : null

  return (
    <div className="relative min-h-svh overflow-x-clip bg-background">
      <div className="ambient" aria-hidden />
      <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-3 px-4 sm:px-6">
          <LogoMark live={verified} busy={busy !== null} />
          <div className="flex items-baseline gap-2">
            <span className="font-semibold tracking-tight">OpenJBL</span>
            <span className="hidden text-sm text-muted-foreground sm:inline">EQ Control</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <AnimatePresence>
              {busy && (
                <motion.span key="busy" className="hidden sm:inline-flex" {...pop}>
                  <Badge variant="outline" className="gap-1.5">
                    <Loader2Icon className="animate-spin" />
                    {busy}
                  </Badge>
                </motion.span>
              )}
            </AnimatePresence>
            <Badge variant={verified ? "default" : "outline"} className="gap-1.5 transition-colors duration-300">
              <LiveDot live={verified} />
              <AnimatePresence mode="wait" initial={false}>
                <motion.span key={verified ? "on" : "off"} {...swap}>
                  {verified ? target?.model : "Not connected"}
                </motion.span>
              </AnimatePresence>
            </Badge>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <motion.main
        className="relative mx-auto grid max-w-[1440px] gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[320px_minmax(0,1fr)]"
        variants={stagger(0.06)}
        initial="hidden"
        animate="show"
      >
        <motion.div variants={rise} className="flex flex-col gap-6">
          <DevicePanel
            target={verified ? (target ?? null) : null}
            devices={devices}
            models={models}
            defaultPid={state?.pid ?? ""}
            busy={busy}
            onSetup={setup}
            onScan={scan}
            onConnect={onConnect}
            onReverify={onReverify}
            onDisconnect={disconnect}
          />
          <ActivityLog events={events} />
          <p className="px-1 text-[11px] text-muted-foreground">
            v{state?.version} · build {state?.build} · not affiliated with JBL or Harman
          </p>
        </motion.div>

        <motion.div variants={rise} className="flex min-w-0 flex-col gap-3 self-start">
          {/* Not overflow-hidden: the chart inside sticks to the window while the list scrolls. */}
          <Card className="overflow-visible">
            <CardHeader>
              <CardTitle className="text-base">Equalizer</CardTitle>
              <CardDescription>
                {controls ? `${controls.name} · ${controls.count} bands · ${controls.eq_path}` : "Loading model…"}
              </CardDescription>
              <CardAction>
                <AnimatePresence>
                  {!verified && (
                    <motion.span key="browse" className="inline-flex" {...pop}>
                      <Badge variant="outline" className="gap-1">
                        <LockIcon />
                        Browse only
                      </Badge>
                    </motion.span>
                  )}
                </AnimatePresence>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-5">
              <AnimatePresence initial={false}>
                {!verified && (
                  <motion.div
                    key="connect-hint"
                    className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed px-4 py-3"
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4, transition: { duration: 0.12 } }}
                    transition={{ duration: 0.2, ease: EASE_OUT }}
                  >
                    <BluetoothSearchingIcon className="size-4 shrink-0 text-muted-foreground" />
                    <p className="min-w-0 flex-1 text-sm text-muted-foreground">
                      Browse and compare curves freely. Connect your speaker to hear them.
                    </p>
                    <Button size="sm" disabled={busy !== null} onClick={setup}>
                      Connect speaker
                    </Button>
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] xl:items-start">
                <div className="order-2 min-w-0 xl:order-1">
                  <ProfilePicker
                    tiers={tiers}
                    tier={tier}
                    selected={profile?.key ?? null}
                    onSpeaker={onSpeaker}
                    onTierChange={onTierChange}
                    onSelect={onSelect}
                    onHover={onHover}
                  />
                </div>
                <div className="order-1 flex min-w-0 flex-col gap-4 xl:sticky xl:top-20 xl:order-2">
                  {controls && gains.length > 0 && (
                    <EqSurface
                      controls={controls}
                      title={title}
                      gains={gains}
                      morphKey={morph}
                      edited={edited}
                      extended={profile?.extended ?? false}
                      speakerGains={speakerGains}
                      ghost={ghost?.gains ?? null}
                      ghostName={ghost ? displayName(ghost) : null}
                      onChange={onGainsChange}
                      onCommit={onCommit}
                    />
                  )}
                </div>
              </div>
              {/* Below the grid, not under the chart: in the sticky column it made
                  the column taller than the list, and the chart stopped sticking. */}
              <AnimatePresence mode="popLayout">
                {outcome && controls && <WriteResult key={outcome.transaction_id} outcome={outcome} frequencies={controls.frequencies} />}
              </AnimatePresence>
            </CardContent>
          </Card>

          <ActionBar
            verified={verified}
            busy={busy}
            title={edited ? `${title} · edited` : title}
            live={live}
            liveStatus={liveStatus}
            canApply={profile !== null && gains.length > 0}
            canDelete={tier === "user" && !!profile?.key.startsWith("user-")}
            justVerified={justVerified}
            onLiveChange={onLiveChange}
            onRead={readCurrent}
            onPreview={showPreview}
            onSave={openSave}
            onDelete={deleteProfile}
            onApply={applyCurrent}
          />
        </motion.div>
      </motion.main>

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Save profile</DialogTitle>
            <DialogDescription>Stored as a tonal curve, so it still means something on another JBL model.</DialogDescription>
          </DialogHeader>
          <form
            className="flex flex-col gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              if (saveName.trim()) saveProfile()
            }}
          >
            <Label htmlFor="profile-name">Name</Label>
            <Input id="profile-name" autoFocus placeholder="Living room" value={saveName} onChange={(e) => setSaveName(e.target.value)} />
          </form>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSaveOpen(false)}>
              Cancel
            </Button>
            <Button disabled={!saveName.trim()} onClick={saveProfile}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={preview !== null} onOpenChange={(open) => !open && setPreview(null)}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Packet preview</DialogTitle>
            <DialogDescription>Exactly what Apply will send · {preview?.path}. Nothing has been sent.</DialogDescription>
          </DialogHeader>
          <div className="max-h-80 overflow-y-auto rounded-lg border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed break-all">
            {preview?.frames.map((frame, i) => <p key={i}>{frame}</p>)}
          </div>
          <p className="font-mono text-xs text-muted-foreground">gains {preview?.gains.map(formatDb).join("  ")}</p>
        </DialogContent>
      </Dialog>

      <AlertDialog open={danger !== null} onOpenChange={(open) => !open && setDanger(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Write a boost past +6 dB?</AlertDialogTitle>
            <AlertDialogDescription>
              A boost beyond the model's own range has to come out of the DSP's headroom and the limiter, so it can clip and then
              get quieter. Turn the volume down before you continue.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                const request = danger
                setDanger(null)
                if (request) void write(request.key, request.gains, { confirmDanger: true })
              }}
            >
              Write anyway
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
