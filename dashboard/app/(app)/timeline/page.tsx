import { DateNav } from "@/components/DateNav";
import { Timeline, TimelineLegend } from "@/components/Timeline";
import { apiGet } from "@/lib/api";
import { yesterdayIsoDate } from "@/lib/format";
import type { TimelineResponse } from "@/lib/types";

export default async function TimelinePage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  const targetDate = date ?? yesterdayIsoDate();
  const { devices } = await apiGet<TimelineResponse>(`/v1/days/${targetDate}/timeline`);

  const dayStartUtc = `${targetDate}T04:00:00Z`; // day_start_hour default; devices' own coverage rows carry the real bound
  const dayEndUtc = devices[0]?.coverage.at(-1)?.end_ts ?? `${targetDate}T04:00:00Z`;

  return (
    <div>
      <DateNav basePath="/timeline" date={targetDate} />
      <TimelineLegend />

      <div className="mt-6 flex flex-col gap-8">
        {devices.length === 0 ? (
          <p className="text-sm text-neutral-500">No devices reported activity this day.</p>
        ) : (
          devices.map((device) => (
            <Timeline
              key={device.device_id}
              deviceName={device.name}
              dayStartUtc={device.coverage[0]?.start_ts ?? dayStartUtc}
              dayEndUtc={device.coverage.at(-1)?.end_ts ?? dayEndUtc}
              coverage={device.coverage}
              sessions={device.sessions}
            />
          ))
        )}
      </div>
    </div>
  );
}
