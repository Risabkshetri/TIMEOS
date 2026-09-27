import { DateNav } from "@/components/DateNav";
import { Timeline, TimelineLegend } from "@/components/Timeline";
import { TimelineViewToggle } from "@/components/TimelineViewToggle";
import { UnifiedTimeline } from "@/components/UnifiedTimeline";
import { apiGet } from "@/lib/api";
import { yesterdayIsoDate } from "@/lib/format";
import type { TimelineResponse } from "@/lib/types";

export default async function TimelinePage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string; view?: string }>;
}) {
  const { date, view: viewParam } = await searchParams;
  const targetDate = date ?? yesterdayIsoDate();
  const view = viewParam === "unified" ? "unified" : "per_device";

  const { devices, unified } = await apiGet<TimelineResponse>(
    `/v1/days/${targetDate}/timeline?view=${view}`,
  );

  const fallbackStartUtc = `${targetDate}T04:00:00Z`; // day_start_hour default
  const dayStartUtc =
    view === "unified"
      ? (unified[0]?.start_ts ?? fallbackStartUtc)
      : (devices[0]?.coverage[0]?.start_ts ?? fallbackStartUtc);
  const dayEndUtc =
    view === "unified"
      ? (unified.at(-1)?.end_ts ?? fallbackStartUtc)
      : (devices[0]?.coverage.at(-1)?.end_ts ?? fallbackStartUtc);

  return (
    <div>
      <DateNav basePath="/timeline" date={targetDate} />
      <TimelineViewToggle date={targetDate} view={view} />
      <TimelineLegend />

      <div className="mt-6 flex flex-col gap-8">
        {view === "unified" ? (
          unified.length === 0 ? (
            <p className="text-sm text-neutral-500">No classified activity this day.</p>
          ) : (
            <UnifiedTimeline dayStartUtc={dayStartUtc} dayEndUtc={dayEndUtc} activities={unified} />
          )
        ) : devices.length === 0 ? (
          <p className="text-sm text-neutral-500">No devices reported activity this day.</p>
        ) : (
          devices.map((device) => (
            <Timeline
              key={device.device_id}
              deviceName={device.name}
              dayStartUtc={device.coverage[0]?.start_ts ?? fallbackStartUtc}
              dayEndUtc={device.coverage.at(-1)?.end_ts ?? fallbackStartUtc}
              coverage={device.coverage}
              sessions={device.sessions}
            />
          ))
        )}
      </div>
    </div>
  );
}
