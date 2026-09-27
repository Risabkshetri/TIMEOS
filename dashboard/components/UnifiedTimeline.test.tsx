import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UnifiedTimeline } from "@/components/UnifiedTimeline";
import type { ActivityOut } from "@/lib/types";

const DAY_START = "2026-09-25T04:00:00Z";
const DAY_END = "2026-09-26T04:00:00Z";

function activity(overrides: Partial<ActivityOut>): ActivityOut {
  return {
    id: "a1",
    category_key: "development",
    category_label: "Development",
    app_keys: ["github.com"],
    devices: ["device-1"],
    is_cross_device: false,
    start_ts: "2026-09-25T05:00:00Z",
    end_ts: "2026-09-25T06:00:00Z",
    duration_s: 3600,
    confidence: 0.75,
    classification_source: "seed",
    ...overrides,
  };
}

describe("UnifiedTimeline", () => {
  it("renders one segment per activity", () => {
    render(
      <UnifiedTimeline
        dayStartUtc={DAY_START}
        dayEndUtc={DAY_END}
        activities={[
          activity({ id: "a1" }),
          activity({ id: "a2", start_ts: "2026-09-25T07:00:00Z", end_ts: "2026-09-25T08:00:00Z" }),
        ]}
      />,
    );

    expect(screen.getAllByTestId("unified-timeline-segment")).toHaveLength(2);
  });

  it("marks a cross-device activity distinctly from a single-device one", () => {
    render(
      <UnifiedTimeline
        dayStartUtc={DAY_START}
        dayEndUtc={DAY_END}
        activities={[
          activity({ id: "single", is_cross_device: false, devices: ["phone"] }),
          activity({
            id: "cross",
            is_cross_device: true,
            devices: ["phone", "browser"],
            start_ts: "2026-09-25T07:00:00Z",
            end_ts: "2026-09-25T08:00:00Z",
          }),
        ]}
      />,
    );

    const segments = screen.getAllByTestId("unified-timeline-segment");
    const single = segments.find((el) => el.dataset.crossDevice === "false")!;
    const cross = segments.find((el) => el.dataset.crossDevice === "true")!;
    expect(single.className).not.toBe(cross.className);
    expect(cross.title).toContain("2 devices");
  });

  it("caps rendered activities at 200 and notes how many were omitted", () => {
    const many = Array.from({ length: 250 }, (_, i) =>
      activity({ id: `a${i}`, start_ts: DAY_START, end_ts: DAY_START }),
    );

    render(<UnifiedTimeline dayStartUtc={DAY_START} dayEndUtc={DAY_END} activities={many} />);

    expect(screen.getAllByTestId("unified-timeline-segment")).toHaveLength(200);
    expect(screen.getByText(/Showing the first 200 of 250 activities/)).toBeInTheDocument();
  });
});
