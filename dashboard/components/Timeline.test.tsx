import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Timeline, TimelineLegend } from "@/components/Timeline";
import type { CoverageInterval } from "@/lib/types";

const DAY_START = "2026-09-13T04:00:00Z";
const DAY_END = "2026-09-14T04:00:00Z";

function interval(startOffsetHours: number, endOffsetHours: number, state: CoverageInterval["state"]) {
  const start = new Date(DAY_START);
  start.setUTCHours(start.getUTCHours() + startOffsetHours);
  const end = new Date(DAY_START);
  end.setUTCHours(end.getUTCHours() + endOffsetHours);
  return { start_ts: start.toISOString(), end_ts: end.toISOString(), state };
}

// §25: "component tests for timeline rendering of all four coverage states".
const ALL_FOUR_STATES: CoverageInterval[] = [
  interval(0, 6, "UNOBSERVED"),
  interval(6, 14, "TRACKED"),
  interval(14, 18, "IDLE"),
  interval(18, 24, "DEVICE_OFFLINE"),
];

describe("Timeline", () => {
  it("renders one segment per coverage interval, each tagged with its state", () => {
    render(
      <Timeline
        deviceName="Test Phone"
        dayStartUtc={DAY_START}
        dayEndUtc={DAY_END}
        coverage={ALL_FOUR_STATES}
        sessions={[]}
      />,
    );

    const segments = screen.getAllByTestId("timeline-segment");
    expect(segments).toHaveLength(4);
    const states = segments.map((el) => el.dataset.state);
    expect(states).toEqual(["UNOBSERVED", "TRACKED", "IDLE", "DEVICE_OFFLINE"]);
  });

  it("renders UNOBSERVED with the hatched pattern class, distinct from DEVICE_OFFLINE's solid grey", () => {
    render(
      <Timeline
        deviceName="Test Phone"
        dayStartUtc={DAY_START}
        dayEndUtc={DAY_END}
        coverage={ALL_FOUR_STATES}
        sessions={[]}
      />,
    );

    const segments = screen.getAllByTestId("timeline-segment");
    const unobserved = segments.find((el) => el.dataset.state === "UNOBSERVED")!;
    const offline = segments.find((el) => el.dataset.state === "DEVICE_OFFLINE")!;

    expect(unobserved.className).toContain("timeline-hatched");
    expect(offline.className).not.toContain("timeline-hatched");
    // Both are visually "grey" in spirit but must not share a class, or they'd be indistinguishable.
    expect(unobserved.className).not.toBe(offline.className);
  });

  it("explicitly labels each state in a title attribute, never leaving a segment unlabelled", () => {
    render(
      <Timeline
        deviceName="Test Phone"
        dayStartUtc={DAY_START}
        dayEndUtc={DAY_END}
        coverage={ALL_FOUR_STATES}
        sessions={[]}
      />,
    );

    const segments = screen.getAllByTestId("timeline-segment");
    for (const segment of segments) {
      expect(segment.title.length).toBeGreaterThan(0);
    }
    const offlineSegment = segments.find((el) => el.dataset.state === "DEVICE_OFFLINE")!;
    expect(offlineSegment.title).toContain("Device offline");
  });

  it("renders app sessions as a separate row when present", () => {
    render(
      <Timeline
        deviceName="Test Phone"
        dayStartUtc={DAY_START}
        dayEndUtc={DAY_END}
        coverage={ALL_FOUR_STATES}
        sessions={[
          {
            app_key: "com.android.chrome",
            start_ts: interval(6, 7, "TRACKED").start_ts,
            end_ts: interval(6, 7, "TRACKED").end_ts,
            duration_s: 3600,
            interaction_count: 3,
          },
        ]}
      />,
    );

    expect(screen.getByTestId("timeline-sessions-row")).toBeInTheDocument();
    expect(screen.getAllByTestId("timeline-app-session")).toHaveLength(1);
  });

  it("omits the sessions row entirely when there are no sessions", () => {
    render(
      <Timeline
        deviceName="Test Phone"
        dayStartUtc={DAY_START}
        dayEndUtc={DAY_END}
        coverage={ALL_FOUR_STATES}
        sessions={[]}
      />,
    );

    expect(screen.queryByTestId("timeline-sessions-row")).not.toBeInTheDocument();
  });
});

describe("TimelineLegend", () => {
  it("labels all four coverage states", () => {
    render(<TimelineLegend />);
    expect(screen.getByText("Tracked")).toBeInTheDocument();
    expect(screen.getByText("Idle")).toBeInTheDocument();
    expect(screen.getByText("Unobserved")).toBeInTheDocument();
    expect(screen.getByText("Device offline")).toBeInTheDocument();
  });
});
