import { DateNav } from "@/components/DateNav";
import { MetricCard } from "@/components/MetricCard";
import { apiGet } from "@/lib/api";
import { formatDuration, formatPercent, yesterdayIsoDate } from "@/lib/format";
import type { DayResponse } from "@/lib/types";

export default async function TodayPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  const targetDate = date ?? yesterdayIsoDate();
  const { metrics, categories } = await apiGet<DayResponse>(`/v1/days/${targetDate}`);

  return (
    <div>
      <DateNav basePath="/today" date={targetDate} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Screen time"
          value={formatDuration(metrics.screen_time_s)}
          coverageRatio={metrics.coverage_ratio}
        />
        <MetricCard
          label="Active time"
          value={formatDuration(metrics.active_time_s)}
          coverageRatio={metrics.coverage_ratio}
          subtext="screen on, excluding idle"
        />
        <MetricCard
          label="Deep work"
          value={formatDuration(metrics.deep_work_s)}
          coverageRatio={metrics.coverage_ratio}
        />
        <MetricCard
          label="Focused work"
          value={formatDuration(metrics.focused_work_s)}
          coverageRatio={metrics.coverage_ratio}
        />
        <MetricCard
          label="Distraction"
          value={formatDuration(metrics.distraction_s)}
          coverageRatio={metrics.coverage_ratio}
        />
        <MetricCard
          label="Fragmentation"
          value={
            metrics.fragmentation_index === null
              ? "n/a"
              : formatPercent(metrics.fragmentation_index)
          }
          coverageRatio={metrics.coverage_ratio}
          subtext={
            metrics.fragmentation_index === null
              ? "needs ≥60% coverage to compute"
              : "higher = more fragmented"
          }
        />
        <MetricCard
          label="Context switches"
          value={String(metrics.context_switches)}
          coverageRatio={metrics.coverage_ratio}
          subtext={`${metrics.switches_per_hour.toFixed(1)}/hour`}
        />
        <MetricCard
          label="Unlocks"
          value={String(metrics.unlock_count)}
          coverageRatio={metrics.coverage_ratio}
        />
      </div>

      <h2 className="mt-8 mb-3 text-lg font-semibold">Where time went</h2>
      {categories.length === 0 ? (
        <p className="text-sm text-neutral-500">No classified activity this day.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {categories.map((c) => (
            <li key={c.key} className="flex justify-between border-b border-neutral-100 py-1.5 text-sm dark:border-neutral-800">
              <span>{c.label}</span>
              <span className="tabular-nums text-neutral-600 dark:text-neutral-400">
                {formatDuration(c.duration_s)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
