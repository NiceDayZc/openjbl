import { TriangleAlertIcon } from "lucide-react"

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import type { Profile, ProfileTiers } from "@/lib/api"
import { cn } from "@/lib/utils"

export type Tier = keyof ProfileTiers

const TIER_LABELS: Record<Tier, string> = { standard: "Standard", lab: "LAB", user: "My profiles" }
const TIER_HINTS: Record<Tier, string> = {
  standard: "Inside the model's own app range. Full volume, any JBL.",
  lab: "Cut-only precision curves, fitted to the speaker's real filters.",
  user: "Curves you saved. Edit any profile, then Save as.",
}

export function displayName(profile: Profile): string {
  return profile.name.replace(/^LAB \/ /, "")
}

function Sparkline({ values }: { values: number[] }) {
  const limit = Math.max(6, ...values.map(Math.abs))
  const points = values
    .map((value, i) => `${(i / (values.length - 1)) * 64},${12 - (value / limit) * 10}`)
    .join(" ")
  return (
    <svg viewBox="0 0 64 24" className="h-6 w-16 shrink-0 text-muted-foreground group-data-[selected=true]/profile:text-foreground" aria-hidden>
      <line x1="0" x2="64" y1="12" y2="12" stroke="currentColor" strokeOpacity="0.25" strokeDasharray="2 3" />
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

interface ProfilePickerProps {
  tiers: ProfileTiers | null
  tier: Tier
  selected: string | null
  onTierChange: (tier: Tier) => void
  onSelect: (profile: Profile) => void
}

export function ProfilePicker({ tiers, tier, selected, onTierChange, onSelect }: ProfilePickerProps) {
  const profiles = tiers?.[tier] ?? []
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          spacing={0}
          value={tier}
          onValueChange={(value) => value && onTierChange(value as Tier)}
        >
          {(Object.keys(TIER_LABELS) as Tier[]).map((key) => (
            <ToggleGroupItem key={key} value={key} className="px-3">
              {TIER_LABELS[key]}
              <span className="ml-1 font-mono text-[10px] text-muted-foreground tabular-nums">{tiers?.[key].length ?? 0}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <p className="text-xs text-muted-foreground">{TIER_HINTS[tier]}</p>
      </div>
      {profiles.length === 0 ? (
        <div className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          No saved profiles yet. Shape a curve below, then press <span className="text-foreground">Save as</span>.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {profiles.map((profile) => {
            const active = profile.key === selected
            const unsupported = profile.gains === null
            return (
              <button
                key={profile.key}
                type="button"
                disabled={unsupported}
                title={profile.error ?? profile.description}
                data-selected={active}
                onClick={() => onSelect(profile)}
                className={cn(
                  "group/profile flex items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors outline-none",
                  "hover:bg-muted/60 focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-40",
                  active ? "border-foreground bg-muted/60" : "border-border",
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-medium">{displayName(profile)}</span>
                    {profile.boosts && <TriangleAlertIcon className="size-3.5 shrink-0" aria-label="Boosts past the safe range" />}
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-muted-foreground">{profile.description}</p>
                </div>
                <Sparkline values={profile.curve} />
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
