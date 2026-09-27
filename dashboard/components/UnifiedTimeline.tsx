import { percentSpan } from "@/components/Timeline";
import { formatDuration, formatTime } from "@/lib/format";
import type { ActivityOut } from "@/lib/types";

// §38 Phase 10: the single cross-device band alternative to Timeline.tsx's per-device bands —
// one segment per already-clustered `activities` row (see
// timeos.analytics.merge.cluster_cross_device_activities). A cross-device segment (2+ devices
// contributed, e.g. phone + laptop on the same stretch of development work) gets a distinct ring
// and its device count in the tooltip, so it visually reads as "more than one device" rather than
// looking identical to an ordinary single-device span.
const MAX_RENDERED_ACTIVITIES = 200;

interface UnifiedTimelineProps {
  dayStartUtc: string;
  dayEndUtc: string;
  activities: ActivityOut[];
}

export function UnifiedTimeline({ dayStartUtc, dayEndUtc, activities }: UnifiedTimelineProps) {
  const dayStartMs = new Date(dayStartUtc).getTime();
  const dayEndMs = new Date(dayEndUtc).getTime();

  return (
    <div className="flex flex-col gap-1.5" data-testid="unified-timeline">
      <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
        All devices
      </span>

      <div
        className="relative h-8 w-full overflow-hidden rounded bg-neutral-100 dark:bg-neutral-800"
        data-testid="unified-timeline-row"
      >
        {activities.slice(0, MAX_RENDERED_ACTIVITIES).map((activity) => {
          const { leftPct, widthPct } = percentSpan(
            activity.start_ts,
            activity.end_ts,
            dayStartMs,
            dayEndMs,
          );
          const tooltip = `${activity.category_label}${
            activity.is_cross_device ? ` — ${activity.devices.length} devices` : ""
          } — ${formatTime(activity.start_ts)}–${formatTime(activity.end_ts)} (${formatDuration(activity.duration_s)})`;
          return (
            <div
              key={activity.id}
              className={`absolute top-0 h-full border-r border-white dark:border-neutral-950 ${
                activity.is_cross_device
                  ? "bg-emerald-500 ring-2 ring-inset ring-emerald-300"
                  : "bg-sky-500/70"
              }`}
              style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 0.15)}%` }}
              data-testid="unified-timeline-segment"
              data-cross-device={activity.is_cross_device}
              title={tooltip}
            />
          );
        })}
      </div>
      {activities.length > MAX_RENDERED_ACTIVITIES ? (
        <span className="text-xs text-neutral-500">
          Showing the first {MAX_RENDERED_ACTIVITIES} of {activities.length} activities.
        </span>
      ) : null}
    </div>
  );
}
