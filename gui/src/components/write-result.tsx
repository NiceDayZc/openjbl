import { memo } from "react"
import { motion } from "motion/react"

import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { WriteOutcome } from "@/lib/api"
import { formatDb, formatHz } from "@/lib/eq"
import { EASE_OUT, spring } from "@/lib/motion"

const RESULT_LABELS: Record<WriteOutcome["result"], string> = {
  verified: "Verified",
  "ack-issue": "Ack issue",
  mismatch: "Mismatch",
  unverified: "Unverified",
}

export const WriteResult = memo(function WriteResult({ outcome, frequencies }: { outcome: WriteOutcome; frequencies: number[] }) {
  const { verification } = outcome
  return (
    <motion.div
      className="flex flex-col gap-3 rounded-lg border p-4"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4, transition: { duration: 0.12 } }}
      transition={{ duration: 0.28, ease: EASE_OUT }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <motion.span initial={{ scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ ...spring, delay: 0.08 }} className="inline-flex">
          <Badge variant={outcome.result === "verified" ? "default" : outcome.result === "mismatch" ? "destructive" : "outline"}>
            {RESULT_LABELS[outcome.result]}
          </Badge>
        </motion.span>
        <span className="text-sm font-medium">{outcome.outcome}</span>
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">
          TX {outcome.transaction_id} · {outcome.elapsed_ms} ms · ack {outcome.ack.toLowerCase()}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">{outcome.message}</p>
      {verification.actual && (
        <Table className="font-mono text-xs">
          <TableHeader>
            <TableRow>
              <TableHead className="h-8">Band</TableHead>
              <TableHead className="h-8 text-right">Requested</TableHead>
              <TableHead className="h-8 text-right">Speaker</TableHead>
              <TableHead className="h-8 text-right">Δ</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {verification.expected.map((expected, i) => {
              const delta = verification.deltas?.[i] ?? 0
              return (
                <motion.tr
                  key={i}
                  data-slot="table-row"
                  className="border-b transition-colors hover:bg-muted/50"
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.22, ease: EASE_OUT, delay: 0.1 + i * 0.03 }}
                >
                  <TableCell className="py-1.5">{formatHz(frequencies[i] ?? 0)} Hz</TableCell>
                  <TableCell className="py-1.5 text-right tabular-nums">{formatDb(expected)}</TableCell>
                  <TableCell className="py-1.5 text-right tabular-nums">{formatDb(verification.actual?.[i] ?? 0)}</TableCell>
                  <TableCell className={delta === 0 ? "py-1.5 text-right text-muted-foreground" : "py-1.5 text-right font-semibold"}>
                    {delta === 0 ? "·" : formatDb(delta)}
                  </TableCell>
                </motion.tr>
              )
            })}
          </TableBody>
        </Table>
      )}
    </motion.div>
  )
})
