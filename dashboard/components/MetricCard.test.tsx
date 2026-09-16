import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCard } from "@/components/MetricCard";

// §25: "a test asserting every metric card renders a coverage badge".
describe("MetricCard", () => {
  it("always renders a coverage badge alongside its value", () => {
    render(<MetricCard label="Screen time" value="2h 30m" coverageRatio={0.85} />);
    expect(screen.getByTestId("coverage-badge")).toBeInTheDocument();
    expect(screen.getByText("Screen time")).toBeInTheDocument();
    expect(screen.getByText(/2h 30m/)).toBeInTheDocument();
  });

  it("renders a coverage badge even at the lowest possible coverage", () => {
    render(<MetricCard label="Deep work" value="0m" coverageRatio={0} />);
    expect(screen.getByTestId("coverage-badge")).toBeInTheDocument();
  });

  it("renders a coverage badge even at full coverage", () => {
    render(<MetricCard label="Deep work" value="4h" coverageRatio={1} />);
    expect(screen.getByTestId("coverage-badge")).toBeInTheDocument();
  });

  it("prefixes the value with '~' when coverage is below the 0.6 gate (§14.3)", () => {
    render(<MetricCard label="Fragmentation" value="42%" coverageRatio={0.3} />);
    expect(screen.getByText("~42%")).toBeInTheDocument();
  });

  it("does not prefix the value when coverage clears the gate", () => {
    render(<MetricCard label="Fragmentation" value="42%" coverageRatio={0.8} />);
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.queryByText("~42%")).not.toBeInTheDocument();
  });
});
