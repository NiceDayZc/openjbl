import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { WriteOutcome } from "@/lib/api"
import { formatDb, formatHz } from "@/lib/eq"

const RESULT_LABELS: Record<WriteOutcome["result"], string> = {
  verified: "Verified",
  "ack-issue": "Ack issue",
  mismatch: "Mismatch",
  unverified: "Unverified",
}

export function WriteResult({ outcome, frequencies }: { outcome: WriteOutcome; frequencies: number[] }) {
  const { verification } = outcome
  return (
    <div className="flex flex-col gap-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={outcome.result === "verified" ? "default" : outcome.result === "mismatch" ? "destructive" : "outline"}>
          {RESULT_LABELS[outcome.result]}
        </Badge>
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
                <TableRow key={i}>
                  <TableCell className="py-1.5">{formatHz(frequencies[i] ?? 0)} Hz</TableCell>
                  <TableCell className="py-1.5 text-right tabular-nums">{formatDb(expected)}</TableCell>
                  <TableCell className="py-1.5 text-right tabular-nums">{formatDb(verification.actual?.[i] ?? 0)}</TableCell>
                  <TableCell className={delta === 0 ? "py-1.5 text-right text-muted-foreground" : "py-1.5 text-right font-semibold"}>
                    {delta === 0 ? "·" : formatDb(delta)}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
