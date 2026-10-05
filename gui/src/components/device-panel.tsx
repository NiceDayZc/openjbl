import { useState } from "react"
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
import type { Device, ModelSummary, Target } from "@/lib/api"

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
    <li className="flex flex-col gap-2 px-3 py-2.5" data-testid="device-row">
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
        <div className="flex items-center gap-2 pl-7">
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
        </div>
      )}
    </li>
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

export function DevicePanel({
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
  const jbl = devices.filter((device) => device.is_jbl)
  const shown = showAll ? devices : jbl
  return (
    <Card>
      <CardHeader>
        <CardTitle>Speaker</CardTitle>
        <CardDescription>{target ? "Connected over Bluetooth LE" : "Close the JBL app on nearby phones first"}</CardDescription>
        {target && (
          <CardAction>
            <Badge variant="outline" className="gap-1">
              <CheckIcon />
              Verified
            </Badge>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {target ? (
          <>
            <div className="flex flex-col gap-1">
              <span className="text-2xl font-semibold tracking-tight">{target.model}</span>
              <span className="truncate font-mono text-xs text-muted-foreground" title={target.address}>
                {target.name} · {target.address}
              </span>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-lg border p-3 text-xs">
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
            </dl>
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" disabled={working} onClick={onReverify}>
                <RefreshCwIcon data-icon="inline-start" />
                Re-verify
              </Button>
              <Button variant="ghost" className="flex-1" disabled={working} onClick={onDisconnect}>
                <UnplugIcon data-icon="inline-start" />
                Disconnect
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Finds the strongest JBL nearby, connects and checks its EQ route. Nothing is written to the speaker.
            </p>
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
                  <ul className="flex flex-col divide-y rounded-lg border">
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
                  </ul>
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
          </>
        )}
      </CardContent>
    </Card>
  )
}
