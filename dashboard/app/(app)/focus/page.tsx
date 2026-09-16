import { DateNav } from "@/components/DateNav";
import { MetricCard } from "@/components/MetricCard";
import { apiGet } from "@/lib/api";
import { formatDuration, formatPercent, formatTime, yesterdayIsoDate } from "@/lib/format";
import type { DayResponse, FocusResponse } from "@/lib/types";

export default async function FocusPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  const targetDate = date ?? yesterdayIsoDate();

  const [{ metrics }, { sessions }] = await Promise.all([
    apiGet<DayResponse>(`/v1/days/${targetDate}`),
    apiGet<FocusResponse>(`/v1/days/${targetDate}/focus`),
  ]);

  return (
    <div>
      <DateNav basePath="/focus" date={targetDate} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard
          label="Longest focus session"
          value={formatDuration(metrics.longest_focus_s)}
          coverageRatio={metrics.coverage_ratio}
        />
        <MetricCard
          label="Average focus session"
          value={formatDuration(metrics.avg_focus_s)}
          coverageRatio={metrics.coverage_ratio}
        />
        <MetricCard
          label="Focus sessions"
          value={String(metrics.focus_session_count)}
          coverageRatio={metrics.coverage_ratio}
          subtext={`${metrics.interruptions} interruptions absorbed`}
        />
      </div>

      <h2 className="mt-8 mb-3 text-lg font-semibold">Session list</h2>
      {sessions.length === 0 ? (
        <p className="text-sm text-neutral-500">
          No session this day reached the 15-minute focus threshold.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {sessions.map((session, i) => (
            <li
              key={`${session.start_ts}-${i}`}
              className="flex items-center justify-between rounded border border-neutral-200 px-3 py-2 text-sm dark:border-neutral-800"
            >
              <div className="flex items-center gap-3">
                <span className="font-medium">{session.category_label}</span>
                {session.is_deep_work ? (
                  <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
                    Deep work
                  </span>
                ) : null}
              </div>
              <span className="text-neutral-500">
                {formatTime(session.start_ts)}–{formatTime(session.end_ts)}
              </span>
              <span className="tabular-nums">{formatDuration(session.duration_s)}</span>
              <span className="text-xs text-neutral-500">
                {session.interruption_count} interruption
                {session.interruption_count === 1 ? "" : "s"} ·{" "}
                {formatPercent(session.attributed_ratio)} attributed
              </span>
            </li>
          ))}
        </ul>
      )}

      <h2 className="mt-8 mb-3 text-lg font-semibold">Interruption timeline</h2>
      {sessions.length === 0 ? (
        <p className="text-sm text-neutral-500">Nothing to show without any focus sessions.</p>
      ) : (
        <div className="flex flex-col gap-1">
          {sessions.map((session, i) => (
            <div key={`${session.start_ts}-timeline-${i}`} className="flex items-center gap-2 text-xs">
              <span className="w-28 shrink-0 text-neutral-500">{formatTime(session.start_ts)}</span>
              <div className="h-2 flex-1 overflow-hidden rounded bg-neutral-100 dark:bg-neutral-800">
                <div
                  className="h-full bg-indigo-400"
                  style={{ width: `${Math.min(session.attributed_ratio * 100, 100)}%` }}
                  title={`${session.interruption_count} interruptions`}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
