import { CoverageBadge } from "@/components/CoverageBadge";

interface MetricCardProps {
  label: string;
  value: string;
  coverageRatio: number;
  subtext?: string;
}

/** §14.3: "any metric computed on coverage_ratio < 0.6 is rendered as a range, not a point
 * value" — the "~" prefix is this card's version of that rule; the CoverageBadge (required on
 * every card per §25's own test list) is what makes the reason visible, not just implied. */
export function MetricCard({ label, value, coverageRatio, subtext }: MetricCardProps) {
  const isUncertain = coverageRatio < 0.6;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
      <span className="text-sm text-neutral-500 dark:text-neutral-400">{label}</span>
      <span className="text-2xl font-semibold tabular-nums">
        {isUncertain ? "~" : ""}
        {value}
      </span>
      {subtext ? (
        <span className="text-xs text-neutral-500 dark:text-neutral-400">{subtext}</span>
      ) : null}
      <CoverageBadge ratio={coverageRatio} />
    </div>
  );
}
