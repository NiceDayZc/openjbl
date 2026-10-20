import { memo } from "react"
import { TriangleAlertIcon } from "lucide-react"
import { AnimatePresence, LayoutGroup, motion } from "motion/react"

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import type { Profile, ProfileTiers } from "@/lib/api"
import { riseSmall, spring, stagger, swap } from "@/lib/motion"
import { cn } from "@/lib/utils"

export type Tier = keyof ProfileTiers

const TIER_LABELS: Record<Tier, string> = { standard: "Standard", lab: "LAB", user: "My profiles" }
const TIER_HINTS: Record<Tier, string> = {
  standard: "Inside the model's own app range. Full volume, any JBL.",
  lab: "Cut-only curves, fitted to the speaker's real filters.",
  user: "Curves you saved. Shape any profile, then Save as.",
}

// LAB is long enough to need headings; the grouping comes from the profiles' own tags.
const GROUPS = [
  { id: "room", title: "Rooms & spaces" },
  { id: "character", title: "Sound character" },
  { id: "use", title: "Situations" },
]

function groupOf(profile: Profile): string {
  if (profile.tags.includes("room")) return "room"
  if (profile.tags.includes("use-case")) return "use"
  return "character"
}

export function displayName(profile: Profile): string {
  return profile.name.replace(/^LAB \/ /, "")
}

function Sparkline({ values }: { values: number[] }) {
  const limit = Math.max(6, ...values.map(Math.abs))
  const points = values.map((value, i) => `${(i / (values.length - 1)) * 64},${12 - (value / limit) * 10}`).join(" ")
  return (
    <svg
      viewBox="0 0 64 24"
      className="h-5 w-12 shrink-0 text-muted-foreground transition-colors duration-200 group-hover/profile:text-foreground group-data-[selected=true]/profile:text-foreground"
      aria-hidden
    >
      <line x1="0" x2="64" y1="12" y2="12" stroke="currentColor" strokeOpacity="0.25" strokeDasharray="2 3" />
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

interface CardProps {
  profile: Profile
  active: boolean
  onSpeaker: boolean
  onSelect: (profile: Profile) => void
  onHover: (profile: Profile | null) => void
}

function ProfileCard({ profile, active, onSpeaker, onSelect, onHover }: CardProps) {
  const unsupported = profile.gains === null
  return (
    <motion.button
      type="button"
      variants={riseSmall}
      whileTap={unsupported ? undefined : { scale: 0.98 }}
      disabled={unsupported}
      title={profile.error ?? profile.description}
      data-selected={active}
      onClick={() => onSelect(profile)}
      onPointerEnter={(event) => event.pointerType === "mouse" && onHover(profile)}
      onPointerLeave={() => onHover(null)}
      className={cn(
        "group/profile relative flex items-start gap-3 rounded-lg border border-border px-3 py-2.5 text-left outline-none",
        "transition-[border-color,background-color,translate] duration-200 hover:-translate-y-px hover:border-foreground/30 hover:bg-muted/30",
        "focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-40",
      )}
    >
      {active && (
        <motion.span layoutId="profile-active" className="absolute -inset-px rounded-lg border border-foreground bg-muted/60" transition={spring} />
      )}
      <div className="relative min-w-0 flex-1">
        <div className="flex items-start gap-1.5">
          <span className="line-clamp-2 text-[13px] leading-tight font-medium">{displayName(profile)}</span>
          {profile.boosts && <TriangleAlertIcon className="mt-px size-3.5 shrink-0" aria-label="Boosts past the safe range" />}
        </div>
        <p className="mt-1 line-clamp-2 text-xs leading-snug text-muted-foreground">{profile.description}</p>
      </div>
      <span className="relative">
        <Sparkline values={profile.curve} />
      </span>
      <AnimatePresence initial={false}>
        {onSpeaker && (
          <motion.span
            key="on-speaker"
            className="absolute -top-2 right-3 z-10 inline-flex items-center gap-1 rounded-full bg-foreground px-1.5 py-px text-[10px] font-medium text-background shadow-sm"
            initial={{ opacity: 0, scale: 0.6, y: 4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.6 }}
            transition={spring}
          >
            <span className="size-1 rounded-full bg-background" />
            On speaker
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  )
}

interface ProfilePickerProps {
  tiers: ProfileTiers | null
  tier: Tier
  selected: string | null
  /** The profile whose curve the speaker reported last, if any matches. */
  onSpeaker: string | null
  onTierChange: (tier: Tier) => void
  onSelect: (profile: Profile) => void
  onHover: (profile: Profile | null) => void
}

export const ProfilePicker = memo(function ProfilePicker({
  tiers,
  tier,
  selected,
  onSpeaker,
  onTierChange,
  onSelect,
  onHover,
}: ProfilePickerProps) {
  const profiles = tiers?.[tier] ?? []
  const sections =
    tier === "lab"
      ? GROUPS.map((group) => ({
          ...group,
          items: profiles.filter((p) => groupOf(p) === group.id),
        })).filter((group) => group.items.length)
      : [{ id: tier, title: null, items: profiles }]

  return (
    <LayoutGroup id="profiles">
      <div className="flex flex-col gap-4">
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
              <ToggleGroupItem key={key} value={key} className="relative px-3 data-[state=on]:bg-transparent">
                {tier === key && <motion.span layoutId="tier-pill" className="absolute inset-0 rounded-[inherit] bg-muted" transition={spring} />}
                <span className="relative">
                  {TIER_LABELS[key]}
                  <span className="ml-1 font-mono text-[10px] text-muted-foreground tabular-nums">{tiers?.[key].length ?? 0}</span>
                </span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <AnimatePresence mode="wait" initial={false}>
            <motion.p key={tier} className="text-xs text-muted-foreground" {...swap}>
              {TIER_HINTS[tier]}
            </motion.p>
          </AnimatePresence>
        </div>

        {profiles.length === 0 ? (
          <motion.div key={`${tier}-empty`} {...swap} className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
            No saved profiles yet. Shape a curve, then press <span className="text-foreground">Save as</span>.
          </motion.div>
        ) : (
          // Keyed by tier: a new tier mounts fresh and staggers in at once,
          // without waiting for the old one to animate out first.
          <motion.div key={tier} className="flex flex-col gap-4" variants={stagger(0.018)} initial="hidden" animate="show">
            {sections.map((section) => (
              <section key={section.id} className="flex flex-col gap-2">
                {section.title && (
                  <motion.h3 variants={riseSmall} className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    {section.title}
                  </motion.h3>
                )}
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-2 2xl:grid-cols-3">
                  {section.items.map((profile) => (
                    <ProfileCard
                      key={profile.key}
                      profile={profile}
                      active={profile.key === selected}
                      onSpeaker={profile.key === onSpeaker}
                      onSelect={onSelect}
                      onHover={onHover}
                    />
                  ))}
                </div>
              </section>
            ))}
          </motion.div>
        )}
      </div>
    </LayoutGroup>
  )
})
