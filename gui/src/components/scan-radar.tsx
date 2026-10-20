import { BluetoothIcon } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"

/** Rings that ripple out from the radio while it is searching or connecting. */
export function ScanRadar({ label, fast = false }: { label: string; fast?: boolean }) {
  const reduce = useReducedMotion()
  const period = fast ? 1.4 : 2.4
  return (
    <div className="flex flex-col items-center gap-3 py-2" role="status">
      <div className="relative flex size-28 items-center justify-center">
        {!reduce &&
          [0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="absolute inset-0 rounded-full border border-foreground/60 bg-foreground/[0.04]"
              initial={{ scale: 0.35, opacity: 0 }}
              animate={{ scale: [0.35, 1.05], opacity: [0.7, 0] }}
              transition={{ duration: period, repeat: Infinity, delay: (i * period) / 3, ease: [0.22, 1, 0.36, 1] }}
            />
          ))}
        <span className="absolute inset-[30%] rounded-full bg-foreground/5" />
        <motion.span
          className="relative flex size-10 items-center justify-center rounded-full bg-foreground text-background shadow-lg"
          animate={reduce ? undefined : { scale: [1, 1.06, 1] }}
          transition={{ duration: period / 2, repeat: Infinity, ease: "easeInOut" }}
        >
          <BluetoothIcon className="size-5" />
        </motion.span>
      </div>
      <motion.span
        key={label}
        className="text-xs text-muted-foreground"
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
      >
        {label}
      </motion.span>
    </div>
  )
}
