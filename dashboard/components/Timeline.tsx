import type { AppSessionOut, CoverageInterval, CoverageState } from "@/lib/types";
import { formatTime } from "@/lib/format";

// §25: "UNOBSERVED rendered as hatched grey and DEVICE_OFFLINE as solid grey, both explicitly
// labelled. Never white space, never zero." The hatched pattern (timeline-hatched, defined in
// globals.css) is what visually distinguishes "we don't know" from "the device was off" — both
// read as grey, but only one is a diagonal stripe, matching the explicit-labelling requirement.
const STATE_COLOR_CLASS: Record<CoverageState, string> = {
  TRACKED: "bg-indigo-500",
  IDLE: "bg-indigo-200 dark:bg-indigo-900",
  UNOBSERVED: "timeline-hatched",
  DEVICE_OFFLINE: "bg-neutral-400 dark:bg-neutral-600",
};

const STATE_LABEL: Record<CoverageState, string> = {
  TRACKED: "Tracked",
  IDLE: "Idle",
  UNOBSERVED: "Unobserved",
  DEVICE_OFFLINE: "Device offline",
};

function percentSpan(startIso: string, endIso: string, dayStartMs: number, dayEndMs: number) {
  const totalMs = Math.max(dayEndMs - dayStartMs, 1);
  const startMs = new Date(startIso).getTime() - dayStartMs;
  const endMs = new Date(endIso).getTime() - dayStartMs;
  const leftPct = (Math.max(startMs, 0) / totalMs) * 100;
  const widthPct = (Math.max(endMs - Math.max(startMs, 0), 0) / totalMs) * 100;
  return { leftPct, widthPct };
}

interface TimelineProps {
  deviceName: string;
  dayStartUtc: string;
  dayEndUtc: string;
  coverage: CoverageInterval[];
  sessions: AppSessionOut[];
}

export function Timeline({ deviceName, dayStartUtc, dayEndUtc, coverage, sessions }: TimelineProps) {
  const dayStartMs = new Date(dayStartUtc).getTime();
  const dayEndMs = new Date(dayEndUtc).getTime();

  return (
    <div className="flex flex-col gap-1.5" data-testid="device-timeline">
      <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">{deviceName}</span>

      <div
        className="relative h-8 w-full overflow-hidden rounded bg-neutral-100 dark:bg-neutral-800"
        data-testid="timeline-coverage-row"
      >
        {coverage.map((interval) => {
          const { leftPct, widthPct } = percentSpan(
            interval.start_ts,
            interval.end_ts,
            dayStartMs,
            dayEndMs,
          );
          return (
            <div
              key={`${interval.start_ts}-${interval.state}`}
              className={`absolute top-0 h-full ${STATE_COLOR_CLASS[interval.state]}`}
              style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
              data-testid="timeline-segment"
              data-state={interval.state}
              title={`${STATE_LABEL[interval.state]}: ${formatTime(interval.start_ts)}–${formatTime(interval.end_ts)}`}
            />
          );
        })}
      </div>

      {sessions.length > 0 && (
        <div
          className="relative h-6 w-full overflow-hidden rounded bg-neutral-50 dark:bg-neutral-900"
          data-testid="timeline-sessions-row"
        >
          {sessions.map((session, i) => {
            const { leftPct, widthPct } = percentSpan(
              session.start_ts,
              session.end_ts,
              dayStartMs,
              dayEndMs,
            );
            return (
              <div
                key={`${session.start_ts}-${i}`}
                className="absolute top-0 h-full border-r border-white bg-sky-500/70 dark:border-neutral-950"
                style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 0.15)}%` }}
                title={`${session.app_key} — ${formatTime(session.start_ts)}–${formatTime(session.end_ts)}`}
                data-testid="timeline-app-session"
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

export function TimelineLegend() {
  const states: CoverageState[] = ["TRACKED", "IDLE", "UNOBSERVED", "DEVICE_OFFLINE"];
  return (
    <div className="flex flex-wrap gap-4 text-xs text-neutral-600 dark:text-neutral-400">
      {states.map((state) => (
        <span key={state} className="flex items-center gap-1.5">
          <span className={`inline-block h-3 w-3 rounded-sm ${STATE_COLOR_CLASS[state]}`} />
          {STATE_LABEL[state]}
        </span>
      ))}
    </div>
  );
}
