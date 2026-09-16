import { formatPercent } from "@/lib/format";

// §14.3's gate: below 0.6, every metric on that window must be shown as uncertain rather than a
// confident point value. This badge is the visible half of that rule — every MetricCard renders
// one (§25's Phase 5 test requirement) so coverage is never silently assumed.
const LOW_COVERAGE_THRESHOLD = 0.6;
const HIGH_COVERAGE_THRESHOLD = 0.9;

export function CoverageBadge({ ratio }: { ratio: number }) {
  const isLow = ratio < LOW_COVERAGE_THRESHOLD;
  const isHigh = ratio >= HIGH_COVERAGE_THRESHOLD;

  const colorClasses = isLow
    ? "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300"
    : isHigh
      ? "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300"
      : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300";

  const label = isLow ? "low coverage" : isHigh ? "good coverage" : "partial coverage";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${colorClasses}`}
      title={`${formatPercent(ratio)} of this window was observed`}
      data-testid="coverage-badge"
      data-coverage-level={isLow ? "low" : isHigh ? "high" : "partial"}
    >
      {formatPercent(ratio)} · {label}
    </span>
  );
}
