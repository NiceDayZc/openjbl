import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { AudioLinesIcon, DownloadIcon, EyeIcon, Loader2Icon, LockIcon, MoonIcon, SaveIcon, SunIcon, Trash2Icon, ZapIcon } from "lucide-react"
import { useTheme } from "next-themes"
import { toast } from "sonner"

import { ActivityLog } from "@/components/activity-log"
import { BandSliders } from "@/components/band-sliders"
import { DevicePanel } from "@/components/device-panel"
import { displayName, ProfilePicker, type Tier } from "@/components/profile-picker"
import { ResponseChart } from "@/components/response-chart"
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
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
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

const STORAGE_KEY = "openjbl.eq"

function remembered(): { tier?: Tier; profile?: string } {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}")
  } catch {
    return {}
  }
}

function remember(tier: Tier, profile: string) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ tier, profile }))
  } catch {
    // Private windows can refuse storage; the page works without it.
  }
}

function fail(error: unknown, title = "Something went wrong") {
  toast.error(title, { description: error instanceof Error ? error.message : String(error) })
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const dark = resolvedTheme !== "light"
  return (
    <Button variant="ghost" size="icon" aria-label="Toggle theme" onClick={() => setTheme(dark ? "light" : "dark")}>
      {dark ? <SunIcon /> : <MoonIcon />}
    </Button>
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
  const [speakerGains, setSpeakerGains] = useState<number[] | null>(null)
  const [outcome, setOutcome] = useState<WriteOutcome | null>(null)
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [pending, setPending] = useState<string | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState("")
  const [dangerOpen, setDangerOpen] = useState(false)
  const lastSeq = useRef(0)

  const verified = state?.verified ?? false
  const pid = state?.target?.pid ?? state?.pid ?? ""
  const busy = state?.busy ?? pending

  const refreshState = useCallback(async () => {
    try {
      setState(await api.state())
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
    setGains(next.gains ?? [])
    setEdited(false)
    remember(nextTier, next.key)
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
        setSpeakerGains(null)
        const saved = remembered()
        const wantedTier: Tier = !model.extended_allowed && saved.tier === "lab" ? "standard" : (saved.tier ?? (model.extended_allowed ? "lab" : "standard"))
        const pool = result[wantedTier]
        const pick =
          pool.find((p) => p.key === saved.profile && p.gains) ??
          pool.find((p) => p.gains) ??
          result.standard.find((p) => p.key === "balanced")
        setTier(pick && pool.includes(pick) ? wantedTier : "standard")
        if (pick) choose(pick, pick && pool.includes(pick) ? wantedTier : "standard")
      } catch (error) {
        fail(error, "Could not load the model")
      }
    })()
    return () => {
      cancelled = true
    }
  }, [pid, loadProfiles, choose])

  const run = async <T,>(label: string, action: () => Promise<T>): Promise<T | undefined> => {
    setPending(label)
    try {
      return await action()
    } catch (error) {
      if (error instanceof ApiError && error.status === 428) throw error
      fail(error, `${label} failed`)
      return undefined
    } finally {
      setPending(null)
      refreshState()
    }
  }

  const setup = () =>
    run("Auto setup", async () => {
      const result = await api.setup()
      setDevices(result.devices)
      if (result.target) {
        toast.success(`${result.target.model} connected`, { description: "EQ route verified. Nothing has been written." })
      } else {
        const unnamed = result.devices.find((device) => device.is_jbl && device.live && !device.pid)
        toast.warning(unnamed ? "Choose the speaker's model" : "Pick a speaker", {
          description: unnamed
            ? `${unnamed.name || "A JBL speaker"} did not say which model it is. Pick the model under it, then press Connect.`
            : `Found ${result.devices.length} device(s); ${result.reason}.`,
        })
      }
    })

  const scan = () =>
    run("Scanning", async () => {
      const result = await api.scan()
      setDevices(result.devices)
      toast(`${result.devices.length} device(s) found`)
    })

  const connect = (address: string, devicePid: string) =>
    run("Connecting", async () => {
      const target = await api.connect(address, devicePid)
      toast.success(`${target.model} connected`, { description: "EQ route verified. Nothing has been written." })
    })

  const disconnect = () => run("Disconnecting", () => api.disconnect())

  const readCurrent = () =>
    run("Reading EQ", async () => {
      const result = await api.read()
      if (result.gains) {
        setSpeakerGains(result.gains)
        toast("Read the speaker's current EQ", { description: `Shown dashed on the chart · ${result.gains.map(formatDb).join("  ")}` })
      } else {
        toast.warning("The reply could not be decoded")
      }
    })

  const showPreview = () =>
    run("Preview", async () => {
      if (!profile) return
      setPreview(await api.preview(profile.key, gains))
    })

  const apply = async (confirmDanger = false) => {
    if (!profile) return
    try {
      const result = await run("Writing EQ", () => api.apply(profile.key, gains, confirmDanger))
      if (!result) return
      setOutcome(result)
      if (result.verification.actual) setSpeakerGains(result.verification.actual)
      const show = result.severity === "information" ? toast.success : result.severity === "warning" ? toast.warning : toast.error
      show(result.title, { description: result.message })
    } catch (error) {
      if (error instanceof ApiError && error.status === 428) setDangerOpen(true)
    }
  }

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

  const deleteProfile = () =>
    run("Delete", async () => {
      if (!profile) return
      await api.deleteProfile(profile.key)
      const result = await loadProfiles(pid)
      const next = result.user[0] ?? result.standard[0]
      if (!result.user.length) setTier("standard")
      if (next) choose(next, result.user.length ? "user" : "standard")
      toast(`Deleted “${profile.name}”`)
    })

  const changeTier = (next: Tier) => {
    setTier(next)
    const pool = tiers?.[next] ?? []
    const keep = pool.find((p) => p.key === profile?.key)
    const pick = keep ?? pool.find((p) => p.gains)
    if (pick) choose(pick, next)
  }

  const extended = profile?.extended ?? false
  const boosting = gains.some((g) => g > 6)
  const range = useMemo(() => (gains.length ? `${formatDb(Math.min(...gains))} … ${formatDb(Math.max(...gains))} dB` : "—"), [gains])

  return (
    <div className="min-h-svh bg-background">
      <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:px-6">
          <div className="flex size-8 items-center justify-center rounded-lg bg-foreground text-background">
            <AudioLinesIcon className="size-4" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-semibold tracking-tight">OpenJBL</span>
            <span className="hidden text-sm text-muted-foreground sm:inline">EQ Control</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {busy && (
              <Badge variant="outline" className="gap-1.5">
                <Loader2Icon className="animate-spin" />
                {busy}
              </Badge>
            )}
            <Badge variant={verified ? "default" : "outline"} className="gap-1.5">
              <span className={verified ? "size-1.5 rounded-full bg-primary-foreground" : "size-1.5 rounded-full border border-current"} />
              {verified ? state?.target?.model : "Not connected"}
            </Badge>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <div className="flex flex-col gap-6">
          <DevicePanel
            target={verified ? (state?.target ?? null) : null}
            devices={devices}
            models={models}
            defaultPid={state?.pid ?? ""}
            busy={busy}
            onSetup={setup}
            onScan={scan}
            onConnect={(device, devicePid) => connect(device.address, devicePid)}
            onReverify={() => state?.target && connect(state.target.address, state.target.pid)}
            onDisconnect={disconnect}
          />
          <ActivityLog events={events} />
          <p className="px-1 text-[11px] text-muted-foreground">
            v{state?.version} · build {state?.build} · not affiliated with JBL or Harman
          </p>
        </div>

        <Card className="self-start">
          <CardHeader>
            <CardTitle className="text-base">Equalizer</CardTitle>
            <CardDescription>
              {controls ? `${controls.name} · ${controls.count} bands · ${controls.eq_path}` : "Loading model…"}
            </CardDescription>
            <CardAction>
              {!verified && (
                <Badge variant="outline" className="gap-1">
                  <LockIcon />
                  Browse only
                </Badge>
              )}
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <ProfilePicker
              tiers={tiers}
              tier={tier}
              selected={profile?.key ?? null}
              onTierChange={changeTier}
              onSelect={(next) => choose(next, tier)}
            />

            {controls && gains.length > 0 && (
              <div className="flex flex-col gap-4 rounded-xl border p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{profile ? displayName(profile) : "Custom"}</span>
                  {edited && <Badge variant="secondary">Edited</Badge>}
                  {extended && <Badge variant="outline">LAB</Badge>}
                  {boosting && <Badge>Boost &gt; +6 dB</Badge>}
                  <span className="ml-auto font-mono text-xs text-muted-foreground">{range}</span>
                </div>
                <ResponseChart gains={gains} frequencies={controls.frequencies} shape={controls.shape} reference={speakerGains} />
                <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className="h-0.5 w-4 bg-foreground" /> This curve on {controls.shape ? "the speaker's real filters" : "its bands"}
                  </span>
                  {speakerGains && (
                    <span className="flex items-center gap-1.5">
                      <span className="w-4 border-t-[1.5px] border-dashed border-muted-foreground" /> On the speaker now
                    </span>
                  )}
                </div>
                <BandSliders
                  gains={gains}
                  frequencies={controls.frequencies}
                  bands={controls.bands}
                  extended={extended}
                  onChange={(next) => {
                    setGains(next)
                    setEdited(true)
                  }}
                />
              </div>
            )}

            {outcome && controls && <WriteResult outcome={outcome} frequencies={controls.frequencies} />}
          </CardContent>
          <CardFooter className="flex flex-wrap gap-2 border-t bg-muted/30 py-4">
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button variant="outline" disabled={!verified || busy !== null} onClick={readCurrent}>
                    <DownloadIcon data-icon="inline-start" />
                    Read current
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>Read the EQ that is on the speaker now</TooltipContent>
            </Tooltip>
            <Button variant="outline" disabled={!verified || busy !== null || !profile} onClick={showPreview}>
              <EyeIcon data-icon="inline-start" />
              Preview
            </Button>
            <Button variant="outline" disabled={!gains.length || busy !== null} onClick={() => setSaveOpen(true)}>
              <SaveIcon data-icon="inline-start" />
              Save as
            </Button>
            {tier === "user" && profile?.key.startsWith("user-") && (
              <Button variant="ghost" disabled={busy !== null} onClick={deleteProfile}>
                <Trash2Icon data-icon="inline-start" />
                Delete
              </Button>
            )}
            <Button className="ml-auto min-w-44" size="lg" disabled={!verified || busy !== null || !profile} onClick={() => apply()}>
              {busy === "Writing EQ" ? <Loader2Icon data-icon="inline-start" className="animate-spin" /> : <ZapIcon data-icon="inline-start" />}
              {busy === "Writing EQ" ? "Writing & verifying…" : "Apply to speaker"}
            </Button>
          </CardFooter>
        </Card>
      </main>

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

      <AlertDialog open={dangerOpen} onOpenChange={setDangerOpen}>
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
                setDangerOpen(false)
                apply(true)
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
