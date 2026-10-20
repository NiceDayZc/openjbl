import { memo, useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import {
  BluetoothSearchingIcon,
  CheckIcon,
  Loader2Icon,
  RefreshCwIcon,
  SignalHighIcon,
  SignalLowIcon,
  SignalMediumIcon,
  SignalZeroIcon,
  UnplugIcon,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ScanRadar } from "@/components/scan-radar"
import type { Device, ModelSummary, Target } from "@/lib/api"
import { EASE_OUT, riseSmall, spring, stagger, swap } from "@/lib/motion"

function SignalIcon({ rssi }: { rssi: number | null }) {
  if (rssi === null) return <SignalZeroIcon className="size-4 text-muted-foreground" />
  if (rssi >= -60) return <SignalHighIcon className="size-4" />
  if (rssi >= -75) return <SignalMediumIcon className="size-4" />
  return <SignalLowIcon className="size-4" />
}

interface DeviceRowProps {
  device: Device
  models: ModelSummary[]
  defaultPid: string
  disabled: boolean
  onConnect: (device: Device, pid: string) => void
}

function DeviceRow({ device, models, defaultPid, disabled, onConnect }: DeviceRowProps) {
  // A speaker in pairing mode, or already connected to a phone, can advertise
  // only Fast Pair data and no model. It is still the speaker, so let the user
  // name the model; the probe that follows refuses anything that is not it.
  const [pid, setPid] = useState(device.pid ?? (models.some((m) => m.pid === defaultPid) ? defaultPid : ""))
  const needsModel = !device.pid && device.live
  return (
    <motion.li variants={riseSmall} className="flex flex-col gap-2 px-3 py-2.5" data-testid="device-row">
      <div className="flex items-center gap-3">
        <SignalIcon rssi={device.rssi} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{device.model ?? (device.name || "Unnamed device")}</div>
          <div className="truncate font-mono text-[11px] text-muted-foreground">
            {device.rssi === null ? "paired, not advertising" : `${device.rssi} dBm`}
            {device.pid ? ` · PID ${device.pid}` : device.model === null && device.name ? ` · ${device.name}` : ""}
          </div>
        </div>
        {!needsModel && (
          <Button size="sm" variant="outline" disabled={disabled || !device.live || !pid} onClick={() => onConnect(device, pid)}>
            Connect
          </Button>
        )}
      </div>
      {needsModel && (
        <motion.div
          className="flex items-center gap-2 pl-7"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          transition={{ duration: 0.25, ease: EASE_OUT, delay: 0.08 }}
        >
          <Select value={pid} onValueChange={setPid}>
            <SelectTrigger size="sm" className="min-w-0 flex-1" aria-label="Speaker model">
              <SelectValue placeholder="Choose the model" />
            </SelectTrigger>
            <SelectContent>
              {models.map((model) => (
                <SelectItem key={model.pid} value={model.pid}>
                  {model.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" disabled={disabled || !pid} onClick={() => onConnect(device, pid)}>
            Connect
          </Button>
        </motion.div>
      )}
    </motion.li>
  )
}

interface DevicePanelProps {
  target: Target | null
  devices: Device[]
  models: ModelSummary[]
  defaultPid: string
  busy: string | null
  onSetup: () => void
  onScan: () => void
  onConnect: (device: Device, pid: string) => void
  onReverify: () => void
  onDisconnect: () => void
}

export const DevicePanel = memo(function DevicePanel({
  target,
  devices,
  models,
  defaultPid,
  busy,
  onSetup,
  onScan,
  onConnect,
  onReverify,
  onDisconnect,
}: DevicePanelProps) {
  const [showAll, setShowAll] = useState(false)
  const working = busy !== null
  const searching = busy === "Auto setup" || busy === "Scanning" || busy === "Connecting"
  const jbl = devices.filter((device) => device.is_jbl)
  const shown = showAll ? devices : jbl
  return (
    <Card>
      <CardHeader>
        <CardTitle>Speaker</CardTitle>
        <CardDescription>{target ? "Connected over Bluetooth LE" : "Close the JBL app on nearby phones first"}</CardDescription>
        {target && (
          <CardAction>
            <motion.span initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={spring} className="inline-flex">
              <Badge variant="outline" className="gap-1">
                <CheckIcon />
                Verified
              </Badge>
            </motion.span>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <AnimatePresence mode="wait" initial={false}>
        {target ? (
          <motion.div key="connected" className="flex flex-col gap-4" variants={stagger(0.04)} initial="hidden" animate="show" exit={swap.exit}>
            <motion.div variants={riseSmall} className="flex flex-col gap-1">
              <span className="text-2xl font-semibold tracking-tight">{target.model}</span>
              <span className="truncate font-mono text-xs text-muted-foreground" title={target.address}>
                {target.name} · {target.address}
              </span>
            </motion.div>
            <motion.dl variants={riseSmall} className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-lg border p-3 text-xs">
              <div>
                <dt className="text-muted-foreground">Firmware</dt>
                <dd className="mt-0.5 font-mono">{target.firmware}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Model PID</dt>
                <dd className="mt-0.5 font-mono">{target.pid}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-muted-foreground">EQ route</dt>
                <dd className="mt-0.5 font-mono break-all">{target.eq_path}</dd>
              </div>
            </motion.dl>
            <motion.div variants={riseSmall} className="flex gap-2">
              <Button variant="outline" className="flex-1" disabled={working} onClick={onReverify}>
                <RefreshCwIcon data-icon="inline-start" />
                Re-verify
              </Button>
              <Button variant="ghost" className="flex-1" disabled={working} onClick={onDisconnect}>
                <UnplugIcon data-icon="inline-start" />
                Disconnect
              </Button>
            </motion.div>
          </motion.div>
        ) : (
          <motion.div key="idle" className="flex flex-col gap-4" {...swap}>
            <AnimatePresence mode="wait" initial={false}>
              {searching ? (
                <motion.div key="radar" {...swap}>
                  <ScanRadar label={busy === "Connecting" ? "Connecting and verifying…" : "Listening for JBL speakers…"} fast={busy === "Connecting"} />
                </motion.div>
              ) : (
                <motion.p key="hint" {...swap} className="text-sm text-muted-foreground">
                  Finds the strongest JBL nearby, connects and checks its EQ route. Nothing is written to the speaker.
                </motion.p>
              )}
            </AnimatePresence>
            <div className="flex gap-2">
              <Button size="lg" className="flex-1" disabled={working} onClick={onSetup}>
                {busy === "Auto setup" || busy === "Connecting" ? (
                  <Loader2Icon data-icon="inline-start" className="animate-spin" />
                ) : (
                  <BluetoothSearchingIcon data-icon="inline-start" />
                )}
                {busy === "Auto setup" ? "Searching…" : busy === "Connecting" ? "Connecting…" : "Scan & connect"}
              </Button>
              <Button size="lg" variant="outline" disabled={working} onClick={onScan}>
                {busy === "Scanning" ? <Loader2Icon className="animate-spin" /> : "Scan"}
              </Button>
            </div>
            {devices.length > 0 && (
              <div className="flex flex-col gap-2">
                {shown.length > 0 ? (
                  <motion.ul
                    key={devices.map((d) => d.address).join()}
                    className="flex flex-col divide-y overflow-hidden rounded-lg border"
                    variants={stagger(0.035)}
                    initial="hidden"
                    animate="show"
                  >
                    {shown.slice(0, 12).map((device) => (
                      <DeviceRow
                        key={device.address}
                        device={device}
                        models={models}
                        defaultPid={defaultPid}
                        disabled={working}
                        onConnect={onConnect}
                      />
                    ))}
                  </motion.ul>
                ) : (
                  <p className="rounded-lg border border-dashed px-3 py-4 text-center text-xs text-muted-foreground">
                    No JBL speaker was advertising. Turn it on, or press its Bluetooth button, then scan again.
                  </p>
                )}
                {devices.length > jbl.length && (
                  <Button variant="link" size="xs" className="self-start px-0 text-muted-foreground" onClick={() => setShowAll(!showAll)}>
                    {showAll ? "Show JBL only" : `Show all ${devices.length} Bluetooth devices`}
                  </Button>
                )}
              </div>
            )}
          </motion.div>
        )}
        </AnimatePresence>
      </CardContent>
    </Card>
  )
})
